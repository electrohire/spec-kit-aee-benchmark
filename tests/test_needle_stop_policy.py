"""Needle Workstream B0: the adopted stop policy as harness behavior
(protocol PC-8, amendment 2026-10-21). All offline; scripted fakes
only, no inference, no Docker.

Frozen-record grounding — read before the replays below:
``reports/local/upstream-stopped-01-04-20261020/README.md`` and its
``audit.json``. The four stopped episodes each attempted one endpoint
of twelve, stopped during the first constitution phase, and left
eleven endpoints unattempted under the old stop-everything rule:

- Episode 01: missing actor framework scaffold — the run's own
  equipment was incomplete (corrected prospectively in PR 52).
  4 setup calls / 1 scored call, no proposal, ungraded.
- Episode 04: the model requested ``README.md`` in Dask, which uses
  ``README.rst`` — an ordinary model mistake. 4 setup calls / 1 scored
  call, no proposal, ungraded. The README's own words: "no harness
  fix or retry"; the failure was the model's own, yet it stopped the
  whole study like an equipment fault.

The gap, stated rather than hidden: those episodes ran under the
upstream coding controller, not ``runner.run()``. Their retained
records carry the narrative and token counts above, but no
``(status, reason)`` pair in this harness's terms, and this harness
has no halt kind for a wrong-filename request as such — inside
``runner.run()`` a wrong filename is a tool observation within an
attempt, not a halt. The frozen records therefore do not determine
episode 04's (or 01's) mechanical shape in this harness. The replays
below use the closest record-grounded shapes this harness actually
generates, with the substitution named in each test:

- Episode 04 -> a proven model outcome in this harness's own terms:
  an attempt the AEE gate blocks with its recovery bound exhausted
  (``execute_attempt`` returns ``blocked``; the runner records
  ``limit`` / ``"AEE recovery bound"`` -> ``model_outcome`` /
  ``aee_gate_recovery_exhausted``). It shares episode 04's defining
  property — the failure originates in the model's own work, proven
  mechanically by the harness's gate/accounting over the calls
  ledger, with no equipment or integrity fault — and it is one of
  only two proven model outcomes the taxonomy has ever had.
- Episode 01 -> an error halt naming the missing scaffold in the
  solver image (``premise_equipment`` / ``infrastructure_error``
  under the taxonomy's existing markers, classification semantics
  unchanged). In this harness the scaffold's analogue is the staged
  workflow/image the attempt runs on; its absence is an equipment
  fault, exactly as episode 01's audit classifies it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]/"src"))

import pytest

from benchmark_runner import runner
from benchmark_runner.accounting import BudgetExceeded
from benchmark_runner.runner import LimitHit
from benchmark_runner.store import Store, write_json
from benchmark_runner.tripwires import record_tripwire

ROOT = Path(__file__).parents[1]


class _Sandbox:
    details = {"image": "img", "digest": "d"}

    def __init__(self, image, base="base"):
        self._base = base

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, command, timeout=None):
        if "git rev-parse" in command:
            return {"exit_code": 0, "stdout": self._base + "\n", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}


def _patch(monkeypatch, execute, sandbox_cls=_Sandbox):
    monkeypatch.setattr(runner, "verify_freeze", lambda *a: None)
    monkeypatch.setattr(runner, "validate_live", lambda *a, **k: None)
    monkeypatch.setattr(runner, "DockerSandbox", sandbox_cls)
    monkeypatch.setattr(runner, "make_provider", lambda *a, **k: object())
    monkeypatch.setattr(runner, "execute_attempt", execute)


def _manifest(ids=("a1", "a2", "a3")):
    return {"freeze_id": "f" * 16,
            "config": {"purpose": "test", "global_cap_usd": 100,
                       "attempt_cap_usd": 25},
            "tasks": {"tasks": [{"instance_id": "task-1", "image": "img",
                                  "base_commit": "base"}]},
            "schedule": [{"attempt_id": i, "task_id": "task-1",
                          "arm": "baseline", "repeat": 1} for i in ids]}


def _terminal(store):
    final = {}
    for e in store.events("attempts"):
        final[e["attempt_id"]] = e
    return final


def _tripwires(store):
    return {e["attempt_id"]: e for e in store.events("tripwires")}


# --- Episode 04 shape: proven model outcome, scored, schedule continues -----

def test_episode_04_shape_model_outcome_scored_and_schedule_continues(tmp_path, monkeypatch):
    """Substitution (see module docstring): episode 04's wrong-filename
    mistake has no halt representation in this harness; it is replayed
    as this harness's proven model outcome — the AEE gate blocks the
    attempt and the recovery bound is exhausted. The attempt stands as
    scored (its blocked record, assessment and repair count retained)
    and the next scheduled attempts still run to completion."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if identity["attempt_id"] == "a1":
            return {"blocked": True, "assessment_outcome": "block",
                    "assessment_headline_outcome": "iterate",
                    "repair_count": 2, "tool_calls": 3}
        return {}

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "limit"
    assert final["a1"]["reason"] == "AEE recovery bound"
    # The attempt stands as scored: its own record is retained whole.
    assert final["a1"]["blocked"] is True
    assert final["a1"]["assessment_outcome"] == "block"
    assert final["a1"]["repair_count"] == 2
    # The schedule continued: both later attempts ran to completion.
    assert final["a2"]["status"] == "completed"
    assert final["a3"]["status"] == "completed"
    (trip,) = [e for e in store.events("tripwires")]
    assert trip["attempt_id"] == "a1"
    assert trip["halt_class"] == "model_outcome"
    assert trip["halt_kind"] == "aee_gate_recovery_exhausted"
    assert trip["behavior"] == "score_and_continue"
    assert trip["behavior_changed"] is True


