# Plan: token-bucket rate limiter

1. Per-instance dict mapping key -> [tokens: float, last: float]. No
   class-level or module-level mutable state (C05).
2. On entry to each public method, refill the key's bucket first:
   `tokens = min(capacity, tokens + (now - last) * rate)`, then set
   `last = now`. Keep fractional tokens (C03, C06).
3. New keys start at `(capacity, now)` — a full bucket (C01, C02).
4. `allow(key)`: after refill, if `tokens >= 1.0`, store `tokens - 1.0` and
   return True; else return False without consuming (C01). No sleeping,
   ever (C04).
5. `retry_after(key)`: after refill, return 0.0 if `tokens >= 1.0`, else
   `max(0.0, (1.0 - tokens) / rate)` (C07).
6. Clock: `self._clock = clock if clock is not None else time.monotonic`;
   call it exactly once per public method so a fake clock advances
   deterministically.
7. `__init__` raises ValueError for `rate <= 0` or `capacity <= 0`.
