"""Wallet provider abstraction for signing transactions."""

from abc import ABC, abstractmethod
from pathlib import Path

from eth_account import Account
from eth_account.signers.local import LocalAccount
from pydantic import SecretStr


class WalletProvider(ABC):
    """Abstract wallet provider for signing transactions."""

    @abstractmethod
    def get_account(self) -> LocalAccount:
        """Get the wallet account for signing.

        Returns
        -------
        LocalAccount
            The account instance for transaction signing.
        """
        ...

    @property
    def address(self) -> str:
        """Get the wallet address.

        Returns
        -------
        str
            The checksummed wallet address.
        """
        return self.get_account().address


class EnvironmentWallet(WalletProvider):
    """Load private key from environment variable or file.

    Parameters
    ----------
    private_key : SecretStr, optional
        The private key as a SecretStr (from env var).
    private_key_file : str, optional
        Path to a file containing the private key.

    Raises
    ------
    ValueError
        If neither private_key nor private_key_file is provided.
    FileNotFoundError
        If private_key_file does not exist.
    """

    def __init__(
        self,
        private_key: SecretStr | None = None,
        private_key_file: str | None = None,
    ):
        if private_key is not None:
            self._account = Account.from_key(private_key.get_secret_value())
        elif private_key_file is not None:
            # Expand ~ to user home directory
            key_path = Path(private_key_file).expanduser()
            if not key_path.exists():
                raise FileNotFoundError(f"Private key file not found: {private_key_file}")
            key_content = key_path.read_text().strip()
            self._account = Account.from_key(key_content)
        else:
            raise ValueError("Either private_key or private_key_file must be provided")

    def get_account(self) -> LocalAccount:
        """Get the wallet account for signing.

        Returns
        -------
        LocalAccount
            The account instance for transaction signing.
        """
        return self._account
