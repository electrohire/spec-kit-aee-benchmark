"""Hidden acceptance tests for ratelimit. Every test is pinned to >= 1
constraint id via PINS (checked by the alignment gate)."""
import pytest
from ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


PINS = {
    "test_c01_consume_and_deny": ["C01"],
    "test_c01_new_key_full_bucket": ["C01"],
    "test_c01_constructor_validation": ["C01"],
    "test_c02_key_isolation": ["C02"],
    "test_c02_time_does_not_leak_across_keys": ["C02"],
    "test_c03_fractional_refill": ["C03"],
    "test_c03_capacity_cap": ["C03"],
    "test_c04_allow_does_not_sleep": ["C04"],
    "test_c05_instances_independent": ["C05"],
    "test_c06_exact_boundary_usable": ["C06"],
    "test_c06_no_truncation": ["C06"],
    "test_c07_retry_after_now": ["C07"],
    "test_c07_retry_after_future": ["C07"],
}


def test_c01_consume_and_deny():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=2.0, clock=c)
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    assert rl.allow("a") is False  # bucket empty, nothing consumed


def test_c01_new_key_full_bucket():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=3.0, clock=c)
    assert rl.allow("new") is True


def test_c01_constructor_validation():
    with pytest.raises(ValueError):
        RateLimiter(rate=0, capacity=1.0)
    with pytest.raises(ValueError):
        RateLimiter(rate=1.0, capacity=-2.0)


def test_c02_key_isolation():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    assert rl.allow("b") is True  # b unaffected by a's consumption


def test_c02_time_does_not_leak_across_keys():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert rl.allow("a") is True
    c.advance(10.0)
    assert rl.allow("a") is True  # a refilled
    # b was never touched: still exactly one token, not affected by a's refill
    assert rl.allow("b") is True
    assert rl.allow("b") is False


def test_c03_fractional_refill():
    c = FakeClock()
    rl = RateLimiter(rate=2.0, capacity=2.0, clock=c)
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    c.advance(0.5)  # half a second -> exactly one token at rate 2.0
    assert rl.allow("a") is True
    assert rl.allow("a") is False


def test_c03_capacity_cap():
    c = FakeClock()
    rl = RateLimiter(rate=10.0, capacity=2.0, clock=c)
    c.advance(100.0)  # far more idle time than a full bucket needs
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    assert rl.allow("a") is False  # capped at 2, no banking


def test_c04_allow_does_not_sleep():
    c = FakeClock()
    rl = RateLimiter(rate=0.001, capacity=1.0, clock=c)
    assert rl.allow("a") is True
    start = c.t
    assert rl.allow("a") is False
    assert c.t == start  # fake clock never advanced: allow did not sleep


def test_c05_instances_independent():
    c = FakeClock()
    r1 = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    r2 = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert r1.allow("k") is True
    assert r1.allow("k") is False
    assert r2.allow("k") is True  # r2 unaffected by r1
    # No mutable class-level state: no dict/set/list values in the class dict.
    assert not any(isinstance(v, (dict, set, list)) for v in vars(RateLimiter).values())


def test_c06_exact_boundary_usable():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=2.0, clock=c)
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    c.advance(1.0)  # exactly one token becomes available at this instant
    assert rl.allow("a") is True  # boundary token usable immediately


def test_c06_no_truncation():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=2.0, clock=c)
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    c.advance(0.5)
    # Half a token is not enough -- and this call triggers a refill, so a
    # truncating implementation banks 0 here and can never recover it.
    assert rl.allow("a") is False
    c.advance(0.5)
    # Two half-token refills must accumulate to a whole token.
    assert rl.allow("a") is True


def test_c07_retry_after_now():
    c = FakeClock()
    rl = RateLimiter(rate=1.0, capacity=1.0, clock=c)
    assert rl.retry_after("a") == 0.0


def test_c07_retry_after_future():
    c = FakeClock()
    rl = RateLimiter(rate=2.0, capacity=1.0, clock=c)
    assert rl.allow("a") is True
    assert rl.retry_after("a") == pytest.approx(0.5)
    assert rl.retry_after("a") >= 0.0
