"""Tests for Prometheus metrics."""

from prometheus_client import REGISTRY

from tide.observability.metrics import (
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


class TestMetrics:
    """Tests for Prometheus metrics."""

    def test_requests_counter_labels(self):
        """REQUESTS counter has correct labels."""
        # Increment counter
        REQUESTS.labels(token="atn", status="success").inc()

        # Verify metric exists
        sample = REGISTRY.get_sample_value(
            "tide_requests_total",
            {"token": "atn", "status": "success"},
        )
        assert sample is not None
        assert sample >= 1

    def test_tokens_distributed_counter(self):
        """TOKENS_DISTRIBUTED counter tracks distribution."""
        initial = (
            REGISTRY.get_sample_value(
                "tide_tokens_distributed_total",
                {"token": "ntn"},
            )
            or 0
        )

        TOKENS_DISTRIBUTED.labels(token="ntn").inc(100)

        current = REGISTRY.get_sample_value(
            "tide_tokens_distributed_total",
            {"token": "ntn"},
        )
        assert current == initial + 100

    def test_cdp_operations_counter(self):
        """CDP_OPERATIONS counter tracks operations."""
        CDP_OPERATIONS.labels(operation="borrow").inc()

        sample = REGISTRY.get_sample_value(
            "tide_cdp_operations_total",
            {"operation": "borrow"},
        )
        assert sample is not None
        assert sample >= 1

    def test_token_balance_gauge(self):
        """TOKEN_BALANCE gauge tracks balances."""
        TOKEN_BALANCE.labels(token="atn").set(500.5)

        sample = REGISTRY.get_sample_value(
            "tide_balance",
            {"token": "atn"},
        )
        assert sample == 500.5

    def test_cdp_collateral_ratio_gauge(self):
        """CDP_COLLATERAL_RATIO gauge tracks ratio."""
        CDP_COLLATERAL_RATIO.set(175.5)

        sample = REGISTRY.get_sample_value("tide_cdp_collateral_ratio")
        assert sample == 175.5

    def test_cdp_collateral_amount_gauge(self):
        """CDP_COLLATERAL_AMOUNT gauge tracks collateral."""
        CDP_COLLATERAL_AMOUNT.set(1000)

        sample = REGISTRY.get_sample_value("tide_cdp_collateral_amount")
        assert sample == 1000

    def test_cdp_debt_amount_gauge(self):
        """CDP_DEBT_AMOUNT gauge tracks debt."""
        CDP_DEBT_AMOUNT.set(250.75)

        sample = REGISTRY.get_sample_value("tide_cdp_debt_amount")
        assert sample == 250.75

    def test_request_duration_histogram(self):
        """REQUEST_DURATION histogram tracks timing."""
        REQUEST_DURATION.labels(token="atn").observe(0.5)

        # Check that observation was recorded
        sample = REGISTRY.get_sample_value(
            "tide_request_duration_seconds_count",
            {"token": "atn"},
        )
        assert sample is not None
        assert sample >= 1

    def test_transaction_duration_histogram(self):
        """TRANSACTION_DURATION histogram tracks timing."""
        TRANSACTION_DURATION.labels(operation="transfer").observe(5.0)

        sample = REGISTRY.get_sample_value(
            "tide_transaction_duration_seconds_count",
            {"operation": "transfer"},
        )
        assert sample is not None
        assert sample >= 1
