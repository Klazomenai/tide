"""Tests for Rate Limiter module."""

import time
from unittest.mock import MagicMock

import pytest

from tide.faucet.rate_limiter import RateLimiter, RateLimitResult


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_allowed_result(self):
        """RateLimitResult can represent allowed request."""
        result = RateLimitResult(
            allowed=True,
            remaining=9,
            cooldown_seconds=None,
            reason=None,
        )

        assert result.allowed is True
        assert result.remaining == 9
        assert result.cooldown_seconds is None
        assert result.reason is None

    def test_denied_result_daily_limit(self):
        """RateLimitResult can represent daily limit denial."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            cooldown_seconds=None,
            reason="Daily request limit reached",
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.reason == "Daily request limit reached"

    def test_denied_result_cooldown(self):
        """RateLimitResult can represent cooldown denial."""
        result = RateLimitResult(
            allowed=False,
            remaining=5,
            cooldown_seconds=1800,
            reason="Please wait 30 minutes before next request",
        )

        assert result.allowed is False
        assert result.cooldown_seconds == 1800


class TestRateLimiterMemory:
    """Tests for RateLimiter using in-memory storage."""

    def test_initialization_defaults(self):
        """RateLimiter initializes with default values."""
        limiter = RateLimiter()

        assert limiter._daily_limit == 10
        assert limiter._cooldown_seconds == 3600  # 60 minutes

    def test_initialization_custom(self):
        """RateLimiter accepts custom values."""
        limiter = RateLimiter(daily_limit=5, cooldown_minutes=30)

        assert limiter._daily_limit == 5
        assert limiter._cooldown_seconds == 1800

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        """First request from a user is allowed."""
        limiter = RateLimiter()

        result = await limiter.check_limit("user123")

        assert result.allowed is True
        assert result.remaining == 9  # 10 - 1 (anticipating the request)

    @pytest.mark.asyncio
    async def test_record_and_check(self):
        """Recording a request updates the limit."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=0)

        await limiter.record_request("user123")
        result = await limiter.check_limit("user123")

        # With 0 cooldown, should still be allowed
        assert result.allowed is True
        assert result.remaining == 8  # 10 - 1 recorded - 1 anticipated

    @pytest.mark.asyncio
    async def test_daily_limit_enforced(self):
        """Daily limit is enforced after reaching max requests."""
        limiter = RateLimiter(daily_limit=3, cooldown_minutes=0)

        # Record 3 requests using public API
        for _ in range(3):
            await limiter.record_request("user123")

        result = await limiter.check_limit("user123")

        assert result.allowed is False
        assert result.remaining == 0
        assert result.reason == "Daily request limit reached"

    @pytest.mark.asyncio
    async def test_cooldown_enforced(self):
        """Cooldown period is enforced between requests."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=60)

        # Record a request using public API
        await limiter.record_request("user123")

        result = await limiter.check_limit("user123")

        assert result.allowed is False
        assert result.cooldown_seconds is not None
        assert result.cooldown_seconds > 0
        assert "wait" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_cooldown_expires(self):
        """Request is allowed after cooldown expires."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=1)

        # Manually add a request from the past
        past_time = time.time() - 120  # 2 minutes ago
        limiter._memory_requests["user123"] = [past_time]

        result = await limiter.check_limit("user123")

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_get_remaining(self):
        """get_remaining returns correct count."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=0)

        remaining = await limiter.get_remaining("user123")
        assert remaining == 10

        await limiter.record_request("user123")
        remaining = await limiter.get_remaining("user123")
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_get_cooldown_no_cooldown(self):
        """get_cooldown returns None when no cooldown active."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=60)

        cooldown = await limiter.get_cooldown("user123")
        assert cooldown is None

    @pytest.mark.asyncio
    async def test_get_cooldown_active(self):
        """get_cooldown returns timedelta when cooldown active."""
        limiter = RateLimiter(daily_limit=10, cooldown_minutes=60)

        await limiter.record_request("user123")
        cooldown = await limiter.get_cooldown("user123")

        assert cooldown is not None
        assert cooldown.total_seconds() > 0

    def test_reset_user(self):
        """reset_user clears user's rate limit data."""
        limiter = RateLimiter()

        limiter._memory_requests["user123"] = [time.time()]
        limiter.reset_user("user123")

        assert "user123" not in limiter._memory_requests

    @pytest.mark.asyncio
    async def test_memory_cleanup(self):
        """Old entries are cleaned up."""
        limiter = RateLimiter()

        # Add old request (8 days ago) - direct setup of internal state
        old_time = time.time() - (8 * 86400)
        limiter._memory_requests["user123"] = [old_time]

        # Record new request triggers cleanup via public API
        await limiter.record_request("user123")

        # Old entry should be cleaned up, only new one remains
        assert len(limiter._memory_requests["user123"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_users_independent(self):
        """Rate limits are independent per user."""
        limiter = RateLimiter(daily_limit=2, cooldown_minutes=0)

        # User 1 uses both requests
        await limiter.record_request("user1")
        await limiter.record_request("user1")

        result1 = await limiter.check_limit("user1")
        result2 = await limiter.check_limit("user2")

        assert result1.allowed is False
        assert result2.allowed is True


class TestRateLimiterRedis:
    """Tests for RateLimiter Redis functionality."""

    def test_redis_init_failure_fallback(self):
        """Falls back to memory when Redis connection fails."""
        # Invalid Redis URL should fail gracefully
        limiter = RateLimiter(redis_url="redis://invalid:9999")

        assert limiter._redis is None

    @pytest.mark.asyncio
    async def test_redis_check_limit(self):
        """RateLimiter Redis check works with mocked Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        limiter = RateLimiter(daily_limit=10, cooldown_minutes=60)
        limiter._redis = mock_redis

        # Use public async API which delegates to sync Redis method
        result = await limiter.check_limit("user123")

        assert result.allowed is True
        assert result.remaining == 9
