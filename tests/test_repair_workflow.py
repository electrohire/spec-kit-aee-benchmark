"""Offline treatment-fidelity tests for the repair_workflow arm (Claim A, Option B).

No Docker, no network, no model calls: the agent phase loop, the AEE
assessor, the sandbox, and the public-test runner are all stubbed. What is
tested is the treatment logic: the six frozen phases execute in order with
the frozen skill prompts, AEE assessment gates each AEE phase, a block
triggers a bounded recovery re-run, a sustained block terminates the loop
honestly, and the return shape matches what the grader and the outcome
classifier expect.
"""
import json
from pathlib import Path

import pytest

import benchmark_runner.matched_repair as mr
from benchmark_runner.store import Store

TASK_ID = "mr-tinydb-token_alias-20260921"
WF_ATTEMPT = TASK_ID + "--repair_workflow-1"
DIAG_ATTEMPT = TASK_ID + "--diagnose"

CFG = {"timeout_seconds": 60, "max_calls": 64, "max_input_tokens": 32768,
       "max_output_tokens": 4096, "token_cap": 1000000, "max_recovery_rounds": 2}


class FakeAgent:
    def __init__(self):
        self.messages = []
        self.n_calls = 0
        self.model = type("Model", (), {"phase": None})()
        self.env = type("Env", (), {"tool_calls": 7})()

    def add_messages(self, *msgs):
        self.messages.extend(msgs)


class FakeSandbox:
    def __init__(self):
        self.staged = None

    def stage_workflow(self, root):
        self.staged = str(root)

    def execute(self, command, timeout=None):
        return {"exit_code": 0, "stdout": "", "stderr": ""}


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    store = Store(tmp_path / "store")
    store.append("diagnostics", {
        "attempt_id": DIAG_ATTEMPT, "task_id": TASK_ID,
        "summary": {"done": {"summary": "suspected defect in token aliasing"}},
        "diagnostic_changed_source": False})
    manifest = {"schedule": [{"task_id": TASK_ID, "arm": "diagnose",
                              "attempt_id": DIAG_ATTEMPT}]}
    identity = {"attempt_id": WF_ATTEMPT, "task_id": TASK_ID, "arm": "repair_workflow",
                "experiment_id": "exp", "run_id": "run", "purpose": "test"}
    task = {"instance_id": TASK_ID}
    agent, sandbox = FakeAgent(), FakeSandbox()
    calls = {"phases": [], "assessments": []}

    def fake_phase(agent_, model_, store_, identity_, cfg_, phase, instructions,
                   spec, limit, deadline, claims):
        calls["phases"].append({"phase": phase, "claims": claims, "limit": limit,
                                "has_skill": "speckit-" in instructions,
                                "has_brief": TASK_ID in spec})
        # Mirror the real run_matched_phase evidence write.
        store_.append("phases", {**identity_, "phase": phase})
        return {"phase": phase,
                "done": {"action": "done", "summary": "phase ok",
                         "claims": {"schema_version": "1.0", "claims": []}},
                "completed": True, "errors": [], "calls": 3}

    monkeypatch.setattr(mr, "_new_agent", lambda provider, deadline: agent)
    monkeypatch.setattr(mr, "run_matched_phase", fake_phase)
    monkeypatch.setattr(mr, "run_public_tests",
                        lambda sb: {"passed": True, "test_count": 5, "output": "ok"})
    monkeypatch.setattr(mr, "snapshot_package", lambda sb, pkg: b"fake-tar")
    monkeypatch.setattr(mr, "git_clean", lambda sb: False)  # source was changed
    return {"store": store, "manifest": manifest, "identity": identity,
            "task": task, "agent": agent, "sandbox": sandbox, "calls": calls,
            "monkeypatch": monkeypatch}


def _run(monkeypatch, harness, outcomes):
    calls = harness["calls"]
    seq = list(outcomes)

    def fake_assess(root, claims, phase, store, attempt_id):
        calls["assessments"].append(phase)
        # Mirror the real assess() evidence write.
        store.append("assessments", {**harness["identity"], "phase": phase})
        return {"outcome": seq.pop(0) if seq else "pass", "findings": []}

    monkeypatch.setattr(mr, "assess", fake_assess)
    return mr.run_workflow_repair(Path(__file__).resolve().parents[1], harness["task"], None,
                                  harness["sandbox"], harness["store"],
                                  harness["identity"], dict(CFG),
                                  harness["manifest"])


