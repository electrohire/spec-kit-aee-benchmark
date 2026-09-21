# Token-bucket rate limiter

Build `ratelimit.py` with class `RateLimiter(rate, capacity, clock=None)`.

`rate` is tokens per second (a positive float) and `capacity` is the maximum
burst size (a positive number). `clock` is an optional zero-argument callable
returning the current time in seconds; it defaults to `time.monotonic` and
tests inject a fake clock. Public API: `allow(key)` and `retry_after(key)`.
Construction with non-positive `rate` or `capacity` raises `ValueError`.

## C01: allow consumes token
`allow` consumes one token and returns True when a token is available. When
no token is available it returns False and consumes nothing. A brand-new key
starts with a full bucket.

## C02: per-key isolation
Each key has an independent bucket. Consuming tokens for one key, or the
passage of time observed through one key's calls, never changes another key's
token count. This isolation is stated here once and relied on throughout.

## C03: continuous refill
Tokens refill continuously at `rate`/second, keeping fractional tokens. For
example, at rate 2.0, half a second of idle time yields half a token. The
bucket never holds more than `capacity` tokens; idle time beyond a full
bucket is discarded rather than banked.

## C04: never blocks
`allow(key)` returns immediately in all cases. It must not sleep, wait, retry,
or perform any I/O.

## C05: no shared state
Two `RateLimiter` instances are fully independent, even with identical
parameters and keys. No class-level or module-level mutable state may leak
between instances. (Negative constraint.)

## C06: boundary tokens usable
Tokens available exactly at the current clock reading are consumable
immediately. If the bucket holds at least 1.0 tokens at time t, then `allow`
at time t returns True. Fractional tokens must be retained, never truncated
to integers.

## C07: retry_after estimate
`retry_after(key)` returns 0.0 when a token is available now. Otherwise it
returns the seconds until the bucket reaches one token, computed as
`(1 - tokens) / rate`, and it never returns a negative value.
