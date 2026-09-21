"""TTL cache with LRU eviction (reference implementation)."""
import time
from copy import deepcopy


class TTLCache:
    def __init__(self, maxsize, default_ttl=None, clock=None):
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if default_ttl is not None and default_ttl < 0:
            raise ValueError("default_ttl must be non-negative or None")
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._clock = clock if clock is not None else time.monotonic
        self._data = {}
        self._seq = 0

    def _purge_expired(self, now):
        for key in [k for k, (_, expiry, _) in self._data.items()
                    if expiry is not None and now > expiry]:
            del self._data[key]

    def _touch(self, key):
        self._seq += 1
        self._data[key][2] = self._seq

    def set(self, key, value, ttl=None):
        if ttl is None:
            ttl = self._default_ttl
        if ttl is not None and ttl < 0:
            raise ValueError("ttl must be non-negative or None")
        now = self._clock()
        self._purge_expired(now)
        expiry = None if ttl is None else now + ttl
        if key not in self._data and len(self._data) >= self._maxsize:
            lru = min(self._data, key=lambda k: self._data[k][2])
            del self._data[lru]
        self._data[key] = [deepcopy(value), expiry, 0]
        self._touch(key)

    def get(self, key, default=None):
        now = self._clock()
        entry = self._data.get(key)
        if entry is None:
            return default
        value, expiry, _ = entry
        if expiry is not None and now > expiry:
            del self._data[key]
            return default
        self._touch(key)
        return deepcopy(entry[0])

    def delete(self, key):
        self._data.pop(key, None)

    def __len__(self):
        self._purge_expired(self._clock())
        return len(self._data)
