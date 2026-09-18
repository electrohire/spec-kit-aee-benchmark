# cachetools milestone 3

Resume after a context-free handoff with repository files and notes preserved. R01-R06 remain active.
R07: Constructor now accepts timer=None (default time.monotonic). put adds ttl=None, where None means no expiration and a finite nonnegative int/float excluding bool sets expiry at timer()+ttl. Invalid TTL raises ValueError before any mutation. TTL zero is immediately expired. At the exact expiry boundary a key is expired.
R08: Expired entries must be removed before get, put, len, resize and invalidation, without touching the recency of surviving entries. Overwriting an entry replaces its prior expiry. Tag invalidation counts only live entries. A missing/expired get raises KeyError. Existing callers without timer/ttl retain previous behavior.

Implementation source: src/cachetools/tagged.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.
