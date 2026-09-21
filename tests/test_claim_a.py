"""Offline tests for the Claim A campaign module.

No Docker, no network, no model calls: the freeze builder's Docker-touching
gates are monkeypatched; what is tested is the wiring (schedules, configs,
manifest structure, backend separation).
"""
import json
from pathlib import Path

import pytest

import benchmark_runner.claim_a as claim_a
from benchmark_runner.claim_a import (
    CLAIM_A_SEED,
    calibration_config,
    calibration_schedule,
    main_config_frontier,
    main_config_local,
    main_schedule,
    pilot_schedule,
)


def test_calibration_config_is_frontier_scored():
    cfg = calibration_config()
    assert cfg["purpose"] == "claim_a_calibration"
    assert cfg["provider_backend"] == "openai"
    assert cfg["seed"] == CLAIM_A_SEED
    assert cfg["real_smoke_verified"] is True
    assert "RUN" in cfg["budget_authorization"]


def test_main_frontier_config():
    cfg = main_config_frontier([])
    assert cfg["purpose"] == "claim_a_main"
    assert cfg["provider_backend"] == "openai"
    assert cfg["reasoning_effort"] == "medium"


def test_main_local_config_requires_model_env(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)
    with pytest.raises(ValueError, match="LOCAL_MODEL_NAME"):
        main_config_local([])
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    cfg = main_config_local([("tinydb", "x", CLAIM_A_SEED)])
    assert cfg["provider_backend"] == "local"
    assert cfg["model"] == "qwen3-8b-local"
    assert "reasoning_effort" not in cfg  # OpenAI-only; LocalProvider must not receive it
    assert cfg["prices"]["output"] == 0.0
    assert cfg["real_smoke_verified"] is False  # until the pilot evidence lands
    cfg2 = main_config_local([("tinydb", "x", CLAIM_A_SEED)],
                             real_smoke_evidence="pilot run ok")
    assert cfg2["real_smoke_verified"] is True
    assert cfg2["real_smoke_evidence"] == "pilot run ok"


def test_calibration_schedule():
    cands = [("tinydb", "a", CLAIM_A_SEED), ("cachetools", "b", CLAIM_A_SEED)]
    sched = calibration_schedule(cands)
    assert len(sched) == 6  # 2 tasks x (1 diagnose + 2 repairs)
    arms = [s["arm"] for s in sched[:3]]
    assert arms == ["diagnose", "repair_ordinary", "repair_ordinary"]
    ids = [s["attempt_id"] for s in sched]
    assert len(set(ids)) == 6  # unique attempt ids (resume keys)
    assert sched[0]["task_id"] == "mr-tinydb-a-20260921"
    # deterministic: same input, same output
    assert calibration_schedule(cands) == sched


def test_main_schedule_arms():
    kept = [("tinydb", "a", CLAIM_A_SEED)]
    f = main_schedule(kept, "repair_ordinary")
    l = main_schedule(kept, "repair_guided")
    assert [s["arm"] for s in f] == ["diagnose", "repair_ordinary", "repair_ordinary"]
    assert [s["arm"] for s in l] == ["diagnose", "repair_guided", "repair_guided"]
    # same task ids across backends: the offline analysis pairs them by task
    assert [s["task_id"] for s in f] == [s["task_id"] for s in l]
    with pytest.raises(AssertionError):
        main_schedule(kept, "diagnose")


def test_pilot_schedule_single_task():
    kept = [("tinydb", "a", CLAIM_A_SEED), ("cachetools", "b", CLAIM_A_SEED)]
    sched = pilot_schedule(kept)
    assert len(sched) == 2
    assert all(s["task_id"] == "mr-tinydb-a-20260921" for s in sched)
    assert [s["arm"] for s in sched] == ["diagnose", "repair_guided"]


FAKE_CALIBRATION = {
    "fixtures": [
        {"project": "tinydb", "variant": "a", "image": "img-a", "base_commit": "c" * 40,
         "grade": {"test_count": 10}},
        {"project": "cachetools", "variant": "b", "image": "img-b", "base_commit": "d" * 40,
         "grade": {"test_count": 12}},
        {"project": "tinydb", "variant": "clean", "image": "img-c", "base_commit": "e" * 40,
         "grade": {"test_count": 8}},
    ]
}


@pytest.fixture()
def patched_gates(monkeypatch):
    monkeypatch.setattr(claim_a, "verify_reservation_bounds", lambda cfg: {"verified": True})
    monkeypatch.setattr(claim_a, "audit_solver_image",
                        lambda image, project: {"audit_pass": True, "hidden_markers": []})
    monkeypatch.setattr(claim_a, "run_grade_smoke", lambda cal: {"passed": True})
    monkeypatch.setattr(claim_a, "source_hash", lambda path: "hash")
    monkeypatch.setattr(claim_a, "frozen_paths", lambda root: ["pyproject.toml"])


