import json

import pytest
from jsonschema import ValidationError

from benchmark_runner.accounting import Budget
from benchmark_runner.provider import OpenAIProvider, ProviderError
from benchmark_runner.store import Store


def _mock_transport(monkeypatch, response):
    # Mock the surrogate helper (no real credential exchange in tests).
    class FakeDC:
        @staticmethod
        def ensure_allowed_url(url, hosts): pass
        @staticmethod
        def add_surrogate_to_request(req, cred, allowed_hosts=None): pass
        @staticmethod
        def read_json_response(handle): return json.loads(handle.read())
    monkeypatch.setattr("benchmark_runner.provider.dc", FakeDC())
    # Auth resolution is a separate unit; pin it so the transport test
    # exercises query() without a live /models probe.
    monkeypatch.setattr("benchmark_runner.provider.resolve_auth", lambda: ("connector", None))
    class Handle:
        headers = {"x-request-id": "synthetic-request"}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps(response).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Handle())


def _provider(store, budget, arm="baseline"):
    return OpenAIProvider(dict(model="synthetic-model", reasoning_effort="low", max_input_tokens=1000,
          max_output_tokens=100, prices=dict(input=2, cached_input=1, output=4), price_snapshot_id="synthetic"),
          store, budget, {"attempt_id": "test", "experiment_id": "synthetic", "run_id": "synthetic",
                          "arm": arm, "task_id": "synthetic", "repeat": 1})


_SYNTHETIC_RESPONSE = {"model": "synthetic-model", "choices": [{"message": {"content": "done"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30,
                      "prompt_tokens_details": {"cached_tokens": 20},
                      "completion_tokens_details": {"reasoning_tokens": 10}}}


def test_real_transport_adapter_with_mock_response(tmp_path, monkeypatch):
    _mock_transport(monkeypatch, _SYNTHETIC_RESPONSE)
    store = Store(tmp_path)
    budget = Budget(store, 1, 1)
    provider = _provider(store, budget)
    assert provider.query([], "solve", 10) == "done"
    call = store.events("calls")[0]
    from benchmark_runner.schema import validate_call
    validate_call(call)
    with pytest.raises(ValidationError):
        validate_call({k: v for k, v in call.items() if k != "phase"})
    assert call["cost"] == "0.0003" and call["request_id"] == "synthetic-request"
    assert call["reasoning_tokens"] == 10
    # No credential material should appear in stored artifacts.
    assert "hsurr" not in "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    def fail(*a, **k): raise TimeoutError()
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10, retry=1)
    retry = store.events("calls")[1]
    assert retry["cost"] is None and retry["retry"] == 1
    assert budget.charges()[retry["call_id"]]["status"] == "reserved"


def test_query_validates_identity_before_spending(tmp_path, monkeypatch):
    # Fail-fast: an identity that cannot pass telemetry validation must raise
    # before any HTTP request (no spend) and before any budget reservation.
    def boom(*a, **k): raise AssertionError("HTTP request must not happen")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget, arm="not_an_arm")
    with pytest.raises(ValidationError):
        provider.query([], "solve", 10)
    assert store.events("calls") == []
    assert budget.charges() == {}


def test_query_settles_budget_when_post_request_validation_fails(tmp_path, monkeypatch):
    # If post-request telemetry validation rejects the event, the reservation
    # must still settle (no leaked reservation) and the error must propagate;
    # the invalid event itself is not logged.
    _mock_transport(monkeypatch, _SYNTHETIC_RESPONSE)
    def reject(event): raise ValidationError("synthetic telemetry rejection")
    monkeypatch.setattr("benchmark_runner.provider.validate_call", reject)
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget)
    with pytest.raises(ValidationError):
        provider.query([], "solve", 10)
    assert store.events("calls") == []
    charges = budget.charges()
    assert len(charges) == 1
    charge = next(iter(charges.values()))
    assert charge["status"] == "settled" and charge["amount"] == "0.0003"
def test_validate_call_accepts_matched_repair_arms():
    # Regression: the matched-repair cloud port logs calls with its own arm
    # vocabulary; the shared CALL_SCHEMA enum must accept them, otherwise paid
    # calls fail telemetry validation after the HTTP request (spend invisible).
    from benchmark_runner.schema import validate_call
    from benchmark_runner.matched_repair import MATCHED_ARMS
    base = {
        "experiment_id": "e", "run_id": "r", "task_id": "t", "repeat": 1,
        "attempt_id": "a", "phase": "p", "call_id": "c", "request_id": None,
        "provider": "openai", "model": "m", "response_model": "m",
        "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:00:01+00:00",
        "duration_seconds": 1.0, "input_tokens": 10, "cached_input_tokens": 0,
        "output_tokens": 5, "reasoning_tokens": 0, "unknown_reason": None,
        "price_snapshot_id": "s", "cost_basis": "list_price_estimate",
        "currency": "USD", "cost": "0.0001", "retry": 0, "error": None,
        "artifacts": {},
    }
    assert set(MATCHED_ARMS) == {"diagnose", "repair_ordinary", "repair_guided"}
    for arm in MATCHED_ARMS:
        validate_call({**base, "arm": arm})
