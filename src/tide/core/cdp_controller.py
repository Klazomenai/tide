"""CDP Mode Controller for TIDE.

Controls CDP behavior based on configured mode:
- auto: Automatic rebalancing within CR thresholds
- manual: Only responds to explicit commands
- disabled: No CDP operations allowed
"""

import asyncio
import logging
from decimal import Decimal

from tide.config import CDPEmergencyAction, CDPMode
from tide.core.cdp import CDPHealth, CDPManager, CDPStatus

logger = logging.getLogger(__name__)


class CDPController:
    """Controls CDP operations based on configured mode.

    Parameters
    ----------
    cdp_manager : CDPManager
        The CDP manager instance.
    mode : CDPMode
        Operating mode (auto, manual, disabled).
    check_interval_minutes : int
        Interval between health checks in auto mode.
    emergency_action : CDPEmergencyAction
        Action to take when CDP health is critical.
    """

    def __init__(
        self,
        cdp_manager: CDPManager,
        mode: CDPMode = CDPMode.AUTO,
        check_interval_minutes: int = 5,
        emergency_action: CDPEmergencyAction = CDPEmergencyAction.ALERT,
    ):
        self._cdp = cdp_manager
        self._mode = mode
        self._check_interval = check_interval_minutes * 60  # Convert to seconds
        self._emergency_action = emergency_action
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def mode(self) -> CDPMode:
        """Get current operating mode."""
        return self._mode

    @property
    def is_running(self) -> bool:
        """Check if auto-monitoring is running."""
        return self._running

    def get_status(self) -> CDPStatus:
        """Get current CDP status.

        Returns
        -------
        CDPStatus
            Current CDP status.

        Raises
        ------
        RuntimeError
            If mode is disabled.
        """
        if self._mode == CDPMode.DISABLED:
            raise RuntimeError("CDP operations are disabled")
        return self._cdp.get_status()

    def deposit(self, amount: Decimal) -> str:
        """Deposit NTN collateral.

        Parameters
        ----------
        amount : Decimal
            Amount to deposit.

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        RuntimeError
            If mode is disabled.
        """
        if self._mode == CDPMode.DISABLED:
            raise RuntimeError("CDP operations are disabled")
        return self._cdp.deposit(amount)

    def withdraw(self, amount: Decimal) -> str:
        """Withdraw NTN collateral.

        Parameters
        ----------
        amount : Decimal
            Amount to withdraw.

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        RuntimeError
            If mode is disabled.
        """
        if self._mode == CDPMode.DISABLED:
            raise RuntimeError("CDP operations are disabled")
        return self._cdp.withdraw(amount)

    def borrow(self, amount: Decimal) -> str:
        """Borrow ATN.

        Parameters
        ----------
        amount : Decimal
            Amount to borrow.

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        RuntimeError
            If mode is disabled.
        """
        if self._mode == CDPMode.DISABLED:
            raise RuntimeError("CDP operations are disabled")
        return self._cdp.borrow(amount)

    def repay(self, amount: Decimal) -> str:
        """Repay ATN debt.

        Parameters
        ----------
        amount : Decimal
            Amount to repay.

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        RuntimeError
            If mode is disabled.
        """
        if self._mode == CDPMode.DISABLED:
            raise RuntimeError("CDP operations are disabled")
        return self._cdp.repay(amount)

    async def start_monitoring(self) -> None:
        """Start automatic CDP monitoring (auto mode only).

        Only runs in AUTO mode. In MANUAL or DISABLED modes, this is a no-op.
        """
        if self._mode != CDPMode.AUTO:
            logger.info(
                "CDP monitoring not started - mode is not AUTO",
                extra={"mode": self._mode.value},
            )
            return

        if self._running:
            logger.warning("CDP monitoring already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info(
            "CDP auto-monitoring started",
            extra={"interval_seconds": self._check_interval},
        )

    async def stop_monitoring(self) -> None:
        """Stop automatic CDP monitoring."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("CDP auto-monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop for auto mode."""
        while self._running:
            try:
                await self._check_and_rebalance()
            except Exception as e:
                logger.error(
                    "Error in CDP monitoring loop",
                    extra={"error": str(e)},
                    exc_info=True,
                )

            await asyncio.sleep(self._check_interval)

    async def _check_and_rebalance(self) -> None:
        """Check CDP health and rebalance if needed."""
        status = self._cdp.get_status()

        logger.debug(
            "CDP health check",
            extra={
                "health": status.health.value,
                "cr": str(status.collateralization_ratio),
                "collateral": str(status.collateral),
                "debt": str(status.debt),
            },
        )

        # Handle emergency situations
        if status.health == CDPHealth.CRITICAL:
            await self._handle_emergency(status)
            return

        # Handle danger zone
        if status.health == CDPHealth.DANGER:
            await self._handle_danger(status)
            return

        # Normal rebalancing
        action = self._cdp.calculate_rebalance_action()
        if action:
            action_type, amount = action
            await self._execute_rebalance(action_type, amount)

    async def _handle_emergency(self, status: CDPStatus) -> None:
        """Handle critical CDP health.

        Parameters
        ----------
        status : CDPStatus
            Current CDP status.
        """
        logger.warning(
            "CDP in CRITICAL state - emergency action triggered",
            extra={
                "health": status.health.value,
                "cr": str(status.collateralization_ratio),
                "emergency_action": self._emergency_action.value,
            },
        )

        if self._emergency_action == CDPEmergencyAction.ALERT:
            # Just log/alert - no automatic action
            logger.critical(
                "CDP CRITICAL: Manual intervention required",
                extra={
                    "collateral": str(status.collateral),
                    "debt": str(status.debt),
                    "cr": str(status.collateralization_ratio),
                },
            )

        elif self._emergency_action == CDPEmergencyAction.REPAY:
            # Attempt to repay debt to restore health
            action = self._cdp.calculate_rebalance_action()
            if action and action[0] == "repay":
                _, amount = action
                try:
                    tx_hash = self._cdp.repay(amount)
                    logger.info(
                        "Emergency repayment executed",
                        extra={"tx_hash": tx_hash, "amount": str(amount)},
                    )
                except Exception as e:
                    logger.error(
                        "Emergency repayment failed",
                        extra={"error": str(e)},
                        exc_info=True,
                    )

        elif self._emergency_action == CDPEmergencyAction.PAUSE:
            # Stop all operations
            logger.critical(
                "CDP CRITICAL: Pausing all operations",
                extra={"previous_mode": self._mode.value},
            )
            self._mode = CDPMode.DISABLED
            await self.stop_monitoring()

    async def _handle_danger(self, status: CDPStatus) -> None:
        """Handle danger zone CDP health.

        Parameters
        ----------
        status : CDPStatus
            Current CDP status.
        """
        logger.warning(
            "CDP in DANGER zone - attempting rebalance",
            extra={
                "health": status.health.value,
                "cr": str(status.collateralization_ratio),
            },
        )

        action = self._cdp.calculate_rebalance_action()
        if action:
            action_type, amount = action
            await self._execute_rebalance(action_type, amount)

    async def _execute_rebalance(self, action_type: str, amount: Decimal) -> None:
        """Execute a rebalance action.

        Parameters
        ----------
        action_type : str
            Type of action ('deposit', 'withdraw', 'borrow', 'repay').
        amount : Decimal
            Amount for the action.
        """
        logger.info(
            "Executing CDP rebalance",
            extra={"action": action_type, "amount": str(amount)},
        )

        try:
            if action_type == "deposit":
                tx_hash = self._cdp.deposit(amount)
            elif action_type == "withdraw":
                tx_hash = self._cdp.withdraw(amount)
            elif action_type == "borrow":
                tx_hash = self._cdp.borrow(amount)
            elif action_type == "repay":
                tx_hash = self._cdp.repay(amount)
            else:
                logger.error(f"Unknown rebalance action: {action_type}")
                return

            logger.info(
                "CDP rebalance completed",
                extra={"action": action_type, "tx_hash": tx_hash, "amount": str(amount)},
            )

        except Exception as e:
            logger.error(
                "CDP rebalance failed",
                extra={"action": action_type, "amount": str(amount), "error": str(e)},
                exc_info=True,
            )