def _write_calibration(tmp_path):
    p = tmp_path / "calibration.json"
    p.write_text(json.dumps(FAKE_CALIBRATION))
    return p


def test_build_freeze_manifest(tmp_path, patched_gates, monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    cal = _write_calibration(tmp_path)
    pairs = [("tinydb", "a", CLAIM_A_SEED), ("cachetools", "b", CLAIM_A_SEED)]
    cfg = main_config_local(pairs, real_smoke_evidence="pilot ok")
    manifest = claim_a.build_freeze(
        tmp_path / "out", cal, cfg, main_schedule(pairs, "repair_guided"),
        pairs, "freeze-test", "notes", "selection")
    assert manifest["config"]["provider_backend"] == "local"
    assert manifest["config"]["reservation_bound_verified"] is True
    assert manifest["config"]["grader_smoke_verified"] is True
    assert manifest["config"]["solver_image_audit_verified"] is True
    assert len(manifest["schedule"]) == 6
    assert len(manifest["pairs"]) == 2
    assert len(manifest["tasks"]["tasks"]) == 2
    assert manifest["tasks"]["tasks"][0]["hidden_test_count"] == 10
    # freeze_id is deterministic over the manifest content
    out_file = tmp_path / "out" / "freeze-test.json"
    assert out_file.exists()
    reread = json.loads(out_file.read_text())
    assert reread["freeze_id"] == manifest["freeze_id"]


def test_build_freeze_rejects_unknown_fixture(tmp_path, patched_gates):
    cal = _write_calibration(tmp_path)
    with pytest.raises(ValueError, match="no calibrated fixture"):
        claim_a.build_freeze(tmp_path / "out", cal, calibration_config(),
                             [], [("tinydb", "nope", CLAIM_A_SEED)],
                             "freeze-test", "notes", "selection")


def test_build_freeze_rejects_empty_candidates(monkeypatch):
    monkeypatch.setattr(claim_a, "CLAIM_A_CANDIDATES", ())
    with pytest.raises(ValueError, match="CLAIM_A_CANDIDATES is empty"):
        claim_a.cmd_freeze_calibration(
            type("A", (), {"out": Path("/tmp/x"), "calibration": Path("/tmp/y")})())


def test_analyze_band_and_compare(tmp_path, monkeypatch):
    # Exercise the analysis script against a synthetic run store.
    from benchmark_runner.store import Store, write_json
    run = tmp_path / "run"
    run.mkdir()
    store = Store(run)
    # two tasks, two ordinary repairs each: t1 splits 1/1 (kept), t2 passes 2/2 (dropped)
    attempts = [
        {"attempt_id": "t1-r1", "task_id": "mr-tinydb-a-20260921", "arm": "repair_ordinary",
         "status": "completed",
         "repair_rounds": [{"public": {"passed": True}, "source_changed": True}]},
        {"attempt_id": "t1-r2", "task_id": "mr-tinydb-a-20260921", "arm": "repair_ordinary",
         "status": "completed",
         "repair_rounds": [{"public": {"passed": True}, "source_changed": False}]},
        {"attempt_id": "t2-r1", "task_id": "mr-cachetools-b-20260921", "arm": "repair_ordinary",
         "status": "completed",
         "repair_rounds": [{"public": {"passed": True}, "source_changed": True}]},
        {"attempt_id": "t2-r2", "task_id": "mr-cachetools-b-20260921", "arm": "repair_ordinary",
         "status": "completed",
         "repair_rounds": [{"public": {"passed": True}, "source_changed": True}]},
    ]
    for a in attempts:
        store.append("attempts", a)
    for aid, passed in [("t1-r1", True), ("t1-r2", False), ("t2-r1", True), ("t2-r2", True)]:
        store.append("hidden_grades", {"attempt_id": aid, "graded": True, "hidden_passed": passed,
                                      "test_count": 4, "failed_cases": [] if passed else ["x"]})
    import subprocess, sys
    script = str(Path(__file__).resolve().parents[1] / "scripts" / "analyze_claim_a.py")
    kept = tmp_path / "kept.json"
    r = subprocess.run([sys.executable, script, "band", "--run", str(run), "--out", str(kept)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "kept 1/2 tasks" in r.stdout
    assert json.loads(kept.read_text()) == [["tinydb", "a", 20260921]]
