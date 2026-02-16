"""Prometheus metrics for TIDE faucet.

Metrics:
- tide_requests_total: Counter of faucet requests by token and status
- tide_tokens_distributed_total: Counter of tokens distributed
- tide_cdp_operations_total: Counter of CDP operations
- tide_balance: Gauge of token balances
- tide_cdp_collateral_ratio: Gauge of CDP collateralization ratio
- tide_cdp_collateral_amount: Gauge of CDP collateral
- tide_cdp_debt_amount: Gauge of CDP debt
- tide_request_duration_seconds: Histogram of request duration
- tide_transaction_duration_seconds: Histogram of transaction duration
"""

from prometheus_client import Counter, Gauge, Histogram

# Counters
REQUESTS = Counter(
    "tide_requests_total",
    "Total number of faucet requests",
    ["token", "status"],
)

TOKENS_DISTRIBUTED = Counter(
    "tide_tokens_distributed_total",
    "Total tokens distributed",
    ["token"],
)

CDP_OPERATIONS = Counter(
    "tide_cdp_operations_total",
    "Total CDP operations",
    ["operation"],
)

# Gauges
TOKEN_BALANCE = Gauge(
    "tide_balance",
    "Current token balance",
    ["token"],
)

CDP_COLLATERAL_RATIO = Gauge(
    "tide_cdp_collateral_ratio",
    "CDP collateralization ratio percentage",
)

CDP_COLLATERAL_AMOUNT = Gauge(
    "tide_cdp_collateral_amount",
    "CDP collateral amount in NTN",
)

CDP_DEBT_AMOUNT = Gauge(
    "tide_cdp_debt_amount",
    "CDP debt amount in ATN",
)

# Histograms
REQUEST_DURATION = Histogram(
    "tide_request_duration_seconds",
    "Request processing duration",
    ["token"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

TRANSACTION_DURATION = Histogram(
    "tide_transaction_duration_seconds",
    "Blockchain transaction duration",
    ["operation"],
    buckets=(1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
