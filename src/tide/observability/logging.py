"""Structured logging for TIDE faucet.

Features:
- JSON or text format output
- Request ID propagation
- Sensitive data redaction
- Configurable log level
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# Context variable for request ID
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Fields that should be redacted (use specific names to avoid conflicts with
# legitimate fields like "token" which is used for token types e.g. "atn", "ntn")
REDACTED_FIELDS = frozenset(
    {
        "private_key",
        "secret",
        "password",
        "api_key",
        "bot_token",
        "app_token",
        "auth_token",
        "bearer_token",
        "access_token",
        "signing_secret",
    }
)


def _add_request_id(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add request ID to log event if available."""
    request_id = request_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def _redact_sensitive(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Redact sensitive fields from log events."""
    for key in event_dict:
        if key.lower() in REDACTED_FIELDS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(
    level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure structured logging for the application.

    Parameters
    ----------
    level : str
        Log level (DEBUG, INFO, WARNING, ERROR).
    log_format : str
        Output format (json or text).
    """
    # Validate and get log level
    try:
        log_level = getattr(logging, level.upper())
    except AttributeError:
        raise ValueError(
            f"Invalid log level: {level!r}. "
            "Valid levels are: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        ) from None

    # Set up stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Common processors
    processors: list[structlog.typing.Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _add_request_id,
        _redact_sensitive,
    ]

    # Add format-specific renderer
    if log_format.lower() == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Parameters
    ----------
    name : str | None
        Logger name. If None, uses the calling module's name.

    Returns
    -------
    structlog.stdlib.BoundLogger
        Configured logger instance.
    """
    return structlog.get_logger(name)


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current context.

    Parameters
    ----------
    request_id : str
        The request ID to set.
    """
    request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear the request ID for the current context."""
    request_id_var.set(None)