@pytest.mark.parametrize("reason", ["call limit", "wall-time limit",
                                    "next request token reservation exceeds attempt cap"])
def test_disclosed_limit_scored_and_schedule_continues(tmp_path, monkeypatch, reason):
    """The second proven model outcome: a disclosed limit reached,
    raised by the harness's own accounting (LimitHit) over the calls
    ledger. Scored, and the schedule continues."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if identity["attempt_id"] == "a1":
            raise LimitHit(reason)
        return {}

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "limit" and final["a1"]["reason"] == reason
    assert final["a2"]["status"] == "completed"
    assert final["a3"]["status"] == "completed"
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "model_outcome"
    assert trip["halt_kind"] == "disclosed_limit_reached"
    assert trip["behavior"] == "score_and_continue"
    assert trip["behavior_changed"] is True


def test_campaign_budget_limit_halts_despite_limit_status(tmp_path, monkeypatch):
    """Classification, not status, decides: a limit halt for the
    campaign budget is a premise fault and halts the study, unlike
    the disclosed per-attempt limits above."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if identity["attempt_id"] == "a1":
            raise BudgetExceeded("next request reservation would exceed cap")
        return {}

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "limit"
    assert "a2" not in final and "a3" not in final
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "premise_equipment"
    assert trip["halt_kind"] == "campaign_budget_exceeded"
    assert trip["behavior"] == "halt_study"


# --- Episode 01 shape: equipment/premise failure, study halts ---------------

