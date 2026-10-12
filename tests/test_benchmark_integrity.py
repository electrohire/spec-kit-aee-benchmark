"""Spec 003 FR-7 integrity tests: RT4 probe_bench inverted, plus the
re-pin, freeze-addition, resolved-binding, grounding and disclosure
behaviours. All offline: no Docker, no GPU, no network."""
import importlib.util
import json
from pathlib import Path

import pytest

from benchmark_runner.experiment import freeze, verify_freeze
from benchmark_runner.grading import _bind_resolved
from benchmark_runner.reporting import aggregate, article_table
from benchmark_runner.store import Store
from benchmark_runner.workflow import grounded_claims

ROOT = Path(__file__).resolve().parents[1]


def _attempt(store, attempt_id="t--baseline--r1", arm="baseline"):
    store.append("attempts", {"attempt_id": attempt_id, "task_id": "t", "arm": arm,
                              "status": "completed", "duration_seconds": 1})


def _bound_grade(store, attempt_id="t--baseline--r1", resolved=True, exit_code=0):
    log = store.artifact(f"GRADER LOG {attempt_id}".encode())
    store.append("grades", {"attempt_id": attempt_id, "task_id": "t",
                            "run_id": f"bench-{attempt_id}", "resolved": resolved,
                            "reason": None, "grader_exit_code": exit_code,
                            "log": log, "reports": []})


# --- RT4-H4 inverted: a forged grade does not aggregate ---------------------

def test_forged_grade_with_no_grader_artifact_does_not_aggregate(tmp_path):
    store = Store(tmp_path)
    _attempt(store)
    # The probe's forged line: no grader run, no log, no report.
    store.append("grades", {"attempt_id": "t--baseline--r1", "resolved": True})
    report = aggregate(store)
    baseline = report["arms"]["baseline"]
    assert baseline["resolved"] == 0
    assert baseline["resolved_rate"] == 0.0
    assert baseline["unknown_grades"] == 1
    assert report["integrity"]["unverified_grade_attempts"] == ["t--baseline--r1"]
    assert report["integrity"]["verified_grades"] == 0


def test_bound_grade_from_successful_grader_run_aggregates(tmp_path):
    store = Store(tmp_path)
    _attempt(store)
    _bound_grade(store)
    report = aggregate(store)
    assert report["arms"]["baseline"]["resolved"] == 1
    assert report["arms"]["baseline"]["resolved_rate"] == 1.0
    assert report["integrity"]["verified_grades"] == 1
    assert report["integrity"]["unverified_grade_attempts"] == []


def test_grade_from_failed_grader_run_is_not_counted(tmp_path):
    store = Store(tmp_path)
    _attempt(store)
    _bound_grade(store, exit_code=1)
    report = aggregate(store)
    assert report["arms"]["baseline"]["resolved"] == 0
    assert report["integrity"]["unverified_grade_attempts"] == ["t--baseline--r1"]


def test_edited_chained_grade_breaks_the_chain(tmp_path):
    store = Store(tmp_path)
    _attempt(store)
    _bound_grade(store, resolved=False)
    path = tmp_path/"grades.jsonl"
    record = json.loads(path.read_text().splitlines()[0])
    record["resolved"] = True  # hand-edit a chained record in place
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(ValueError, match="hash chain is broken"):
        aggregate(store)


# --- Stream chaining semantics ----------------------------------------------

def test_legacy_stream_is_read_but_reported_unverified(tmp_path):
    store = Store(tmp_path)
    (tmp_path/"attempts.jsonl").write_text(
        json.dumps({"attempt_id": "old", "status": "completed"}) + "\n")
    assert store.events("attempts")[0]["attempt_id"] == "old"
    summary = store.verify_stream("attempts")
    assert summary == {"records": 1, "chained": 0, "legacy_records": 1,
                       "chain_verified": False}
    store.append("attempts", {"attempt_id": "new", "status": "started"})
    summary = store.verify_stream("attempts")
    assert summary["chained"] == 1 and summary["legacy_records"] == 1
    assert [r["attempt_id"] for r in store.events("attempts")] == ["old", "new"]


def test_empty_store_aggregate_is_not_run(tmp_path):
    report = aggregate(Store(tmp_path))
    assert report["status"] == "not_run"
    assert all(m["attempts"] == 0 for m in report["arms"].values())


# --- FR-7.6: resolved binding ------------------------------------------------

