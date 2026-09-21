# Plan: TTL cache with LRU eviction

1. Per-instance dict: key -> [value, expiry_or_None, seq]. `seq` is a
   monotonically increasing access counter for LRU; `expiry` is an absolute
   clock reading or None (C04, C07).
2. `set(key, value, ttl=None)`: resolve `ttl = default_ttl if ttl is None
   else ttl` — never `ttl or default_ttl` (C06). Validate non-negative.
   Purge expired entries at `now`, then if at `maxsize` evict the live entry
   with the smallest seq (C04). Store `[deepcopy(value), expiry, 0]` and
   refresh seq (C03: overwrite replaces everything; C05: deepcopy).
3. `get(key, default=None)`: missing -> default. Expired (`now > expiry`,
   note strict `>`: valid AT the instant, C02) -> delete, return default.
   Else refresh seq (recency, not expiry) and return `deepcopy(value)` (C05).
4. `delete(key)`: `pop(key, None)`.
5. `__len__`: purge expired at now, return live count.
6. Clock: `self._clock = clock if clock is not None else time.monotonic`,
   called once per public method.
7. `__init__` raises ValueError for `maxsize <= 0`; negative explicit ttl in
   `set` raises ValueError.
