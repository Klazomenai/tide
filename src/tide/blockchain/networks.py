"""Network configuration for TIDE.

Network-specific values come from Helm/environment variables.
No hardcoded network definitions - all configuration is external.
"""

from dataclasses import dataclass


@dataclass
class NetworkInfo:
    """Network information derived from runtime config.

    All values are discovered from the RPC endpoint or provided
    via environment variables. No hardcoded networks.

    Attributes
    ----------
    rpc_endpoint : str
        The RPC endpoint URL.
    chain_id : int
        The chain ID (discovered from RPC).
    block_explorer_url : str | None
        Optional block explorer URL for transaction links.
    """

    rpc_endpoint: str
    chain_id: int
    block_explorer_url: str | None = None

    def get_tx_url(self, tx_hash: str) -> str | None:
        """Get the block explorer URL for a transaction.

        Parameters
        ----------
        tx_hash : str
            The transaction hash.

        Returns
        -------
        str | None
            The block explorer URL, or None if no explorer configured.
        """
        if self.block_explorer_url:
            return f"{self.block_explorer_url.rstrip('/')}/tx/{tx_hash}"
        return None

    def get_address_url(self, address: str) -> str | None:
        """Get the block explorer URL for an address.

        Parameters
        ----------
        address : str
            The address.

        Returns
        -------
        str | None
            The block explorer URL, or None if no explorer configured.
        """
        if self.block_explorer_url:
            return f"{self.block_explorer_url.rstrip('/')}/address/{address}"
        return None
