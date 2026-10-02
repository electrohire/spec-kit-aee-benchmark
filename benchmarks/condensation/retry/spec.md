# Retry with backoff

Build `retry.py` with function

`call_with_retry(func, max_attempts, backoff, sleep=None, retry_on=(Exception,)) -> Any`

which calls `func()` and retries on failure.

`sleep` is an injectable sleep function (defaults to `time.sleep`); tests
inject a fake. `retry_on` is a tuple of exception types that trigger a
retry.

## C01: success returns
The first call's return value is returned as-is. No sleep happens when the
first call succeeds.

## C02: bounded attempts
At most `max_attempts` total calls: 1 initial plus retries. `func` is called
at most `max_attempts` times in total (1 initial attempt plus up to
`max_attempts - 1` retries). `max_attempts < 1` raises `ValueError`.

## C03: backoff schedule
Retry `n` sleeps `backoff * 2 ** (n - 1)` seconds. Before retry number `n`
(1-indexed: the first retry is `n = 1`), sleep for `backoff * 2 ** (n - 1)`
seconds: `backoff, 2*backoff, 4*backoff, ...`. `backoff` must be
non-negative; negative raises `ValueError`.

## C04: selective retry
Non-`retry_on` exceptions propagate immediately, with no sleep. An exception
type not listed in `retry_on` propagates immediately with no further
attempts and no sleep. When attempts are exhausted, the LAST exception
raised by `func` is re-raised (not wrapped). This selective-retry rule is
stated here once.

## C05: no pre-sleep
No sleep ever happens before the first call to `func`. (Negative
constraint.)

## C06: exact sleep values
`sleep` gets exactly the C03 values in order, no extras. The injected
`sleep` is called with exactly the values from the C03 schedule, in order:
`backoff`, then `2*backoff`, then `4*backoff`, and so on. No extra calls, no
rounding. This is stated here once.

## C07: single-class retry_on
A single exception class works as a one-tuple `retry_on`. `retry_on` may be
passed as a single exception class instead of a tuple; it is treated as a
one-tuple.

## C08: no wrapper
The last exception is re-raised unwrapped; no wrapper types. Wrapping the
final failure in a dedicated `RetryExhaustedError` (or any other wrapper
type) looks like an improvement, but the specified behavior is to re-raise
the last exception unwrapped (C04). "Fixing" this non-defect breaks the
contract. This is stated here once.
