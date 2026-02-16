"""Tests for wallet provider module."""

import tempfile
from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.constants import TEST_ADDRESS, TEST_PRIVATE_KEY
from tide.core.wallet import EnvironmentWallet, WalletProvider


class TestWalletProvider:
    """Tests for WalletProvider abstract class."""

    def test_wallet_provider_is_abstract(self):
        """WalletProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            WalletProvider()  # type: ignore


class TestEnvironmentWallet:
    """Tests for EnvironmentWallet."""

    def test_load_from_secret_str(self):
        """Load wallet from SecretStr (simulating env var)."""
        wallet = EnvironmentWallet(private_key=SecretStr(TEST_PRIVATE_KEY))

        assert wallet.address == TEST_ADDRESS
        assert wallet.get_account().address == TEST_ADDRESS

    def test_load_from_file(self):
        """Load wallet from key file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write(TEST_PRIVATE_KEY)
            key_file = f.name

        try:
            wallet = EnvironmentWallet(private_key_file=key_file)
            assert wallet.address == TEST_ADDRESS
        finally:
            Path(key_file).unlink()

    def test_load_from_file_with_whitespace(self):
        """Key file with trailing whitespace should work."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write(f"{TEST_PRIVATE_KEY}\n  \n")
            key_file = f.name

        try:
            wallet = EnvironmentWallet(private_key_file=key_file)
            assert wallet.address == TEST_ADDRESS
        finally:
            Path(key_file).unlink()

    def test_missing_key_raises_error(self):
        """Neither key nor file provided should raise ValueError."""
        with pytest.raises(ValueError, match="Either private_key or private_key_file"):
            EnvironmentWallet()

    def test_missing_file_raises_error(self):
        """Non-existent key file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Private key file not found"):
            EnvironmentWallet(private_key_file="/nonexistent/path/key.txt")

    def test_private_key_takes_precedence(self):
        """If both provided, private_key takes precedence over file."""
        # Create a file with a different key
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
            key_file = f.name

        try:
            wallet = EnvironmentWallet(
                private_key=SecretStr(TEST_PRIVATE_KEY),
                private_key_file=key_file,
            )
            # Should use the SecretStr key, not the file
            assert wallet.address == TEST_ADDRESS
        finally:
            Path(key_file).unlink()

    def test_address_property(self):
        """Address property returns checksummed address."""
        wallet = EnvironmentWallet(private_key=SecretStr(TEST_PRIVATE_KEY))

        # Address should be checksummed (mixed case)
        assert wallet.address.startswith("0x")
        assert any(c.isupper() for c in wallet.address[2:])

    def test_account_can_sign(self):
        """Account should be able to sign messages."""
        wallet = EnvironmentWallet(private_key=SecretStr(TEST_PRIVATE_KEY))
        account = wallet.get_account()

        # Account should have sign_message method
        assert hasattr(account, "sign_message")
        assert hasattr(account, "sign_transaction")
