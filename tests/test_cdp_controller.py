"""Tests for CDP Controller module."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tide.config import CDPEmergencyAction, CDPMode
from tide.core.cdp import CDPHealth, CDPStatus
from tide.core.cdp_controller import CDPController


@pytest.fixture
def mock_cdp_manager():
    """Create a mock CDP manager."""
    manager = MagicMock()
    manager.get_status.return_value = CDPStatus(
        exists=True,
        collateral=Decimal("100"),
        debt=Decimal("40"),
        collateralization_ratio=Decimal("250"),
        health=CDPHealth.HEALTHY,
        is_liquidatable=False,
        max_borrowable=Decimal("10"),
        min_collateral_required=Decimal("80"),
    )
    manager.calculate_rebalance_action.return_value = None
    manager.deposit.return_value = "0x1234"
    manager.withdraw.return_value = "0x5678"
    manager.borrow.return_value = "0xabcd"
    manager.repay.return_value = "0xef01"
    return manager


class TestCDPController:
    """Tests for CDPController."""

    def test_controller_initialization(self, mock_cdp_manager):
        """CDPController initializes with manager and mode."""
        controller = CDPController(
            mock_cdp_manager,
            mode=CDPMode.AUTO,
            check_interval_minutes=10,
            emergency_action=CDPEmergencyAction.ALERT,
        )

        assert controller.mode == CDPMode.AUTO
        assert controller._check_interval == 600  # 10 minutes in seconds
        assert controller._emergency_action == CDPEmergencyAction.ALERT

    def test_controller_default_values(self, mock_cdp_manager):
        """CDPController uses sensible defaults."""
        controller = CDPController(mock_cdp_manager)

        assert controller.mode == CDPMode.AUTO
        assert controller._check_interval == 300  # 5 minutes default
        assert controller._emergency_action == CDPEmergencyAction.ALERT

    def test_get_status_auto_mode(self, mock_cdp_manager):
        """get_status works in AUTO mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        status = controller.get_status()

        assert status.exists is True
        assert status.health == CDPHealth.HEALTHY
        mock_cdp_manager.get_status.assert_called_once()

    def test_get_status_manual_mode(self, mock_cdp_manager):
        """get_status works in MANUAL mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.MANUAL)

        status = controller.get_status()

        assert status.exists is True
        mock_cdp_manager.get_status.assert_called_once()

    def test_get_status_disabled_mode(self, mock_cdp_manager):
        """get_status raises error in DISABLED mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.DISABLED)

        with pytest.raises(RuntimeError, match="disabled"):
            controller.get_status()

    def test_deposit_auto_mode(self, mock_cdp_manager):
        """deposit works in AUTO mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        tx_hash = controller.deposit(Decimal("10"))

        assert tx_hash == "0x1234"
        mock_cdp_manager.deposit.assert_called_once_with(Decimal("10"))

    def test_deposit_manual_mode(self, mock_cdp_manager):
        """deposit works in MANUAL mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.MANUAL)

        tx_hash = controller.deposit(Decimal("10"))

        assert tx_hash == "0x1234"

    def test_deposit_disabled_mode(self, mock_cdp_manager):
        """deposit raises error in DISABLED mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.DISABLED)

        with pytest.raises(RuntimeError, match="disabled"):
            controller.deposit(Decimal("10"))

    def test_withdraw_works(self, mock_cdp_manager):
        """withdraw delegates to manager."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        tx_hash = controller.withdraw(Decimal("5"))

        assert tx_hash == "0x5678"
        mock_cdp_manager.withdraw.assert_called_once_with(Decimal("5"))

    def test_borrow_works(self, mock_cdp_manager):
        """borrow delegates to manager."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        tx_hash = controller.borrow(Decimal("10"))

        assert tx_hash == "0xabcd"
        mock_cdp_manager.borrow.assert_called_once_with(Decimal("10"))

    def test_repay_works(self, mock_cdp_manager):
        """repay delegates to manager."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        tx_hash = controller.repay(Decimal("5"))

        assert tx_hash == "0xef01"
        mock_cdp_manager.repay.assert_called_once_with(Decimal("5"))

    def test_is_running_initially_false(self, mock_cdp_manager):
        """is_running is False before start_monitoring."""
        controller = CDPController(mock_cdp_manager)

        assert controller.is_running is False


