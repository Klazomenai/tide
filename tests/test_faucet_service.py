"""Tests for Faucet Service module."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from tide.core.cdp import CDPHealth, CDPStatus
from tide.faucet.distributor import DistributionResult, DistributionStatus
from tide.faucet.rate_limiter import RateLimitResult
from tide.faucet.service import (
    FaucetRequestType,
    FaucetResult,
    FaucetService,
    FaucetStatus,
)


@pytest.fixture
def mock_rate_limiter():
    """Create a mock rate limiter."""
    limiter = MagicMock()
    limiter.check_limit = AsyncMock(
        return_value=RateLimitResult(
            allowed=True,
            remaining=9,
            cooldown_seconds=None,
            reason=None,
        )
    )
    limiter.record_request = AsyncMock()
    limiter.get_remaining = AsyncMock(return_value=9)
    limiter.get_cooldown = AsyncMock(return_value=None)
    return limiter


@pytest.fixture
def mock_cdp_controller():
    """Create a mock CDP controller."""
    controller = MagicMock()
    controller.get_status.return_value = CDPStatus(
        exists=True,
        collateral=Decimal("100"),
        debt=Decimal("40"),
        collateralization_ratio=Decimal("250"),
        health=CDPHealth.HEALTHY,
        is_liquidatable=False,
        max_borrowable=Decimal("10"),
        min_collateral_required=Decimal("80"),
    )
    controller.start_monitoring = AsyncMock()
    controller.stop_monitoring = AsyncMock()
    return controller


@pytest.fixture
def mock_ntn_distributor():
    """Create a mock NTN distributor."""
    distributor = MagicMock()
    distributor.max_amount = Decimal("50")
    distributor.get_balance = AsyncMock(return_value=Decimal("1000"))
    distributor.distribute = AsyncMock(
        return_value=DistributionResult(
            success=True,
            status=DistributionStatus.SUCCESS,
            tx_hash="0xntn123",
            amount=Decimal("10"),
            message="Successfully sent 10 NTN",
        )
    )
    return distributor


@pytest.fixture
def mock_atn_distributor():
    """Create a mock ATN distributor."""
    distributor = MagicMock()
    distributor.max_amount = Decimal("5")
    distributor.get_available = AsyncMock(return_value=Decimal("10"))
    distributor.distribute = AsyncMock(
        return_value=DistributionResult(
            success=True,
            status=DistributionStatus.SUCCESS,
            tx_hash="0xatn123",
            amount=Decimal("1"),
            message="Successfully sent 1 ATN",
        )
    )
    return distributor


class TestFaucetResult:
    """Tests for FaucetResult dataclass."""

    def test_success_result(self):
        """FaucetResult can represent success."""
        result = FaucetResult(
            success=True,
            request_type=FaucetRequestType.ATN,
            tx_hash="0xabc",
            amount=Decimal("1"),
            message="Success",
            remaining_requests=9,
        )

        assert result.success is True
        assert result.request_type == FaucetRequestType.ATN


class TestFaucetStatus:
    """Tests for FaucetStatus dataclass."""

    def test_healthy_status(self):
        """FaucetStatus can represent healthy state."""
        status = FaucetStatus(
            healthy=True,
            cdp_status=None,
            atn_available=Decimal("10"),
            ntn_available=Decimal("100"),
            message="Faucet operational",
        )

        assert status.healthy is True


class TestFaucetService:
    """Tests for FaucetService."""

    def test_initialization(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """FaucetService initializes correctly."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        assert service.is_running is False

    @pytest.mark.asyncio
    async def test_start_stop(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """FaucetService starts and stops correctly."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        await service.start()
        assert service.is_running is True
        mock_cdp_controller.start_monitoring.assert_called_once()

        await service.stop()
        assert service.is_running is False
        mock_cdp_controller.stop_monitoring.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_running(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """start() is idempotent when already running."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        await service.start()
        await service.start()  # Second call should be no-op

        assert mock_cdp_controller.start_monitoring.call_count == 1

    @pytest.mark.asyncio
    async def test_get_status_healthy(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """get_status returns healthy status."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        status = await service.get_status()

        assert status.healthy is True
        assert status.ntn_available == Decimal("1000")
        assert status.atn_available == Decimal("10")

    @pytest.mark.asyncio
    async def test_get_status_cdp_unhealthy(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """get_status reports unhealthy when CDP critical."""
        mock_cdp_controller.get_status.return_value = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("60"),
            collateralization_ratio=Decimal("167"),
            health=CDPHealth.CRITICAL,
            is_liquidatable=True,
            max_borrowable=Decimal("0"),
            min_collateral_required=Decimal("120"),
        )

        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        status = await service.get_status()

        assert status.healthy is False
        assert "critical" in status.message.lower()

    @pytest.mark.asyncio
    async def test_handle_ntn_request_success(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """handle_ntn_request succeeds with valid request."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        result = await service.handle_ntn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
            amount=Decimal("10"),
        )

        assert result.success is True
        assert result.request_type == FaucetRequestType.NTN
        assert result.tx_hash == "0xntn123"
        mock_rate_limiter.record_request.assert_called_once_with("user123")

    @pytest.mark.asyncio
    async def test_handle_ntn_request_rate_limited(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """handle_ntn_request fails when rate limited."""
        mock_rate_limiter.check_limit = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                cooldown_seconds=None,
                reason="Daily limit reached",
            )
        )

        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        result = await service.handle_ntn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
        )

        assert result.success is False
        assert "limit" in result.message.lower()
        mock_ntn_distributor.distribute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_ntn_request_default_amount(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """handle_ntn_request uses default amount when not specified."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
            default_ntn=Decimal("25"),
        )

        await service.handle_ntn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
        )

        mock_ntn_distributor.distribute.assert_called_once_with(
            "0x1234567890123456789012345678901234567890",
            Decimal("25"),
        )

    @pytest.mark.asyncio
    async def test_handle_atn_request_success(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """handle_atn_request succeeds with valid request."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        result = await service.handle_atn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
            amount=Decimal("1"),
        )

        assert result.success is True
        assert result.request_type == FaucetRequestType.ATN
        assert result.tx_hash == "0xatn123"

    @pytest.mark.asyncio
    async def test_handle_atn_request_no_distributor(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
    ):
        """handle_atn_request fails when ATN distributor not available."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=None,
        )

        result = await service.handle_atn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
        )

        assert result.success is False
        assert "not available" in result.message.lower()

    @pytest.mark.asyncio
    async def test_handle_atn_request_distribution_failure(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """handle_atn_request handles distribution failure."""
        mock_atn_distributor.distribute = AsyncMock(
            return_value=DistributionResult(
                success=False,
                status=DistributionStatus.TRANSACTION_FAILED,
                tx_hash=None,
                amount=Decimal("1"),
                message="TX failed",
            )
        )

        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        result = await service.handle_atn_request(
            user_id="user123",
            address="0x1234567890123456789012345678901234567890",
        )

        assert result.success is False
        mock_rate_limiter.record_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_user_status(
        self,
        mock_rate_limiter,
        mock_cdp_controller,
        mock_ntn_distributor,
        mock_atn_distributor,
    ):
        """get_user_status returns user's rate limit info."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=mock_cdp_controller,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=mock_atn_distributor,
        )

        status = await service.get_user_status("user123")

        assert status["remaining_requests"] == 9
        assert status["cooldown_seconds"] == 0
        assert status["max_atn"] == "5"
        assert status["max_ntn"] == "50"

    @pytest.mark.asyncio
    async def test_service_without_cdp(
        self,
        mock_rate_limiter,
        mock_ntn_distributor,
    ):
        """FaucetService works without CDP controller."""
        service = FaucetService(
            rate_limiter=mock_rate_limiter,
            cdp_controller=None,
            ntn_distributor=mock_ntn_distributor,
            atn_distributor=None,
        )

        await service.start()
        assert service.is_running is True

        status = await service.get_status()
        assert status.cdp_status is None
        assert status.atn_available == Decimal("0")

        await service.stop()
