"""Tests for structured logging."""

import logging

import pytest
import structlog

from tide.observability.logging import (
    _add_request_id,
    _redact_sensitive,
    clear_request_id,
    configure_logging,
    get_logger,
    request_id_var,
    set_request_id,
)


class TestRequestIdContext:
    """Tests for request ID context variable."""

    def test_request_id_default_none(self):
        """Request ID is None by default."""
        clear_request_id()
        assert request_id_var.get() is None

    def test_set_request_id(self):
        """set_request_id sets the context variable."""
        set_request_id("req-123")
        assert request_id_var.get() == "req-123"
        clear_request_id()

    def test_clear_request_id(self):
        """clear_request_id clears the context variable."""
        set_request_id("req-456")
        clear_request_id()
        assert request_id_var.get() is None


class TestAddRequestIdProcessor:
    """Tests for _add_request_id processor."""

    def test_adds_request_id_when_set(self):
        """Adds request_id to event dict when set."""
        set_request_id("req-abc")
        try:
            event_dict = {"event": "test"}
            result = _add_request_id(None, None, event_dict)
            assert result["request_id"] == "req-abc"
        finally:
            clear_request_id()

    def test_no_request_id_when_not_set(self):
        """Does not add request_id when not set."""
        clear_request_id()
        event_dict = {"event": "test"}
        result = _add_request_id(None, None, event_dict)
        assert "request_id" not in result


class TestRedactSensitiveProcessor:
    """Tests for _redact_sensitive processor."""

    def test_redacts_private_key(self):
        """Redacts private_key field."""
        event_dict = {"event": "test", "private_key": "0x1234567890"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["private_key"] == "[REDACTED]"

    def test_redacts_secret(self):
        """Redacts secret field."""
        event_dict = {"event": "test", "secret": "supersecret"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["secret"] == "[REDACTED]"

    def test_redacts_password(self):
        """Redacts password field."""
        event_dict = {"event": "test", "password": "hunter2"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["password"] == "[REDACTED]"

    def test_redacts_api_key(self):
        """Redacts api_key field."""
        event_dict = {"event": "test", "api_key": "sk-xxx"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["api_key"] == "[REDACTED]"

    def test_redacts_bot_token(self):
        """Redacts bot_token field."""
        event_dict = {"event": "test", "bot_token": "xoxb-xxx"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["bot_token"] == "[REDACTED]"

    def test_redacts_case_insensitive(self):
        """Redacts fields case-insensitively."""
        event_dict = {"event": "test", "Private_Key": "0x123"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["Private_Key"] == "[REDACTED]"

    def test_preserves_non_sensitive(self):
        """Preserves non-sensitive fields."""
        event_dict = {"event": "test", "user_id": "U123", "amount": "100"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["user_id"] == "U123"
        assert result["amount"] == "100"

    def test_preserves_token_type_field(self):
        """Preserves 'token' field used for token types (atn, ntn)."""
        event_dict = {"event": "distribution", "token": "atn", "amount": "5"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["token"] == "atn"  # Should NOT be redacted

    def test_redacts_signing_secret(self):
        """Redacts signing_secret field."""
        event_dict = {"event": "test", "signing_secret": "abc123"}
        result = _redact_sensitive(None, None, event_dict)
        assert result["signing_secret"] == "[REDACTED]"


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def setup_method(self):
        """Reset structlog before each test."""
        structlog.reset_defaults()

    def test_configure_json_format(self):
        """Configures JSON format logging."""
        configure_logging(level="INFO", log_format="json")

        logger = get_logger("test")
        assert logger is not None

    def test_configure_text_format(self):
        """Configures text format logging."""
        configure_logging(level="DEBUG", log_format="text")

        logger = get_logger("test")
        assert logger is not None

    def test_configure_log_level(self):
        """Configures log level."""
        configure_logging(level="WARNING", log_format="json")

        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_configure_invalid_log_level_raises(self):
        """Invalid log level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            configure_logging(level="INVALID", log_format="json")


class TestGetLogger:
    """Tests for get_logger function."""

    def setup_method(self):
        """Configure logging before each test."""
        structlog.reset_defaults()
        configure_logging(level="INFO", log_format="json")

    def test_get_logger_with_name(self):
        """get_logger returns named logger."""
        logger = get_logger("tide.faucet")
        assert logger is not None

    def test_get_logger_without_name(self):
        """get_logger returns logger without name."""
        logger = get_logger()
        assert logger is not None

    def test_logger_can_log(self):
        """Logger can output log messages."""
        logger = get_logger("test")
        # Should not raise
        logger.info("test message", key="value")


def test_logging_integration(capfd):
    """Integration test for structured logging."""
    structlog.reset_defaults()
    # Force reconfiguration by clearing handlers
    root = logging.getLogger()
    root.handlers.clear()

    configure_logging(level="INFO", log_format="json")

    # Set request ID
    set_request_id("req-integration")

    logger = get_logger("integration")

    # Log with request_id included
    logger.info("test event", user_id="U123", amount=100)

    clear_request_id()

    # Verify output contains expected fields (may be in stdout or stderr)
    captured = capfd.readouterr()
    output = captured.out + captured.err
    assert "req-integration" in output
    assert "test event" in output
    assert "U123" in output
