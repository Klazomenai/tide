"""Tests for Slack command handlers."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from tide.faucet.service import FaucetRequestType, FaucetResult, FaucetStatus
from tide.slack.commands import _parse_distribution_args, register_commands


class TestParseDistributionArgs:
    """Tests for _parse_distribution_args helper."""

    def test_valid_address_only(self):
        """Parses address without amount."""
        address, amount, error = _parse_distribution_args(
            "0x1234567890123456789012345678901234567890"
        )

        assert address == "0x1234567890123456789012345678901234567890"
        assert amount is None
        assert error is None

    def test_valid_address_with_amount(self):
        """Parses address with amount."""
        address, amount, error = _parse_distribution_args(
            "0x1234567890123456789012345678901234567890 10"
        )

        assert address == "0x1234567890123456789012345678901234567890"
        assert amount == Decimal("10")
        assert error is None

    def test_valid_address_with_decimal_amount(self):
        """Parses address with decimal amount."""
        address, amount, error = _parse_distribution_args(
            "0x1234567890123456789012345678901234567890 1.5"
        )

        assert address == "0x1234567890123456789012345678901234567890"
        assert amount == Decimal("1.5")
        assert error is None

    def test_empty_text(self):
        """Returns error for empty text."""
        address, amount, error = _parse_distribution_args("")

        assert address is None
        assert amount is None
        assert "provide an address" in error

    def test_whitespace_only(self):
        """Returns error for whitespace only."""
        address, amount, error = _parse_distribution_args("   ")

        assert address is None
        assert error is not None

    def test_invalid_address_format(self):
        """Returns error for invalid address."""
        address, amount, error = _parse_distribution_args("0x123")

        assert address is None
        assert "Invalid" in error or "valid address" in error

    def test_invalid_address_non_hex(self):
        """Returns error for non-hex characters in address."""
        address, amount, error = _parse_distribution_args(
            "0xGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG"
        )

        assert address is None
        assert error is not None

    def test_negative_amount(self):
        """Returns error for negative amount."""
        # Negative amounts rejected because regex pattern only matches non-negative numbers
        address, amount, error = _parse_distribution_args(
            "0x1234567890123456789012345678901234567890 -10"
        )

        assert address is None
        assert error is not None


class TestRegisterCommands:
    """Tests for register_commands and command handlers."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock Slack app."""
        app = MagicMock()
        app.command = MagicMock(return_value=lambda f: f)
        return app

    @pytest.fixture
    def mock_faucet(self):
        """Create a mock FaucetService."""
        faucet = MagicMock()
        faucet.handle_atn_request = AsyncMock(
            return_value=FaucetResult(
                success=True,
                request_type=FaucetRequestType.ATN,
                tx_hash="0xtxhash",
                amount=Decimal("5"),
                message="Success",
                remaining_requests=9,
            )
        )
        faucet.handle_ntn_request = AsyncMock(
            return_value=FaucetResult(
                success=True,
                request_type=FaucetRequestType.NTN,
                tx_hash="0xtxhash",
                amount=Decimal("10"),
                message="Success",
                remaining_requests=9,
            )
        )
        faucet.get_status = AsyncMock(
            return_value=FaucetStatus(
                healthy=True,
                cdp_status=None,
                atn_available=Decimal("100"),
                ntn_available=Decimal("500"),
                message="Operational",
            )
        )
        faucet.get_user_status = AsyncMock(
            return_value={
                "remaining_requests": 9,
                "cooldown_seconds": 0,
                "max_atn": "5",
                "max_ntn": "50",
            }
        )
        return faucet

    def test_register_commands(self, mock_app, mock_faucet):
        """register_commands registers /tide command."""
        register_commands(mock_app, mock_faucet)

        mock_app.command.assert_called_once_with("/tide")

    @pytest.mark.asyncio
    async def test_handle_atn_command(self, mock_app, mock_faucet):
        """ATN command calls faucet service."""
        # Get the registered handler
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        # Simulate command
        ack = AsyncMock()
        respond = AsyncMock()
        command = {
            "user_id": "U123",
            "text": "atn 0x1234567890123456789012345678901234567890 5",
        }

        await handler(ack, command, respond)

        ack.assert_called_once()
        mock_faucet.handle_atn_request.assert_called_once_with(
            "U123", "0x1234567890123456789012345678901234567890", Decimal("5")
        )
        respond.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_ntn_command(self, mock_app, mock_faucet):
        """NTN command calls faucet service."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {
            "user_id": "U123",
            "text": "ntn 0x1234567890123456789012345678901234567890",
        }

        await handler(ack, command, respond)

        ack.assert_called_once()
        mock_faucet.handle_ntn_request.assert_called_once_with(
            "U123", "0x1234567890123456789012345678901234567890", None
        )

    @pytest.mark.asyncio
    async def test_handle_status_command(self, mock_app, mock_faucet):
        """Status command returns faucet status."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {"user_id": "U123", "text": "status"}

        await handler(ack, command, respond)

        ack.assert_called_once()
        mock_faucet.get_status.assert_called_once()
        mock_faucet.get_user_status.assert_called_once_with("U123")
        respond.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_alerts_command(self, mock_app, mock_faucet):
        """Alerts command returns active alerts."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {"user_id": "U123", "text": "alerts"}

        await handler(ack, command, respond)

        ack.assert_called_once()
        mock_faucet.get_status.assert_called_once()
        respond.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_help_command(self, mock_app, mock_faucet):
        """Help command returns help message."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {"user_id": "U123", "text": "help"}

        await handler(ack, command, respond)

        ack.assert_called_once()
        respond.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, mock_app, mock_faucet):
        """Unknown subcommand returns error."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {"user_id": "U123", "text": "unknown"}

        await handler(ack, command, respond)

        ack.assert_called_once()
        respond.assert_called_once()
        # Check error message was sent
        call_args = respond.call_args[0][0]
        assert "Unknown command" in str(call_args)

    @pytest.mark.asyncio
    async def test_handle_empty_command_shows_help(self, mock_app, mock_faucet):
        """Empty command shows help."""
        handler = None

        def capture_handler(cmd):
            def decorator(f):
                nonlocal handler
                handler = f
                return f

            return decorator

        mock_app.command = capture_handler
        register_commands(mock_app, mock_faucet)

        ack = AsyncMock()
        respond = AsyncMock()
        command = {"user_id": "U123", "text": ""}

        await handler(ack, command, respond)

        ack.assert_called_once()
        respond.assert_called_once()
