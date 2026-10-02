"""Public tests for ratelimit: basic happy path only.

These must pass on BOTH the reference and the trap implementation: they
deliberately use generous margins so they cannot catch the boundary trap.
They do not exercise subtle (C02, C06), negative (C05), or boundary detail.
"""
from ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_public_allow_basic():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=2.0, clock=c)
    assert rl.allow("user") is True
    assert rl.allow("user") is True
    assert rl.allow("user") is False


def test_public_refill():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert rl.allow("user") is True
    assert rl.allow("user") is False
    c.advance(5.0)  # generous: well over one token's worth
    assert rl.allow("user") is True


def test_public_retry_after():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert rl.retry_after("user") == 0.0
    assert rl.allow("user") is True
    assert rl.retry_after("user") > 0.0
