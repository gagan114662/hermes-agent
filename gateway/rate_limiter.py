"""
Per-user rate limiter for the Hermes messaging gateway.

Uses a sliding-window counter (per user, per platform) backed by an in-memory
dict.  State is not persisted — limits reset on process restart.

Configuration (env vars):
    GATEWAY_RATE_LIMIT_PER_MINUTE   max messages per user per minute (default: 20)
    GATEWAY_RATE_LIMIT_BURST        additional burst allowance above the per-minute
                                    rate (default: 5 — allows short bursts)
    GATEWAY_RATE_LIMIT_ENABLED      set to "0" or "false" to disable entirely
                                    (default: enabled)

Usage:
    from gateway.rate_limiter import RateLimiter
    limiter = RateLimiter()          # one instance shared across the gateway

    result = limiter.check("telegram", "user-123")
    if result.limited:
        await adapter.send(chat_id, f"Slow down! Try again in {result.retry_after}s.")
        return
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class RateResult:
    limited: bool
    remaining: int           # requests remaining in the current window
    retry_after: int         # seconds until the window resets (0 when not limited)
    user_key: str


class RateLimiter:
    """
    Sliding-window rate limiter.

    Keeps a deque of timestamps (one per request) per (platform, user_id) key.
    Timestamps older than the window are discarded on each check.
    """

    WINDOW_SECONDS = 60

    def __init__(
        self,
        per_minute: int | None = None,
        burst: int | None = None,
    ) -> None:
        self._per_minute: int = per_minute if per_minute is not None else _env_int(
            "GATEWAY_RATE_LIMIT_PER_MINUTE", 20
        )
        self._burst: int = burst if burst is not None else _env_int(
            "GATEWAY_RATE_LIMIT_BURST", 5
        )
        self._limit: int = self._per_minute + self._burst
        self._enabled: bool = os.environ.get(
            "GATEWAY_RATE_LIMIT_ENABLED", "true"
        ).lower() not in ("0", "false", "no")

        # {user_key: deque[timestamp]}
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, platform: str, user_id: str) -> RateResult:
        """
        Record a request and return whether the user is rate-limited.

        This both *checks* and *records* the request — call it exactly once per
        incoming message.
        """
        if not self._enabled:
            return RateResult(limited=False, remaining=self._limit, retry_after=0,
                              user_key=f"{platform}:{user_id}")

        key = f"{platform}:{user_id}"
        now = time.monotonic()
        cutoff = now - self.WINDOW_SECONDS

        with self._lock:
            window = self._windows.get(key)
            if window is None:
                window = deque()
                self._windows[key] = window

            # Drop stale entries
            while window and window[0] < cutoff:
                window.popleft()

            count = len(window)

            if count >= self._limit:
                # Find how long until the oldest entry expires
                retry_after = max(1, int(self.WINDOW_SECONDS - (now - window[0])) + 1)
                logger.warning(
                    "rate_limiter: %s exceeded %d req/min (count=%d)",
                    key, self._per_minute, count,
                )
                return RateResult(
                    limited=True,
                    remaining=0,
                    retry_after=retry_after,
                    user_key=key,
                )

            # Record this request
            window.append(now)
            remaining = self._limit - len(window)
            return RateResult(
                limited=False,
                remaining=remaining,
                retry_after=0,
                user_key=key,
            )

    def reset(self, platform: str, user_id: str) -> None:
        """Clear the rate-limit window for a specific user (e.g., admin override)."""
        key = f"{platform}:{user_id}"
        with self._lock:
            self._windows.pop(key, None)

    def stats(self) -> dict:
        """Return current window sizes for all tracked users."""
        now = time.monotonic()
        cutoff = now - self.WINDOW_SECONDS
        with self._lock:
            return {
                key: sum(1 for ts in dq if ts >= cutoff)
                for key, dq in self._windows.items()
            }
