"""Spec 006 harness behaviour (protocol amendment 2026-10-20):
lane-1 gate eligibility, recorded acts on a test-verdict basis,
distinct verification evidence, campaign setup sharing and tripwire
records. All offline; synthetic fixtures only, no inference."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]/"src"))

from benchmark_runner import runner
from benchmark_runner.store import Store
from benchmark_runner.tripwires import classify_halt, record_tripwire
from benchmark_runner.workflow import (attach_verification_evidence,
                                       campaign_setup, executed_tests,
                                       gate_outcome_of)

ROOT = Path(__file__).parents[1]
WIDGET_TEST = "pytest -q tests/test_widget.py"


def _tool(store, attempt_id, command, exit_code, stdout="ok"):
    payload = json.dumps({"command": command, "exit_code": exit_code,
                          "stdout": stdout}, sort_keys=True).encode()
    store.append("tools", {"attempt_id": attempt_id, "exit_code": exit_code,
                           "artifact": store.artifact(payload)})
    return store.events("tools")[-1]["artifact"]


def _claims(evidence, tests=(WIDGET_TEST,), status="draft", stage="created"):
    return {"claims": [{
        "id": "REQ-WIDGET-1", "text": "The widget works", "kind": "requirement",
        "status": status, "stage": stage, "boundary": ["Offline fixture"],
        "depends_on": [], "conflicts_with": [], "falsification_tests": list(tests),
        "source_ref": "spec.md#REQ-WIDGET-1", "uncertainty": "low",
        "evidence": evidence}]}


def _citation(artifact, description="Verified run"):
    return {"kind": "observed", "source_id": artifact["sha256"],
            "ref": artifact["path"], "source_quality": "test",
            "description": description}


# --- PC-1: executed tests are tied to claims by inspectable links ------------

def test_executed_tests_cited_artifact_counts_and_names_acceptance(tmp_path):
    store = Store(tmp_path/"run")
    run = _tool(store, "att-1", WIDGET_TEST, 0, "1 passed")
    _tool(store, "att-1", "pytest -q tests/test_unrelated.py", 0)
    _tool(store, "att-2", WIDGET_TEST, 0)  # another attempt's run: not this phase's
    executed = executed_tests(_claims([_citation(run)]), store, "att-1")
    record = executed["REQ-WIDGET-1"]
    assert [a["sha256"] for a in record["artifacts"]] == [run["sha256"]]
    assert record["passed"] is True
    assert record["acceptance"] == {"test": WIDGET_TEST, "sha256": run["sha256"]}


def test_executed_tests_command_match_without_citation(tmp_path):
    store = Store(tmp_path/"run")
    run = _tool(store, "att-1", "python -m " + WIDGET_TEST.replace("pytest", "pytest"), 0)
    executed = executed_tests(_claims([]), store, "att-1")
    assert executed["REQ-WIDGET-1"]["artifacts"][0]["sha256"] == run["sha256"]


def test_executed_tests_no_link_no_record(tmp_path):
    store = Store(tmp_path/"run")
    _tool(store, "att-1", "make docs", 0)
    bogus = {"kind": "observed", "source_id": "0"*64, "ref": "artifacts/none.json",
             "source_quality": "test", "description": "Unverifiable citation"}
    assert executed_tests(_claims([bogus]), store, "att-1") == {}


def test_executed_tests_cited_non_test_artifact_is_not_an_execution(tmp_path):
    store = Store(tmp_path/"run")
    spec = _tool(store, "att-1", "cat spec.md", 0)  # verified citation, not a test run
    assert executed_tests(_claims([_citation(spec)]), store, "att-1") == {}


def test_executed_tests_cited_test_run_ties_without_naming_the_test(tmp_path):
    store = Store(tmp_path/"run")
    run = _tool(store, "att-1", "pytest -q", 0, "3 passed")
    claims = _claims([_citation(run)], tests=("The widget suite passes end to end",))
    record = executed_tests(claims, store, "att-1")["REQ-WIDGET-1"]
    assert record["passed"] is True
    # The citation link does not name a declared test, so it cannot
    # carry acceptance — only checked and ratification follow from it.
    assert record["acceptance"] is None


def test_executed_tests_failure_and_unknown_exit_are_not_passes(tmp_path):
    store = Store(tmp_path/"run")
    failed = _tool(store, "att-1", WIDGET_TEST, 1, "1 failed")
    record = executed_tests(_claims([_citation(failed)]), store, "att-1")["REQ-WIDGET-1"]
    assert record["passed"] is False and record["acceptance"] is None
    store2 = Store(tmp_path/"run2")
    payload = json.dumps({"command": WIDGET_TEST}, sort_keys=True).encode()
    store2.append("tools", {"attempt_id": "att-1",
                            "artifact": store2.artifact(payload)})  # no exit_code recorded
    artifact = store2.events("tools")[-1]["artifact"]
    record = executed_tests(_claims([_citation(artifact)]), store2, "att-1")["REQ-WIDGET-1"]
    assert record["passed"] is False


def test_attach_verification_evidence_makes_sources_distinct(tmp_path):
    store = Store(tmp_path/"run")
    spec = _tool(store, "att-1", "cat spec.md", 0)
    run = _tool(store, "att-1", WIDGET_TEST, 0, "1 passed")
    claims = _claims([_citation(spec, "The phase specification")])
    executed = executed_tests(claims, store, "att-1")
    attached = attach_verification_evidence(claims, executed)
    sources = [e["source_id"] for e in attached["claims"][0]["evidence"]]
    assert sources == [spec["sha256"], run["sha256"]]  # two distinct real sources
    assert attach_verification_evidence(attached, executed) == attached  # idempotent
    assert claims["claims"][0]["evidence"] == [_citation(spec, "The phase specification")]


# --- PC-2: gate eligibility follows lane 1, both lanes ride along ------------

def test_gate_outcome_prefers_lane_1():
    blended = {"outcome": "iterate",
               "lanes": {"lane_1": {"outcome": "pass"},
                         "lane_2": {"stage_counts": {"created": 2}}}}
    assert gate_outcome_of(blended) == "pass"
    composed_shape = {"outcome": "iterate",
                      "metadata": {"lane_states": [{"lane_1": {"outcome": "block"},
                                                     "lane_2": {}}]}}
    assert gate_outcome_of(composed_shape) == "block"
    assert gate_outcome_of({"outcome": "gather_evidence"}) == "gather_evidence"


# --- PC-4: tripwire taxonomy --------------------------------------------------

def test_tripwire_taxonomy():
    assert classify_halt("limit", "AEE recovery bound") == (
        "model_outcome", "aee_gate_recovery_exhausted")
    assert classify_halt("limit", "wall-time limit") == (
        "model_outcome", "disclosed_limit_reached")
    assert classify_halt("limit", "next request token reservation exceeds attempt cap") == (
        "model_outcome", "disclosed_limit_reached")
    assert classify_halt("limit", "next request reservation would exceed cap") == (
        "premise_equipment", "campaign_budget_exceeded")
    assert classify_halt("cancelled", "cancelled") == (
        "premise_equipment", "operator_interrupt")
    assert classify_halt("error", "project tree is not a clean base checkout") == (
        "integrity", "identity_or_freeze_mismatch")
    assert classify_halt("error", "docker daemon unavailable") == (
        "premise_equipment", "infrastructure_error")
    assert classify_halt("error", "something opaque") == ("unknown", "unclassified_error")
    assert classify_halt("infrastructure_failure", "interrupted; no automatic rerun") == (
        "unknown", "interrupted_attempt")
    assert classify_halt("skipped", "pre-skipped: diagnostic evidence not recorded") == (
        "premise_equipment", "prerequisite_evidence_missing")


def test_record_tripwire_appends_only_for_halts(tmp_path):
    store = Store(tmp_path/"run")
    identity = {"attempt_id": "att-1", "arm": "spec_kit", "task_id": "task-1"}
    assert record_tripwire(store, identity, "completed", None) is None
    assert store.events("tripwires") == []
    event = record_tripwire(store, identity, "limit", "AEE recovery bound")
    # PC-8 (2026-10-21): records written under the stop-policy revision
    # name the behavior taken and carry behavior_changed True; under
    # PC-4 this same record carried behavior_changed False.
    assert event["halt_class"] == "model_outcome" and event["behavior_changed"] is True
    assert event["behavior"] == "score_and_continue"
    assert store.events("tripwires") == [event]


# --- PC-1 + PC-2 end to end: a passing fixture phase records its acts --------

def test_assess_records_acts_and_reports_both_lanes(tmp_path):
    from benchmark_runner.workflow import assess
    store = Store(tmp_path/"run")
    run = _tool(store, "att-e2e", WIDGET_TEST, 0, "1 passed")
    composed = assess(ROOT, _claims([_citation(run)]), "specify", store, "att-e2e")
    # The pair is reported on the result: gate follows lane 1 exactly.
    assert composed["lanes"]["lane_1"]["outcome"] == composed["gate_outcome"]
    assert "lane_2" in composed["lanes"]
    (event,) = store.events("assessments")
    assert event["gate_outcome"] == composed["gate_outcome"]
    assert event["lane_1_outcome"] == composed["gate_outcome"]
    acts = event["recorded_acts"]
    assert acts and all(a["basis_type"] == "test-verdict" and a["exit_code"] == 0
                        for a in acts)
    assert [(a["kind"], a["claim_id"]) for a in acts] == [
        ("stage", "REQ-WIDGET-1"), ("ratify", "REQ-WIDGET-1"), ("stage", "REQ-WIDGET-1")]
    # The stored bundle carries the acts: checked, ratified out of
    # draft, and accepted on the executed acceptance test's verdict.
    acted = []
    for ref in event["artifacts"]:
        try:
            payload = json.loads((store.root/ref["path"]).read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("claims"):
            first = payload["claims"][0]
            if (first.get("metadata") or {}).get("recorded_acts"):
                acted.append(payload)
    assert acted, "the act-updated bundle must be stored as an artifact"
    claim = acted[-1]["claims"][0]
    assert claim["stage"] == "accepted" and claim["status"] == "supported"
    recorded = claim["metadata"]["recorded_acts"]
    assert [r["to_stage"] for r in recorded] == ["checked", "accepted"]
    assert all(r["basis_type"] == "test-verdict" for r in recorded)
    assert {r["author"] for r in recorded} == {"benchmark-pipeline"}
    (ratification,) = claim["metadata"]["ratification_events"]
    assert ratification["status"] == "supported"
    assert ratification["basis_type"] == "test-verdict"
    # The report artifact states both lanes and the recorded acts.
    texts = [(store.root/ref["path"]).read_bytes().decode(errors="replace")
             for ref in event["artifacts"]]
    report = next(t for t in texts if t.startswith("# Evaluator report"))
    assert "Gate outcome (lane 1, machine verification):" in report
    assert "Lane 2 (human acceptance):" in report
    assert "Recorded acts: 3" in report


def test_assess_without_executed_tests_records_no_acts(tmp_path):
    from benchmark_runner.workflow import assess
    store = Store(tmp_path/"run")
    claims = _claims([], tests=("A load test observes p95 latency above 250 ms",))
    composed = assess(ROOT, claims, "specify", store, "att-none")
    (event,) = store.events("assessments")
    assert event["recorded_acts"] == []
    assert composed["gate_outcome"] == (composed.get("lanes", {}).get("lane_1") or {}
                                        ).get("outcome", composed["outcome"])


# --- PC-3: campaign setup frozen once, reused across arms ---------------------

class _Provider:
    """Provider-protocol fake, typed exactly as the production providers
    (provider.py / local_provider.py: query(messages, phase, timeout) ->
    the action as a JSON string) and as tests/test_workflow.py's proven
    FakeProvider. The phase arrives as an argument; it is never parsed
    out of the messages."""

    def __init__(self):
        self.seen = []

    def query(self, messages, phase, timeout):
        self.seen.append(phase)
        return json.dumps({"action": "done", "summary": phase + " done",
                           "claims": {"schema_version": "1.0",
                                      "claims": [{"id": "REQ-X"}]}})


class _Sandbox:
    def stage_workflow(self, root):
        pass

    def execute(self, command, timeout):
        return {"exit_code": 0, "stdout": "patch" if "git diff" in command else "",
                "stderr": ""}


_CFG = {"timeout_seconds": 30, "max_input_tokens": 1000, "max_output_tokens": 1000,
        "token_cap": 100000, "max_calls": 50, "max_recovery_rounds": 0}


def _attempt(store, provider, attempt_id, arm, share):
    identity = {"attempt_id": attempt_id, "arm": arm, "task_id": "task-1"}
    task = {"instance_id": "task-1", "problem_statement": "Fixture task."}
    cfg = {**_CFG, "share_campaign_setup": share}
    return runner.execute_attempt(ROOT, task, arm, provider, _Sandbox(), store,
                                  identity, cfg)


def test_campaign_setup_shared_once_across_arms(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "assess", lambda *a, **k: {"outcome": "pass", "findings": []})
    monkeypatch.setattr(runner, "grounded_claims", lambda claims, store, attempt: claims)
    store = Store(tmp_path/"run")
    provider = _Provider()
    _attempt(store, provider, "att-setup-1", "spec_kit", True)
    _attempt(store, provider, "att-setup-2", "spec_kit_aee", True)
    assert provider.seen.count("constitution") == 1  # setup ran once for the campaign
    frozen = campaign_setup(store, "task-1")
    assert frozen["attempt_id"] == "att-setup-1"
    reused = [e for e in store.events("phases")
              if e["attempt_id"] == "att-setup-2" and e["phase"] == "constitution"]
    assert len(reused) == 1 and reused[0]["setup_reused"] is True
    assert reused[0]["setup_source_attempt_id"] == "att-setup-1"


def test_campaign_setup_not_shared_without_the_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "assess", lambda *a, **k: {"outcome": "pass", "findings": []})
    monkeypatch.setattr(runner, "grounded_claims", lambda claims, store, attempt: claims)
    store = Store(tmp_path/"run")
    provider = _Provider()
    _attempt(store, provider, "att-plain-1", "spec_kit", False)
    _attempt(store, provider, "att-plain-2", "spec_kit", False)
    assert provider.seen.count("constitution") == 2  # unchanged behaviour by default
    assert campaign_setup(store, "task-1") is None
