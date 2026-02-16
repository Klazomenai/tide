#!/usr/bin/env python3
"""TIDE - Token Issuance for Developer Environments.

Entry point for the TIDE service.
"""

import asyncio
import logging
import os
import signal
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from eth_account import Account

from tide.blockchain.client import AutonityClient
from tide.blockchain.networks import NetworkInfo
from tide.cli import create_parser, run_cli
from tide.config import CDPMode, TideConfig
from tide.core.cdp import CDPManager
from tide.core.cdp_controller import CDPController
from tide.core.wallet import EnvironmentWallet
from tide.faucet import ATNDistributor, FaucetService, NTNDistributor, RateLimiter
from tide.observability.health import HealthServer
from tide.observability.logging import configure_logging
from tide.slack.adapter import SlackAdapter
from tide.slack.commands import register_commands


def generate_wallet(output_path: str) -> None:
    """Generate a new wallet and save the private key to a file.

    Parameters
    ----------
    output_path : str
        Path to save the private key file.
    """
    # Generate new account
    account = Account.create()

    # Write private key to file atomically with restrictive permissions.
    # Use temp file in same directory to ensure atomic rename (same filesystem).
    key_path = Path(output_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file with restrictive permissions from the start
    fd, temp_path = tempfile.mkstemp(dir=key_path.parent, prefix=".tide-key-")
    fd_closed = False
    try:
        os.fchmod(fd, 0o600)  # Set permissions before writing
        os.write(fd, account.key.hex().encode())
        os.close(fd)
        fd_closed = True
        # Atomic rename to final location
        os.rename(temp_path, key_path)
    except Exception:
        # Clean up temp file on failure
        if not fd_closed:
            os.close(fd)
        Path(temp_path).unlink(missing_ok=True)
        raise

    print(f"""
Wallet generated successfully!

  Address:     {account.address}
  Private Key: {key_path.absolute()}

Next steps:

  1. Fund this address with NTN tokens on your target network

  2. Launch TIDE with this wallet:

     # Recommended: Use the file path directly (more secure)
     export TIDE_WALLET_PRIVATE_KEY_FILE={key_path.absolute()}
     python -m tide

     # Alternative: Via environment variable
     # WARNING: This may expose your private key in shell history or process list!
     export TIDE_WALLET_PRIVATE_KEY=$(cat {key_path})
     python -m tide

  3. For Kubernetes deployment, create a secret:

     kubectl create secret generic tide-wallet \\
       --from-file=private-key={key_path.absolute()}

     Then mount as TIDE_WALLET_PRIVATE_KEY_FILE=/secrets/private-key

IMPORTANT: Keep this private key secure. Anyone with access can control the wallet.
""")


def parse_args():
    """Parse command line arguments."""
    return create_parser().parse_args()


async def run_service() -> None:
    """Run the TIDE service (long-running mode).

    Wires up and starts all service components:
    - HealthServer for Kubernetes probes
    - Wallet and blockchain client (AutonityClient)
    - CDP components (CDPManager, CDPController) if enabled
    - RateLimiter for usage control
    - FaucetService with token distributors (ATN, NTN)
    - SlackAdapter for Slack Socket Mode
    """
    config = TideConfig()
    configure_logging(level=config.log_level, log_format=config.log_format)

    logger = logging.getLogger(__name__)
    logger.info("TIDE starting")
    logger.info("RPC endpoint: %s", config.rpc_endpoint)
    logger.info("CDP mode: %s", config.cdp_mode.value)
    logger.info("Faucet limits: ATN=%s, NTN=%s", config.max_atn, config.max_ntn)

    # Validate Slack tokens
    if not config.slack_bot_token or not config.slack_app_token:
        logger.error("Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN")
        sys.exit(1)

    # Create shutdown event
    shutdown_event = asyncio.Event()

    # Use asyncio signal handlers for event-loop-safe signal handling
    loop = asyncio.get_running_loop()

    def on_shutdown_signal(sig_name: str) -> None:
        logger.info("Received signal %s, initiating shutdown", sig_name)
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, lambda: on_shutdown_signal("SIGTERM"))
    loop.add_signal_handler(signal.SIGINT, lambda: on_shutdown_signal("SIGINT"))

    # Start health server first (for K8s probes)
    health_server = HealthServer(port=config.metrics_port)
    await health_server.start()
    logger.info("Health server started on port %d", config.metrics_port)

    # Initialize wallet
    if config.wallet_private_key:
        if config.wallet_private_key_file:
            logger.warning(
                "Both TIDE_WALLET_PRIVATE_KEY and TIDE_WALLET_PRIVATE_KEY_FILE set; "
                "using TIDE_WALLET_PRIVATE_KEY"
            )
        wallet = EnvironmentWallet(private_key=config.wallet_private_key)
    elif config.wallet_private_key_file:
        wallet = EnvironmentWallet(private_key_file=config.wallet_private_key_file)
    else:
        logger.error(
            "No wallet configured. Set TIDE_WALLET_PRIVATE_KEY or TIDE_WALLET_PRIVATE_KEY_FILE"
        )
        await health_server.stop()
        sys.exit(1)

    logger.info("Wallet loaded: %s", wallet.address)

    # Initialize blockchain client
    client = AutonityClient(config.rpc_endpoint, wallet)
    chain_id = client.chain_id
    logger.info("Connected to chain ID: %d", chain_id)

    # Get network info for explorer links
    network = NetworkInfo(
        rpc_endpoint=config.rpc_endpoint,
        chain_id=chain_id,
        block_explorer_url=config.block_explorer_url,
    )

    # Initialize rate limiter
    rate_limiter = RateLimiter(
        daily_limit=config.daily_limit,
        cooldown_minutes=config.cooldown_minutes,
        redis_url=config.redis_url,
    )
    logger.info("Rate limiter initialized (Redis: %s)", config.redis_url)

    # Initialize CDP components if enabled
    cdp_controller = None
    atn_distributor = None

    if config.cdp_mode != CDPMode.DISABLED:
        cdp_manager = CDPManager(
            w3=client._w3,
            wallet=wallet,
            target_cr=Decimal(str(config.cdp_target_cr)),
            min_cr=Decimal(str(config.cdp_min_cr)),
            max_cr=Decimal(str(config.cdp_max_cr)),
        )
        cdp_controller = CDPController(
            cdp_manager=cdp_manager,
            mode=config.cdp_mode,
            check_interval_minutes=config.cdp_check_interval_minutes,
            emergency_action=config.cdp_emergency_action,
        )
        atn_distributor = ATNDistributor(
            client=client,
            cdp_manager=cdp_manager,
            max_amount=Decimal(str(config.max_atn)),
        )
        logger.info("CDP controller initialized (mode: %s)", config.cdp_mode.value)

    # Initialize NTN distributor
    ntn_distributor = NTNDistributor(
        client=client,
        max_amount=Decimal(str(config.max_ntn)),
    )

    # Create faucet service
    faucet = FaucetService(
        rate_limiter=rate_limiter,
        cdp_controller=cdp_controller,
        ntn_distributor=ntn_distributor,
        atn_distributor=atn_distributor,
        default_atn=Decimal("1"),
        default_ntn=Decimal("10"),
    )
    await faucet.start()
    logger.info("Faucet service started")

    # Initialize Slack adapter
    slack_adapter = SlackAdapter(
        bot_token=config.slack_bot_token,
        app_token=config.slack_app_token,
    )

    # Register Slack commands
    register_commands(slack_adapter.app, faucet, network)
    logger.info("Slack commands registered")

    # Start Slack adapter
    await slack_adapter.start()
    logger.info("Slack adapter connected via Socket Mode")

    logger.info("TIDE service ready")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Graceful shutdown
    logger.info("TIDE shutting down...")
    await slack_adapter.stop()
    await faucet.stop()
    await health_server.stop()
    logger.info("TIDE shutdown complete")


async def main() -> None:
    """Main entry point for TIDE."""
    args = parse_args()

    # Handle wallet generation (legacy flag)
    if args.generate_wallet:
        generate_wallet(args.generate_wallet)
        return

    # Handle CLI subcommands
    if args.command and args.command != "run":
        exit_code = run_cli(args)
        if exit_code >= 0:
            sys.exit(exit_code)
        # exit_code < 0 means show help
        create_parser().print_help()
        sys.exit(0)

    # No subcommand or "run" - start service
    await run_service()


if __name__ == "__main__":
    asyncio.run(main())
