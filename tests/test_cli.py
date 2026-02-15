"""Tests for CLI subcommands."""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tide.cli import (
    CLIContext,
    cmd_cdp_borrow,
    cmd_cdp_deposit,
    cmd_cdp_repay,
    cmd_cdp_status,
    cmd_cdp_withdraw,
    cmd_faucet_atn,
    cmd_faucet_ntn,
    cmd_wallet_address,
    cmd_wallet_balance,
    create_parser,
    run_cli,
)
from tide.config import TideConfig
from tide.core.cdp import CDPHealth, CDPStatus


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_has_subcommands(self):
        """Parser has wallet, cdp, faucet, run subcommands."""
        parser = create_parser()
        # Parse with no args to check structure
        args = parser.parse_args(["wallet", "address"])
        assert args.command == "wallet"
        assert args.wallet_command == "address"

    def test_wallet_subcommands(self):
        """Wallet has address and balance subcommands."""
        parser = create_parser()

        args = parser.parse_args(["wallet", "address"])
        assert args.wallet_command == "address"

        args = parser.parse_args(["wallet", "balance"])
        assert args.wallet_command == "balance"

    def test_cdp_subcommands(self):
        """CDP has status, deposit, withdraw, borrow, repay subcommands."""
        parser = create_parser()

        args = parser.parse_args(["cdp", "status"])
        assert args.cdp_command == "status"

        args = parser.parse_args(["cdp", "deposit", "100"])
        assert args.cdp_command == "deposit"
        assert args.amount == "100"

        args = parser.parse_args(["cdp", "withdraw", "50"])
        assert args.cdp_command == "withdraw"
        assert args.amount == "50"

        args = parser.parse_args(["cdp", "borrow", "25"])
        assert args.cdp_command == "borrow"
        assert args.amount == "25"

        args = parser.parse_args(["cdp", "repay", "10"])
        assert args.cdp_command == "repay"
        assert args.amount == "10"

    def test_faucet_subcommands(self):
        """Faucet has status, atn, ntn subcommands."""
        parser = create_parser()

        args = parser.parse_args(["faucet", "status"])
        assert args.faucet_command == "status"

        args = parser.parse_args(["faucet", "atn", "0x1234567890123456789012345678901234567890"])
        assert args.faucet_command == "atn"
        assert args.address == "0x1234567890123456789012345678901234567890"
        assert args.amount == "1"  # Default

        args = parser.parse_args(
            ["faucet", "ntn", "0x1234567890123456789012345678901234567890", "5"]
        )
        assert args.faucet_command == "ntn"
        assert args.amount == "5"

    def test_global_flags(self):
        """Parser accepts --json and --dry-run flags."""
        parser = create_parser()

        args = parser.parse_args(["--json", "wallet", "address"])
        assert args.json is True

        args = parser.parse_args(["--dry-run", "cdp", "deposit", "100"])
        assert args.dry_run is True

    def test_generate_wallet_flag(self):
        """Parser accepts --generate-wallet for backwards compatibility."""
        parser = create_parser()

        args = parser.parse_args(["--generate-wallet", "/tmp/key.txt"])
        assert args.generate_wallet == "/tmp/key.txt"