def test_episode_01_shape_missing_scaffold_halts_study(tmp_path, monkeypatch):
    """Substitution (see module docstring): episode 01's missing actor
    framework scaffold is replayed as an error halt naming the missing
    scaffold in the solver image — the equipment this harness stages
    for an attempt. Premise/equipment fault: the study halts and no
    later attempt starts."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        raise RuntimeError("solver image missing actor framework scaffold")

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "error"
    assert "scaffold" in final["a1"]["reason"]
    assert "a2" not in final and "a3" not in final  # no later attempt starts
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "premise_equipment"
    assert trip["halt_kind"] == "infrastructure_error"
    assert trip["behavior"] == "halt_study"
    assert trip["behavior_changed"] is True


# --- Every other class halts -------------------------------------------------

def test_unknown_error_halts_study(tmp_path, monkeypatch):
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        raise RuntimeError("something opaque happened")

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "error"
    assert "a2" not in final and "a3" not in final
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "unknown"
    assert trip["halt_kind"] == "unclassified_error"
    assert trip["behavior"] == "halt_study"
    assert trip["behavior_changed"] is True


def test_operator_interrupt_halts_study(tmp_path, monkeypatch):
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        raise KeyboardInterrupt

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert final["a1"]["status"] == "cancelled"
    assert "a2" not in final and "a3" not in final
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "premise_equipment"
    assert trip["halt_kind"] == "operator_interrupt"
    assert trip["behavior"] == "halt_study"


def test_integrity_error_halts_study(tmp_path, monkeypatch):
    """The solver image does not contain the clean base checkout:
    an identity fault, raised by the runner's own pre-attempt check
    before any model work."""
    calls = []

    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        calls.append(identity["attempt_id"])
        return {}

    _patch(monkeypatch, fake, sandbox_cls=lambda image: _Sandbox(image, base="other"))
    out = tmp_path/"out"
    runner.run(ROOT, _manifest(), out)
    store = Store(out)
    final = _terminal(store)
    assert calls == []  # the attempt's model work never ran
    assert final["a1"]["status"] == "error"
    assert "clean base checkout" in final["a1"]["reason"]
    assert "a2" not in final and "a3" not in final
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "integrity"
    assert trip["halt_kind"] == "identity_or_freeze_mismatch"
    assert trip["behavior"] == "halt_study"


def test_interrupted_attempt_on_resume_halts_study(tmp_path, monkeypatch):
    """An attempt found in ``started`` state on resume is recorded as
    an infrastructure failure — class unknown, cause never established
    — and the study halts after recording it: later scheduled attempts
    do not start (before PC-8 the loop proceeded to them)."""
    calls = []

    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        calls.append(identity["attempt_id"])
        return {}

    _patch(monkeypatch, fake)
    out = tmp_path/"out"
    manifest = _manifest()
    store = Store(out)
    store.append("attempts", {"attempt_id": "a1", "status": "started"})
    write_json(out/"freeze.json", manifest)
    runner.run(ROOT, manifest, out)
    final = _terminal(store)
    assert final["a1"]["status"] == "infrastructure_failure"
    assert calls == [] and "a2" not in final and "a3" not in final
    trip = _tripwires(store)["a1"]
    assert trip["halt_class"] == "unknown"
    assert trip["halt_kind"] == "interrupted_attempt"
    assert trip["behavior"] == "halt_study"
    assert trip["behavior_changed"] is True


# --- The pre-skip exclusion: behavior unchanged -------------------------------

def test_preskip_excluded_schedule_continues(tmp_path, monkeypatch):
    """The pre-start diagnostic pre-skip is an admission decision, not
    a halt: PC-8 does not govern it, its tripwire record says so, and
    the schedule continues past it exactly as before."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if arm == "diagnose":
            store.append("diagnostics", {**identity, "timestamp": "t", "claims": []})
        return {}

    _patch(monkeypatch, fake)
    tasks = [{"instance_id": "task-1", "image": "img", "base_commit": "base"},
             {"instance_id": "task-2", "image": "img", "base_commit": "base"}]
    manifest = {"freeze_id": "f" * 16,
                "config": {"purpose": "test", "global_cap_usd": 100,
                           "attempt_cap_usd": 25},
                "tasks": {"tasks": tasks},
                "schedule": [
                    {"attempt_id": "d1", "task_id": "task-1", "arm": "diagnose", "repeat": 1},
                    {"attempt_id": "r2", "task_id": "task-2", "arm": "repair_ordinary", "repeat": 1},
                    {"attempt_id": "b2", "task_id": "task-2", "arm": "baseline", "repeat": 1}]}
    out = tmp_path/"out"
    runner.run(ROOT, manifest, out)
    store = Store(out)
    final = _terminal(store)
    assert final["d1"]["status"] == "completed"
    assert final["r2"]["status"] == "skipped"  # no diagnostics for task-2
    assert final["b2"]["status"] == "completed"  # schedule continued past the skip
    trip = _tripwires(store)["r2"]
    assert trip["halt_kind"] == "prerequisite_evidence_missing"
    assert trip["behavior"] == "skip_and_continue"
    assert trip["behavior_changed"] is False


# --- Tripwire record shape under the revision --------------------------------

def test_record_tripwire_names_behavior_for_each_class(tmp_path):
    store = Store(tmp_path/"run")
    identity = {"attempt_id": "att-1", "arm": "baseline", "task_id": "task-1"}
    assert record_tripwire(store, identity, "completed", None) is None
    cases = [
        (("limit", "AEE recovery bound"), "model_outcome", "score_and_continue", True),
        (("limit", "call limit"), "model_outcome", "score_and_continue", True),
        (("cancelled", "operator interrupt"), "premise_equipment", "halt_study", True),
        (("error", "solver image does not contain a clean base checkout"),
         "integrity", "halt_study", True),
        (("error", "something opaque"), "unknown", "halt_study", True),
        (("infrastructure_failure", "interrupted; no automatic rerun"),
         "unknown", "halt_study", True),
        (("skipped", "pre-skipped: diagnostic evidence not recorded"),
         "premise_equipment", "skip_and_continue", False),
    ]
    for (status, reason), halt_class, behavior, changed in cases:
        event = record_tripwire(store, identity, status, reason)
        assert event["halt_class"] == halt_class
        assert event["behavior"] == behavior
        assert event["behavior_changed"] is changed
    assert len(store.events("tripwires")) == len(cases)
