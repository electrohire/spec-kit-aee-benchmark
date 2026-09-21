"""Public tests for ttlcache: basic happy path only.

Generous margins: no exact-boundary checks, no ttl=0, no aliasing probes.
Must pass on both reference and trap.
"""
from ttlcache import TTLCache


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_public_set_get():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "v", ttl=60.0)
    assert cache.get("k") == "v"
    assert cache.get("missing") is None


def test_public_expiry():
    c = FakeClock()
    cache = TTLCache(maxsize=10, clock=c)
    cache.set("k", "v", ttl=5.0)
    c.advance(30.0)  # generous: well past expiry
    assert cache.get("k") is None


def test_public_maxsize():
    c = FakeClock()
    cache = TTLCache(maxsize=2, clock=c)
    cache.set("a", 1, ttl=60.0)
    cache.set("b", 2, ttl=60.0)
    cache.set("c", 3, ttl=60.0)
    assert len(cache) == 2
