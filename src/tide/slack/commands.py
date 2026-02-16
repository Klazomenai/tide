"""Slack command handlers for TIDE faucet.

Commands:
- /tide atn <address> [amount] - Request ATN tokens
- /tide ntn <address> [amount] - Request NTN tokens
- /tide status - Check faucet status
- /tide alerts - View active alerts
- /tide help - Show help message
"""

import logging
import re
from decimal import Decimal, InvalidOperation

from slack_bolt.async_app import AsyncApp

from tide.blockchain.networks import NetworkInfo
from tide.faucet.service import FaucetService

from .formatter import MessageFormatter

logger = logging.getLogger(__name__)

# Pattern to parse command arguments
ADDRESS_PATTERN = re.compile(r"^(0x[0-9a-fA-F]{40})(?:\s+(\d+(?:\.\d+)?))?$")


def _parse_distribution_args(text: str) -> tuple[str | None, Decimal | None, str | None]:
    """Parse address and optional amount from command text.

    Parameters
    ----------
    text : str
        Command arguments text.

    Returns
    -------
    tuple[str | None, Decimal | None, str | None]
        (address, amount, error_message)
    """
    text = text.strip()
    if not text:
        return None, None, "Please provide an address: `/tide <atn|ntn> <address> [amount]`"

    match = ADDRESS_PATTERN.match(text)
    if not match:
        # Check if it looks like an address but is invalid
        if text.startswith("0x"):
            return None, None, "Invalid Ethereum address format"
        return None, None, "Please provide a valid address: `/tide <atn|ntn> <address> [amount]`"

    address = match.group(1)
    amount = None

    if match.group(2):
        try:
            amount = Decimal(match.group(2))
            if amount <= 0:
                return None, None, "Amount must be positive"
        except InvalidOperation:
            return None, None, "Invalid amount format"

    return address, amount, None


def register_commands(
    app: AsyncApp,
    faucet: FaucetService,
    network: NetworkInfo | None = None,
) -> None:
    """Register all TIDE slash commands with the Slack app.

    Parameters
    ----------
    app : AsyncApp
        Slack Bolt async app instance.
    faucet : FaucetService
        Faucet service for handling requests.
    network : NetworkInfo | None
        Network info for explorer links.
    """
    formatter = MessageFormatter(network)

    @app.command("/tide")
    async def handle_tide_command(ack, command, respond):
        """Handle /tide slash command."""
        await ack()

        try:
            user_id = command["user_id"]
            text = command.get("text", "").strip()

            # Parse subcommand
            parts = text.split(None, 1)
            subcommand = parts[0].lower() if parts else "help"
            args = parts[1] if len(parts) > 1 else ""

            logger.info(
                "Received /tide command",
                extra={
                    "user_id": user_id,
                    "subcommand": subcommand,
                    "command_args": args,
                },
            )

            if subcommand == "atn":
                await _handle_atn(respond, faucet, formatter, user_id, args)
            elif subcommand == "ntn":
                await _handle_ntn(respond, faucet, formatter, user_id, args)
            elif subcommand == "status":
                await _handle_status(respond, faucet, formatter, user_id)
            elif subcommand == "alerts":
                await _handle_alerts(respond, faucet, formatter)
            elif subcommand == "help":
                await _handle_help(respond, faucet, formatter)
            else:
                await respond(
                    formatter.format_error(
                        f"Unknown command: `{subcommand}`. Use `/tide help` for available commands."
                    )
                )
        except Exception:
            logger.exception("Error handling /tide command")
            await respond(formatter.format_error("An unexpected error occurred. Please try again."))


async def _handle_atn(
    respond, faucet: FaucetService, formatter: MessageFormatter, user_id: str, args: str
) -> None:
    """Handle /tide atn command."""
    address, amount, error = _parse_distribution_args(args)
    if error:
        await respond(formatter.format_error(error))
        return

    result = await faucet.handle_atn_request(user_id, address, amount)

    if result.success:
        await respond(formatter.format_distribution_success(result))
    else:
        await respond(formatter.format_distribution_error(result))


async def _handle_ntn(
    respond, faucet: FaucetService, formatter: MessageFormatter, user_id: str, args: str
) -> None:
    """Handle /tide ntn command."""
    address, amount, error = _parse_distribution_args(args)
    if error:
        await respond(formatter.format_error(error))
        return

    result = await faucet.handle_ntn_request(user_id, address, amount)

    if result.success:
        await respond(formatter.format_distribution_success(result))
    else:
        await respond(formatter.format_distribution_error(result))


async def _handle_status(
    respond, faucet: FaucetService, formatter: MessageFormatter, user_id: str
) -> None:
    """Handle /tide status command."""
    status = await faucet.get_status()
    user_status = await faucet.get_user_status(user_id)
    user_remaining = user_status["remaining_requests"]

    await respond(formatter.format_status(status, user_remaining))


async def _handle_alerts(respond, faucet: FaucetService, formatter: MessageFormatter) -> None:
    """Handle /tide alerts command."""
    # Get alerts from CDP controller if available
    alerts = []
    status = await faucet.get_status()

    if status.cdp_status:
        if status.cdp_status.is_liquidatable:
            alerts.append("CDP is at risk of liquidation!")
        if status.cdp_status.health.value in ("critical", "danger"):
            alerts.append(f"CDP health is {status.cdp_status.health.value}")

    if not status.healthy:
        alerts.append(status.message)

    await respond(formatter.format_alerts(alerts))


async def _handle_help(respond, faucet: FaucetService, formatter: MessageFormatter) -> None:
    """Handle /tide help command."""
    user_status = await faucet.get_user_status("_")  # Dummy user for max values
    max_atn = Decimal(user_status["max_atn"])
    max_ntn = Decimal(user_status["max_ntn"])

    await respond(formatter.format_help(max_atn, max_ntn))
