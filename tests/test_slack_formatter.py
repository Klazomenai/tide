"""Tests for Slack message formatter."""

from decimal import Decimal

import pytest

from tide.blockchain.networks import NetworkInfo
from tide.core.cdp import CDPHealth, CDPStatus
from tide.faucet.service import FaucetRequestType, FaucetResult, FaucetStatus
from tide.slack.formatter import MessageFormatter


class TestMessageFormatter:
    """Tests for MessageFormatter."""

    @pytest.fixture
    def formatter(self):
        """Create a formatter without network info."""
        return MessageFormatter()

    @pytest.fixture
    def formatter_with_network(self):
        """Create a formatter with network info."""
        network = NetworkInfo(
            rpc_endpoint="https://rpc.example.com",
            chain_id=65100000,
            block_explorer_url="https://explorer.example.com",
        )
        return MessageFormatter(network)

    def test_format_distribution_success(self, formatter):
        """format_distribution_success returns Block Kit message."""
        result = FaucetResult(
            success=True,
            request_type=FaucetRequestType.NTN,
            tx_hash="0xabcd1234567890",
            amount=Decimal("10"),
            message="Success",
            remaining_requests=5,
        )

        response = formatter.format_distribution_success(result)

        assert "blocks" in response
        blocks = response["blocks"]
        assert len(blocks) == 2
        # Check success message
        assert ":white_check_mark:" in blocks[0]["text"]["text"]
        assert "10 NTN" in blocks[0]["text"]["text"]

    def test_format_distribution_success_with_explorer(self, formatter_with_network):
        """format_distribution_success includes explorer link."""
        result = FaucetResult(
            success=True,
            request_type=FaucetRequestType.ATN,
            tx_hash="0xabcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234",
            amount=Decimal("5"),
            message="Success",
            remaining_requests=3,
        )

        response = formatter_with_network.format_distribution_success(result)

        blocks = response["blocks"]
        # Check for explorer link in transaction field
        tx_field = blocks[1]["fields"][0]["text"]
        assert "explorer.example.com" in tx_field

    def test_format_distribution_error(self, formatter):
        """format_distribution_error returns error Block Kit message."""
        result = FaucetResult(
            success=False,
            request_type=FaucetRequestType.ATN,
            tx_hash=None,
            amount=Decimal("10"),
            message="Rate limit exceeded",
            remaining_requests=0,
        )

        response = formatter.format_distribution_error(result)

        assert "blocks" in response
        blocks = response["blocks"]
        assert ":x:" in blocks[0]["text"]["text"]
        assert "Rate limit exceeded" in blocks[0]["text"]["text"]

    def test_format_status_healthy(self, formatter):
        """format_status returns healthy status message."""
        status = FaucetStatus(
            healthy=True,
            cdp_status=None,
            atn_available=Decimal("100"),
            ntn_available=Decimal("500"),
            message="Faucet operational",
        )

        response = formatter.format_status(status, user_remaining=5)

        assert "blocks" in response
        blocks = response["blocks"]
        # Check header
        assert blocks[0]["type"] == "header"
        assert "Status" in blocks[0]["text"]["text"]
        # Check health emoji
        assert ":white_check_mark:" in blocks[1]["fields"][0]["text"]

    def test_format_status_with_cdp(self, formatter):
        """format_status includes CDP info when available."""
        cdp_status = CDPStatus(
            exists=True,
            collateral=Decimal("100"),
            debt=Decimal("40"),
            collateralization_ratio=Decimal("250"),
            health=CDPHealth.HEALTHY,
            is_liquidatable=False,
            max_borrowable=Decimal("10"),
            min_collateral_required=Decimal("80"),
        )
        status = FaucetStatus(
            healthy=True,
            cdp_status=cdp_status,
            atn_available=Decimal("10"),
            ntn_available=Decimal("500"),
            message="Faucet operational",
        )

        response = formatter.format_status(status, user_remaining=5)

        blocks = response["blocks"]
        # Should have CDP section
        assert len(blocks) == 4
        assert "CDP Health" in blocks[3]["fields"][0]["text"]

    def test_format_help(self, formatter):
        """format_help returns help message."""
        response = formatter.format_help(max_atn=Decimal("5"), max_ntn=Decimal("50"))

        assert "blocks" in response
        blocks = response["blocks"]
        assert blocks[0]["type"] == "header"
        assert "Commands" in blocks[0]["text"]["text"]
        # Check commands are listed
        text = blocks[1]["text"]["text"]
        assert "/tide atn" in text
        assert "/tide ntn" in text
        assert "/tide status" in text
        assert "/tide help" in text

    def test_format_alerts_empty(self, formatter):
        """format_alerts returns no alerts message when empty."""
        response = formatter.format_alerts([])

        assert "blocks" in response
        assert "No active alerts" in response["blocks"][0]["text"]["text"]

    def test_format_alerts_with_alerts(self, formatter):
        """format_alerts lists all alerts."""
        alerts = ["CDP health is critical", "Low balance"]

        response = formatter.format_alerts(alerts)

        assert "blocks" in response
        blocks = response["blocks"]
        assert blocks[0]["type"] == "header"
        assert "critical" in blocks[1]["text"]["text"]
        assert "Low balance" in blocks[1]["text"]["text"]

    def test_format_error(self, formatter):
        """format_error returns error message."""
        response = formatter.format_error("Something went wrong")

        assert "blocks" in response
        assert ":x:" in response["blocks"][0]["text"]["text"]
        assert "Something went wrong" in response["blocks"][0]["text"]["text"]