class TestCDPControllerAsync:
    """Async tests for CDPController."""

    @pytest.mark.asyncio
    async def test_start_monitoring_auto_mode(self, mock_cdp_manager):
        """start_monitoring starts in AUTO mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.AUTO)

        await controller.start_monitoring()

        assert controller.is_running is True

        await controller.stop_monitoring()

        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_start_monitoring_manual_mode_noop(self, mock_cdp_manager):
        """start_monitoring is noop in MANUAL mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.MANUAL)

        await controller.start_monitoring()

        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_start_monitoring_disabled_mode_noop(self, mock_cdp_manager):
        """start_monitoring is noop in DISABLED mode."""
        controller = CDPController(mock_cdp_manager, mode=CDPMode.DISABLED)

        await controller.start_monitoring()

        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_stop_monitoring_when_not_running(self, mock_cdp_manager):
        """stop_monitoring is safe when not running."""
        controller = CDPController(mock_cdp_manager)

        await controller.stop_monitoring()

        assert controller.is_running is False

    @pytest.mark.asyncio
    async def test_check_and_rebalance_healthy(self, mock_cdp_manager):
        """_check_and_rebalance does nothing when healthy."""
        controller = CDPController(mock_cdp_manager)

        await controller._check_and_rebalance()

        # No rebalance action when healthy
        mock_cdp_manager.deposit.assert_not_called()
        mock_cdp_manager.borrow.assert_not_called()
        mock_cdp_manager.repay.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_emergency_alert(self, mock_cdp_manager):
        """_handle_emergency logs critical when action is ALERT."""
        mock_cdp_manager.get_status.return_value = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("60"),
            collateralization_ratio=Decimal("167"),
            health=CDPHealth.CRITICAL,
            is_liquidatable=True,
            max_borrowable=Decimal("0"),
            min_collateral_required=Decimal("120"),
        )

        controller = CDPController(
            mock_cdp_manager,
            emergency_action=CDPEmergencyAction.ALERT,
        )

        with patch("tide.core.cdp_controller.logger") as mock_logger:
            await controller._handle_emergency(mock_cdp_manager.get_status())

            # Should log critical
            mock_logger.critical.assert_called()

    @pytest.mark.asyncio
    async def test_handle_emergency_repay(self, mock_cdp_manager):
        """_handle_emergency attempts repay when action is REPAY."""
        mock_cdp_manager.calculate_rebalance_action.return_value = (
            "repay",
            Decimal("10"),
        )

        controller = CDPController(
            mock_cdp_manager,
            emergency_action=CDPEmergencyAction.REPAY,
        )

        status = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("60"),
            collateralization_ratio=Decimal("167"),
            health=CDPHealth.CRITICAL,
            is_liquidatable=True,
            max_borrowable=Decimal("0"),
            min_collateral_required=Decimal("120"),
        )

        await controller._handle_emergency(status)

        mock_cdp_manager.repay.assert_called_once_with(Decimal("10"))

    @pytest.mark.asyncio
    async def test_handle_emergency_pause(self, mock_cdp_manager):
        """_handle_emergency disables operations when action is PAUSE."""
        controller = CDPController(
            mock_cdp_manager,
            mode=CDPMode.AUTO,
            emergency_action=CDPEmergencyAction.PAUSE,
        )

        status = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("60"),
            collateralization_ratio=Decimal("167"),
            health=CDPHealth.CRITICAL,
            is_liquidatable=True,
            max_borrowable=Decimal("0"),
            min_collateral_required=Decimal("120"),
        )

        await controller._handle_emergency(status)

        assert controller.mode == CDPMode.DISABLED

    @pytest.mark.asyncio
    async def test_execute_rebalance_borrow(self, mock_cdp_manager):
        """_execute_rebalance executes borrow action."""
        controller = CDPController(mock_cdp_manager)

        await controller._execute_rebalance("borrow", Decimal("5"))

        mock_cdp_manager.borrow.assert_called_once_with(Decimal("5"))

    @pytest.mark.asyncio
    async def test_execute_rebalance_repay(self, mock_cdp_manager):
        """_execute_rebalance executes repay action."""
        controller = CDPController(mock_cdp_manager)

        await controller._execute_rebalance("repay", Decimal("5"))

        mock_cdp_manager.repay.assert_called_once_with(Decimal("5"))
