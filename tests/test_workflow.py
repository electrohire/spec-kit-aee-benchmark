import json
from pathlib import Path

import pytest

from benchmark_runner.runner import execute_attempt
from benchmark_runner.store import Store, read_json
from benchmark_runner.workflow import assess, grounded_claims, phase_prompt, phases

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    def __init__(self):
        self.seen = []

    def query(self, messages, phase, timeout):
        self.seen.append(phase)
        if phase == "solve" and self.seen.count(phase) == 1:
            return json.dumps({"action": "shell", "command": "pytest -q"})
        return json.dumps({"action": "done", "summary": "SYNTHETIC fixture",
                           "claims": {"schema_version": "1.0", "claims": [{"id": "REQ-X"}]}})


class FakeSandbox:
    def __init__(self):
        self.staged = False

    def stage_workflow(self, root):
        self.staged = True

    def execute(self, command, timeout=60):
        return {"exit_code": 0, "stdout": "SYNTHETIC PATCH" if "git diff" in command else "1 passed", "stderr": ""}


@pytest.mark.parametrize("arm", ["baseline", "spec_kit", "spec_kit_aee"])
def test_actual_mini_agent_phase_adapter(tmp_path, monkeypatch, arm):
    evaluations = []
    def evaluation(root, claims, phase, store, attempt_id):
        evaluations.append(phase)
        return {"outcome": "pass", "findings": []}
    monkeypatch.setattr("benchmark_runner.runner.assess", evaluation)
    provider, sandbox = FakeProvider(), FakeSandbox()
    result = execute_attempt(ROOT, {"problem_statement": "SYNTHETIC task"}, arm, provider, sandbox,
          Store(tmp_path), {"attempt_id": "test"}, {"timeout_seconds": 60, "max_input_tokens": 100,
          "max_output_tokens": 100, "token_cap": 10000, "max_calls": 20, "max_recovery_rounds": 2})
    assert tuple(dict.fromkeys(provider.seen)) == phases(arm)
    assert evaluations == (["specify", "plan", "tasks", "implement"] if arm == "spec_kit_aee" else [])
    assert sandbox.staged == (arm != "baseline")
    assert result["patch"]["sha256"]
    assert "Spec Kit" not in phase_prompt(ROOT, "baseline", "solve")


def test_aee_recovery_routes_and_retains_patch(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark_runner.runner.assess", lambda *a: {"outcome": "gather_evidence"})
    provider = FakeProvider()
    result = execute_attempt(ROOT, {"problem_statement": "SYNTHETIC task"}, "spec_kit_aee", provider,
          FakeSandbox(), Store(tmp_path), {"attempt_id": "test"}, {"timeout_seconds": 60,
          "max_input_tokens": 100, "max_output_tokens": 100, "token_cap": 10000,
          "max_calls": 20, "max_recovery_rounds": 2})
    assert provider.seen == ["constitution", "specify", "specify", "specify"]
    assert result["blocked"] and result["repair_count"] == 2 and result["patch"]


def test_real_deterministic_extensions_on_synthetic_claim(tmp_path):
    claims = read_json(ROOT/".specify/extensions/aee/templates/aee-claims.json")
    claims["claims"][0]["status"] = "unsupported"
    claims["claims"][0]["evidence"] = []
    result = assess(ROOT, claims, "specify", Store(tmp_path), "test-attempt-1")
    assert result["outcome"] != "pass"
    assert result["metadata"]["evaluator_count"] == 1
    assert Store(tmp_path).events("assessments")[0]["artifacts"]
    controller = assess(ROOT, read_json(ROOT/"specs/001-benchmark/claims.json"), "plan", Store(tmp_path/"controller"), "test-attempt-2")
    assert controller["metadata"]["evaluator_count"] == 1


def test_model_cannot_fabricate_observation_or_use_other_attempt(tmp_path):
    store = Store(tmp_path)
    ref = store.artifact(b"SYNTHETIC command result")
    store.append("tools", {"attempt_id": "a", "artifact": ref})
    claim = {"claims": [{"evidence": [{"ref": ref["path"], "source_id": ref["sha256"], "kind": "observed", "source_quality": "test"}]}]}
    assert grounded_claims(claim, store, "a")["claims"][0]["evidence"][0]["kind"] == "observed"
    assert grounded_claims(claim, store, "b")["claims"][0]["evidence"][0]["kind"] == "asserted"
