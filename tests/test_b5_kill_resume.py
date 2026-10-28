"""B-5 kill-and-resume drill on synthetic stores.

Long campaigns are supervised for hours; the coordinator process
can die (host reboot, VM replacement, operator kill) at any
point. The store is the campaign's memory, and resume must be
exact about money: a finished attempt is never re-run or
re-charged, a charged call is never lost from the ledger, and —
for a kill that lands between attempts, the case the claim's
equality clause describes — campaign totals after resume equal
an unkilled control run exactly.

A mid-attempt kill is the harsher case and the drill proves the
harness's designed answer rather than smoothing it over: the
interrupted attempt has calls charged but no terminal record, so
on resume it is recorded as an interrupted attempt (class
unknown — its cause was never established) and the study halts
with every charge retained and nothing re-run. That is PC-8
applied to the drill, and it matches the semantics the Stage B
baseline leg's resume relied on (its attempt 7 carried a
terminal record and stood; nothing was re-charged).

The between-attempts store is seeded with event records copied
from a real control run — the kill window (after attempt a1's
terminal record is durably appended, before a2 starts) leaves
exactly those records and no others.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest

from benchmark_runner import runner
from benchmark_runner.store import Store, write_json

ROOT = Path(__file__).resolve().parents[1]


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


def _patch(monkeypatch, execute):
    monkeypatch.setattr(runner, "verify_freeze", lambda *a: None)
    monkeypatch.setattr(runner, "validate_live", lambda *a, **k: None)
    monkeypatch.setattr(runner, "DockerSandbox", _Sandbox)
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


CHARGES = {"a1": (1000, 100), "a2": (2000, 200), "a3": (3000, 300)}


def _charging_fake(executed):
    """Each attempt charges two calls with its fixed token pair."""
    def fake(root, task, arm, provider, sandbox, store, identity, cfg,
             manifest=None):
        aid = identity["attempt_id"]
        executed.append(aid)
        tin, tout = CHARGES[aid]
        for n in range(2):
            store.append("calls", {
                **identity, "phase": "specify",
                "call_id": f"{aid}-call-{n}",
                "input_tokens": tin, "output_tokens": tout,
                "usage_status": "reported"})
        return {}
    return fake


def _totals(store):
    per_attempt = {}
    total = 0
    for call in store.events("calls"):
        tokens = (call.get("input_tokens") or 0) + \
                 (call.get("output_tokens") or 0)
        per_attempt[call["attempt_id"]] = \
            per_attempt.get(call["attempt_id"], 0) + tokens
        total += tokens
    return per_attempt, total


def _terminal(store):
    final = {}
    for e in store.events("attempts"):
        final[e["attempt_id"]] = e
    return final


def _control(tmp_path, monkeypatch):
    _patch(monkeypatch, _charging_fake([]))
    out = tmp_path / "control"
    runner.run(ROOT, _manifest(), out)
    return Store(out)


def test_control_campaign_completes_with_expected_totals(tmp_path,
                                                         monkeypatch):
    store = _control(tmp_path, monkeypatch)
    per_attempt, total = _totals(store)
    assert per_attempt == {"a1": 2200, "a2": 4400, "a3": 6600}
    assert total == 13200
    assert {a: e["status"] for a, e in _terminal(store).items()} == {
        "a1": "completed", "a2": "completed", "a3": "completed"}


def test_kill_between_attempts_resume_equals_control(tmp_path,
                                                     monkeypatch):
    control = _control(tmp_path, monkeypatch)
    _, control_total = _totals(control)

    # Seed the post-kill store: a1's records exactly as the real
    # run wrote them (started + terminal + its charged calls),
    # nothing for a2/a3, and the campaign freeze in place.
    out = tmp_path / "killed"
    store = Store(out)
    for event in control.events("attempts"):
        if event["attempt_id"] == "a1":
            store.append("attempts", event)
    for call in control.events("calls"):
        if call["attempt_id"] == "a1":
            store.append("calls", call)
    write_json(out / "freeze.json", _manifest())

    executed = []
    _patch(monkeypatch, _charging_fake(executed))
    runner.run(ROOT, _manifest(), out)

    store = Store(out)
    # a1 was never re-executed; the schedule ran the remainder.
    assert executed == ["a2", "a3"]
    per_attempt, total = _totals(store)
    # No finished attempt re-charged, no charged call lost, and
    # the campaign total equals the unkilled control exactly.
    assert per_attempt == {"a1": 2200, "a2": 4400, "a3": 6600}
    assert total == control_total
    assert {a: e["status"] for a, e in _terminal(store).items()} == {
        "a1": "completed", "a2": "completed", "a3": "completed"}
    assert store.events("tripwires") == []


class _SimulatedKill(BaseException):
    """Stands in for SIGKILL / host death: not an Exception, so the
    runner's per-attempt handlers cannot convert it into a scored
    terminal — the process simply stops, mid-attempt."""


def test_kill_mid_attempt_resume_halts_and_loses_nothing(tmp_path,
                                                         monkeypatch):
    def kill_fake(root, task, arm, provider, sandbox, store, identity,
                  cfg, manifest=None):
        aid = identity["attempt_id"]
        if aid == "a2":
            # One real call is charged, then the coordinator dies.
            store.append("calls", {
                **identity, "phase": "specify", "call_id": "a2-call-0",
                "input_tokens": 777, "output_tokens": 77,
                "usage_status": "reported"})
            raise _SimulatedKill()
        tin, tout = CHARGES[aid]
        store.append("calls", {
            **identity, "phase": "specify", "call_id": f"{aid}-call-0",
            "input_tokens": tin, "output_tokens": tout,
            "usage_status": "reported"})
        return {}

    _patch(monkeypatch, kill_fake)
    out = tmp_path / "midkill"
    with pytest.raises(_SimulatedKill):
        runner.run(ROOT, _manifest(), out)

    store = Store(out)
    assert _terminal(store)["a1"]["status"] == "completed"
    assert _terminal(store)["a2"]["status"] == "started"
    per_attempt, total = _totals(store)
    assert per_attempt == {"a1": 1100, "a2": 854}
    assert total == 1954

    # Resume with a healthy executor: the interrupted attempt is
    # recorded as an interruption and the study halts — nothing
    # is re-run, nothing is re-charged, no charge is lost.
    executed = []
    _patch(monkeypatch, _charging_fake(executed))
    runner.run(ROOT, _manifest(), out)

    store = Store(out)
    assert executed == []
    final = _terminal(store)
    assert final["a1"]["status"] == "completed"
    assert final["a2"]["status"] == "infrastructure_failure"
    assert "a3" not in final
    per_attempt, total = _totals(store)
    assert per_attempt == {"a1": 1100, "a2": 854}
    assert total == 1954
    (trip,) = [e for e in store.events("tripwires")
               if e["attempt_id"] == "a2"]
    assert trip["halt_class"] == "unknown"
    assert trip["halt_kind"] == "interrupted_attempt"
    assert trip["behavior"] == "halt_study"
