"""
Per-client command rate limiting.

Prevents clients from flooding the server with commands.
Uses a token bucket algorithm for smooth rate limiting.
"""

import time
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for client commands.

    Each client gets a bucket that fills at `rate` tokens per second,
    up to `burst` tokens maximum. Each command costs one token.
    """

    def __init__(self, rate: float = 20.0, burst: int = 30):
        """Initialize rate limiter.

        Args:
            rate: Commands per second allowed (sustained)
            burst: Maximum burst size (commands before throttling)
        """
        self.rate = rate
        self.burst = burst
        self._buckets: Dict[str, Tuple[float, float]] = {}  # client_id -> (tokens, last_update)

    def allow(self, client_id: str) -> bool:
        """Check if a command from this client is allowed.

        Args:
            client_id: Client identifier

        Returns:
            True if the command is allowed, False if rate limited
        """
        now = time.monotonic()

        if client_id not in self._buckets:
            self._buckets[client_id] = (self.burst - 1, now)
            return True

        tokens, last_update = self._buckets[client_id]

        # Refill tokens based on elapsed time
        elapsed = now - last_update
        tokens = min(self.burst, tokens + elapsed * self.rate)

        if tokens >= 1.0:
            self._buckets[client_id] = (tokens - 1, now)
            return True

        # Rate limited
        logger.warning(f"Rate limited client {client_id}")
        self._buckets[client_id] = (tokens, now)
        return False

    def remove_client(self, client_id: str) -> None:
        """Remove a client's rate limit state (on disconnect)."""
        self._buckets.pop(client_id, None)

    def cleanup(self, max_age: float = 300.0) -> None:
        """Remove stale entries older than max_age seconds."""
        now = time.monotonic()
        stale = [
            cid for cid, (_, last_update) in self._buckets.items()
            if now - last_update > max_age
        ]
        for cid in stale:
            del self._buckets[cid]
