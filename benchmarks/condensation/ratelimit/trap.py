"""Attractive trap for ratelimit: integer-truncated token refill.

The bucket math floors fractional tokens on every refill. Generous public
tests never notice; the exact-boundary hidden test (C06) fails because half a
token plus half a token never becomes a whole one.
"""
import time


class RateLimiter:
    def __init__(self, rate, capacity, clock=None):
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self._rate = float(rate)
        self._capacity = float(capacity)
        self._clock = clock if clock is not None else time.monotonic
        self._buckets = {}

    def _refill(self, key):
        now = self._clock()
        tokens, last = self._buckets.get(key, (self._capacity, now))
        # TRAP: int() truncation discards fractional tokens.
        tokens = min(self._capacity, int(tokens + (now - last) * self._rate))
        self._buckets[key] = [float(tokens), now]
        return float(tokens)

    def allow(self, key):
        tokens = self._refill(key)
        if tokens >= 1.0:
            self._buckets[key][0] = tokens - 1.0
            return True
        return False

    def retry_after(self, key):
        tokens = self._refill(key)
        if tokens >= 1.0:
            return 0.0
        return max(0.0, (1.0 - tokens) / self._rate)