def test_workflow_runs_six_frozen_phases_with_aee_gates(harness):
    mp = harness["monkeypatch"]
    result = _run(mp, harness, ["pass", "pass", "pass", "pass"])
    phases = [c["phase"] for c in harness["calls"]["phases"]]
    assert phases == ["workflow_constitution", "workflow_specify", "workflow_plan",
                      "workflow_tasks", "workflow_implement", "workflow_converge"]
    # The frozen skill prompt and the shared task brief reach every phase.
    assert all(c["has_skill"] and c["has_brief"] for c in harness["calls"]["phases"])
    assert all(c["limit"] == mr.WORKFLOW_CALLS_PER_PHASE for c in harness["calls"]["phases"])
    # Claims required exactly at the AEE phases.
    assert [c["claims"] for c in harness["calls"]["phases"]] == \
        [False, True, True, True, True, False]
    # AEE assess() gated each AEE phase, in order.
    assert harness["calls"]["assessments"] == ["specify", "plan", "tasks", "implement"]
    assert result["workflow_completed"] is True
    assert result["workflow_blocked"] is False
    assert result["assessment_outcome"] == "pass"
    assert result["workflow_recoveries"] == 0
    assert result["diagnostic_valid"] is True
    # Return shape the grader and outcome classifier expect.
    assert result["package_snapshot"]["sha256"]
    rounds = result["repair_rounds"]
    assert len(rounds) == 1 and rounds[0]["public"]["passed"] is True
    assert rounds[0]["source_changed"] is True
    assert result["tool_calls"] == 0  # run_workflow_repair installs the real MiniEnvironment over the fake env
    # Phase + assessment evidence landed in the append-only store.
    assert len(harness["store"].events("phases")) == 6
    assert len(harness["store"].events("assessments")) == 4
    # Inter-phase condensation replaced the raw history with a compact handoff
    # built from recorded phase summaries (the final phase is left intact).
    msgs = harness["agent"].messages
    assert len(msgs) == 2
    assert msgs[0] == {"role": "system", "content": mr.COMMON}
    assert msgs[1]["role"] == "user"
    assert "Workflow conversation condensed" in msgs[1]["content"]
    assert "workflow_implement: completed=True, summary=phase ok" in msgs[1]["content"]
    assert "/workflow/specs" in msgs[1]["content"]


def test_workflow_block_triggers_bounded_recovery(harness):
    mp = harness["monkeypatch"]
    result = _run(mp, harness, ["block", "pass", "pass", "pass", "pass"])
    phases = [c["phase"] for c in harness["calls"]["phases"]]
    assert "workflow_specify_recovery1" in phases
    assert result["workflow_recoveries"] == 1
    assert result["workflow_blocked"] is False
    assert result["workflow_completed"] is True
    # Recovery re-runs are bounded by max_recovery_rounds.
    assert phases.count("workflow_specify_recovery1") == 1
    assert not any("recovery2" in p for p in phases)


def test_workflow_sustained_block_terminates_honestly(harness):
    mp = harness["monkeypatch"]
    cfg = dict(CFG, max_recovery_rounds=1)
    calls = harness["calls"]

    def fake_assess(root, claims, phase, store, attempt_id):
        calls["assessments"].append(phase)
        return {"outcome": "block", "findings": []}

    mp.setattr(mr, "assess", fake_assess)
    result = mr.run_workflow_repair(Path(__file__).resolve().parents[1], harness["task"], None,
                                    harness["sandbox"], harness["store"],
                                    harness["identity"], cfg, harness["manifest"])
    phases = [c["phase"] for c in harness["calls"]["phases"]]
    # specify blocked, one recovery re-run blocked again -> loop terminates;
    # later phases never execute.
    assert phases == ["workflow_constitution", "workflow_specify",
                      "workflow_specify_recovery1"]
    assert result["workflow_blocked"] is True
    assert result["workflow_completed"] is True  # phases ran; the block is recorded, not hidden
    assert result["assessment_outcome"] == "block"
    assert result["package_snapshot"]["sha256"]  # still gradable


def test_condense_workflow_history_replaces_messages_with_handoff():
    agent = FakeAgent()
    agent.messages = [{"role": "system", "content": "stale system"},
                      {"role": "user", "content": "stale history " * 500}]
    summaries = [
        {"phase": "workflow_constitution", "completed": True,
         "done": {"action": "done", "summary": "constitution done"}},
        {"phase": "workflow_specify", "completed": False, "done": None},
    ]
    mr._condense_workflow_history(agent, summaries)
    assert len(agent.messages) == 2
    assert agent.messages[0] == {"role": "system", "content": mr.COMMON}
    body = agent.messages[1]["content"]
    assert agent.messages[1]["role"] == "user"
    assert "Workflow conversation condensed" in body
    assert "workflow_constitution: completed=True, summary=constitution done" in body
    assert "workflow_specify: completed=False, summary=(no recorded summary)" in body
    assert "/workflow/specs" in body
    # Nothing invented: only recorded summaries appear.
    assert "stale history" not in body
