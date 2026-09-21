"""Hidden acceptance tests for retry. Every test pinned via PINS."""
import pytest
from retry import call_with_retry

PINS = {
    "test_c01_success_no_sleep": ["C01"],
    "test_c02_bounded_attempts": ["C02"],
    "test_c02_max_attempts_one": ["C02"],
    "test_c02_invalid_max_attempts": ["C02"],
    "test_c03_backoff_schedule": ["C03"],
    "test_c03_negative_backoff": ["C03"],
    "test_c04_non_retryable_propagates": ["C04"],
    "test_c04_last_exception_reraised": ["C04"],
    "test_c05_no_sleep_before_first": ["C05"],
    "test_c06_exact_sleep_values": ["C06"],
    "test_c07_single_class": ["C07"],
    "test_c08_no_wrapper_phantom": ["C08"],
}


def test_c01_success_no_sleep():
    sleeps = []
    calls = []

    def func():
        calls.append(1)
        return "ok"

    assert call_with_retry(func, 3, 1.0, sleep=sleeps.append) == "ok"
    assert calls == [1]
    assert sleeps == []


def test_c02_bounded_attempts():
    calls = []

    def func():
        calls.append(1)
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        call_with_retry(func, 3, 1.0, sleep=lambda s: None)
    assert len(calls) == 3


def test_c02_max_attempts_one():
    calls = []
    sleeps = []

    def func():
        calls.append(1)
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        call_with_retry(func, 1, 5.0, sleep=sleeps.append)
    assert len(calls) == 1
    assert sleeps == []


def test_c02_invalid_max_attempts():
    with pytest.raises(ValueError):
        call_with_retry(lambda: 1, 0, 1.0, sleep=lambda s: None)


def test_c03_backoff_schedule():
    sleeps = []
    calls = []

    def func():
        calls.append(1)
        if len(calls) < 4:
            raise RuntimeError("x")
        return "ok"

    assert call_with_retry(func, 5, 0.5, sleep=sleeps.append) == "ok"
    assert sleeps == [0.5, 1.0, 2.0]


def test_c03_negative_backoff():
    with pytest.raises(ValueError):
        call_with_retry(lambda: 1, 3, -1.0, sleep=lambda s: None)


def test_c04_non_retryable_propagates():
    calls = []
    sleeps = []

    def func():
        calls.append(1)
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        call_with_retry(func, 3, 1.0, sleep=sleeps.append,
                        retry_on=(RuntimeError,))
    assert len(calls) == 1
    assert sleeps == []


def test_c04_last_exception_reraised():
    errs = [RuntimeError("a"), RuntimeError("b")]
    it = iter(errs)

    def func():
        raise next(it)

    with pytest.raises(RuntimeError) as ei:
        call_with_retry(func, 2, 1.0, sleep=lambda s: None)
    assert ei.value is errs[1]


def test_c05_no_sleep_before_first():
    sleeps = []
    assert call_with_retry(lambda: 1, 3, 2.0, sleep=sleeps.append) == 1
    assert sleeps == []


def test_c06_exact_sleep_values():
    sleeps = []

    def func():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        call_with_retry(func, 4, 0.25, sleep=sleeps.append)
    assert sleeps == [0.25, 0.5, 1.0]


def test_c07_single_class():
    calls = []

    def func():
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("x")
        return "done"

    assert call_with_retry(func, 3, 1.0, sleep=lambda s: None,
                           retry_on=RuntimeError) == "done"
    assert len(calls) == 2


def test_c08_no_wrapper_phantom():
    # Phantom non-defect: the last exception must propagate unwrapped, not
    # inside a RetryExhaustedError-style wrapper.
    def func():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError) as ei:
        call_with_retry(func, 2, 1.0, sleep=lambda s: None)
    assert type(ei.value) is RuntimeError
