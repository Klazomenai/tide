"""Token Distributors for TIDE faucet.

NTN Distribution:
- Direct ERC20 transfer from faucet wallet
- Simple balance check before transfer

ATN Distribution:
- Borrows from CDP to fulfill requests
- Maintains safe collateralization ratio
- Transfers borrowed ATN to recipient
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from tide.blockchain import AutonityClient
from tide.core.cdp import CDPHealth, CDPManager

logger = logging.getLogger(__name__)

# Ethereum address pattern: 0x followed by 40 hex characters
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


def validate_address(address: str) -> bool:
    """Validate Ethereum address format.

    Parameters
    ----------
    address : str
        Address to validate.

    Returns
    -------
    bool
        True if valid Ethereum address format.
    """
    return bool(ADDRESS_PATTERN.match(address))


def _validate_address_result(address: str, amount: Decimal) -> "DistributionResult | None":
    """Validate address and return error result if invalid."""
    if not validate_address(address):
        return DistributionResult(
            success=False,
            status=DistributionStatus.INVALID_ADDRESS,
            tx_hash=None,
            amount=amount,
            message=f"Invalid address format: {address}",
        )
    return None


def _validate_amount_result(
    amount: Decimal, max_amount: Decimal, token: str
) -> "DistributionResult | None":
    """Validate amount and return error result if invalid."""
    if amount <= 0:
        return DistributionResult(
            success=False,
            status=DistributionStatus.INVALID_AMOUNT,
            tx_hash=None,
            amount=amount,
            message="Amount must be positive",
        )
    if amount > max_amount:
        return DistributionResult(
            success=False,
            status=DistributionStatus.INVALID_AMOUNT,
            tx_hash=None,
            amount=amount,
            message=f"Amount exceeds maximum of {max_amount} {token}",
        )
    return None


class DistributionStatus(str, Enum):
    """Distribution result status."""

    SUCCESS = "success"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    INSUFFICIENT_COLLATERAL = "insufficient_collateral"
    CDP_UNHEALTHY = "cdp_unhealthy"
    INVALID_ADDRESS = "invalid_address"
    INVALID_AMOUNT = "invalid_amount"
    TRANSACTION_FAILED = "transaction_failed"


@dataclass
class DistributionResult:
    """Result of a distribution attempt."""

    success: bool
    status: DistributionStatus
    tx_hash: str | None
    amount: Decimal
    message: str


class NTNDistributor:
    """Distributes NTN (Newton) tokens to requesting addresses.

    NTN is an ERC20 token that can be transferred directly from
    the faucet wallet.

    Parameters
    ----------
    client : AutonityClient
        Autonity blockchain client.
    max_amount : Decimal
        Maximum NTN per request.
    """

    def __init__(
        self,
        client: AutonityClient,
        max_amount: Decimal = Decimal("50"),
    ):
        self._client = client
        self._max_amount = max_amount

    @property
    def max_amount(self) -> Decimal:
        """Maximum NTN amount per request."""
        return self._max_amount

    async def get_balance(self) -> Decimal:
        """Get faucet's NTN balance.

        Returns
        -------
        Decimal
            Available NTN balance.
        """
        return self._client.get_ntn_balance(self._client.wallet_address)

    async def validate_request(self, address: str, amount: Decimal) -> DistributionResult | None:
        """Validate a distribution request.

        Parameters
        ----------
        address : str
            Recipient address.
        amount : Decimal
            Amount to distribute.

        Returns
        -------
        DistributionResult | None
            Error result if validation fails, None if valid.
        """
        # Validate address and amount
        if error := _validate_address_result(address, amount):
            return error
        if error := _validate_amount_result(amount, self._max_amount, "NTN"):
            return error

        # Check balance
        balance = await self.get_balance()
        if balance < amount:
            return DistributionResult(
                success=False,
                status=DistributionStatus.INSUFFICIENT_BALANCE,
                tx_hash=None,
                amount=amount,
                message=f"Insufficient NTN balance: {balance} < {amount}",
            )

        return None  # Validation passed

    async def distribute(self, address: str, amount: Decimal) -> DistributionResult:
        """Distribute NTN to an address.

        Parameters
        ----------
        address : str
            Recipient address.
        amount : Decimal
            Amount of NTN to send.

        Returns
        -------
        DistributionResult
            Result of the distribution attempt.
        """
        # Validate first
        error = await self.validate_request(address, amount)
        if error:
            return error

        try:
            tx_hash = self._client.transfer_ntn(address, amount)
            logger.info(
                "NTN distributed",
                extra={
                    "tx_hash": tx_hash,
                    "recipient": address,
                    "amount": str(amount),
                },
            )
            return DistributionResult(
                success=True,
                status=DistributionStatus.SUCCESS,
                tx_hash=tx_hash,
                amount=amount,
                message=f"Successfully sent {amount} NTN",
            )
        except Exception as e:
            logger.error(
                "NTN distribution failed",
                extra={"recipient": address, "amount": str(amount), "error": str(e)},
                exc_info=True,
            )
            return DistributionResult(
                success=False,
                status=DistributionStatus.TRANSACTION_FAILED,
                tx_hash=None,
                amount=amount,
                message=f"Transaction failed: {str(e)}",
            )


class ATNDistributor:
    """Distributes ATN (Auton) tokens via CDP borrowing.

    ATN is borrowed from the CDP and transferred to recipients.
    Maintains safe collateralization ratio during borrowing.

    Parameters
    ----------
    client : AutonityClient
        Autonity blockchain client.
    cdp_manager : CDPManager
        CDP manager for borrowing operations.
    max_amount : Decimal
        Maximum ATN per request.
    """

    def __init__(
        self,
        client: AutonityClient,
        cdp_manager: CDPManager,
        max_amount: Decimal = Decimal("5"),
    ):
        self._client = client
        self._cdp = cdp_manager
        self._max_amount = max_amount

    @property
    def max_amount(self) -> Decimal:
        """Maximum ATN amount per request."""
        return self._max_amount

    async def get_available(self) -> Decimal:
        """Get available ATN that can be borrowed safely.

        Returns
        -------
        Decimal
            Amount of ATN that can be borrowed while maintaining
            a safe collateralization ratio.
        """
        status = self._cdp.get_status()
        if not status.exists:
            return Decimal("0")
        return status.max_borrowable

    async def get_wallet_balance(self) -> Decimal:
        """Get faucet's ATN wallet balance.

        Returns
        -------
        Decimal
            Available ATN in wallet (not borrowed yet).
        """
        return self._client.get_atn_balance(self._client.wallet_address)

    async def validate_request(self, address: str, amount: Decimal) -> DistributionResult | None:
        """Validate a distribution request.

        Parameters
        ----------
        address : str
            Recipient address.
        amount : Decimal
            Amount to distribute.

        Returns
        -------
        DistributionResult | None
            Error result if validation fails, None if valid.
        """
        # Validate address and amount
        if error := _validate_address_result(address, amount):
            return error
        if error := _validate_amount_result(amount, self._max_amount, "ATN"):
            return error

        # Check CDP health
        status = self._cdp.get_status()
        if status.health in (CDPHealth.CRITICAL, CDPHealth.DANGER):
            return DistributionResult(
                success=False,
                status=DistributionStatus.CDP_UNHEALTHY,
                tx_hash=None,
                amount=amount,
                message=f"CDP health is {status.health.value}, cannot distribute ATN",
            )

        # Check if we have enough borrowable capacity
        # First check wallet balance, then borrowable amount
        wallet_balance = await self.get_wallet_balance()
        if wallet_balance >= amount:
            # Have enough in wallet, no need to borrow
            return None

        # Need to borrow the difference
        need_to_borrow = amount - wallet_balance
        available = await self.get_available()
        if available < need_to_borrow:
            return DistributionResult(
                success=False,
                status=DistributionStatus.INSUFFICIENT_COLLATERAL,
                tx_hash=None,
                amount=amount,
                message=f"Insufficient capacity: have {available} ATN, need {need_to_borrow}",
            )

        return None  # Validation passed

    async def distribute(self, address: str, amount: Decimal) -> DistributionResult:
        """Distribute ATN to an address.

        Will borrow from CDP if wallet balance is insufficient.

        Parameters
        ----------
        address : str
            Recipient address.
        amount : Decimal
            Amount of ATN to send.

        Returns
        -------
        DistributionResult
            Result of the distribution attempt.
        """
        # Validate first
        error = await self.validate_request(address, amount)
        if error:
            return error

        try:
            # Check if we need to borrow
            wallet_balance = await self.get_wallet_balance()
            if wallet_balance < amount:
                borrow_amount = amount - wallet_balance
                logger.info(
                    "Borrowing ATN from CDP",
                    extra={"amount": str(borrow_amount)},
                )
                self._cdp.borrow(borrow_amount)

            # Transfer ATN
            tx_hash = self._client.transfer_atn(address, amount)
            logger.info(
                "ATN distributed",
                extra={
                    "tx_hash": tx_hash,
                    "recipient": address,
                    "amount": str(amount),
                },
            )
            return DistributionResult(
                success=True,
                status=DistributionStatus.SUCCESS,
                tx_hash=tx_hash,
                amount=amount,
                message=f"Successfully sent {amount} ATN",
            )
        except Exception as e:
            logger.error(
                "ATN distribution failed",
                extra={"recipient": address, "amount": str(amount), "error": str(e)},
                exc_info=True,
            )
            return DistributionResult(
                success=False,
                status=DistributionStatus.TRANSACTION_FAILED,
                tx_hash=None,
                amount=amount,
                message=f"Transaction failed: {str(e)}",
            )
