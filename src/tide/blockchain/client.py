"""Autonity client wrapper for TIDE operations."""

import logging
from decimal import Decimal

from autonity import Autonity
from web3 import Web3
from web3.types import TxReceipt

from tide.core.wallet import WalletProvider

logger = logging.getLogger(__name__)


class AutonityClient:
    """Wrapper around autonity.py for TIDE faucet operations.

    Parameters
    ----------
    rpc_endpoint : str
        The Autonity RPC endpoint URL.
    wallet : WalletProvider
        The wallet provider for signing transactions.
    """

    def __init__(self, rpc_endpoint: str, wallet: WalletProvider):
        self._w3 = Web3(Web3.HTTPProvider(rpc_endpoint))
        self._wallet = wallet
        self._autonity = Autonity(self._w3)

    @property
    def connected(self) -> bool:
        """Check if connected to the RPC endpoint.

        Returns
        -------
        bool
            True if connected, False otherwise.
        """
        return self._w3.is_connected()

    @property
    def chain_id(self) -> int:
        """Get the chain ID from the connected network.

        Returns
        -------
        int
            The chain ID.
        """
        return self._w3.eth.chain_id

    @property
    def wallet_address(self) -> str:
        """Get the faucet wallet address.

        Returns
        -------
        str
            The checksummed wallet address.
        """
        return self._wallet.address

    def get_atn_balance(self, address: str) -> Decimal:
        """Get ATN (native coin) balance.

        Parameters
        ----------
        address : str
            The address to query.

        Returns
        -------
        Decimal
            Balance in ATN (ether units).
        """
        checksum_address = Web3.to_checksum_address(address)
        wei = self._w3.eth.get_balance(checksum_address)
        return Decimal(str(self._w3.from_wei(wei, "ether")))

    def get_ntn_balance(self, address: str) -> Decimal:
        """Get NTN (Newton token) balance.

        Parameters
        ----------
        address : str
            The address to query.

        Returns
        -------
        Decimal
            Balance in NTN (ether units).
        """
        checksum_address = Web3.to_checksum_address(address)
        balance = self._autonity.balance_of(checksum_address)
        return Decimal(str(self._w3.from_wei(balance, "ether")))

    def transfer_atn(self, to: str, amount: Decimal) -> str:
        """Transfer ATN (native coin) to an address.

        Parameters
        ----------
        to : str
            The recipient address.
        amount : Decimal
            Amount to transfer in ATN (ether units).

        Returns
        -------
        str
            The transaction hash.
        """
        checksum_to = Web3.to_checksum_address(to)
        value_wei = self._w3.to_wei(amount, "ether")

        tx = {
            "to": checksum_to,
            "value": value_wei,
            "gas": 21000,
            "gasPrice": self._w3.eth.gas_price,
            "nonce": self._w3.eth.get_transaction_count(self._wallet.address),
            "chainId": self._w3.eth.chain_id,
        }

        signed = self._wallet.get_account().sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(
            "ATN transfer submitted",
            extra={
                "tx_hash": tx_hash.hex(),
                "to": checksum_to,
                "amount": str(amount),
            },
        )

        return tx_hash.hex()

    def transfer_ntn(self, to: str, amount: Decimal) -> str:
        """Transfer NTN (Newton token) to an address.

        Parameters
        ----------
        to : str
            The recipient address.
        amount : Decimal
            Amount to transfer in NTN (ether units).

        Returns
        -------
        str
            The transaction hash.
        """
        checksum_to = Web3.to_checksum_address(to)
        amount_wei = self._w3.to_wei(amount, "ether")

        # Build transfer transaction from Autonity contract
        tx = self._autonity.transfer(checksum_to, amount_wei).build_transaction(
            {
                "from": self._wallet.address,
                "gas": 100000,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(self._wallet.address),
                "chainId": self._w3.eth.chain_id,
            }
        )

        signed = self._wallet.get_account().sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(
            "NTN transfer submitted",
            extra={
                "tx_hash": tx_hash.hex(),
                "to": checksum_to,
                "amount": str(amount),
            },
        )

        return tx_hash.hex()

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> TxReceipt:
        """Wait for a transaction receipt.

        Parameters
        ----------
        tx_hash : str
            The transaction hash to wait for.
        timeout : int, optional
            Maximum time to wait in seconds. Default is 120.

        Returns
        -------
        TxReceipt
            The transaction receipt.

        Raises
        ------
        TimeoutError
            If the transaction is not mined within the timeout.
        """
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def get_faucet_balances(self) -> dict[str, Decimal]:
        """Get the faucet wallet balances.

        Returns
        -------
        dict[str, Decimal]
            Dictionary with 'atn' and 'ntn' balances.
        """
        return {
            "atn": self.get_atn_balance(self._wallet.address),
            "ntn": self.get_ntn_balance(self._wallet.address),
        }
