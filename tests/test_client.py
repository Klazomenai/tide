"""Tests for Autonity client module."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from tide.blockchain.client import AutonityClient
from tide.core.wallet import EnvironmentWallet  # noqa: F401

# Test private key (DO NOT USE IN PRODUCTION - this is a well-known test key)
TEST_PRIVATE_KEY = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TEST_ADDRESS = "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c"
TEST_RECIPIENT = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"


@pytest.fixture
def mock_wallet():
    """Create a real wallet for testing."""
    return EnvironmentWallet(private_key=SecretStr(TEST_PRIVATE_KEY))


@pytest.fixture
def mock_web3():
    """Create a mock Web3 instance."""
    with patch("tide.blockchain.client.Web3") as mock_w3_class:
        mock_w3 = MagicMock()
        mock_w3_class.return_value = mock_w3
        mock_w3_class.HTTPProvider = MagicMock()
        mock_w3_class.to_checksum_address = lambda x: x
        mock_w3_class.to_wei = lambda val, unit: int(Decimal(str(val)) * 10**18)
        mock_w3.from_wei = lambda val, unit: Decimal(str(val)) / Decimal(10**18)
        mock_w3.to_wei = lambda val, unit: int(Decimal(str(val)) * 10**18)
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 65100000
        mock_w3.eth.gas_price = 1000000000
        mock_w3.eth.get_balance.return_value = 5000000000000000000  # 5 ATN
        mock_w3.eth.get_transaction_count.return_value = 0
        yield mock_w3_class, mock_w3


@pytest.fixture
def mock_autonity():
    """Create a mock Autonity contract."""
    with patch("tide.blockchain.client.Autonity") as mock_autonity_class:
        mock_contract = MagicMock()
        mock_autonity_class.return_value = mock_contract
        mock_contract.balance_of.return_value = 10000000000000000000  # 10 NTN
        yield mock_autonity_class, mock_contract


class TestAutonityClient:
    """Tests for AutonityClient."""

    def test_client_initialization(self, mock_wallet, mock_web3, mock_autonity):
        """Client initializes with RPC endpoint and wallet."""
        mock_w3_class, _ = mock_web3

        AutonityClient("http://localhost:8545", mock_wallet)

        mock_w3_class.HTTPProvider.assert_called_once_with("http://localhost:8545")

    def test_connected_property(self, mock_wallet, mock_web3, mock_autonity):
        """Connected property returns Web3 connection status."""
        _, mock_w3 = mock_web3

        client = AutonityClient("http://localhost:8545", mock_wallet)

        assert client.connected is True
        mock_w3.is_connected.return_value = False
        assert client.connected is False

    def test_chain_id_property(self, mock_wallet, mock_web3, mock_autonity):
        """Chain ID property returns network chain ID."""
        _, mock_w3 = mock_web3
        mock_w3.eth.chain_id = 65100000

        client = AutonityClient("http://localhost:8545", mock_wallet)

        assert client.chain_id == 65100000

    def test_wallet_address_property(self, mock_wallet, mock_web3, mock_autonity):
        """Wallet address property returns faucet address."""
        client = AutonityClient("http://localhost:8545", mock_wallet)

        assert client.wallet_address == TEST_ADDRESS

    def test_get_atn_balance(self, mock_wallet, mock_web3, mock_autonity):
        """Get ATN balance returns correct value."""
        _, mock_w3 = mock_web3
        mock_w3.eth.get_balance.return_value = 5000000000000000000  # 5 ATN in wei

        client = AutonityClient("http://localhost:8545", mock_wallet)
        balance = client.get_atn_balance(TEST_RECIPIENT)

        assert balance == Decimal("5")

    def test_get_ntn_balance(self, mock_wallet, mock_web3, mock_autonity):
        """Get NTN balance returns correct value."""
        _, mock_contract = mock_autonity
        mock_contract.balance_of.return_value = 10000000000000000000  # 10 NTN in wei

        client = AutonityClient("http://localhost:8545", mock_wallet)
        balance = client.get_ntn_balance(TEST_RECIPIENT)

        assert balance == Decimal("10")

    def test_transfer_atn(self, mock_web3, mock_autonity):
        """Transfer ATN submits transaction and returns hash."""
        _, mock_w3 = mock_web3
        mock_w3.eth.send_raw_transaction.return_value = bytes.fromhex("abcd1234" * 8)

        # Use fully mocked wallet to avoid real signing
        mock_wallet = MagicMock()
        mock_wallet.address = TEST_ADDRESS
        mock_account = MagicMock()
        mock_account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed")
        mock_wallet.get_account.return_value = mock_account

        client = AutonityClient("http://localhost:8545", mock_wallet)
        tx_hash = client.transfer_atn(TEST_RECIPIENT, Decimal("1.5"))

        assert tx_hash == "abcd1234" * 8
        mock_w3.eth.send_raw_transaction.assert_called_once()
        mock_account.sign_transaction.assert_called_once()

    def test_transfer_ntn(self, mock_web3, mock_autonity):
        """Transfer NTN submits transaction and returns hash."""
        _, mock_w3 = mock_web3
        _, mock_contract = mock_autonity

        mock_tx_func = MagicMock()
        mock_tx_func.build_transaction.return_value = {
            "to": TEST_RECIPIENT,
            "value": 0,
            "gas": 100000,
            "gasPrice": 1000000000,
            "nonce": 0,
            "chainId": 65100000,
            "data": "0x",
        }
        mock_contract.transfer.return_value = mock_tx_func
        mock_w3.eth.send_raw_transaction.return_value = bytes.fromhex("beef5678" * 8)

        # Use fully mocked wallet to avoid real signing
        mock_wallet = MagicMock()
        mock_wallet.address = TEST_ADDRESS
        mock_account = MagicMock()
        mock_account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed")
        mock_wallet.get_account.return_value = mock_account

        client = AutonityClient("http://localhost:8545", mock_wallet)
        tx_hash = client.transfer_ntn(TEST_RECIPIENT, Decimal("5"))

        assert tx_hash == "beef5678" * 8
        mock_contract.transfer.assert_called_once()
        mock_account.sign_transaction.assert_called_once()

    def test_get_faucet_balances(self, mock_wallet, mock_web3, mock_autonity):
        """Get faucet balances returns both ATN and NTN."""
        _, mock_w3 = mock_web3
        _, mock_contract = mock_autonity
        mock_w3.eth.get_balance.return_value = 100000000000000000000  # 100 ATN
        mock_contract.balance_of.return_value = 500000000000000000000  # 500 NTN

        client = AutonityClient("http://localhost:8545", mock_wallet)
        balances = client.get_faucet_balances()

        assert balances["atn"] == Decimal("100")
        assert balances["ntn"] == Decimal("500")

    def test_wait_for_receipt(self, mock_wallet, mock_web3, mock_autonity):
        """Wait for receipt calls Web3 with correct params."""
        _, mock_w3 = mock_web3
        mock_receipt = {"status": 1, "transactionHash": bytes.fromhex("abcd" * 16)}
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        client = AutonityClient("http://localhost:8545", mock_wallet)
        receipt = client.wait_for_receipt("0x" + "abcd" * 16, timeout=60)

        assert receipt == mock_receipt
        mock_w3.eth.wait_for_transaction_receipt.assert_called_once_with(
            "0x" + "abcd" * 16, timeout=60
        )
