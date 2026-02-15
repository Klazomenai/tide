"""Tests for TIDE main entry point."""

import sys
from unittest.mock import patch

import pytest

from tide.main import generate_wallet, parse_args


class TestParseArgs:
    """Tests for argument parsing."""

    def test_no_args(self):
        """No arguments returns empty namespace."""
        with patch("sys.argv", ["tide"]):
            args = parse_args()
            assert args.generate_wallet is None

    def test_generate_wallet_arg(self):
        """--generate-wallet sets output path."""
        with patch("sys.argv", ["tide", "--generate-wallet", "/tmp/key.txt"]):
            args = parse_args()
            assert args.generate_wallet == "/tmp/key.txt"


class TestGenerateWallet:
    """Tests for wallet generation."""

    def test_generates_valid_key(self, tmp_path):
        """Generates a valid Ethereum private key."""
        key_file = tmp_path / "wallet.key"

        with patch("builtins.print"):  # Suppress output
            generate_wallet(str(key_file))

        assert key_file.exists()
        content = key_file.read_text()

        # Should be hex string (with or without 0x prefix)
        assert len(content) in (64, 66)  # 64 hex chars, or 66 with 0x
        if content.startswith("0x"):
            content = content[2:]
        assert all(c in "0123456789abcdef" for c in content)

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod not supported on Windows")
    def test_sets_restrictive_permissions(self, tmp_path):
        """Key file has 600 permissions."""
        key_file = tmp_path / "wallet.key"

        with patch("builtins.print"):
            generate_wallet(str(key_file))

        mode = key_file.stat().st_mode
        # Check owner read/write only (0o600)
        assert mode & 0o777 == 0o600

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories if needed."""
        key_file = tmp_path / "nested" / "path" / "wallet.key"

        with patch("builtins.print"):
            generate_wallet(str(key_file))

        assert key_file.exists()

    def test_prints_instructions(self, tmp_path, capsys):
        """Prints usage instructions."""
        key_file = tmp_path / "wallet.key"

        generate_wallet(str(key_file))

        output = capsys.readouterr().out
        assert "Wallet generated successfully" in output
        assert "Address:" in output
        assert "0x" in output  # Address starts with 0x
        assert "TIDE_WALLET_PRIVATE_KEY" in output
        assert "kubectl create secret" in output

    def test_key_loads_with_eth_account(self, tmp_path):
        """Generated key can be loaded by eth_account."""
        from eth_account import Account

        key_file = tmp_path / "wallet.key"

        with patch("builtins.print"):
            generate_wallet(str(key_file))

        content = key_file.read_text().strip()
        account = Account.from_key(content)

        # Should derive a valid address
        assert account.address.startswith("0x")
        assert len(account.address) == 42

    def test_key_works_with_environment_wallet(self, tmp_path):
        """Generated key works with EnvironmentWallet."""
        from tide.core.wallet import EnvironmentWallet

        key_file = tmp_path / "wallet.key"

        with patch("builtins.print"):
            generate_wallet(str(key_file))

        wallet = EnvironmentWallet(private_key_file=str(key_file))
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42
