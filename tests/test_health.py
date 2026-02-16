"""Tests for health check endpoints."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from tide.observability.health import (
    CheckResult,
    HealthCheck,
    HealthResult,
    HealthServer,
    HealthStatus,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """HealthStatus has expected values."""
        assert HealthStatus.OK.value == "ok"
        assert HealthStatus.ERROR.value == "error"
        assert HealthStatus.NOT_READY.value == "not_ready"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_ok(self):
        """CheckResult stores OK status."""
        result = CheckResult(name="test", status=HealthStatus.OK)
        assert result.name == "test"
        assert result.status == HealthStatus.OK
        assert result.message is None

    def test_check_result_with_message(self):
        """CheckResult stores error message."""
        result = CheckResult(
            name="redis",
            status=HealthStatus.ERROR,
            message="connection refused",
        )
        assert result.name == "redis"
        assert result.status == HealthStatus.ERROR
        assert result.message == "connection refused"


class TestHealthResult:
    """Tests for HealthResult dataclass."""

    def test_health_result_ok(self):
        """HealthResult to_dict for OK status."""
        result = HealthResult(status=HealthStatus.OK)
        assert result.to_dict() == {"status": "ok"}

    def test_health_result_with_checks(self):
        """HealthResult to_dict includes checks."""
        result = HealthResult(
            status=HealthStatus.NOT_READY,
            checks={"redis": "ok", "slack": "error: timeout"},
        )
        assert result.to_dict() == {
            "status": "not_ready",
            "checks": {"redis": "ok", "slack": "error: timeout"},
        }


class MockHealthCheck(HealthCheck):
    """Mock health check for testing."""

    def __init__(self, name: str, status: HealthStatus, message: str | None = None):
        self._name = name
        self._status = status
        self._message = message

    @property
    def name(self) -> str:
        return self._name

    async def check(self) -> CheckResult:
        return CheckResult(name=self._name, status=self._status, message=self._message)


class FailingHealthCheck(HealthCheck):
    """Health check that raises an exception."""

    @property
    def name(self) -> str:
        return "failing"

    async def check(self) -> CheckResult:
        raise RuntimeError("Check failed")


class TestHealthServer:
    """Tests for HealthServer endpoints."""

    @pytest.fixture
    async def health_server(self):
        """Create a HealthServer for testing."""
        server = HealthServer()
        return server

    @pytest.fixture
    async def app_client(self, health_server):
        """Create test client with HealthServer app."""
        app = web.Application()
        app.router.add_get("/health", health_server._handle_health)
        app.router.add_get("/ready", health_server._handle_ready)
        app.router.add_get("/metrics", health_server._handle_metrics)

        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        yield client, health_server
        await client.close()

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_ok(self, app_client):
        """GET /health returns 200 OK."""
        client, _ = app_client
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_ready_endpoint_no_checks(self, app_client):
        """GET /ready returns 200 when no checks configured."""
        client, _ = app_client
        resp = await client.get("/ready")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_ready_endpoint_all_checks_pass(self, app_client):
        """GET /ready returns 200 when all checks pass."""
        client, server = app_client
        server.add_check(MockHealthCheck("redis", HealthStatus.OK))
        server.add_check(MockHealthCheck("slack", HealthStatus.OK))

        resp = await client.get("/ready")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["redis"] == "ok"
        assert data["checks"]["slack"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_endpoint_check_fails(self, app_client):
        """GET /ready returns 503 when a check fails."""
        client, server = app_client
        server.add_check(MockHealthCheck("redis", HealthStatus.OK))
        server.add_check(MockHealthCheck("slack", HealthStatus.ERROR, "connection timeout"))

        resp = await client.get("/ready")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"] == "ok"
        assert data["checks"]["slack"] == "connection timeout"

    @pytest.mark.asyncio
    async def test_ready_endpoint_check_raises(self, app_client):
        """GET /ready handles check exceptions."""
        client, server = app_client
        server.add_check(MockHealthCheck("redis", HealthStatus.OK))
        server.add_check(FailingHealthCheck())

        resp = await client.get("/ready")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "not_ready"
        # Error should include exception type and message
        assert "RuntimeError" in data["checks"]["failing"]
        assert "Check failed" in data["checks"]["failing"]

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, app_client):
        """GET /metrics returns Prometheus metrics."""
        client, _ = app_client
        resp = await client.get("/metrics")
        assert resp.status == 200
        assert "text/plain" in resp.content_type
        body = await resp.text()
        # Should contain some metrics
        assert len(body) > 0


@pytest.mark.asyncio
async def test_health_server_lifecycle():
    """HealthServer start and stop lifecycle."""
    server = HealthServer(host="127.0.0.1", port=18080)

    await server.start()
    assert server._runner is not None
    assert server._site is not None

    await server.stop()

    # Verify cleanup after stop
    assert server._runner is None
    assert server._site is None
