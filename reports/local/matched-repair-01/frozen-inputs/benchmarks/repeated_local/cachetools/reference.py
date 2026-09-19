from copy import deepcopy
from math import isfinite
from time import monotonic
from cachetools import Cache, LRUCache

class TaggedCache:
    def __init__(self, maxsize, timer=None):
        self._validate_size(maxsize)
        self._cache = LRUCache(maxsize)
        self._timer = monotonic if timer is None else timer

    @staticmethod
    def _validate_size(size):
        if type(size) is not int or size <= 0:
            raise ValueError('invalid maxsize')

    @staticmethod
    def _tags(tags):
        if isinstance(tags, str):
            raise ValueError('tags must not be a string')
        try:
            items = list(tags)
        except TypeError as exc:
            raise ValueError('invalid tags') from exc
        if any(not isinstance(tag, str) for tag in items):
            raise ValueError('tag must be a string')
        return set(items)

    def _expire(self):
        now = self._timer()
        for key in list(self._cache):
            entry = Cache.__getitem__(self._cache, key)
            if entry[2] is not None and now >= entry[2]:
                del self._cache[key]

    @property
    def maxsize(self):
        return self._cache.maxsize

    def __len__(self):
        self._expire()
        return len(self._cache)

    def put(self, key, value, tags=(), ttl=None):
        tags = self._tags(tags)
        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int,float)) or not isfinite(ttl) or ttl < 0):
            raise ValueError('invalid ttl')
        value = deepcopy(value)
        hash(key)
        self._expire()
        expiry = None if ttl is None else self._timer() + ttl
        self._cache[key] = (value, tags, expiry)
        self._expire()

    def get(self, key):
        self._expire()
        return deepcopy(self._cache[key][0])

    def invalidate(self, tag):
        return self.invalidate_many([tag])

    def invalidate_many(self, tags, mode='any'):
        tags = self._tags(tags)
        if mode not in ('any','all'):
            raise ValueError('invalid mode')
        self._expire()
        if not tags:
            return 0
        doomed = []
        for key in list(self._cache):
            current = Cache.__getitem__(self._cache,key)[1]
            if (bool(current & tags) if mode == 'any' else tags <= current):
                doomed.append(key)
        for key in doomed:
            del self._cache[key]
        return len(doomed)

    def resize(self, maxsize):
        self._validate_size(maxsize)
        self._expire()
        old = self._cache
        keys = list(old._LRUCache__order)
        new = LRUCache(maxsize)
        for key in keys:
            new[key] = Cache.__getitem__(old,key)
        self._cache = new
