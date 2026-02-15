"""Tests for Slack adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from tide.slack.adapter import PlatformAdapter, SlackAdapter


class TestPlatformAdapter:
    """Tests for PlatformAdapter abstract base class."""

    def test_platform_adapter_is_abstract(self):
        """PlatformAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            PlatformAdapter()


class TestSlackAdapter:
    """Tests for SlackAdapter."""

    @pytest.fixture
    def bot_token(self):
        """Create a test bot token."""
        return SecretStr("xoxb-test-token")

    @pytest.fixture
    def app_token(self):
        """Create a test app token."""
        return SecretStr("xapp-test-token")

    def test_initialization(self, bot_token, app_token):
        """SlackAdapter initializes correctly."""
        with patch("tide.slack.adapter.AsyncApp"):
            adapter = SlackAdapter(bot_token, app_token)

            assert adapter.is_running is False
            assert adapter.app is not None

    def test_app_property(self, bot_token, app_token):
        """app property returns the Bolt app instance."""
        with patch("tide.slack.adapter.AsyncApp") as mock_app_class:
            mock_app = MagicMock()
            mock_app_class.return_value = mock_app
            adapter = SlackAdapter(bot_token, app_token)

            assert adapter.app == mock_app

    @pytest.mark.asyncio
    async def test_start(self, bot_token, app_token):
        """start() connects via Socket Mode."""
        with (
            patch("tide.slack.adapter.AsyncApp"),
            patch("tide.slack.adapter.AsyncSocketModeHandler") as mock_handler_class,
        ):
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            adapter = SlackAdapter(bot_token, app_token)
            await adapter.start()

            assert adapter.is_running is True
            mock_handler.connect_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_running(self, bot_token, app_token):
        """start() does nothing if already running."""
        with (
            patch("tide.slack.adapter.AsyncApp"),
            patch("tide.slack.adapter.AsyncSocketModeHandler") as mock_handler_class,
        ):
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            adapter = SlackAdapter(bot_token, app_token)
            await adapter.start()
            await adapter.start()  # Second call should do nothing

            # connect_async should only be called once
            assert mock_handler.connect_async.call_count == 1

    @pytest.mark.asyncio
    async def test_stop(self, bot_token, app_token):
        """stop() disconnects from Socket Mode."""
        with (
            patch("tide.slack.adapter.AsyncApp"),
            patch("tide.slack.adapter.AsyncSocketModeHandler") as mock_handler_class,
        ):
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler

            adapter = SlackAdapter(bot_token, app_token)
            await adapter.start()
            await adapter.stop()

            assert adapter.is_running is False
            mock_handler.close_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, bot_token, app_token):
        """stop() does nothing if not running."""
        with patch("tide.slack.adapter.AsyncApp"):
            adapter = SlackAdapter(bot_token, app_token)
            await adapter.stop()  # Should not raise

            assert adapter.is_running is False
