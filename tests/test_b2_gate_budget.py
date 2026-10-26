"""B-2 (Benchmarking Improvement Program, 2026-10-25): per-phase
call bounds exist (the phase guard); what was missing is a
separate budget for the assessment-gate loop, so gate churn can
never spend a phase's productive budget.

The October 24 shape: a specify phase whose every submission is
rejected by the claims gate, resubmitting until the phase's
whole call guard is gone, with the later phases never reached.
Under a freeze-configured gate_loop_budget_calls, the calls a
gate iteration consumes draw on the gate budget; the phase
guard reads only the productive prefix of the phase's calls;
and exhausting the gate budget ends the phase with the artifacts
that exist — the attempt proceeds. Without the config key,
behavior is the pre-B-2 behavior bit-for-bit (the control tests
below pin the old outcome on the same streams).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from benchmark_runner import runner
from benchmark_runner.store import Store
from test_amendment1_runner import BASE_CFG, FakeSandbox, ROOT


@pytest.fixture(autouse=True)
def assess_passes(monkeypatch):
    """The gate's verdict is not what these tests measure; the
    claims path up to the gate (resolution, grounding) runs for
    real, and the gate itself is stubbed to pass — except in the
    iterate-repairs test, which installs its own assess."""
    monkeypatch.setattr(
        runner, "assess",
        lambda root, claims, phase, store, attempt_id: {
            "outcome": "pass", "findings": [], "confidence": 1.0,
            "uncertainty": "", "next_action": "none"})

MALFORMED = {"claims": [{"id": "c1", "kind": "assertion",
                         "evidence": ["a-string-not-an-object"]}]}
VALID_EMPTY = {"schema_version": "1.0", "claims": []}


class ClaimsProvider:
    """Per-phase scripted provider whose done steps carry a
    claims payload. A script step is ("shell", tin, tout) or
    ("done", tin, tout, claims). The last step repeats."""

    def __init__(self, store, identity, script):
        self.store, self.identity, self.script = store, identity, script
        self.counts = {}

    def query(self, messages, phase, timeout):
        idx = self.counts.get(phase, 0)
        self.counts[phase] = idx + 1
        step = self.script[phase][min(idx, len(self.script[phase]) - 1)]
        kind, tin, tout = step[0], step[1], step[2]
        self.store.append("calls", {
            **self.identity, "phase": phase,
            "call_id": f"{self.identity['attempt_id']}-{phase}-{idx}",
            "input_tokens": tin, "output_tokens": tout,
            "usage_status": "reported"})
        if kind == "done":
            return json.dumps({"action": "done", "summary": "fixture",
                               "claims": step[3]})
        return json.dumps({"action": "shell", "command": "true"})


def run_attempt(tmp_path, script, cfg_extra=None):
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK",
                "arm": "spec_kit_aee", "repeat": 1}
    provider = ClaimsProvider(store, identity, script)
    cfg = {**BASE_CFG, **(cfg_extra or {})}
    result = runner.execute_attempt(
        ROOT, {"problem_statement": "fixture"}, "spec_kit_aee",
        provider, FakeSandbox(), store, identity, cfg)
    return store, provider, result


def base_script():
    return {
        "constitution": [("done", 100, 50, VALID_EMPTY)],
        "specify": [("done", 100, 50, MALFORMED)],
        "plan": [("done", 100, 50, VALID_EMPTY)],
        "tasks": [("done", 100, 50, VALID_EMPTY)],
        "implement": [("done", 100, 50, VALID_EMPTY)],
        "converge": [("done", 100, 50, VALID_EMPTY)],
    }


def phase_calls(store, phase):
    return [c for c in store.events("calls") if c["phase"] == phase]


def test_infinite_resubmission_terminates_on_the_gate_budget(tmp_path):
    store, provider, result = run_attempt(
        tmp_path, base_script(), {"gate_loop_budget_calls": 6})
    # The phase ended on its gate budget, recorded as such...
    assert result.get("gate_loop_exhausted") == ["specify"]
    events = [e for e in store.events("phases")
              if e.get("kind") == "gate_loop_exhausted"]
    assert len(events) == 1 and events[0]["phase"] == "specify"
    assert events[0]["gate_calls"] >= 6
    # ...having spent a bounded number of specify calls (one
    # productive submission plus the gate budget, not the whole
    # 40-call phase guard)...
    assert len(phase_calls(store, "specify")) <= 9
    # ...and the attempt proceeded to the next phase.
    assert len(phase_calls(store, "plan")) >= 1
    assert result.get("phase_exhausted") is None


def test_without_the_key_the_same_stream_burns_the_phase_guard(tmp_path):
    # Control: the pre-B-2 semantics, bit-for-bit — the loop is
    # stopped only by the phase guard, and plan is never reached.
    store, provider, result = run_attempt(tmp_path, base_script())
    assert result.get("phase_exhausted") == "specify"
    # The 40-call guard plus the driver's one bounded finalize
    # attempt for a drafting phase.
    assert len(phase_calls(store, "specify")) == 41
    assert phase_calls(store, "plan") == []
    assert "gate_loop_exhausted" not in result


def test_october_24_pattern_reshaped(tmp_path):
    # The recorded October 24 trajectory shape: the first specify
    # call is already a gate submission and every later call is a
    # resubmission — 41 calls, all gate churn, nothing productive
    # after the first. Reshaped against a gate budget of 8, the
    # phase terminates on the loop budget with the attempt's
    # remaining phases funded and reachable.
    script = base_script()
    script["constitution"] = [("done", 100, 50, VALID_EMPTY)]
    store, provider, result = run_attempt(
        tmp_path, script, {"gate_loop_budget_calls": 8})
    assert result.get("gate_loop_exhausted") == ["specify"]
    assert len(phase_calls(store, "specify")) <= 11
    assert len(phase_calls(store, "plan")) >= 1


def test_iterate_repairs_draw_on_the_gate_budget(tmp_path, monkeypatch):
    # A gate that always answers "iterate": repair rounds are
    # gate-loop calls. (A "block" answer is terminal in the
    # driver and never reaches the repair loop.) With a gate
    # budget of 3 the phase ends on the gate budget long before
    # the recovery bound (10) is reached.
    calls = {}

    def assess_iterate(root, claims, phase, store, attempt_id):
        calls[phase] = calls.get(phase, 0) + 1
        return {"outcome": "iterate", "findings": [],
                "confidence": 0.5, "uncertainty": "fixture",
                "next_action": "repair",
                "lanes": {"lane_1": {"outcome": "iterate"},
                          "lane_2": {}}}

    monkeypatch.setattr(runner, "assess", assess_iterate)
    script = base_script()
    script["specify"] = [("done", 100, 50, VALID_EMPTY),
                         ("shell", 100, 50),
                         ("done", 100, 50, VALID_EMPTY)]
    store, provider, result = run_attempt(
        tmp_path, script,
        {"gate_loop_budget_calls": 3, "max_recovery_rounds": 10})
    # Specify ends on the gate budget — the budget, not the
    # recovery bound of 10, is what stops the repair loop...
    assert result.get("gate_loop_exhausted", [])[0] == "specify"
    assert calls.get("specify", 0) <= 4
    # ...and the attempt proceeds to the next phase (which, under
    # the same always-iterate gate, exhausts its own budget too).
    assert len(phase_calls(store, "plan")) >= 1