class TestCLIContext:
    """Tests for CLI context."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock(spec=TideConfig)
        config.rpc_endpoint = "https://rpc.example.com"
        config.wallet_private_key = None
        config.wallet_private_key_file = None
        config.cdp_target_cr = 2.5
        config.cdp_min_cr = 2.2
        config.cdp_max_cr = 3.0
        return config

    def test_context_stores_config(self, mock_config):
        """Context stores config and flags."""
        ctx = CLIContext(mock_config, dry_run=True, json_output=True)
        assert ctx.config == mock_config
        assert ctx.dry_run is True
        assert ctx.json_output is True

    def test_wallet_raises_without_key(self, mock_config):
        """Wallet property raises if no key configured."""
        ctx = CLIContext(mock_config)
        with pytest.raises(ValueError, match="No wallet configured"):
            _ = ctx.wallet

    def test_output_json(self, mock_config, capsys):
        """Output in JSON format."""
        ctx = CLIContext(mock_config, json_output=True)
        ctx.output({"foo": "bar", "num": Decimal("123.456")})

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["foo"] == "bar"
        assert data["num"] == "123.456"

    def test_output_text(self, mock_config, capsys):
        """Output in text format."""
        ctx = CLIContext(mock_config, json_output=False)
        ctx.output({"address": "0x123", "balance": "100"})

        captured = capsys.readouterr()
        assert "address: 0x123" in captured.out
        assert "balance: 100" in captured.out


class TestWalletCommands:
    """Tests for wallet commands."""

    @pytest.fixture
    def mock_ctx(self):
        """Create mock context with wallet."""
        config = MagicMock(spec=TideConfig)
        config.rpc_endpoint = "https://rpc.example.com"
        ctx = CLIContext(config)
        ctx._wallet = MagicMock()
        ctx._wallet.address = "0xABCD1234567890ABCD1234567890ABCD12345678"
        ctx._client = MagicMock()
        ctx._client.connected = True
        ctx._client.chain_id = 65100000
        ctx._client.get_faucet_balances.return_value = {
            "atn": Decimal("100.5"),
            "ntn": Decimal("200.25"),
        }
        return ctx

    def test_wallet_address(self, mock_ctx, capsys):
        """wallet address shows address."""
        result = cmd_wallet_address(mock_ctx)
        assert result == 0

        captured = capsys.readouterr()
        assert "0xABCD1234567890ABCD1234567890ABCD12345678" in captured.out

    def test_wallet_balance(self, mock_ctx, capsys):
        """wallet balance shows ATN and NTN."""
        result = cmd_wallet_balance(mock_ctx)
        assert result == 0

        captured = capsys.readouterr()
        assert "100.5" in captured.out
        assert "200.25" in captured.out

    def test_wallet_balance_not_connected(self, mock_ctx, capsys):
        """wallet balance fails if not connected."""
        mock_ctx._client.connected = False
        result = cmd_wallet_balance(mock_ctx)
        assert result == 1

        captured = capsys.readouterr()
        assert "Not connected" in captured.out


class TestCDPCommands:
    """Tests for CDP commands."""

    @pytest.fixture
    def mock_ctx(self):
        """Create mock context with CDP manager."""
        config = MagicMock(spec=TideConfig)
        config.rpc_endpoint = "https://rpc.example.com"
        ctx = CLIContext(config)
        ctx._wallet = MagicMock()
        ctx._client = MagicMock()
        ctx._client.connected = True
        ctx._cdp_manager = MagicMock()
        return ctx

    def test_cdp_status(self, mock_ctx, capsys):
        """cdp status shows CDP info."""
        mock_ctx._cdp_manager.get_status.return_value = CDPStatus(
            exists=True,
            collateral=Decimal("1000"),
            debt=Decimal("400"),
            collateralization_ratio=Decimal("250"),
            health=CDPHealth.HEALTHY,
            is_liquidatable=False,
            max_borrowable=Decimal("100"),
            min_collateral_required=Decimal("720"),
        )

        result = cmd_cdp_status(mock_ctx)
        assert result == 0

        captured = capsys.readouterr()
        assert "1000" in captured.out
        assert "400" in captured.out
        assert "healthy" in captured.out

    def test_cdp_deposit_dry_run(self, mock_ctx, capsys):
        """cdp deposit with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_cdp_deposit(mock_ctx, "100")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        assert "100" in captured.out
        mock_ctx._cdp_manager.deposit.assert_not_called()

    def test_cdp_deposit_executes(self, mock_ctx, capsys):
        """cdp deposit executes transaction."""
        mock_ctx.dry_run = False
        mock_ctx._cdp_manager.deposit.return_value = "0xabc123"

        result = cmd_cdp_deposit(mock_ctx, "100")
        assert result == 0

        mock_ctx._cdp_manager.deposit.assert_called_once_with(Decimal("100"))
        captured = capsys.readouterr()
        assert "0xabc123" in captured.out

    def test_cdp_withdraw_dry_run(self, mock_ctx, capsys):
        """cdp withdraw with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_cdp_withdraw(mock_ctx, "50")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        mock_ctx._cdp_manager.withdraw.assert_not_called()

    def test_cdp_borrow_dry_run(self, mock_ctx, capsys):
        """cdp borrow with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_cdp_borrow(mock_ctx, "25")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        mock_ctx._cdp_manager.borrow.assert_not_called()

    def test_cdp_repay_dry_run(self, mock_ctx, capsys):
        """cdp repay with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_cdp_repay(mock_ctx, "10")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        mock_ctx._cdp_manager.repay.assert_not_called()

    def test_cdp_deposit_invalid_amount(self, mock_ctx, capsys):
        """cdp deposit with invalid amount."""
        result = cmd_cdp_deposit(mock_ctx, "not-a-number")
        assert result == 1

        captured = capsys.readouterr()
        assert "Invalid amount" in captured.out

    def test_cdp_deposit_zero_amount(self, mock_ctx, capsys):
        """cdp deposit with zero amount."""
        result = cmd_cdp_deposit(mock_ctx, "0")
        assert result == 1

        captured = capsys.readouterr()
        assert "must be positive" in captured.out


class TestFaucetCommands:
    """Tests for faucet commands."""

    @pytest.fixture
    def mock_ctx(self):
        """Create mock context with client."""
        config = MagicMock(spec=TideConfig)
        config.rpc_endpoint = "https://rpc.example.com"
        ctx = CLIContext(config)
        ctx._wallet = MagicMock()
        ctx._wallet.address = "0xFaucet"
        ctx._client = MagicMock()
        ctx._client.connected = True
        ctx._client.chain_id = 65100000
        ctx._client.get_faucet_balances.return_value = {
            "atn": Decimal("1000"),
            "ntn": Decimal("5000"),
        }
        return ctx

    def test_faucet_atn_dry_run(self, mock_ctx, capsys):
        """faucet atn with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_faucet_atn(mock_ctx, "0x1234", "5")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        assert "0x1234" in captured.out
        mock_ctx._client.transfer_atn.assert_not_called()

    def test_faucet_atn_executes(self, mock_ctx, capsys):
        """faucet atn executes transfer."""
        mock_ctx.dry_run = False
        mock_ctx._client.transfer_atn.return_value = "0xdef456"

        result = cmd_faucet_atn(mock_ctx, "0x1234", "5")
        assert result == 0

        mock_ctx._client.transfer_atn.assert_called_once_with("0x1234", Decimal("5"))
        captured = capsys.readouterr()
        assert "0xdef456" in captured.out

    def test_faucet_ntn_dry_run(self, mock_ctx, capsys):
        """faucet ntn with --dry-run."""
        mock_ctx.dry_run = True
        result = cmd_faucet_ntn(mock_ctx, "0x5678", "10")
        assert result == 0

        captured = capsys.readouterr()
        assert "dry_run" in captured.out
        mock_ctx._client.transfer_ntn.assert_not_called()

    def test_faucet_ntn_executes(self, mock_ctx, capsys):
        """faucet ntn executes transfer."""
        mock_ctx.dry_run = False
        mock_ctx._client.transfer_ntn.return_value = "0xghi789"

        result = cmd_faucet_ntn(mock_ctx, "0x5678", "10")
        assert result == 0

        mock_ctx._client.transfer_ntn.assert_called_once_with("0x5678", Decimal("10"))


