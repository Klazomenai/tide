"""Tests for CDP Manager module."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tide.core.cdp import SCALE_FACTOR, CDPHealth, CDPManager, CDPStatus

# Mock CDP data
MOCK_CDP_WITH_DEBT = MagicMock(
    timestamp=1000000,
    collateral=int(Decimal("100") * SCALE_FACTOR),  # 100 NTN
    principal=int(Decimal("40") * SCALE_FACTOR),  # 40 ATN principal
    interest=0,
    last_aggregated_interest_exponent=0,
)

MOCK_CDP_EMPTY = MagicMock(
    timestamp=0,
    collateral=0,
    principal=0,
    interest=0,
    last_aggregated_interest_exponent=0,
)

MOCK_CONFIG = MagicMock(
    min_collateralization_ratio=int(Decimal("2.0") * SCALE_FACTOR),
    liquidation_ratio=int(Decimal("1.8") * SCALE_FACTOR),
    target_price=int(Decimal("1.0") * SCALE_FACTOR),
)


@pytest.fixture
def mock_wallet():
    """Create a mock wallet."""
    wallet = MagicMock()
    wallet.address = "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c"
    wallet.get_account.return_value = MagicMock(
        sign_transaction=MagicMock(return_value=MagicMock(raw_transaction=b"signed"))
    )
    return wallet


@pytest.fixture
def mock_web3():
    """Create a mock Web3 instance."""
    w3 = MagicMock()
    w3.eth.chain_id = 65100000
    w3.eth.gas_price = 1000000000
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.send_raw_transaction.return_value = bytes.fromhex("abcd" * 16)
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
    return w3


@pytest.fixture
def mock_stabilization():
    """Create a mock Stabilization contract."""
    stabilization = MagicMock()
    stabilization.cdps.return_value = MOCK_CDP_WITH_DEBT
    stabilization.debt_amount.return_value = int(Decimal("40") * SCALE_FACTOR)
    stabilization.collateral_price.return_value = int(SCALE_FACTOR)  # 1:1 NTN:ATN
    stabilization.collateral_price_acu.return_value = int(SCALE_FACTOR)
    stabilization.is_liquidatable.return_value = False
    stabilization.max_borrow.return_value = int(Decimal("50") * SCALE_FACTOR)
    stabilization.minimum_collateral.return_value = int(Decimal("80") * SCALE_FACTOR)
    stabilization.config.return_value = MOCK_CONFIG
    stabilization.liquidation_ratio.return_value = int(Decimal("1.8") * SCALE_FACTOR)
    stabilization._contract.address = "0x1234567890123456789012345678901234567890"

    # Mock transaction builders
    for method in ["deposit", "withdraw", "borrow", "repay"]:
        getattr(stabilization, method).return_value.build_transaction.return_value = {
            "to": "0x1234",
            "data": "0x",
            "gas": 100000,
            "gasPrice": 1000000000,
            "nonce": 0,
            "chainId": 65100000,
        }

    return stabilization


@pytest.fixture
def mock_autonity():
    """Create a mock Autonity contract."""
    autonity = MagicMock()
    autonity.get_config.return_value.contracts.stabilization_contract = (
        "0x1234567890123456789012345678901234567890"
    )
    autonity.approve.return_value.build_transaction.return_value = {
        "to": "0x1234",
        "data": "0x",
        "gas": 100000,
        "gasPrice": 1000000000,
        "nonce": 0,
        "chainId": 65100000,
    }
    return autonity


class TestCDPHealth:
    """Tests for CDPHealth enum."""

    def test_all_health_values(self):
        """All health values exist."""
        assert CDPHealth.CRITICAL == "critical"
        assert CDPHealth.DANGER == "danger"
        assert CDPHealth.HEALTHY == "healthy"
        assert CDPHealth.OVERCOLLATERALIZED == "overcollateralized"
        assert CDPHealth.NO_CDP == "no_cdp"


class TestCDPStatus:
    """Tests for CDPStatus dataclass."""

    def test_status_creation(self):
        """CDPStatus can be created with all fields."""
        status = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("40"),
            collateralization_ratio=Decimal("250"),
            health=CDPHealth.HEALTHY,
            is_liquidatable=False,
            max_borrowable=Decimal("10"),
            min_collateral_required=Decimal("80"),
        )

        assert status.exists is True
        assert status.collateral == Decimal("100")
        assert status.debt == Decimal("40")
        assert status.collateralization_ratio == Decimal("250")
        assert status.health == CDPHealth.HEALTHY


class TestCDPManager:
    """Tests for CDPManager."""

    def test_manager_initialization(self, mock_web3, mock_wallet):
        """CDPManager initializes with web3 and wallet."""
        with patch("tide.core.cdp.Autonity"):
            manager = CDPManager(mock_web3, mock_wallet)

            assert manager.target_cr == Decimal("2.5")
            assert manager.min_cr == Decimal("2.2")
            assert manager.max_cr == Decimal("3.0")

    def test_manager_custom_thresholds(self, mock_web3, mock_wallet):
        """CDPManager accepts custom CR thresholds."""
        with patch("tide.core.cdp.Autonity"):
            manager = CDPManager(
                mock_web3,
                mock_wallet,
                target_cr=Decimal("2.0"),
                min_cr=Decimal("1.9"),
                max_cr=Decimal("2.5"),
            )

            assert manager.target_cr == Decimal("2.0")
            assert manager.min_cr == Decimal("1.9")
            assert manager.max_cr == Decimal("2.5")

    def test_get_status_with_cdp(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """get_status returns correct status when CDP exists."""
        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                status = manager.get_status()

                assert status.exists is True
                assert status.collateral == Decimal("100")
                assert status.debt == Decimal("40")
                assert status.is_liquidatable is False

    def test_get_status_no_cdp(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """get_status returns NO_CDP when no CDP exists."""
        mock_stabilization.cdps.return_value = MOCK_CDP_EMPTY

        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                status = manager.get_status()

                assert status.exists is False
                assert status.health == CDPHealth.NO_CDP
                assert status.collateral == Decimal("0")
                assert status.debt == Decimal("0")

    def test_deposit(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """deposit sends approval and deposit transactions."""
        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization
                manager._autonity = mock_autonity

                tx_hash = manager.deposit(Decimal("10"))

                assert tx_hash == "abcd" * 16
                mock_autonity.approve.assert_called_once()
                mock_stabilization.deposit.assert_called_once()

    def test_deposit_invalid_amount(self, mock_web3, mock_wallet):
        """deposit raises ValueError for non-positive amount."""
        with patch("tide.core.cdp.Autonity"):
            manager = CDPManager(mock_web3, mock_wallet)

            with pytest.raises(ValueError, match="must be positive"):
                manager.deposit(Decimal("0"))

            with pytest.raises(ValueError, match="must be positive"):
                manager.deposit(Decimal("-10"))

    def test_withdraw(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """withdraw sends withdraw transaction."""
        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                tx_hash = manager.withdraw(Decimal("5"))

                assert tx_hash == "abcd" * 16
                mock_stabilization.withdraw.assert_called_once()

    def test_borrow(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """borrow sends borrow transaction."""
        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                tx_hash = manager.borrow(Decimal("10"))

                assert tx_hash == "abcd" * 16
                mock_stabilization.borrow.assert_called_once()

    def test_repay(self, mock_web3, mock_wallet, mock_stabilization, mock_autonity):
        """repay sends repay transaction with value."""
        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                tx_hash = manager.repay(Decimal("5"))

                assert tx_hash == "abcd" * 16
                mock_stabilization.repay.assert_called_once()

    def test_calculate_health_healthy(self, mock_web3, mock_wallet, mock_stabilization):
        """_calculate_health returns HEALTHY for CR in target range."""
        with patch("tide.core.cdp.Autonity"):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                # 250% CR is healthy (between 220% min and 300% max)
                health = manager._calculate_health(Decimal("250"))
                assert health == CDPHealth.HEALTHY

    def test_calculate_health_danger(self, mock_web3, mock_wallet, mock_stabilization):
        """_calculate_health returns DANGER for CR below min."""
        with patch("tide.core.cdp.Autonity"):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                # 200% CR is danger (below 220% min but above 180% liquidation)
                health = manager._calculate_health(Decimal("200"))
                assert health == CDPHealth.DANGER

    def test_calculate_health_critical(self, mock_web3, mock_wallet, mock_stabilization):
        """_calculate_health returns CRITICAL for CR below liquidation."""
        with patch("tide.core.cdp.Autonity"):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                # 170% CR is critical (below 180% liquidation ratio)
                health = manager._calculate_health(Decimal("170"))
                assert health == CDPHealth.CRITICAL

    def test_calculate_health_overcollateralized(self, mock_web3, mock_wallet, mock_stabilization):
        """_calculate_health returns OVERCOLLATERALIZED for CR above max."""
        with patch("tide.core.cdp.Autonity"):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                # 350% CR is overcollateralized (above 300% max)
                health = manager._calculate_health(Decimal("350"))
                assert health == CDPHealth.OVERCOLLATERALIZED

    def test_calculate_rebalance_no_action_needed(
        self, mock_web3, mock_wallet, mock_stabilization, mock_autonity
    ):
        """calculate_rebalance_action returns None when healthy."""
        # Set up a healthy CDP (250% CR)
        mock_stabilization.cdps.return_value = MOCK_CDP_WITH_DEBT
        mock_stabilization.debt_amount.return_value = int(Decimal("40") * SCALE_FACTOR)

        with patch("tide.core.cdp.Autonity", return_value=mock_autonity):
            with patch("tide.core.cdp.Stabilization", return_value=mock_stabilization):
                manager = CDPManager(mock_web3, mock_wallet)
                manager._stabilization = mock_stabilization

                action = manager.calculate_rebalance_action()
                assert action is None