def test_bind_resolved_rules():
    assert _bind_resolved({True}, "t", 0) == (True, None)
    assert _bind_resolved(set(), "t", 0) == (None, "no independent resolved field")
    resolved, reason = _bind_resolved({True}, "t", 2)
    assert resolved is None and "grader exited 2" in reason
    with pytest.raises(ValueError, match="conflicting grader reports"):
        _bind_resolved({True, False}, "t", 0)


# --- FR-7.5: freeze additions -------------------------------------------------

def _freeze_root(tmp_path):
    (tmp_path/"configs").mkdir()
    (tmp_path/"manifests").mkdir()
    (tmp_path/"docs").mkdir()
    (tmp_path/"scripts").mkdir()
    (tmp_path/"configs/experiment.yaml").write_text("repeats: 1\nseed: 1\n")
    (tmp_path/"manifests/tasks.json").write_text(json.dumps({"tasks": []}))
    (tmp_path/"manifests/versions.json").write_text("{}")
    (tmp_path/"docs/protocol.md").write_text("SYNTHETIC")
    (tmp_path/"uv.lock").write_text("SYNTHETIC")
    return freeze(tmp_path, tmp_path/"freeze.json")


def test_verify_freeze_detects_additions_under_frozen_paths(tmp_path):
    manifest = _freeze_root(tmp_path)
    assert verify_freeze(tmp_path, manifest) == manifest
    (tmp_path/"scripts/injected.py").write_text("# added after freeze\n")
    with pytest.raises(ValueError, match="added under frozen paths"):
        verify_freeze(tmp_path, manifest)


# --- FR-7.4 / RT4-H6 inverted: grounding applies to every kind ---------------

def test_grounding_downgrades_forged_evidence_of_any_kind(tmp_path):
    store = Store(tmp_path)
    claims = {"claims": [{"id": "C1", "evidence": [
        {"kind": "inferred", "source_id": "fake", "ref": "tests/test_x.py",
         "source_quality": "test", "description": "tests pass"},
        {"kind": "asserted", "source_id": "fake", "ref": "x",
         "source_quality": "primary", "description": "d"},
        {"kind": "observed", "source_id": "fake", "ref": "x",
         "source_quality": "test", "description": "d"}]}]}
    out = grounded_claims(claims, store, "attempt-1")
    for evidence in out["claims"][0]["evidence"]:
        assert evidence["kind"] == "asserted"
        assert evidence["source_quality"] == "model"


def test_grounding_keeps_verified_evidence_of_any_kind(tmp_path):
    store = Store(tmp_path)
    artifact = store.artifact(b"real tool output")
    store.append("tools", {"attempt_id": "attempt-1", "artifact": artifact})
    claims = {"claims": [{"id": "C1", "evidence": [
        {"kind": kind, "source_id": artifact["sha256"], "ref": artifact["path"],
         "source_quality": "test", "description": "d"}
        for kind in ("observed", "inferred")]}]}
    out = grounded_claims(claims, store, "attempt-1")
    assert [e["kind"] for e in out["claims"][0]["evidence"]] == ["observed", "inferred"]


# --- FR-7.7: archived-run disclosure ------------------------------------------

def test_archived_runs_are_disclosed_not_silent(tmp_path):
    store = Store(tmp_path/"scored")
    _attempt(store)
    _bound_grade(store)
    archive = tmp_path/"scored-prev-20260101-000000"
    archive.mkdir()
    (archive/"attempts.jsonl").write_text(
        json.dumps({"attempt_id": "old-1"}) + "\n" + json.dumps({"attempt_id": "old-2"}) + "\n")
    report = aggregate(store)
    assert report["archived_runs"]["count"] == 1
    assert report["archived_runs"]["attempts"] == 2
    # The archived attempts are provenance only: not in the denominators.
    assert report["arms"]["baseline"]["attempts"] == 1
    assert "Archived prior runs disclosed: 1 (2 attempts)" in article_table(report)


# --- FR-7.2: pins resolve and the drift check has teeth ------------------------

def _check_pins():
    spec = importlib.util.spec_from_file_location("check_pins", ROOT/"scripts/check_pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recorded_pins_match_vendored_bytes():
    assert _check_pins().main() == 0


def test_tree_digest_detects_vendored_drift(tmp_path):
    module = _check_pins()
    base = tmp_path/"ext"
    base.mkdir()
    (base/"extension.yml").write_text("version: 1.0.0\n")
    before = module.tree_digest(base, set())
    (base/"extension.yml").write_text("version: 1.0.1\n")
    assert module.tree_digest(base, set()) != before
