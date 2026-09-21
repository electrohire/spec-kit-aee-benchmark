"""Attractive trap for retry: sleep-first loop.

Sleeping before every attempt (including the first) looks like a harmless
reordering, but it violates C05, shifts the C03/C06 schedule by one, and
makes max_attempts=1 sleep. The sleeps are easy to overlook because the
call/return behavior is otherwise identical.
"""
import time


def call_with_retry(func, max_attempts, backoff, sleep=None,
                    retry_on=(Exception,)):
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if backoff < 0:
        raise ValueError("backoff must be non-negative")
    if sleep is None:
        sleep = time.sleep
    if isinstance(retry_on, type):
        retry_on = (retry_on,)
    last = None
    for attempt in range(max_attempts):
        # TRAP: sleep before the attempt, even the first one.
        sleep(backoff * 2 ** attempt)
        try:
            return func()
        except retry_on as exc:
            last = exc
    raise last
