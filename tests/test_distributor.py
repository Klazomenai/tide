"""Tests for Token Distributor modules."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tide.core.cdp import CDPHealth, CDPStatus
from tide.faucet.distributor import (
    ATNDistributor,
    DistributionResult,
    DistributionStatus,
    NTNDistributor,
    validate_address,
)


class TestValidateAddress:
    """Tests for validate_address function."""

    def test_valid_address(self):
        """validate_address accepts valid Ethereum address."""
        assert validate_address("0x1234567890123456789012345678901234567890") is True

    def test_valid_address_mixed_case(self):
        """validate_address accepts mixed case hex."""
        assert validate_address("0xAbCdEf1234567890123456789012345678901234") is True

    def test_invalid_no_prefix(self):
        """validate_address rejects address without 0x prefix."""
        assert validate_address("1234567890123456789012345678901234567890") is False

    def test_invalid_short(self):
        """validate_address rejects short address."""
        assert validate_address("0x123") is False

    def test_invalid_long(self):
        """validate_address rejects long address."""
        assert validate_address("0x12345678901234567890123456789012345678901") is False

    def test_invalid_non_hex(self):
        """validate_address rejects non-hex characters."""
        assert validate_address("0xGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG") is False

    def test_invalid_empty(self):
        """validate_address rejects empty string."""
        assert validate_address("") is False


class TestDistributionResult:
    """Tests for DistributionResult dataclass."""

    def test_success_result(self):
        """DistributionResult can represent success."""
        result = DistributionResult(
            success=True,
            status=DistributionStatus.SUCCESS,
            tx_hash="0xabc123",
            amount=Decimal("10"),
            message="Successfully sent 10 NTN",
        )

        assert result.success is True
        assert result.status == DistributionStatus.SUCCESS
        assert result.tx_hash == "0xabc123"

    def test_failure_result(self):
        """DistributionResult can represent failure."""
        result = DistributionResult(
            success=False,
            status=DistributionStatus.INSUFFICIENT_BALANCE,
            tx_hash=None,
            amount=Decimal("100"),
            message="Insufficient balance",
        )

        assert result.success is False
        assert result.tx_hash is None


class TestNTNDistributor:
    """Tests for NTNDistributor."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock AutonityClient."""
        client = MagicMock()
        client.wallet_address = "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c"
        client.get_ntn_balance = MagicMock(return_value=Decimal("1000"))
        client.transfer_ntn = MagicMock(return_value="0xtxhash123")
        return client

    def test_initialization(self, mock_client):
        """NTNDistributor initializes with defaults."""
        distributor = NTNDistributor(mock_client)

        assert distributor.max_amount == Decimal("50")

    def test_custom_max_amount(self, mock_client):
        """NTNDistributor accepts custom max amount."""
        distributor = NTNDistributor(mock_client, max_amount=Decimal("100"))

        assert distributor.max_amount == Decimal("100")

    @pytest.mark.asyncio
    async def test_get_balance(self, mock_client):
        """get_balance returns client balance."""
        distributor = NTNDistributor(mock_client)

        balance = await distributor.get_balance()

        assert balance == Decimal("1000")
        mock_client.get_ntn_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_invalid_address(self, mock_client):
        """validate_request rejects invalid address."""
        distributor = NTNDistributor(mock_client)

        result = await distributor.validate_request("invalid", Decimal("10"))

        assert result is not None
        assert result.status == DistributionStatus.INVALID_ADDRESS

    @pytest.mark.asyncio
    async def test_validate_short_address(self, mock_client):
        """validate_request rejects short address."""
        distributor = NTNDistributor(mock_client)

        result = await distributor.validate_request("0x123", Decimal("10"))

        assert result is not None
        assert result.status == DistributionStatus.INVALID_ADDRESS

    @pytest.mark.asyncio
    async def test_validate_zero_amount(self, mock_client):
        """validate_request rejects zero amount."""
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("0"))

        assert result is not None
        assert result.status == DistributionStatus.INVALID_AMOUNT

    @pytest.mark.asyncio
    async def test_validate_negative_amount(self, mock_client):
        """validate_request rejects negative amount."""
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("-10"))

        assert result is not None
        assert result.status == DistributionStatus.INVALID_AMOUNT

    @pytest.mark.asyncio
    async def test_validate_exceeds_max(self, mock_client):
        """validate_request rejects amount exceeding max."""
        distributor = NTNDistributor(mock_client, max_amount=Decimal("50"))
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("100"))

        assert result is not None
        assert result.status == DistributionStatus.INVALID_AMOUNT
        assert "50" in result.message

    @pytest.mark.asyncio
    async def test_validate_insufficient_balance(self, mock_client):
        """validate_request rejects when balance insufficient."""
        mock_client.get_ntn_balance = MagicMock(return_value=Decimal("5"))
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("10"))

        assert result is not None
        assert result.status == DistributionStatus.INSUFFICIENT_BALANCE

    @pytest.mark.asyncio
    async def test_validate_success(self, mock_client):
        """validate_request returns None for valid request."""
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("10"))

        assert result is None

    @pytest.mark.asyncio
    async def test_distribute_success(self, mock_client):
        """distribute successfully transfers NTN."""
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.distribute(address, Decimal("10"))

        assert result.success is True
        assert result.status == DistributionStatus.SUCCESS
        assert result.tx_hash == "0xtxhash123"
        mock_client.transfer_ntn.assert_called_once_with(address, Decimal("10"))

    @pytest.mark.asyncio
    async def test_distribute_validation_failure(self, mock_client):
        """distribute returns validation error."""
        distributor = NTNDistributor(mock_client)

        result = await distributor.distribute("invalid", Decimal("10"))

        assert result.success is False
        assert result.status == DistributionStatus.INVALID_ADDRESS

    @pytest.mark.asyncio
    async def test_distribute_transaction_failure(self, mock_client):
        """distribute handles transaction failure."""
        mock_client.transfer_ntn = MagicMock(side_effect=Exception("TX failed"))
        distributor = NTNDistributor(mock_client)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.distribute(address, Decimal("10"))

        assert result.success is False
        assert result.status == DistributionStatus.TRANSACTION_FAILED
        assert "TX failed" in result.message


