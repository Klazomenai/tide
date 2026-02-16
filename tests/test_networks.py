"""Tests for network configuration module."""

from tide.blockchain.networks import NetworkInfo


class TestNetworkInfo:
    """Tests for NetworkInfo dataclass."""

    def test_basic_creation(self):
        """NetworkInfo can be created with required fields."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
        )

        assert network.rpc_endpoint == "http://localhost:8545"
        assert network.chain_id == 65100000
        assert network.block_explorer_url is None

    def test_with_block_explorer(self):
        """NetworkInfo can include block explorer URL."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
            block_explorer_url="https://explorer.example.com",
        )

        assert network.block_explorer_url == "https://explorer.example.com"

    def test_get_tx_url_with_explorer(self):
        """get_tx_url returns correct URL when explorer configured."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
            block_explorer_url="https://explorer.example.com",
        )
        tx_hash = "0xabcd1234"

        url = network.get_tx_url(tx_hash)

        assert url == "https://explorer.example.com/tx/0xabcd1234"

    def test_get_tx_url_without_explorer(self):
        """get_tx_url returns None when no explorer configured."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
        )

        url = network.get_tx_url("0xabcd1234")

        assert url is None

    def test_get_tx_url_strips_trailing_slash(self):
        """get_tx_url handles trailing slash in explorer URL."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
            block_explorer_url="https://explorer.example.com/",
        )

        url = network.get_tx_url("0xabcd1234")

        assert url == "https://explorer.example.com/tx/0xabcd1234"

    def test_get_address_url_with_explorer(self):
        """get_address_url returns correct URL when explorer configured."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
            block_explorer_url="https://explorer.example.com",
        )
        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"

        url = network.get_address_url(address)

        assert url == f"https://explorer.example.com/address/{address}"

    def test_get_address_url_without_explorer(self):
        """get_address_url returns None when no explorer configured."""
        network = NetworkInfo(
            rpc_endpoint="http://localhost:8545",
            chain_id=65100000,
        )

        url = network.get_address_url("0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00")

        assert url is None
