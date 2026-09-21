# Phase 2: implement the retry helper

{context_block}

Implement `/work/retry.py` with function
`call_with_retry(func, max_attempts, backoff, sleep=None, retry_on=(Exception,))`
as specified. Public tests are in `/work/tests_public.py`; run them with
`python -m pytest -q /work/tests_public.py`. Do not modify the public tests.
You have at most 8 actions, then return done with an honest summary of what
was implemented and any unresolved issues.
