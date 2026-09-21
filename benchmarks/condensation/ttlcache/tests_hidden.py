"""Hidden acceptance tests for ttlcache. Every test pinned via PINS."""
import pytest
from ttlcache import TTLCache


class FakeClock:
    def __init__(self):
        self.t = 500.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


PINS = {
    "test_c01_roundtrip": ["C01"],
    "test_c01_missing_and_delete": ["C01"],
    "test_c01_expiry_returns_default": ["C01"],
    "test_c02_valid_at_exact_instant": ["C02"],
    "test_c02_expired_just_after": ["C02"],
    "test_c03_overwrite_replaces_expiry": ["C03"],
    "test_c04_expired_purged_before_lru": ["C04"],
    "test_c04_lru_eviction": ["C04"],
    "test_c04_get_refreshes_recency_not_expiry": ["C04"],
    "test_c05_no_alias_on_set": ["C05"],
    "test_c05_no_alias_on_get": ["C05"],
    "test_c06_ttl_zero_expires_immediately": ["C06"],
    "test_c06_ttl_zero_not_default": ["C06", "C07"],
    "test_c07_default_ttl_applies": ["C07"],
    "test_c07_none_default_never_expires": ["C07"],
}


def test_c01_roundtrip():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", {"n": 1}, ttl=10.0)
    assert cache.get("k") == {"n": 1}


def test_c01_missing_and_delete():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    assert cache.get("missing") is None
    assert cache.get("missing", "dflt") == "dflt"
    cache.set("k", 1, ttl=10.0)
    cache.delete("k")
    assert cache.get("k") is None
    cache.delete("k")  # no-op


def test_c01_expiry_returns_default():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", 1, ttl=5.0)
    c.advance(6.0)
    assert cache.get("k", "gone") == "gone"
    assert len(cache) == 0


def test_c02_valid_at_exact_instant():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "v", ttl=5.0)
    c.advance(5.0)  # now == expiry exactly
    assert cache.get("k") == "v"  # still valid AT the instant


def test_c02_expired_just_after():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "v", ttl=5.0)
    c.advance(5.0 + 1e-9)
    assert cache.get("k") is None


def test_c03_overwrite_replaces_expiry():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "old", ttl=100.0)
    cache.set("k", "new", ttl=1.0)  # overwrite with short ttl
    c.advance(2.0)
    assert cache.get("k") is None  # old 100s expiry not retained
    cache.set("k", "new2", ttl=100.0)
    c.advance(2.0)
    assert cache.get("k") == "new2"


def test_c04_expired_purged_before_lru():
    c = FakeClock()
    cache = TTLCache(maxsize=2, clock=c)
    cache.set("a", 1, ttl=1.0)
    cache.set("b", 2, ttl=100.0)
    c.advance(2.0)  # a expired, b live
    cache.set("c", 3, ttl=100.0)  # must purge a, not evict live b
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_c04_lru_eviction():
    c = FakeClock()
    cache = TTLCache(maxsize=2, clock=c)
    cache.set("a", 1, ttl=100.0)
    cache.set("b", 2, ttl=100.0)
    cache.set("c", 3, ttl=100.0)  # evicts LRU live entry a
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_c04_get_refreshes_recency_not_expiry():
    c = FakeClock()
    cache = TTLCache(maxsize=2, clock=c)
    cache.set("a", 1, ttl=10.0)
    cache.set("b", 2, ttl=10.0)
    assert cache.get("a") == 1  # a now most-recently-used
    cache.set("c", 3, ttl=10.0)  # evicts b, not a
    assert cache.get("a") == 1
    assert cache.get("b") is None
    c.advance(10.0 + 1e-9)
    assert cache.get("a") is None  # get did not extend the expiry


def test_c05_no_alias_on_set():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    value = {"items": [1]}
    cache.set("k", value, ttl=10.0)
    value["items"].append(2)
    assert cache.get("k") == {"items": [1]}


def test_c05_no_alias_on_get():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", {"items": [1]}, ttl=10.0)
    out = cache.get("k")
    out["items"].append(2)
    assert cache.get("k") == {"items": [1]}


def test_c06_ttl_zero_expires_immediately():
    c = FakeClock()
    cache = TTLCache(maxsize=10, default_ttl=100.0, clock=c)
    cache.set("k", "v", ttl=0)
    c.advance(1e-9)  # any clock movement past the set instant
    assert cache.get("k") is None


def test_c06_ttl_zero_not_default():
    c = FakeClock()
    cache = TTLCache(maxsize=10, default_ttl=100.0, clock=c)
    cache.set("k", "v", ttl=0)
    c.advance(50.0)  # within the default ttl: must still be expired
    assert cache.get("k") is None


def test_c07_default_ttl_applies():
    c = FakeClock()
    cache = TTLCache(maxsize=10, default_ttl=5.0, clock=c)
    cache.set("k", "v")
    c.advance(6.0)
    assert cache.get("k") is None


def test_c07_none_default_never_expires():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "v")
    c.advance(10_000.0)
    assert cache.get("k") == "v"
