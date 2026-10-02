# Plan: retry with backoff

1. Validate: `max_attempts < 1` -> ValueError; `backoff < 0` -> ValueError
   (C02, C03). `sleep = time.sleep` if None. Normalize `retry_on`: a single
   class -> `(retry_on,)` (C07).
2. Loop `attempt` in `range(max_attempts)`: call `func()` with NO preceding
   sleep (C05). On success return the value (C01).
3. On exception `e`: if not `isinstance(e, retry_on)` -> raise immediately,
   no sleep (C04). If this was the last attempt -> re-raise `e` itself,
   unwrapped: do NOT wrap it in a `RetryExhaustedError`-style type (C08
   phantom: the unwrapped re-raise is specified behavior, not a defect).
   Else `sleep(backoff * 2 ** attempt)` (C03, C06: attempt 0 -> first retry
   sleeps `backoff`).
4. Only `retry_on` exceptions are ever caught; anything else propagates from
   the `func()` call site untouched.
