"""Slack adapter for TIDE faucet.

Features:
- Socket Mode connection (no public webhook needed)
- Async lifecycle management
- Error handling for connection issues
"""

import logging
from abc import ABC, abstractmethod

from pydantic import SecretStr
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """Abstract base class for chat platform adapters.

    Enables future support for Discord, Telegram, etc.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter and connect to the platform."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter and disconnect from the platform."""
        ...

    @property
    @abstractmethod
    def app(self):
        """Get the underlying platform app instance."""
        ...


class SlackAdapter(PlatformAdapter):
    """Slack adapter using Bolt for Python with Socket Mode.

    Parameters
    ----------
    bot_token : SecretStr
        Slack bot token (xoxb-...).
    app_token : SecretStr
        Slack app-level token (xapp-...) for Socket Mode.
    """

    def __init__(
        self,
        bot_token: SecretStr,
        app_token: SecretStr,
    ):
        self._bot_token = bot_token
        self._app_token = app_token
        self._app = AsyncApp(token=bot_token.get_secret_value())
        self._handler: AsyncSocketModeHandler | None = None
        self._running = False

    @property
    def app(self) -> AsyncApp:
        """Get the Slack Bolt app instance."""
        return self._app

    @property
    def is_running(self) -> bool:
        """Check if the adapter is running."""
        return self._running

    async def start(self) -> None:
        """Start the Slack adapter and connect via Socket Mode."""
        if self._running:
            logger.warning("Slack adapter already running")
            return

        self._handler = AsyncSocketModeHandler(
            self._app,
            self._app_token.get_secret_value(),
        )

        logger.info("Starting Slack adapter via Socket Mode")
        try:
            await self._handler.connect_async()
        except Exception as e:
            logger.error("Failed to connect Slack adapter", extra={"error": str(e)})
            self._handler = None
            raise
        self._running = True
        logger.info("Slack adapter connected")

    async def stop(self) -> None:
        """Stop the Slack adapter and disconnect."""
        if not self._running:
            return

        if self._handler:
            logger.info("Stopping Slack adapter")
            await self._handler.close_async()
            self._handler = None

        self._running = False
        logger.info("Slack adapter stopped")