class TestRunCLI:
    """Tests for run_cli function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock(spec=TideConfig)
        config.rpc_endpoint = "https://rpc.example.com"
        config.wallet_private_key = None
        config.wallet_private_key_file = "/tmp/test-key"
        config.cdp_target_cr = 2.5
        config.cdp_min_cr = 2.2
        config.cdp_max_cr = 3.0
        return config

    def test_run_cli_wallet_address(self, mock_config):
        """run_cli routes to wallet address."""
        parser = create_parser()
        args = parser.parse_args(["wallet", "address"])

        with (
            patch("tide.cli.TideConfig", return_value=mock_config),
            patch("tide.cli.EnvironmentWallet") as mock_wallet_cls,
        ):
            mock_wallet = MagicMock()
            mock_wallet.address = "0xTest"
            mock_wallet_cls.return_value = mock_wallet

            result = run_cli(args)
            assert result == 0

    def test_run_cli_unknown_command(self, mock_config, capsys):
        """run_cli returns error for unknown subcommand."""
        parser = create_parser()
        args = parser.parse_args(["wallet"])
        args.wallet_command = None  # Simulate missing subcommand

        with patch("tide.cli.TideConfig", return_value=mock_config):
            result = run_cli(args)
            assert result == 1

            captured = capsys.readouterr()
            assert "Usage:" in captured.err
