"""Rate Limiter for TIDE faucet.

Features:
- Per-user daily request limits
- Cooldown period between requests
- In-memory fallback for development
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _format_cooldown(seconds: int) -> str:
    """Format cooldown duration for user display."""
    if seconds < 60:
        return f"Please wait {seconds} seconds before next request"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if remaining_seconds > 0:
        return f"Please wait {minutes}m {remaining_seconds}s before next request"
    return f"Please wait {minutes} minutes before next request"


def _get_utc_date() -> str:
    """Get current UTC date string for consistent day boundaries."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int  # Remaining requests today
    cooldown_seconds: int | None  # Seconds until next request allowed
    reason: str | None  # Rejection reason if not allowed


class RateLimiter:
    """Rate limiter for faucet requests.

    Uses Redis for persistence in production, with in-memory fallback
    for development/testing.

    Parameters
    ----------
    daily_limit : int
        Maximum requests per user per day.
    cooldown_minutes : int
        Minutes required between requests.
    redis_url : str | None
        Redis connection URL. If None, uses in-memory storage.
    """

    def __init__(
        self,
        daily_limit: int = 10,
        cooldown_minutes: int = 60,
        redis_url: str | None = None,
    ):
        self._daily_limit = daily_limit
        self._cooldown_seconds = cooldown_minutes * 60
        self._redis_url = redis_url
        self._redis = None  # Redis instance or None

        # In-memory fallback storage
        self._memory_requests: dict[str, list[float]] = {}

        if redis_url:
            self._init_redis(redis_url)

    def _init_redis(self, redis_url: str) -> None:
        """Initialize Redis connection."""
        try:
            from redis import Redis

            self._redis = Redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("Redis connected for rate limiting", extra={"url": redis_url})
        except Exception as e:
            logger.warning(
                "Redis connection failed, using in-memory rate limiting",
                extra={"error": str(e)},
            )
            self._redis = None

    def _get_day_key(self, user_id: str) -> str:
        """Get Redis key for daily request count (UTC-based)."""
        day = _get_utc_date()
        return f"tide:ratelimit:{user_id}:{day}"

    def _get_cooldown_key(self, user_id: str) -> str:
        """Get Redis key for cooldown timestamp."""
        return f"tide:cooldown:{user_id}"

    async def check_limit(self, user_id: str) -> RateLimitResult:
        """Check if a user can make a request.

        Parameters
        ----------
        user_id : str
            User identifier (e.g., Slack user ID).

        Returns
        -------
        RateLimitResult
            Whether the request is allowed and rate limit info.
        """
        if self._redis:
            return self._check_limit_redis(user_id)
        return self._check_limit_memory(user_id)

    def _check_limit_redis(self, user_id: str) -> RateLimitResult:
        """Check rate limit using Redis."""
        now = time.time()
        day_key = self._get_day_key(user_id)
        cooldown_key = self._get_cooldown_key(user_id)

        # Check cooldown
        last_request = self._redis.get(cooldown_key)
        if last_request:
            elapsed = now - float(last_request)
            if elapsed < self._cooldown_seconds:
                remaining_cooldown = int(self._cooldown_seconds - elapsed)
                count = int(self._redis.get(day_key) or 0)
                return RateLimitResult(
                    allowed=False,
                    remaining=max(0, self._daily_limit - count),
                    cooldown_seconds=remaining_cooldown,
                    reason=_format_cooldown(remaining_cooldown),
                )

        # Check daily limit
        count = int(self._redis.get(day_key) or 0)
        if count >= self._daily_limit:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                cooldown_seconds=None,
                reason="Daily request limit reached",
            )

        return RateLimitResult(
            allowed=True,
            remaining=self._daily_limit - count - 1,
            cooldown_seconds=None,
            reason=None,
        )

    def _check_limit_memory(self, user_id: str) -> RateLimitResult:
        """Check rate limit using in-memory storage (UTC-based)."""
        now = time.time()
        # Use UTC midnight as day boundary for consistency with Redis
        utc_now = datetime.now(timezone.utc)
        utc_midnight = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = utc_midnight.timestamp()

        # Get user's requests for today
        requests = self._memory_requests.get(user_id, [])
        today_requests = [r for r in requests if r >= day_start]

        # Check cooldown
        if today_requests:
            last_request = max(today_requests)
            elapsed = now - last_request
            if elapsed < self._cooldown_seconds:
                remaining_cooldown = int(self._cooldown_seconds - elapsed)
                return RateLimitResult(
                    allowed=False,
                    remaining=max(0, self._daily_limit - len(today_requests)),
                    cooldown_seconds=remaining_cooldown,
                    reason=_format_cooldown(remaining_cooldown),
                )

        # Check daily limit
        if len(today_requests) >= self._daily_limit:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                cooldown_seconds=None,
                reason="Daily request limit reached",
            )

        return RateLimitResult(
            allowed=True,
            remaining=self._daily_limit - len(today_requests) - 1,
            cooldown_seconds=None,
            reason=None,
        )

    async def record_request(self, user_id: str) -> None:
        """Record a successful request for a user.

        Parameters
        ----------
        user_id : str
            User identifier.
        """
        if self._redis:
            self._record_request_redis(user_id)
        else:
            self._record_request_memory(user_id)

    def _record_request_redis(self, user_id: str) -> None:
        """Record request in Redis."""
        now = time.time()
        day_key = self._get_day_key(user_id)
        cooldown_key = self._get_cooldown_key(user_id)

        # Increment daily count with TTL of 24 hours
        pipe = self._redis.pipeline()
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)
        pipe.set(cooldown_key, str(now), ex=self._cooldown_seconds)
        pipe.execute()

        logger.debug(
            "Rate limit recorded",
            extra={"user_id": user_id, "day_key": day_key},
        )

    def _record_request_memory(self, user_id: str) -> None:
        """Record request in memory."""
        now = time.time()
        if user_id not in self._memory_requests:
            self._memory_requests[user_id] = []
        self._memory_requests[user_id].append(now)

        # Cleanup old entries (keep last 7 days)
        cutoff = now - (7 * 86400)
        self._memory_requests[user_id] = [r for r in self._memory_requests[user_id] if r >= cutoff]

    async def get_remaining(self, user_id: str) -> int:
        """Get remaining requests for today.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        int
            Number of remaining requests.
        """
        result = await self.check_limit(user_id)
        # If allowed, remaining already accounts for -1, so add it back
        if result.allowed:
            return result.remaining + 1
        return result.remaining

    async def get_cooldown(self, user_id: str) -> timedelta | None:
        """Get cooldown time remaining.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        timedelta | None
            Time until next request allowed, or None if no cooldown.
        """
        result = await self.check_limit(user_id)
        if result.cooldown_seconds:
            return timedelta(seconds=result.cooldown_seconds)
        return None

    def reset_user(self, user_id: str) -> None:
        """Reset rate limit for a user (admin function).

        Parameters
        ----------
        user_id : str
            User identifier.
        """
        if self._redis:
            day_key = self._get_day_key(user_id)
            cooldown_key = self._get_cooldown_key(user_id)
            self._redis.delete(day_key, cooldown_key)
        else:
            self._memory_requests.pop(user_id, None)

        logger.info("Rate limit reset for user", extra={"user_id": user_id})
