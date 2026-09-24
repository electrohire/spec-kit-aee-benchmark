"""Regression tests for the diagnose-arm poisoning root cause (2026-09-22).

Root cause: one failed provider call recorded unknown usage (input/output
tokens None, cost None) and raised ProviderError. The next step of the phase
loop saw ANY call with unknown usage and raised
LimitHit("unknown token usage; cannot enforce attempt token ceiling"), killing
the attempt with no diagnostic evidence and blocking all dependent repair arms.

The fix: unknown-usage calls are charged their full max_input + max_output
reservation (conservative, fail-closed), so a transient provider failure
never kills the attempt at the ceiling check.

These tests drive the real run_matched_phase loop and the real run() loop
with stub agents/transport, pinning the fixed behavior end to end.
"""
import time

import pytest

from benchmark_runner.accounting import Budget, attempt_token_usage
from benchmark_runner.matched_repair import run_matched_phase
from benchmark_runner.provider import ProviderError
from benchmark_runner.store import Store


def _identity(attempt_id="test-attempt"):
    return {"experiment_id": "e", "run_id": "r", "task_id": "tinydb/p1",
            "repeat": 1, "attempt_id": attempt_id, "arm": "diagnose"}


def _cfg():
    return {"max_input_tokens": 1000, "max_output_tokens": 100,
            "token_cap": 100_000, "max_calls": 8}


class _StubModel:
    def __init__(self):
        self.phase = None
        self.last = None

    def begin_phase(self, claims, limit):
        pass


class _PoisonedAgent:
    """First query() records a failed physical call (unknown usage, the exact
    shape OpenAIProvider logs for a 429-exhausted request) and raises
    ProviderError; the second query() succeeds with a done action.

    Under the old code the phase died at the next step's ceiling check with
    LimitHit("unknown token usage; cannot enforce attempt token ceiling").
    """

    def __init__(self, store, identity, model):
        self.store, self.identity, self.model = store, identity, model
        self.n_calls = 0
        self.messages = []
        self._queries = 0

    def add_messages(self, *msgs):
        self.messages.extend(msgs)

    def execute_actions(self, message):
        pass

    def query(self):
        self._queries += 1
        if self._queries == 1:
            self.n_calls += 1
            self.store.append("calls", {
                **self.identity, "call_id": "failed-physical-1", "request_id": None,
                "phase": "diagnose", "provider": "openai", "model": "m",
                "response_model": None,
                "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:00:01+00:00",
                "duration_seconds": 1.0, "input_tokens": None, "cached_input_tokens": None,
                "output_tokens": None, "reasoning_tokens": None,
                "unknown_reason": "HTTPError", "price_snapshot_id": "s",
                "cost_basis": "list_price_estimate", "currency": "USD", "cost": None,
                "retry": 2, "error": "HTTPError", "artifacts": {}})
            raise ProviderError("HTTPError")
        self.n_calls += 1
        self.model.last = {"action": "done", "summary": "diagnostic complete"}
        return "done-message"


def test_failed_provider_call_does_not_poison_attempt(tmp_path):
    store = Store(tmp_path)
    identity = _identity()
    model = _StubModel()
    agent = _PoisonedAgent(store, identity, model)
    result = run_matched_phase(agent, model, store, identity, _cfg(),
                               "diagnose", "instructions", "spec", limit=4,
                               deadline=time.monotonic() + 60, claims=None)
    # The attempt continued past the failed call instead of dying at the
    # ceiling check: the phase completed with the stub's done action.
    assert result["completed"] is True
    assert result["done"]["action"] == "done"
    # The failure was recorded honestly, not retried away or hidden.
    assert any("ProviderError" in e for e in result["errors"])
    calls = [c for c in store.events("calls") if c["attempt_id"] == identity["attempt_id"]]
    assert len(calls) == 1
    failed = calls[0]
    assert failed["error"] == "HTTPError" and failed["cost"] is None
    assert failed["input_tokens"] is None and failed["unknown_reason"] == "HTTPError"
    # And the ceiling still accounts for it conservatively.
    assert attempt_token_usage(calls, _cfg()) == 1100


def test_run_preskips_dependent_repair_before_started_event(tmp_path, monkeypatch):
    """run() pre-skips a dependent repair arm when the task's diagnostic
    evidence is unavailable: no attempt-start event, no inference, and the
    honest "skipped" record. A repair arm WITH diagnostics still runs."""
    from benchmark_runner import runner as runner_mod

    monkeypatch.setattr(runner_mod, "verify_freeze", lambda root, manifest: None)
    monkeypatch.setattr(runner_mod, "validate_live", lambda manifest, smoke=False: None)

    class FakeSandbox:
        details = {"image": "img", "digest": "d"}
        def __init__(self, image): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): return {"exit_code": 0, "stdout": "base\n"}

    monkeypatch.setattr(runner_mod, "DockerSandbox", FakeSandbox)
    monkeypatch.setattr(runner_mod, "make_provider", lambda *a, **k: object())

    def fake_execute(root, task, arm, provider, sandbox, store, identity, cfg, manifest):
        if arm == "diagnose":
            store.append("diagnostics", {**identity, "timestamp": "t", "claims": []})
        return {}

    monkeypatch.setattr(runner_mod, "execute_attempt", fake_execute)

    tasks = [
        {"instance_id": "tinydb/p1", "image": "img", "base_commit": "base"},
        {"instance_id": "tinydb/p2", "image": "img", "base_commit": "base"},
    ]
    manifest = {
        "freeze_id": "f" * 16,
        "config": {"purpose": "test", "global_cap_usd": 100, "attempt_cap_usd": 25,
                   "provider_backend": "local", "timeout_seconds": 60},
        "tasks": {"tasks": tasks},
        "schedule": [
            {"task_id": "tinydb/p1", "arm": "diagnose", "attempt_id": "d1", "repeat": 1},
            {"task_id": "tinydb/p1", "arm": "repair_ordinary", "attempt_id": "r1", "repeat": 1},
            # tinydb/p2 has no diagnose entry: its repair arm must pre-skip.
            {"task_id": "tinydb/p2", "arm": "repair_ordinary", "attempt_id": "r2", "repeat": 1},
        ],
    }
    attempts = runner_mod.run("/tmp", manifest, str(tmp_path / "out"))
    by_id = {}
    for e in attempts:
        by_id.setdefault(e["attempt_id"], []).append(e["status"])

    # Diagnose and the repair with diagnostics ran to completion.
    assert by_id["d1"] == ["started", "completed"]
    assert by_id["r1"] == ["started", "completed"]
    # The repair without diagnostics was pre-skipped: exactly one record,
    # status "skipped", and crucially no "started" event (no inference was
    # ever issued for it).
    assert by_id["r2"] == ["skipped"]
    skipped = [e for e in attempts if e["attempt_id"] == "r2"][0]
    assert "diagnostic evidence not recorded" in skipped["reason"]
    assert "no inference issued" in skipped["reason"]
