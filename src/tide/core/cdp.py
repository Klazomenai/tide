"""CDP (Collateralized Debt Position) Manager for TIDE.

Manages ATN liquidity through the Autonity Stabilization contract:
- NTN (Newton) is used as collateral
- ATN (Auton) is borrowed against the collateral
- Maintains healthy collateralization ratios to avoid liquidation
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from autonity import Autonity, Stabilization
from web3 import Web3

from tide.core.wallet import WalletProvider

logger = logging.getLogger(__name__)

# Scale factor used by Stabilization contract (18 decimals)
SCALE_FACTOR = Decimal(10**18)


class CDPHealth(str, Enum):
    """CDP health status based on collateralization ratio."""

    CRITICAL = "critical"  # Below liquidation ratio (180%)
    DANGER = "danger"  # Below min CR (default 220%)
    HEALTHY = "healthy"  # Within target range
    OVERCOLLATERALIZED = "overcollateralized"  # Above max CR (default 300%)
    NO_CDP = "no_cdp"  # No CDP exists


@dataclass
class CDPStatus:
    """Current CDP status information."""

    exists: bool
    collateral: Decimal  # NTN collateral in ether units
    debt: Decimal  # ATN debt in ether units
    collateralization_ratio: Decimal | None  # As percentage (e.g., 250 = 250%)
    health: CDPHealth
    is_liquidatable: bool
    max_borrowable: Decimal  # Additional ATN that can be borrowed
    min_collateral_required: Decimal  # Minimum NTN to maintain current debt


class CDPManager:
    """Manages CDP operations for TIDE faucet.

    Parameters
    ----------
    w3 : Web3
        Web3 instance connected to Autonity network.
    wallet : WalletProvider
        Wallet provider for signing transactions.
    target_cr : Decimal
        Target collateralization ratio (e.g., 2.5 for 250%).
    min_cr : Decimal
        Minimum CR before adding collateral (e.g., 2.2 for 220%).
    max_cr : Decimal
        Maximum CR before borrowing more (e.g., 3.0 for 300%).
    """

    def __init__(
        self,
        w3: Web3,
        wallet: WalletProvider,
        target_cr: Decimal = Decimal("2.5"),
        min_cr: Decimal = Decimal("2.2"),
        max_cr: Decimal = Decimal("3.0"),
    ):
        self._w3 = w3
        self._wallet = wallet
        self._autonity = Autonity(w3)
        self._stabilization: Stabilization | None = None

        # CR thresholds as ratios (not percentages)
        self.target_cr = target_cr
        self.min_cr = min_cr
        self.max_cr = max_cr

    @property
    def stabilization(self) -> Stabilization:
        """Get the Stabilization contract instance (lazy loaded)."""
        if self._stabilization is None:
            # Stabilization factory auto-fetches contract address from network config
            self._stabilization = Stabilization(self._w3)
        return self._stabilization

    def get_status(self) -> CDPStatus:
        """Get current CDP status.

        Returns
        -------
        CDPStatus
            Current CDP status including collateral, debt, and health.
        """
        address = self._wallet.address
        cdp = self.stabilization.cdps(address)

        # Check if CDP exists (has collateral or debt)
        if cdp.collateral == 0 and cdp.principal == 0:
            return CDPStatus(
                exists=False,
                collateral=Decimal("0"),
                debt=Decimal("0"),
                collateralization_ratio=None,
                health=CDPHealth.NO_CDP,
                is_liquidatable=False,
                max_borrowable=Decimal("0"),
                min_collateral_required=Decimal("0"),
            )

        # Get current values
        collateral_wei = cdp.collateral
        debt_wei = self.stabilization.debt_amount(address)

        collateral = Decimal(str(collateral_wei)) / SCALE_FACTOR
        debt = Decimal(str(debt_wei)) / SCALE_FACTOR

        # Calculate CR if there's debt
        cr: Decimal | None = None
        if debt > 0:
            # Get collateral price in ATN terms
            collateral_price = self.stabilization.collateral_price()
            collateral_value = (
                Decimal(str(collateral_wei)) * Decimal(str(collateral_price)) / SCALE_FACTOR
            )
            cr = (collateral_value / Decimal(str(debt_wei))) * Decimal("100")

        # Determine health status
        health = self._calculate_health(cr)

        # Check liquidatable status
        is_liquidatable = self.stabilization.is_liquidatable(address)

        # Calculate max borrowable
        max_borrow_wei = self.stabilization.max_borrow(collateral_wei)
        max_borrowable = Decimal(str(max_borrow_wei)) / SCALE_FACTOR
        # Subtract current debt to get additional borrowable
        additional_borrowable = max(Decimal("0"), max_borrowable - debt)

        # Calculate minimum collateral for current debt
        min_collateral_required = Decimal("0")
        if debt_wei > 0:
            config = self.stabilization.config()
            mcr = config.min_collateralization_ratio
            collateral_price_acu = self.stabilization.collateral_price_acu()
            target_price = config.target_price
            min_coll_wei = self.stabilization.minimum_collateral(
                debt_wei, collateral_price_acu, target_price, mcr
            )
            min_collateral_required = Decimal(str(min_coll_wei)) / SCALE_FACTOR

        return CDPStatus(
            exists=True,
            collateral=collateral,
            debt=debt,
            collateralization_ratio=cr,
            health=health,
            is_liquidatable=is_liquidatable,
            max_borrowable=additional_borrowable,
            min_collateral_required=min_collateral_required,
        )

    def _calculate_health(self, cr: Decimal | None) -> CDPHealth:
        """Calculate health status from collateralization ratio.

        Parameters
        ----------
        cr : Decimal | None
            Collateralization ratio as percentage (e.g., 250 for 250%).

        Returns
        -------
        CDPHealth
            Health status.
        """
        if cr is None:
            return CDPHealth.HEALTHY  # No debt = healthy

        # Convert percentage to ratio for comparison
        cr_ratio = cr / Decimal("100")

        # Get liquidation ratio from contract
        liq_ratio = Decimal(str(self.stabilization.liquidation_ratio())) / SCALE_FACTOR

        if cr_ratio < liq_ratio:
            return CDPHealth.CRITICAL
        elif cr_ratio < self.min_cr:
            return CDPHealth.DANGER
        elif cr_ratio > self.max_cr:
            return CDPHealth.OVERCOLLATERALIZED
        else:
            return CDPHealth.HEALTHY

    def deposit(self, amount: Decimal) -> str:
        """Deposit NTN collateral into CDP.

        Parameters
        ----------
        amount : Decimal
            Amount of NTN to deposit (in ether units).

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        ValueError
            If amount is not positive.
        """
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")

        amount_wei = int(amount * SCALE_FACTOR)
        address = self._wallet.address

        # First, approve the Stabilization contract to spend NTN
        stabilization_address = self.stabilization._contract.address
        approve_tx = self._autonity.approve(stabilization_address, amount_wei).build_transaction(
            {
                "from": address,
                "gas": 100000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed_approve = self._wallet.get_account().sign_transaction(approve_tx)
        approve_hash = self._w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        self._w3.eth.wait_for_transaction_receipt(approve_hash)

        logger.info(
            "NTN approval for deposit",
            extra={"tx_hash": approve_hash.hex(), "amount": str(amount)},
        )

        # Now deposit
        deposit_tx = self.stabilization.deposit(amount_wei).build_transaction(
            {
                "from": address,
                "gas": 300000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed_deposit = self._wallet.get_account().sign_transaction(deposit_tx)
        deposit_hash = self._w3.eth.send_raw_transaction(signed_deposit.raw_transaction)

        logger.info(
            "NTN deposited to CDP",
            extra={"tx_hash": deposit_hash.hex(), "amount": str(amount)},
        )

        return deposit_hash.hex()

    def withdraw(self, amount: Decimal) -> str:
        """Withdraw NTN collateral from CDP.

        Parameters
        ----------
        amount : Decimal
            Amount of NTN to withdraw (in ether units).

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        ValueError
            If amount is not positive or would make CDP liquidatable.
        """
        if amount <= 0:
            raise ValueError("Withdraw amount must be positive")

        amount_wei = int(amount * SCALE_FACTOR)
        address = self._wallet.address

        withdraw_tx = self.stabilization.withdraw(amount_wei).build_transaction(
            {
                "from": address,
                "gas": 200000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed = self._wallet.get_account().sign_transaction(withdraw_tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(
            "NTN withdrawn from CDP",
            extra={"tx_hash": tx_hash.hex(), "amount": str(amount)},
        )

        return tx_hash.hex()

    def borrow(self, amount: Decimal) -> str:
        """Borrow ATN against CDP collateral.

        Parameters
        ----------
        amount : Decimal
            Amount of ATN to borrow (in ether units).

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        ValueError
            If amount is not positive or exceeds borrow limit.
        """
        if amount <= 0:
            raise ValueError("Borrow amount must be positive")

        amount_wei = int(amount * SCALE_FACTOR)
        address = self._wallet.address

        borrow_tx = self.stabilization.borrow(amount_wei).build_transaction(
            {
                "from": address,
                "gas": 300000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed = self._wallet.get_account().sign_transaction(borrow_tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(
            "ATN borrowed from CDP",
            extra={"tx_hash": tx_hash.hex(), "amount": str(amount)},
        )

        return tx_hash.hex()

    def repay(self, amount: Decimal) -> str:
        """Repay ATN debt.

        Parameters
        ----------
        amount : Decimal
            Amount of ATN to repay (in ether units).

        Returns
        -------
        str
            Transaction hash.

        Raises
        ------
        ValueError
            If amount is not positive.
        """
        if amount <= 0:
            raise ValueError("Repay amount must be positive")

        amount_wei = int(amount * SCALE_FACTOR)
        address = self._wallet.address

        # Repay is a payable function - ATN is sent as value
        repay_tx = self.stabilization.repay().build_transaction(
            {
                "from": address,
                "value": amount_wei,
                "gas": 200000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed = self._wallet.get_account().sign_transaction(repay_tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(
            "ATN repaid to CDP",
            extra={"tx_hash": tx_hash.hex(), "amount": str(amount)},
        )

        return tx_hash.hex()

    def calculate_rebalance_action(self) -> tuple[str, Decimal] | None:
        """Calculate what action is needed to rebalance CDP.

        Returns
        -------
        tuple[str, Decimal] | None
            Tuple of (action, amount) where action is 'deposit', 'withdraw',
            'borrow', or 'repay'. Returns None if no action needed.
        """
        status = self.get_status()

        if not status.exists:
            return None

        if status.collateralization_ratio is None:
            return None

        cr_ratio = status.collateralization_ratio / Decimal("100")

        # If critical or danger, need to add collateral or repay
        if status.health in (CDPHealth.CRITICAL, CDPHealth.DANGER):
            # Calculate how much to repay to reach target CR
            # target_cr = collateral_value / debt
            # debt_new = collateral_value / target_cr
            # repay_amount = debt - debt_new
            if status.debt > 0:
                collateral_value = status.debt * cr_ratio
                target_debt = collateral_value / self.target_cr
                repay_amount = status.debt - target_debt
                if repay_amount > 0:
                    return ("repay", repay_amount)

        # If overcollateralized, can borrow more
        if status.health == CDPHealth.OVERCOLLATERALIZED:
            # Calculate how much to borrow to reach target CR
            if status.debt > 0:
                collateral_value = status.debt * cr_ratio
                target_debt = collateral_value / self.target_cr
                borrow_amount = target_debt - status.debt
                # Don't borrow more than allowed
                borrow_amount = min(borrow_amount, status.max_borrowable)
                if borrow_amount > Decimal("0.01"):  # Minimum threshold
                    return ("borrow", borrow_amount)

        return None
