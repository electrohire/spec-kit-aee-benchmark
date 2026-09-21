"""Retry with exponential backoff (reference implementation)."""
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
    for attempt in range(max_attempts):
        try:
            return func()
        except retry_on as exc:
            if attempt == max_attempts - 1:
                raise
            sleep(backoff * 2 ** attempt)
