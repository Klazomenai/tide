"""Faucet Service for TIDE.

Coordinates all faucet components:
- Rate limiter
- CDP manager/controller
- Token distributors
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from tide.core.cdp import CDPHealth, CDPStatus
from tide.core.cdp_controller import CDPController

from .distributor import ATNDistributor, NTNDistributor
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class FaucetRequestType(str, Enum):
    """Type of faucet request."""

    ATN = "atn"
    NTN = "ntn"


@dataclass
class FaucetResult:
    """Result of a faucet request."""

    success: bool
    request_type: FaucetRequestType
    tx_hash: str | None
    amount: Decimal
    message: str
    remaining_requests: int


@dataclass
class FaucetStatus:
    """Current faucet status."""

    healthy: bool
    cdp_status: CDPStatus | None
    atn_available: Decimal
    ntn_available: Decimal
    message: str


class FaucetService:
    """Main faucet service orchestrating all components.

    Parameters
    ----------
    rate_limiter : RateLimiter
        Rate limiter instance.
    cdp_controller : CDPController | None
        CDP controller for ATN operations (None if CDP disabled).
    ntn_distributor : NTNDistributor
        NTN token distributor.
    atn_distributor : ATNDistributor | None
        ATN token distributor (None if CDP disabled).
    default_atn : Decimal
        Default ATN amount if not specified.
    default_ntn : Decimal
        Default NTN amount if not specified.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter,
        cdp_controller: CDPController | None,
        ntn_distributor: NTNDistributor,
        atn_distributor: ATNDistributor | None,
        default_atn: Decimal = Decimal("1"),
        default_ntn: Decimal = Decimal("10"),
    ):
        self._rate_limiter = rate_limiter
        self._cdp_controller = cdp_controller
        self._ntn_distributor = ntn_distributor
        self._atn_distributor = atn_distributor
        self._default_atn = default_atn
        self._default_ntn = default_ntn
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if the faucet service is running."""
        return self._running

    async def start(self) -> None:
        """Start the faucet service.

        Initializes CDP monitoring if in AUTO mode.
        """
        if self._running:
            logger.warning("Faucet service already running")
            return

        # Start CDP monitoring if enabled
        if self._cdp_controller:
            await self._cdp_controller.start_monitoring()

        self._running = True
        logger.info("Faucet service started")

    async def stop(self) -> None:
        """Stop the faucet service.

        Gracefully stops CDP monitoring.
        """
        if not self._running:
            return

        # Stop CDP monitoring
        if self._cdp_controller:
            await self._cdp_controller.stop_monitoring()

        self._running = False
        logger.info("Faucet service stopped")

    async def get_status(self) -> FaucetStatus:
        """Get current faucet status.

        Returns
        -------
        FaucetStatus
            Current status of the faucet.
        """
        cdp_status = None
        atn_available = Decimal("0")

        # Get CDP status if available
        if self._cdp_controller:
            try:
                cdp_status = self._cdp_controller.get_status()
                if self._atn_distributor:
                    atn_available = await self._atn_distributor.get_available()
            except RuntimeError:
                # CDP disabled
                pass

        # Get NTN balance
        ntn_available = await self._ntn_distributor.get_balance()

        # Determine health
        healthy = True
        message = "Faucet operational"

        if cdp_status and cdp_status.health in (CDPHealth.CRITICAL, CDPHealth.DANGER):
            healthy = False
            message = f"CDP health: {cdp_status.health.value}"
        elif ntn_available <= 0 and atn_available <= 0:
            healthy = False
            message = "No tokens available for distribution"

        return FaucetStatus(
            healthy=healthy,
            cdp_status=cdp_status,
            atn_available=atn_available,
            ntn_available=ntn_available,
            message=message,
        )

    async def handle_atn_request(
        self,
        user_id: str,
        address: str,
        amount: Decimal | None = None,
    ) -> FaucetResult:
        """Handle an ATN distribution request.

        Parameters
        ----------
        user_id : str
            User identifier for rate limiting.
        address : str
            Recipient address.
        amount : Decimal | None
            Amount to send, uses default if None.

        Returns
        -------
        FaucetResult
            Result of the request.
        """
        amount = amount or self._default_atn

        # Check if ATN distribution is available
        if not self._atn_distributor:
            return FaucetResult(
                success=False,
                request_type=FaucetRequestType.ATN,
                tx_hash=None,
                amount=amount,
                message="ATN distribution is not available (CDP disabled)",
                remaining_requests=await self._rate_limiter.get_remaining(user_id),
            )

        # Check rate limit
        rate_result = await self._rate_limiter.check_limit(user_id)
        if not rate_result.allowed:
            return FaucetResult(
                success=False,
                request_type=FaucetRequestType.ATN,
                tx_hash=None,
                amount=amount,
                message=rate_result.reason or "Rate limit exceeded",
                remaining_requests=rate_result.remaining,
            )

        # Attempt distribution
        result = await self._atn_distributor.distribute(address, amount)

        # Record successful request
        if result.success:
            await self._rate_limiter.record_request(user_id)

        remaining = await self._rate_limiter.get_remaining(user_id)

        return FaucetResult(
            success=result.success,
            request_type=FaucetRequestType.ATN,
            tx_hash=result.tx_hash,
            amount=result.amount,
            message=result.message,
            remaining_requests=remaining,
        )

    async def handle_ntn_request(
        self,
        user_id: str,
        address: str,
        amount: Decimal | None = None,
    ) -> FaucetResult:
        """Handle an NTN distribution request.

        Parameters
        ----------
        user_id : str
            User identifier for rate limiting.
        address : str
            Recipient address.
        amount : Decimal | None
            Amount to send, uses default if None.

        Returns
        -------
        FaucetResult
            Result of the request.
        """
        amount = amount or self._default_ntn

        # Check rate limit
        rate_result = await self._rate_limiter.check_limit(user_id)
        if not rate_result.allowed:
            return FaucetResult(
                success=False,
                request_type=FaucetRequestType.NTN,
                tx_hash=None,
                amount=amount,
                message=rate_result.reason or "Rate limit exceeded",
                remaining_requests=rate_result.remaining,
            )

        # Attempt distribution
        result = await self._ntn_distributor.distribute(address, amount)

        # Record successful request
        if result.success:
            await self._rate_limiter.record_request(user_id)

        remaining = await self._rate_limiter.get_remaining(user_id)

        return FaucetResult(
            success=result.success,
            request_type=FaucetRequestType.NTN,
            tx_hash=result.tx_hash,
            amount=result.amount,
            message=result.message,
            remaining_requests=remaining,
        )

    async def get_user_status(self, user_id: str) -> dict:
        """Get rate limit status for a user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        dict
            User's rate limit status.
        """
        remaining = await self._rate_limiter.get_remaining(user_id)
        cooldown = await self._rate_limiter.get_cooldown(user_id)

        return {
            "remaining_requests": remaining,
            "cooldown_seconds": cooldown.total_seconds() if cooldown else 0,
            "max_atn": str(self._atn_distributor.max_amount) if self._atn_distributor else "0",
            "max_ntn": str(self._ntn_distributor.max_amount),
        }
