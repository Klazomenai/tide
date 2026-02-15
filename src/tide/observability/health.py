"""Health check endpoints for TIDE faucet.

Endpoints:
- /health: Liveness probe (200 if process is alive)
- /ready: Readiness probe (200 if service can handle requests)
- /metrics: Prometheus metrics endpoint
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from aiohttp import web
from prometheus_client import REGISTRY, generate_latest

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status values."""

    OK = "ok"
    ERROR = "error"
    NOT_READY = "not_ready"


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str | None = None


@dataclass
class HealthResult:
    """Combined health check result."""

    status: HealthStatus
    checks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        result = {"status": self.status.value}
        if self.checks:
            result["checks"] = self.checks
        return result


class HealthCheck(ABC):
    """Abstract base class for health checks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the health check."""
        ...

    @abstractmethod
    async def check(self) -> CheckResult:
        """Perform the health check.

        Returns
        -------
        CheckResult
            The result of the health check.
        """
        ...


class HealthServer:
    """HTTP server for health and metrics endpoints.

    Parameters
    ----------
    host : str
        Host to bind to.
    port : int
        Port to bind to.
    """

    # Default to 0.0.0.0 to allow external access in containerized environments.
    # Kubernetes probes and Prometheus scraping require the server to be accessible
    # from outside the container. Override with host="127.0.0.1" for local-only access.
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):  # noqa: S104
        self._host = host
        self._port = port
        self._checks: list[HealthCheck] = []
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    def add_check(self, check: HealthCheck) -> None:
        """Add a health check.

        Parameters
        ----------
        check : HealthCheck
            The health check to add.
        """
        self._checks.append(check)

    async def start(self) -> None:
        """Start the health server."""
        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/ready", self._handle_ready)
        self._app.router.add_get("/metrics", self._handle_metrics)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        logger.info(
            "Health server started",
            extra={"host": self._host, "port": self._port},
        )

    async def stop(self) -> None:
        """Stop the health server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            logger.info("Health server stopped")

    async def _handle_health(self, _request: web.Request) -> web.Response:
        """Handle /health endpoint (liveness probe)."""
        return web.json_response({"status": "ok"})

    async def _handle_ready(self, _request: web.Request) -> web.Response:
        """Handle /ready endpoint (readiness probe)."""
        result = await self._check_readiness()

        status_code = 200 if result.status == HealthStatus.OK else 503
        return web.json_response(result.to_dict(), status=status_code)

    async def _handle_metrics(self, _request: web.Request) -> web.Response:
        """Handle /metrics endpoint (Prometheus)."""
        metrics = generate_latest(REGISTRY)
        return web.Response(
            body=metrics,
            content_type="text/plain",
            charset="utf-8",
        )

    async def _check_readiness(self) -> HealthResult:
        """Run all readiness checks.

        Returns
        -------
        HealthResult
            Combined result of all checks.
        """
        if not self._checks:
            return HealthResult(status=HealthStatus.OK)

        checks: dict[str, str] = {}
        all_ok = True

        for check in self._checks:
            try:
                result = await check.check()
                if result.status == HealthStatus.OK:
                    checks[result.name] = "ok"
                else:
                    checks[result.name] = result.message or "error"
                    all_ok = False
            except Exception as e:
                # Re-raise system-level exceptions
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                logger.exception("Health check failed", extra={"check": check.name})
                checks[check.name] = f"error: {type(e).__name__}: {e}"
                all_ok = False

        return HealthResult(
            status=HealthStatus.OK if all_ok else HealthStatus.NOT_READY,
            checks=checks,
        )
