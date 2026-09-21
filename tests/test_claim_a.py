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
    # Workflow treatment budget: six phases x WORKFLOW_CALLS_PER_PHASE actions
    # plus bounded AEE recovery headroom; local calls are zero marginal dollars.
    assert cfg["max_calls"] == 64
    assert cfg["max_calls"] >= 6 * 8


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
    l = main_schedule(kept, "repair_workflow")
    assert [s["arm"] for s in f] == ["diagnose", "repair_ordinary", "repair_ordinary"]
    assert [s["arm"] for s in l] == ["diagnose", "repair_workflow", "repair_workflow"]
    # same task ids across backends: the offline analysis pairs them by task
    assert [s["task_id"] for s in f] == [s["task_id"] for s in l]
    with pytest.raises(AssertionError):
        main_schedule(kept, "diagnose")
    with pytest.raises(AssertionError):
        main_schedule(kept, "repair_guided")  # superseded by the workflow treatment


def test_pilot_schedule_single_task():
    kept = [("tinydb", "a", CLAIM_A_SEED), ("cachetools", "b", CLAIM_A_SEED)]
    sched = pilot_schedule(kept)
    assert len(sched) == 2
    assert all(s["task_id"] == "mr-tinydb-a-20260921" for s in sched)
    assert [s["arm"] for s in sched] == ["diagnose", "repair_workflow"]


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
        tmp_path / "out", cal, cfg, main_schedule(pairs, "repair_workflow"),
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


def test_repair_workflow_arm_registered():
    from benchmark_runner.matched_repair import MATCHED_ARMS
    from benchmark_runner.schema import ARM_ENUM
    assert "repair_workflow" in MATCHED_ARMS
    assert "repair_workflow" in ARM_ENUM  # provider telemetry rejects unknown arms


def test_workflow_treatment_uses_frozen_phases_and_prompts(tmp_path):
    # Treatment fidelity: the repair_workflow arm must execute the exact
    # frozen six-phase Spec-Kit+AEE workflow with the frozen skill prompts,
    # not a reimplementation.
    from benchmark_runner.workflow import AEE_PHASES, phase_prompt, phases
    assert phases("spec_kit_aee") == ("constitution", "specify", "plan",
                                      "tasks", "implement", "converge")
    assert AEE_PHASES == {"specify", "plan", "tasks", "implement"}
    root = Path(__file__).resolve().parents[1]
    for phase in phases("spec_kit_aee"):
        prompt = phase_prompt(root, "spec_kit_aee", phase)
        assert f"speckit-{phase}" in prompt  # the actual frozen skill file
        assert "Code lives in /testbed" in prompt  # the frozen adapter framing


def test_workflow_call_budget_documented(monkeypatch):
    from benchmark_runner.matched_repair import WORKFLOW_CALLS_PER_PHASE
    assert WORKFLOW_CALLS_PER_PHASE == 8
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    local_cfg = main_config_local([("tinydb", "x", CLAIM_A_SEED)])
    # Six phases x per-phase actions, plus bounded AEE recovery headroom.
    assert local_cfg["max_calls"] >= 6 * WORKFLOW_CALLS_PER_PHASE


def test_execute_matched_attempt_routes_workflow(monkeypatch):
    import benchmark_runner.matched_repair as mr
    seen = {}
    def fake_run_workflow(root, task, provider, sandbox, store, identity, cfg, manifest):
        seen["called"] = True
        return {"ok": True}
    monkeypatch.setattr(mr, "run_workflow_repair", fake_run_workflow)
    out = mr.execute_matched_attempt(None, None, "repair_workflow", None, None,
                                     None, None, None, None)
    assert out == {"ok": True}
    assert seen.get("called") is True


def test_problem_statement_names_workflow_treatment():
    from benchmark_runner.claim_a import problem_statement
    text = problem_statement("mr-tinydb-x-20260921", "tinydb")
    assert "Spec-Kit+AEE workflow" in text
    assert "guided" not in text.lower()


def test_analyze_compare_with_workflow_arm(tmp_path):
    # The offline comparison must pair frontier ordinary repair against the
    # local workflow arm (not the superseded guided arm).
    from benchmark_runner.store import Store
    import subprocess, sys
    script = str(Path(__file__).resolve().parents[1] / "scripts" / "analyze_claim_a.py")
    kept = tmp_path / "kept.json"
    kept.write_text(json.dumps([["tinydb", "a", 20260921]]))
    task_id = "mr-tinydb-a-20260921"
    run_f, run_l = tmp_path / "frontier", tmp_path / "local"
    run_f.mkdir(); run_l.mkdir()
    sf, sl = Store(run_f), Store(run_l)
    sf.append("attempts", {"attempt_id": "f1", "task_id": task_id, "arm": "repair_ordinary",
                           "status": "completed",
                           "repair_rounds": [{"public": {"passed": True}, "source_changed": True}]})
    sf.append("hidden_grades", {"attempt_id": "f1", "graded": True, "hidden_passed": True,
                               "test_count": 4, "failed_cases": []})
    sf.append("calls", {"attempt_id": "f1", "cost": "0.50"})
    sl.append("attempts", {"attempt_id": "l1", "task_id": task_id, "arm": "repair_workflow",
                           "status": "completed",
                           "repair_rounds": [{"public": {"passed": True}, "source_changed": True}],
                           "workflow_completed": True})
    sl.append("hidden_grades", {"attempt_id": "l1", "graded": True, "hidden_passed": True,
                               "test_count": 4, "failed_cases": []})
    sl.append("calls", {"attempt_id": "l1", "cost": "0"})
    r = subprocess.run([sys.executable, script, "compare", "--frontier", str(run_f),
                        "--local", str(run_l), "--kept", str(kept)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "NON-INFERIOR" in r.stdout
    assert "dollars per accepted" in r.stdout
