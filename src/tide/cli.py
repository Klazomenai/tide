"""CLI subcommands for TIDE testing and operations.

Provides command-line interface for:
- Wallet operations (address, balance)
- CDP operations (status, deposit, withdraw, borrow, repay)
- Faucet operations (atn, ntn, status)
- Governance operations (cdp-status, get-supply-operator, set-supply-operator)
"""

import argparse
import json
import os
import sys
from decimal import Decimal, InvalidOperation

from web3 import Web3

from tide.blockchain.client import AutonityClient
from tide.config import TideConfig
from tide.core.cdp import CDPManager
from tide.core.wallet import EnvironmentWallet

# Error selector for Stabilization contract's Unauthorized error
UNAUTHORIZED_ERROR_SELECTOR = "82b42900"

# Test address for simulating contract calls to detect restrictions
RESTRICTION_TEST_ADDRESS = "0x0000000000000000000000000000000000000001"


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="tide",
        description="TIDE - Token Issuance for Developer Environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without executing",
    )

    # Legacy flags (for backwards compatibility)
    parser.add_argument(
        "--generate-wallet",
        metavar="FILE",
        help="Generate a new wallet and save private key to FILE, then exit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Wallet subcommand
    wallet_parser = subparsers.add_parser("wallet", help="Wallet operations")
    wallet_sub = wallet_parser.add_subparsers(dest="wallet_command")

    wallet_sub.add_parser("address", help="Show wallet address")
    wallet_sub.add_parser("balance", help="Show wallet ATN and NTN balances")

    # CDP subcommand
    cdp_parser = subparsers.add_parser("cdp", help="CDP operations")
    cdp_sub = cdp_parser.add_subparsers(dest="cdp_command")

    cdp_sub.add_parser("status", help="Show CDP status")

    deposit_parser = cdp_sub.add_parser("deposit", help="Deposit NTN collateral")
    deposit_parser.add_argument("amount", type=str, help="Amount of NTN to deposit")

    withdraw_parser = cdp_sub.add_parser("withdraw", help="Withdraw NTN collateral")
    withdraw_parser.add_argument("amount", type=str, help="Amount of NTN to withdraw")

    borrow_parser = cdp_sub.add_parser("borrow", help="Borrow ATN against collateral")
    borrow_parser.add_argument("amount", type=str, help="Amount of ATN to borrow")

    repay_parser = cdp_sub.add_parser("repay", help="Repay ATN debt")
    repay_parser.add_argument("amount", type=str, help="Amount of ATN to repay")

    # Faucet subcommand
    faucet_parser = subparsers.add_parser("faucet", help="Faucet operations")
    faucet_sub = faucet_parser.add_subparsers(dest="faucet_command")

    faucet_sub.add_parser("status", help="Show faucet wallet balances")

    atn_parser = faucet_sub.add_parser("atn", help="Send ATN to address")
    atn_parser.add_argument("address", type=str, help="Recipient address")
    atn_parser.add_argument("amount", type=str, nargs="?", default="1", help="Amount (default: 1)")

    ntn_parser = faucet_sub.add_parser("ntn", help="Send NTN to address")
    ntn_parser.add_argument("address", type=str, help="Recipient address")
    ntn_parser.add_argument("amount", type=str, nargs="?", default="1", help="Amount (default: 1)")

    # Run subcommand (start service)
    subparsers.add_parser("run", help="Start the TIDE service")

    # Governance subcommand
    gov_parser = subparsers.add_parser("governance", help="Governance operations")
    gov_sub = gov_parser.add_subparsers(dest="gov_command")

    gov_sub.add_parser("cdp-status", help="Show CDP restriction status")
    gov_sub.add_parser("get-supply-operator", help="Get current ATN supply operator")

    set_op_parser = gov_sub.add_parser("set-supply-operator", help="Set ATN supply operator")
    set_op_parser.add_argument("address", type=str, help="New supply operator address")

    return parser


class CLIContext:
    """Shared context for CLI commands."""

    def __init__(self, config: TideConfig, dry_run: bool = False, json_output: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.json_output = json_output
        self._wallet: EnvironmentWallet | None = None
        self._governance_wallet: EnvironmentWallet | None = None
        self._client: AutonityClient | None = None
        self._cdp_manager: CDPManager | None = None
        self._w3: Web3 | None = None

    @property
    def wallet(self) -> EnvironmentWallet:
        """Get wallet (lazy loaded)."""
        if self._wallet is None:
            if self.config.wallet_private_key:
                self._wallet = EnvironmentWallet(private_key=self.config.wallet_private_key)
            elif self.config.wallet_private_key_file:
                self._wallet = EnvironmentWallet(
                    private_key_file=self.config.wallet_private_key_file
                )
            else:
                raise ValueError(
                    "No wallet configured. "
                    "Set TIDE_WALLET_PRIVATE_KEY or TIDE_WALLET_PRIVATE_KEY_FILE"
                )
        return self._wallet

    @property
    def governance_wallet(self) -> EnvironmentWallet:
        """Get governance wallet (lazy loaded, separate from faucet wallet).

        Loads from TIDE_GOVERNANCE_PRIVATE_KEY or TIDE_GOVERNANCE_PRIVATE_KEY_FILE.
        """
        if self._governance_wallet is None:
            from pydantic import SecretStr

            gov_key = os.environ.get("TIDE_GOVERNANCE_PRIVATE_KEY")
            gov_key_file = os.environ.get("TIDE_GOVERNANCE_PRIVATE_KEY_FILE")
            if gov_key:
                self._governance_wallet = EnvironmentWallet(private_key=SecretStr(gov_key))
            elif gov_key_file:
                self._governance_wallet = EnvironmentWallet(private_key_file=gov_key_file)
            else:
                raise ValueError(
                    "No governance wallet configured. "
                    "Set TIDE_GOVERNANCE_PRIVATE_KEY or TIDE_GOVERNANCE_PRIVATE_KEY_FILE"
                )
        return self._governance_wallet

    @property
    def w3(self) -> Web3:
        """Get Web3 instance (lazy loaded)."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(self.config.rpc_endpoint))
        return self._w3

    @property
    def client(self) -> AutonityClient:
        """Get Autonity client (lazy loaded)."""
        if self._client is None:
            self._client = AutonityClient(self.config.rpc_endpoint, self.wallet)
        return self._client

    @property
    def cdp_manager(self) -> CDPManager:
        """Get CDP manager (lazy loaded)."""
        if self._cdp_manager is None:
            from web3 import Web3

            w3 = Web3(Web3.HTTPProvider(self.config.rpc_endpoint))
            self._cdp_manager = CDPManager(
                w3,
                self.wallet,
                target_cr=Decimal(str(self.config.cdp_target_cr)),
                min_cr=Decimal(str(self.config.cdp_min_cr)),
                max_cr=Decimal(str(self.config.cdp_max_cr)),
            )
        return self._cdp_manager

    def output(self, data: dict) -> None:
        """Output data in the appropriate format."""
        if self.json_output:
            # Convert Decimal to string for JSON serialization
            def decimal_default(obj):
                if isinstance(obj, Decimal):
                    return str(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            print(json.dumps(data, default=decimal_default, indent=2))
        else:
            self._print_formatted(data)

    def _print_formatted(self, data: dict, indent: int = 0) -> None:
        """Print data in human-readable format."""
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"{prefix}{key}:")
                self._print_formatted(value, indent + 1)
            else:
                print(f"{prefix}{key}: {value}")


# Wallet commands


def cmd_wallet_address(ctx: CLIContext) -> int:
    """Show wallet address."""
    try:
        address = ctx.wallet.address
        ctx.output({"address": address})
        return 0
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_wallet_balance(ctx: CLIContext) -> int:
    """Show wallet balances."""
    try:
        if not ctx.client.connected:
            ctx.output({"error": "Not connected to RPC endpoint"})
            return 1

        balances = ctx.client.get_faucet_balances()
        ctx.output(
            {
                "address": ctx.wallet.address,
                "atn": balances["atn"],
                "ntn": balances["ntn"],
                "rpc": ctx.config.rpc_endpoint,
                "chain_id": ctx.client.chain_id,
            }
        )
        return 0
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


# CDP commands


def cmd_cdp_status(ctx: CLIContext) -> int:
    """Show CDP status."""
    try:
        if not ctx.client.connected:
            ctx.output({"error": "Not connected to RPC endpoint"})
            return 1

        status = ctx.cdp_manager.get_status()
        ctx.output(
            {
                "exists": status.exists,
                "collateral_ntn": status.collateral,
                "debt_atn": status.debt,
                "collateralization_ratio": status.collateralization_ratio,
                "health": status.health.value,
                "is_liquidatable": status.is_liquidatable,
                "max_borrowable_atn": status.max_borrowable,
                "min_collateral_required_ntn": status.min_collateral_required,
            }
        )
        return 0
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_cdp_deposit(ctx: CLIContext, amount_str: str) -> int:
    """Deposit NTN collateral."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "deposit",
                    "amount_ntn": amount,
                    "message": f"Would deposit {amount} NTN as collateral",
                }
            )
            return 0

        tx_hash = ctx.cdp_manager.deposit(amount)
        ctx.output(
            {
                "success": True,
                "action": "deposit",
                "amount_ntn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_cdp_withdraw(ctx: CLIContext, amount_str: str) -> int:
    """Withdraw NTN collateral."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "withdraw",
                    "amount_ntn": amount,
                    "message": f"Would withdraw {amount} NTN collateral",
                }
            )
            return 0

        tx_hash = ctx.cdp_manager.withdraw(amount)
        ctx.output(
            {
                "success": True,
                "action": "withdraw",
                "amount_ntn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_cdp_borrow(ctx: CLIContext, amount_str: str) -> int:
    """Borrow ATN against collateral."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "borrow",
                    "amount_atn": amount,
                    "message": f"Would borrow {amount} ATN against collateral",
                }
            )
            return 0

        tx_hash = ctx.cdp_manager.borrow(amount)
        ctx.output(
            {
                "success": True,
                "action": "borrow",
                "amount_atn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_cdp_repay(ctx: CLIContext, amount_str: str) -> int:
    """Repay ATN debt."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "repay",
                    "amount_atn": amount,
                    "message": f"Would repay {amount} ATN debt",
                }
            )
            return 0

        tx_hash = ctx.cdp_manager.repay(amount)
        ctx.output(
            {
                "success": True,
                "action": "repay",
                "amount_atn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


# Faucet commands


def cmd_faucet_status(ctx: CLIContext) -> int:
    """Show faucet wallet balances."""
    # Same as wallet balance for now
    return cmd_wallet_balance(ctx)


def cmd_faucet_atn(ctx: CLIContext, address: str, amount_str: str) -> int:
    """Send ATN to address."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "transfer_atn",
                    "to": address,
                    "amount_atn": amount,
                    "message": f"Would send {amount} ATN to {address}",
                }
            )
            return 0

        tx_hash = ctx.client.transfer_atn(address, amount)
        ctx.output(
            {
                "success": True,
                "action": "transfer_atn",
                "to": address,
                "amount_atn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_faucet_ntn(ctx: CLIContext, address: str, amount_str: str) -> int:
    """Send NTN to address."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            ctx.output({"error": "Amount must be positive"})
            return 1

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "transfer_ntn",
                    "to": address,
                    "amount_ntn": amount,
                    "message": f"Would send {amount} NTN to {address}",
                }
            )
            return 0

        tx_hash = ctx.client.transfer_ntn(address, amount)
        ctx.output(
            {
                "success": True,
                "action": "transfer_ntn",
                "to": address,
                "amount_ntn": amount,
                "tx_hash": tx_hash,
            }
        )
        return 0
    except InvalidOperation:
        ctx.output({"error": f"Invalid amount: {amount_str}"})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


# Governance commands


def cmd_gov_cdp_status(ctx: CLIContext) -> int:
    """Show CDP restriction status."""
    try:
        from autonity import Stabilization

        stab = Stabilization(ctx.w3)
        config = stab.config()

        # Detect restricted state by simulating a deposit call
        # If we get Unauthorized (0x82b42900), it's restricted
        restricted = False
        try:
            stab.deposit(1).call({"from": RESTRICTION_TEST_ADDRESS})
        except Exception as e:
            if UNAUTHORIZED_ERROR_SELECTOR in str(e):
                restricted = True

        # Get CDP accounts - addresses with active CDPs
        cdp_accounts = stab.accounts()
        if not cdp_accounts:
            cdp_accounts = []

        ctx.output(
            {
                "restricted": restricted,
                "borrow_interest_rate": str(config.borrow_interest_rate),
                "liquidation_ratio": str(Decimal(str(config.liquidation_ratio)) / Decimal("1e18")),
                "min_collateralization_ratio": str(
                    Decimal(str(config.min_collateralization_ratio)) / Decimal("1e18")
                ),
                "cdp_accounts": cdp_accounts,
                "rpc": ctx.config.rpc_endpoint,
                "chain_id": ctx.w3.eth.chain_id,
            }
        )
        return 0
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_gov_get_supply_operator(ctx: CLIContext) -> int:
    """Get current ATN supply operator.

    Note: The _atnSupplyOperator is a private variable in the contract.
    We detect if restrictions are active and who can perform operations.
    """
    try:
        from autonity import Stabilization

        stab = Stabilization(ctx.w3)

        # Get CDP account holders
        accounts = stab.accounts()

        # Detect if restricted
        restricted = False
        try:
            stab.deposit(1).call({"from": RESTRICTION_TEST_ADDRESS})
        except Exception as e:
            if UNAUTHORIZED_ERROR_SELECTOR in str(e):
                restricted = True

        ctx.output(
            {
                "restricted": restricted,
                "cdp_accounts": accounts if accounts else [],
                "note": "Supply operator is private storage; use cdp-status for restriction state",
            }
        )
        return 0
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def cmd_gov_set_supply_operator(ctx: CLIContext, address: str) -> int:
    """Set ATN supply operator.

    Requires TIDE_GOVERNANCE_PRIVATE_KEY or TIDE_GOVERNANCE_PRIVATE_KEY_FILE.
    """
    try:
        from autonity import Stabilization

        # Validate address
        if not Web3.is_address(address):
            ctx.output({"error": f"Invalid address: {address}"})
            return 1

        address = Web3.to_checksum_address(address)
        stab = Stabilization(ctx.w3)
        gov_wallet = ctx.governance_wallet
        gov_address = gov_wallet.address

        if ctx.dry_run:
            ctx.output(
                {
                    "dry_run": True,
                    "action": "set_atn_supply_operator",
                    "new_operator": address,
                    "governance_address": gov_address,
                    "message": f"Would set ATN supply operator to {address}",
                }
            )
            return 0

        # Build transaction
        tx = stab.set_atn_supply_operator(address).build_transaction(
            {
                "from": gov_address,
                "gas": 100000,
                "gasPrice": ctx.w3.eth.gas_price,
                "nonce": ctx.w3.eth.get_transaction_count(gov_address),
                "chainId": ctx.w3.eth.chain_id,
            }
        )

        # Sign and send
        signed = gov_wallet.get_account().sign_transaction(tx)
        tx_hash = ctx.w3.eth.send_raw_transaction(signed.raw_transaction)

        # Wait for receipt
        receipt = ctx.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            ctx.output(
                {
                    "success": True,
                    "action": "set_atn_supply_operator",
                    "new_operator": address,
                    "tx_hash": tx_hash.hex(),
                    "gas_used": receipt.gasUsed,
                }
            )
            return 0
        else:
            ctx.output(
                {
                    "success": False,
                    "action": "set_atn_supply_operator",
                    "tx_hash": tx_hash.hex(),
                    "error": "Transaction reverted",
                }
            )
            return 1

    except ValueError as e:
        if "No governance wallet" in str(e):
            ctx.output(
                {
                    "error": str(e),
                    "hint": "Set TIDE_GOVERNANCE_PRIVATE_KEY_FILE environment variable",
                }
            )
        else:
            ctx.output({"error": str(e)})
        return 1
    except Exception as e:
        ctx.output({"error": str(e)})
        return 1


def run_cli(args: argparse.Namespace) -> int:
    """Execute CLI command based on parsed arguments.

    Returns
    -------
    int
        Exit code: 0 for success, positive for error, -1 signals caller
        to show help or start service mode (no CLI command specified).
    """
    # Load config
    try:
        config = TideConfig()
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"Configuration error: {e}"}))
        else:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    ctx = CLIContext(config, dry_run=args.dry_run, json_output=args.json)

    # Route to appropriate command
    if args.command == "wallet":
        if args.wallet_command == "address":
            return cmd_wallet_address(ctx)
        elif args.wallet_command == "balance":
            return cmd_wallet_balance(ctx)
        else:
            print("Usage: tide wallet [address|balance]", file=sys.stderr)
            return 1

    elif args.command == "cdp":
        if args.cdp_command == "status":
            return cmd_cdp_status(ctx)
        elif args.cdp_command == "deposit":
            return cmd_cdp_deposit(ctx, args.amount)
        elif args.cdp_command == "withdraw":
            return cmd_cdp_withdraw(ctx, args.amount)
        elif args.cdp_command == "borrow":
            return cmd_cdp_borrow(ctx, args.amount)
        elif args.cdp_command == "repay":
            return cmd_cdp_repay(ctx, args.amount)
        else:
            print("Usage: tide cdp [status|deposit|withdraw|borrow|repay]", file=sys.stderr)
            return 1

    elif args.command == "faucet":
        if args.faucet_command == "status":
            return cmd_faucet_status(ctx)
        elif args.faucet_command == "atn":
            return cmd_faucet_atn(ctx, args.address, args.amount)
        elif args.faucet_command == "ntn":
            return cmd_faucet_ntn(ctx, args.address, args.amount)
        else:
            print("Usage: tide faucet [status|atn|ntn]", file=sys.stderr)
            return 1

    elif args.command == "governance":
        if args.gov_command == "cdp-status":
            return cmd_gov_cdp_status(ctx)
        elif args.gov_command == "get-supply-operator":
            return cmd_gov_get_supply_operator(ctx)
        elif args.gov_command == "set-supply-operator":
            return cmd_gov_set_supply_operator(ctx, args.address)
        else:
            print(
                "Usage: tide governance [cdp-status|get-supply-operator|set-supply-operator]",
                file=sys.stderr,
            )
            return 1

    else:
        # No subcommand - show help
        return -1  # Signal to caller to show help or run service
