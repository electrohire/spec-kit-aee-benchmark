# TTL cache with LRU eviction

Build `ttlcache.py` with class `TTLCache(maxsize, default_ttl=None,
clock=None)`.

`maxsize` is a positive integer bounding live entries. `default_ttl` is the
TTL in seconds applied when `set` is called without an explicit `ttl`;
`None` means entries never expire by default. `clock` is an optional
zero-argument callable returning seconds, defaulting to `time.monotonic`;
tests inject a fake clock. API: `set(key, value, ttl=None)`,
`get(key, default=None)`, `delete(key)`, `__len__`. Construction with
`maxsize <= 0` raises `ValueError`.

## C01: set/get with expiry
`get` returns the stored value until the TTL elapses, else `default`.
`set(key, value, ttl)` stores the value; `get` on a missing key returns
`default`. `delete(key)` removes the entry if present and is a no-op
otherwise.

## C02: expiry instant valid
An entry is live at the exact expiry instant and expires only after it.
With `expiry = set_time + ttl`, the entry is live iff `now <= expiry`. This
boundary rule is stated here once and relied on throughout.

## C03: overwrite restarts expiry
Overwriting a key replaces its value and restarts its expiry. The new
expiry comes from the call's TTL (or the default); the old expiry is never
retained.

## C04: evict expired then LRU
When `set` would exceed `maxsize`, expired entries are purged first. If the
cache is still full, the least-recently-used live entry is evicted. Access
recency covers both `get` and `set`: a successful `get` refreshes recency but
never extends the expiry.

## C05: defensive copies
The cache copies values on `set` and on `get`, never aliasing caller memory.
Mutating the object passed to `set` afterwards must not change the cached
value, and mutating the object returned by `get` must not change the cached
value. (Negative constraint.)

## C06: ttl=0 immediate
Explicit `ttl=0` expires the entry at once; it never falls back to the
default. It must not be confused with `ttl=None` (use the default): the
tempting `ttl or self._default_ttl` idiom turns an explicit 0 into the
default TTL. With `default_ttl=None`, `ttl=None` means the entry never
expires.

## C07: default TTL
Omitted `ttl` uses `default_ttl`; `None` means no expiry. An explicit `ttl`
always overrides the default, including `ttl=0`.
