"""Public tests for retry: basic happy path only.

Sleeps are discarded, so the sleep-first trap passes too.
"""
import pytest
from retry import call_with_retry


def test_public_success():
    assert call_with_retry(lambda: "ok", 3, 1.0, sleep=lambda s: None) == "ok"


def test_public_retries_then_succeeds():
    calls = []

    def func():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("x")
        return "win"

    assert call_with_retry(func, 5, 1.0, sleep=lambda s: None) == "win"
    assert len(calls) == 3


def test_public_exhausted():
    def func():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        call_with_retry(func, 2, 1.0, sleep=lambda s: None)
