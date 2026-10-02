"""Offline tests for the local inference backend (Claim A).

No network: urllib.request.urlopen is monkeypatched. No paid calls.
"""
import json
from decimal import Decimal

import pytest

import benchmark_runner.local_provider as local_mod
from benchmark_runner.local_provider import LocalProvider, check_local_server
from benchmark_runner.runner import make_provider
from benchmark_runner.provider import OpenAIProvider
from benchmark_runner.accounting import Budget
from benchmark_runner.schema import validate_call


class FakeHandle:
    headers = {}
    def __init__(self, payload):
        self._payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self): return json.dumps(self._payload).encode()


class FakeStore:
    def __init__(self):
        self.log = []
    def artifact(self, data):
        return "artifact-sha"
    def append(self, kind, event):
        assert kind in ("calls", "budget")
        self.log.append((kind, event))
    def events(self, kind):
        return [e for k, e in self.log if k == kind]


IDENTITY = {"experiment_id": "exp", "run_id": "run0123456789ab", "arm": "repair_ordinary",
            "task_id": "t1", "repeat": 1, "attempt_id": "a1", "purpose": "test"}
CFG = {"model": "qwen3-8b-local", "max_output_tokens": 64, "provider_backend": "local"}


def _route(models_payload, chat_payload):
    def fake(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if url.endswith("/models"):
            return FakeHandle(models_payload)
        return FakeHandle(chat_payload)
    return fake


def _chat_payload(model="qwen3-8b-local"):
    return {"id": "chatcmpl-1", "model": model,
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
                      "prompt_tokens_details": {"cached_tokens": 0},
                      "completion_tokens_details": {"reasoning_tokens": 0}}}


def test_model_name_required(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)
    with pytest.raises(ValueError, match="LOCAL_MODEL_NAME"):
        check_local_server()


def test_check_local_server_rejects_wrong_checkpoint(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    monkeypatch.setattr("urllib.request.urlopen",
                        _route({"data": [{"id": "some-other-model"}]}, {}))
    with pytest.raises(ValueError, match="wrong checkpoint"):
        check_local_server()


def test_check_local_server_fail_closed_when_down(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    def fail(*a, **k):
        raise TimeoutError()
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(ValueError, match="unreachable"):
        check_local_server()


def test_query_zero_cost_and_openai_params_omitted(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    captured = {}
    def fake(req, *a, **k):
        url = req.full_url
        if url.endswith("/models"):
            return FakeHandle({"data": [{"id": "qwen3-8b-local"}]})
        captured["payload"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.header_items())
        return FakeHandle(_chat_payload())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    store = FakeStore()
    provider = LocalProvider(CFG, store, Budget(store, "100", "25"), IDENTITY)
    assert provider.query([{"role": "user", "content": "hi"}], "repair", 30) == "ok"
    # No OpenAI-only parameters leak into the local payload.
    assert "reasoning_effort" not in captured["payload"]
    assert "service_tier" not in captured["payload"]
    assert "Authorization" not in captured["headers"]
    calls = [e for k, e in store.log if k == "calls"]
    assert len(calls) == 1
    event = calls[0]
    assert event["cost_basis"] == "local_inference"
    assert event["cost"] == "0"
    assert event["provider"] == "local"
    assert event["price_snapshot_id"] == "local-inference"
    validate_call(event)  # schema accepts the local cost basis
    budget_events = [e for k, e in store.log if k == "budget"]
    assert [e["status"] for e in budget_events] == ["reserved", "settled"]
    assert all(Decimal(e["amount"]) == 0 for e in budget_events)


def test_make_provider_selects_backend(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    monkeypatch.setattr("urllib.request.urlopen",
                        _route({"data": [{"id": "qwen3-8b-local"}]}, {}))
    store = FakeStore()
    budget = Budget(store, "100", "25")
    assert isinstance(make_provider(CFG, store, budget, IDENTITY), LocalProvider)
    assert isinstance(make_provider({}, store, budget, IDENTITY), OpenAIProvider)


def test_schema_accepts_local_inference_cost_basis():
    event = {"experiment_id": "e", "run_id": "r", "arm": "repair_ordinary",
             "task_id": "t", "repeat": 1, "attempt_id": "a", "phase": "repair",
             "call_id": "c", "request_id": None, "provider": "local",
             "model": "qwen3-8b-local", "response_model": "qwen3-8b-local",
             "started_at": "2026-09-21T00:00:00Z", "ended_at": "2026-09-21T00:00:01Z",
             "duration_seconds": 1.0, "input_tokens": 10, "cached_input_tokens": 0,
             "output_tokens": 2, "reasoning_tokens": 0, "unknown_reason": None,
             "price_snapshot_id": "local-inference", "cost_basis": "local_inference",
             "currency": "USD", "cost": "0", "retry": 0, "error": None,
             "artifacts": {"request": "x", "response": "y"}}
    validate_call(event)


def test_extract_text_prefers_content():
    from benchmark_runner.local_provider import _extract_text
    text, fallback, stripped = _extract_text(
        {"role": "assistant", "content": '{"action": "done"}'})
    assert text == '{"action": "done"}'
    assert fallback is False and stripped is False


def test_extract_text_falls_back_to_reasoning_content():
    from benchmark_runner.local_provider import _extract_text
    # llama.cpp with --reasoning-format splits the answer out of content.
    text, fallback, stripped = _extract_text(
        {"role": "assistant", "content": "",
         "reasoning_content": '{"action": "shell", "command": "true"}'})
    assert text == '{"action": "shell", "command": "true"}'
    assert fallback is True


def test_extract_text_strips_think_blocks():
    from benchmark_runner.local_provider import _extract_text
    # Default llama.cpp behavior: Qwen3 <think> blocks land in content.
    text, fallback, stripped = _extract_text(
        {"role": "assistant",
         "content": "<think>Let me check the code.</think>\n{\"action\": \"done\"}"})
    assert text == '{"action": "done"}'
    assert stripped is True and fallback is False


def test_extract_text_empty_when_nothing():
    from benchmark_runner.local_provider import _extract_text
    text, fallback, stripped = _extract_text({"role": "assistant"})
    assert text == ""
    assert fallback is False and stripped is False
