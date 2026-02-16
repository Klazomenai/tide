"""Observability module for TIDE faucet."""

from .health import HealthCheck, HealthServer, HealthStatus
from .logging import clear_request_id, configure_logging, get_logger, set_request_id
from .metrics import (
    CDP_COLLATERAL_AMOUNT,
    CDP_COLLATERAL_RATIO,
    CDP_DEBT_AMOUNT,
    CDP_OPERATIONS,
    REQUEST_DURATION,
    REQUESTS,
    TOKEN_BALANCE,
    TOKENS_DISTRIBUTED,
    TRANSACTION_DURATION,
)

__all__ = [
    # Health
    "HealthCheck",
    "HealthServer",
    "HealthStatus",
    # Logging
    "clear_request_id",
    "configure_logging",
    "get_logger",
    "set_request_id",
    # Metrics
    "CDP_COLLATERAL_AMOUNT",
    "CDP_COLLATERAL_RATIO",
    "CDP_DEBT_AMOUNT",
    "CDP_OPERATIONS",
    "REQUEST_DURATION",
    "REQUESTS",
    "TOKEN_BALANCE",
    "TOKENS_DISTRIBUTED",
    "TRANSACTION_DURATION",
]