class TestATNDistributor:
    """Tests for ATNDistributor."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock AutonityClient."""
        client = MagicMock()
        client.wallet_address = "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c"
        client.get_atn_balance = MagicMock(return_value=Decimal("100"))
        client.transfer_atn = MagicMock(return_value="0xtxhash456")
        return client

    @pytest.fixture
    def mock_cdp_manager(self):
        """Create a mock CDPManager."""
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
        manager.borrow.return_value = "0xborrow123"
        return manager

    def test_initialization(self, mock_client, mock_cdp_manager):
        """ATNDistributor initializes with defaults."""
        distributor = ATNDistributor(mock_client, mock_cdp_manager)

        assert distributor.max_amount == Decimal("5")

    @pytest.mark.asyncio
    async def test_get_available(self, mock_client, mock_cdp_manager):
        """get_available returns max borrowable from CDP."""
        distributor = ATNDistributor(mock_client, mock_cdp_manager)

        available = await distributor.get_available()

        assert available == Decimal("10")

    @pytest.mark.asyncio
    async def test_get_available_no_cdp(self, mock_client, mock_cdp_manager):
        """get_available returns 0 when no CDP exists."""
        mock_cdp_manager.get_status.return_value = CDPStatus(
            exists=False,
            collateral=Decimal("0"),
            debt=Decimal("0"),
            collateralization_ratio=None,
            health=CDPHealth.NO_CDP,
            is_liquidatable=False,
            max_borrowable=Decimal("0"),
            min_collateral_required=Decimal("0"),
        )
        distributor = ATNDistributor(mock_client, mock_cdp_manager)

        available = await distributor.get_available()

        assert available == Decimal("0")

    @pytest.mark.asyncio
    async def test_validate_cdp_unhealthy(self, mock_client, mock_cdp_manager):
        """validate_request rejects when CDP is unhealthy."""
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
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("1"))

        assert result is not None
        assert result.status == DistributionStatus.CDP_UNHEALTHY

    @pytest.mark.asyncio
    async def test_validate_insufficient_collateral(self, mock_client, mock_cdp_manager):
        """validate_request rejects when insufficient borrowing capacity."""
        # Wallet has 0 ATN and can only borrow 1
        mock_client.get_atn_balance = MagicMock(return_value=Decimal("0"))
        mock_cdp_manager.get_status.return_value = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("40"),
            collateralization_ratio=Decimal("250"),
            health=CDPHealth.HEALTHY,
            is_liquidatable=False,
            max_borrowable=Decimal("1"),
            min_collateral_required=Decimal("80"),
        )
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("5"))

        assert result is not None
        assert result.status == DistributionStatus.INSUFFICIENT_COLLATERAL

    @pytest.mark.asyncio
    async def test_validate_success_from_wallet(self, mock_client, mock_cdp_manager):
        """validate_request passes when wallet has enough ATN."""
        mock_client.get_atn_balance = MagicMock(return_value=Decimal("10"))
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.validate_request(address, Decimal("5"))

        assert result is None

    @pytest.mark.asyncio
    async def test_distribute_from_wallet(self, mock_client, mock_cdp_manager):
        """distribute uses wallet balance when sufficient."""
        mock_client.get_atn_balance = MagicMock(return_value=Decimal("10"))
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.distribute(address, Decimal("5"))

        assert result.success is True
        mock_cdp_manager.borrow.assert_not_called()
        mock_client.transfer_atn.assert_called_once()

    @pytest.mark.asyncio
    async def test_distribute_with_borrow(self, mock_client, mock_cdp_manager):
        """distribute borrows when wallet balance insufficient."""
        mock_client.get_atn_balance = MagicMock(return_value=Decimal("2"))
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.distribute(address, Decimal("5"))

        assert result.success is True
        mock_cdp_manager.borrow.assert_called_once_with(Decimal("3"))
        mock_client.transfer_atn.assert_called_once()

    @pytest.mark.asyncio
    async def test_distribute_transaction_failure(self, mock_client, mock_cdp_manager):
        """distribute handles transaction failure."""
        mock_client.transfer_atn = MagicMock(side_effect=Exception("TX failed"))
        distributor = ATNDistributor(mock_client, mock_cdp_manager)
        address = "0x1234567890123456789012345678901234567890"

        result = await distributor.distribute(address, Decimal("1"))

        assert result.success is False
        assert result.status == DistributionStatus.TRANSACTION_FAILED
