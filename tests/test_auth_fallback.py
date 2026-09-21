import json

import pytest

import benchmark_runner.provider as provider_mod
from benchmark_runner.provider import resolve_auth
from benchmark_runner.matched_repair import smoke_config, verify_reservation_bounds
from benchmark_runner.accounting import request_prices
from decimal import Decimal


class ModelsHandle:
    headers = {}
    def __init__(self, payload):
        self._payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self): return json.dumps(self._payload).encode()


def _reset_auth(monkeypatch):
    monkeypatch.setattr(provider_mod, "_AUTH", None)


def test_resolve_auth_env_fallback(monkeypatch):
    # No connector on the operator host: OPENAI_API_KEY is used after a
    # successful free /models probe.
    _reset_auth(monkeypatch)
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: ModelsHandle({"data": [{"id": "gpt-6-astra"}]}))
    assert resolve_auth() == ("env", "sk-test-not-a-real-key")
    # Cached: no second probe.
    assert resolve_auth() == ("env", "sk-test-not-a-real-key")


def test_resolve_auth_rejects_bad_key(monkeypatch):
    _reset_auth(monkeypatch)
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    def fail(*a, **k):
        raise TimeoutError()
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(ValueError, match="no usable OpenAI credential"):
        resolve_auth()


def test_resolve_auth_fail_closed_without_any_credential(monkeypatch):
    _reset_auth(monkeypatch)
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no usable OpenAI credential"):
        resolve_auth()


def test_reservation_bound_uses_conservative_max_rates():
    cfg = smoke_config()
    worst = verify_reservation_bounds(cfg)
    ceiling = request_prices(cfg)  # no usage -> max of short/long tiers
    per_call = (Decimal(cfg["max_input_tokens"]) * Decimal(str(ceiling["input"]))
                + Decimal(cfg["max_output_tokens"]) * Decimal(str(ceiling["output"]))
                ) / Decimal(1_000_000)
    assert Decimal(worst["per_call_usd"]) == per_call
    assert Decimal(worst["repair_attempt_usd"]) == per_call * 16
    assert Decimal(worst["diagnostic_attempt_usd"]) == per_call * 8
    # Worst-case repair reservation stays under the $25 attempt cap even at
    # the conservative (long-tier) reservation rates.
    assert Decimal(worst["repair_attempt_usd"]) < Decimal(str(cfg["attempt_cap_usd"]))
