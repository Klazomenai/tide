"""Message formatter for Slack responses."""

from decimal import Decimal

from tide.blockchain.networks import NetworkInfo
from tide.faucet.service import FaucetResult, FaucetStatus


class MessageFormatter:
    """Formats faucet responses for Slack using Block Kit.

    Parameters
    ----------
    network : NetworkInfo | None
        Network info for generating explorer links.
    """

    def __init__(self, network: NetworkInfo | None = None):
        self._network = network

    def format_distribution_success(self, result: FaucetResult) -> dict:
        """Format a successful distribution response.

        Parameters
        ----------
        result : FaucetResult
            The distribution result.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        token = result.request_type.value.upper()
        amount = result.amount

        # Build transaction link if network has explorer
        tx_text = f"`{result.tx_hash}`"
        if self._network and result.tx_hash:
            tx_url = self._network.get_tx_url(result.tx_hash)
            if tx_url:
                tx_text = f"<{tx_url}|{result.tx_hash[:16]}...>"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: *Sent {amount} {token}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Transaction:*\n{tx_text}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Remaining:*\n{result.remaining_requests} requests today",
                    },
                ],
            },
        ]

        return {"blocks": blocks}

    def format_distribution_error(self, result: FaucetResult) -> dict:
        """Format a distribution error response.

        Parameters
        ----------
        result : FaucetResult
            The distribution result.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: *{result.message}*",
                },
            },
        ]

        # Add remaining requests info if available
        if result.remaining_requests is not None:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Remaining: {result.remaining_requests} requests today",
                        }
                    ],
                }
            )

        return {"blocks": blocks}

    def format_status(self, status: FaucetStatus, user_remaining: int) -> dict:
        """Format faucet status response.

        Parameters
        ----------
        status : FaucetStatus
            Current faucet status.
        user_remaining : int
            User's remaining requests.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        health_emoji = ":white_check_mark:" if status.healthy else ":warning:"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "TIDE Faucet Status"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Health:*\n{health_emoji} {status.message}"},
                    {"type": "mrkdwn", "text": f"*Your Remaining:*\n{user_remaining} requests"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*ATN Available:*\n{status.atn_available}"},
                    {"type": "mrkdwn", "text": f"*NTN Available:*\n{status.ntn_available}"},
                ],
            },
        ]

        # Add CDP status if available
        if status.cdp_status and status.cdp_status.exists:
            cdp = status.cdp_status
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*CDP Health:*\n{cdp.health.value}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Collateral Ratio:*\n{cdp.collateralization_ratio}%",
                        },
                    ],
                }
            )

        return {"blocks": blocks}

    def format_help(self, max_atn: Decimal, max_ntn: Decimal) -> dict:
        """Format help message.

        Parameters
        ----------
        max_atn : Decimal
            Maximum ATN per request.
        max_ntn : Decimal
            Maximum NTN per request.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "TIDE Faucet Commands"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Available Commands:*\n\n"
                        "`/tide atn <address> [amount]`\n"
                        f"Request ATN tokens (max {max_atn} per request)\n\n"
                        "`/tide ntn <address> [amount]`\n"
                        f"Request NTN tokens (max {max_ntn} per request)\n\n"
                        "`/tide status`\n"
                        "Check faucet status and your remaining requests\n\n"
                        "`/tide alerts`\n"
                        "View active alerts about CDP health\n\n"
                        "`/tide help`\n"
                        "Show this help message"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Rate limits apply. Use `/tide status` to check your allowance.",
                    }
                ],
            },
        ]

        return {"blocks": blocks}

    def format_alerts(self, alerts: list[str]) -> dict:
        """Format alerts response.

        Parameters
        ----------
        alerts : list[str]
            List of active alerts.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        if not alerts:
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":white_check_mark: No active alerts",
                        },
                    }
                ]
            }

        alert_text = "\n".join(f":warning: {alert}" for alert in alerts)
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Active Alerts"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": alert_text},
            },
        ]

        return {"blocks": blocks}

    def format_error(self, message: str) -> dict:
        """Format a generic error message.

        Parameters
        ----------
        message : str
            Error message.

        Returns
        -------
        dict
            Slack Block Kit message.
        """
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f":x: {message}"},
                }
            ]
        }
