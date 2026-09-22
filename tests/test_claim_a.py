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
    # The band analysis fail-closes on partial runs: the freeze schedule must
    # cover every recorded repair_ordinary attempt.
    (run / "freeze.json").write_text(json.dumps({"schedule": [
        {"attempt_id": a["attempt_id"], "task_id": a["task_id"], "arm": a["arm"]}
        for a in attempts]}))
    import subprocess, sys
    script = str(Path(__file__).resolve().parents[1] / "scripts" / "analyze_claim_a.py")
    kept = tmp_path / "kept.json"
    r = subprocess.run([sys.executable, script, "band", "--run", str(run), "--out", str(kept)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "kept 1/2 tasks" in r.stdout
    assert json.loads(kept.read_text()) == [["tinydb", "a", 20260921]]


def _partial_band_run(tmp_path, mutate):
    """Synthetic calibration run: 2 tasks x 2 ordinary repairs, all graded,
    with a freeze schedule covering every attempt. `mutate` alters one
    attempt/grade to simulate a partial or failed run."""
    from benchmark_runner.store import Store
    run = tmp_path / "run"
    run.mkdir()
    store = Store(run)
    aids = ["t1-r1", "t1-r2", "t2-r1", "t2-r2"]
    tids = {"t1-r1": "mr-tinydb-a-20260921", "t1-r2": "mr-tinydb-a-20260921",
            "t2-r1": "mr-cachetools-b-20260921", "t2-r2": "mr-cachetools-b-20260921"}
    for aid in aids:
        store.append("attempts", {"attempt_id": aid, "task_id": tids[aid],
                                 "arm": "repair_ordinary", "status": "completed",
                                 "repair_rounds": [{"public": {"passed": True},
                                                    "source_changed": True}]})
        store.append("hidden_grades", {"attempt_id": aid, "graded": True,
                                      "hidden_passed": aid in ("t1-r1", "t2-r1"),
                                      "test_count": 4, "failed_cases": []})
    (run / "freeze.json").write_text(json.dumps({"schedule": [
        {"attempt_id": aid, "task_id": tids[aid], "arm": "repair_ordinary"}
        for aid in aids]}))
    mutate(run)
    return run


def _run_band(run, tmp_path):
    a = _load_analyze()
    kept = tmp_path / "kept.json"
    a.cmd_band(type("A", (), {"run": run, "out": kept})())
    return kept


def _drop_attempt(run, aid):
    from benchmark_runner.store import Store
    store = Store(run)
    kept = [e for e in store.events("attempts") if e["attempt_id"] != aid]
    (run / "attempts.jsonl").write_text("".join(json.dumps(e) + "\n" for e in kept))


def test_band_refuses_never_ran_attempt(tmp_path):
    # The 2026-09-21 calibration halted after 7 of 32 tasks; the band gate ran
    # on the partial stream. It must now refuse instead.
    run = _partial_band_run(tmp_path, lambda r: _drop_attempt(r, "t2-r2"))
    with pytest.raises(ValueError, match="never ran"):
        _run_band(run, tmp_path)
    assert not (tmp_path / "kept.json").exists()


def test_band_refuses_error_attempt(tmp_path):
    def mutate(run):
        from benchmark_runner.store import Store
        store = Store(run)
        evts = store.events("attempts")
        for e in evts:
            if e["attempt_id"] == "t2-r2":
                e["status"] = "error"
                e["reason"] = "RuntimeError: diagnostic evidence not recorded"
        (run / "attempts.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evts))
    run = _partial_band_run(tmp_path, mutate)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        _run_band(run, tmp_path)
    assert not (tmp_path / "kept.json").exists()


def test_band_refuses_limit_attempt(tmp_path):
    # A "limit" attempt is terminal but not gradable; the task's pass rate
    # would be computed on fewer attempts than designed.
    def mutate(run):
        from benchmark_runner.store import Store
        store = Store(run)
        evts = store.events("attempts")
        for e in evts:
            if e["attempt_id"] == "t2-r2":
                e["status"] = "limit"
                e["reason"] = "unknown token usage; cannot enforce attempt token ceiling"
        (run / "attempts.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evts))
    run = _partial_band_run(tmp_path, mutate)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        _run_band(run, tmp_path)
    assert not (tmp_path / "kept.json").exists()


def test_band_refuses_ungraded_completed_attempt(tmp_path):
    from benchmark_runner.store import Store
    def mutate(run):
        grades = [e for e in Store(run).events("hidden_grades")
                  if e["attempt_id"] != "t2-r2"]
        (run / "hidden_grades.jsonl").write_text("".join(
            json.dumps(e) + "\n" for e in grades))
    run = _partial_band_run(tmp_path, mutate)
    with pytest.raises(ValueError, match="no hidden grade"):
        _run_band(run, tmp_path)
    assert not (tmp_path / "kept.json").exists()


def test_band_refuses_missing_freeze_schedule(tmp_path):
    from benchmark_runner.store import Store
    run = tmp_path / "run"
    run.mkdir()
    Store(run).append("attempts", {"attempt_id": "t1-r1", "arm": "repair_ordinary",
                                  "status": "completed"})
    with pytest.raises(ValueError, match="no freeze.json"):
        _run_band(run, tmp_path)


def test_error_reason_preserves_exception_message():
    # Regression for the 2026-09-21 calibration halt: the attempt record kept
    # only "RuntimeError" and the diagnostic message was lost.
    from benchmark_runner.runner import error_reason
    e = RuntimeError("diagnostic evidence not recorded for mr-tinydb-x--diagnose")
    assert error_reason(e) == ("RuntimeError: diagnostic evidence not recorded "
                               "for mr-tinydb-x--diagnose")


def test_error_reason_sanitizes_long_multiline_messages():
    from benchmark_runner.runner import error_reason
    e = ValueError("line one\nline two " + "x" * 500)
    reason = error_reason(e)
    assert reason.startswith("ValueError: line one line two")
    assert "\n" not in reason
    assert len(reason) <= len("ValueError: ") + 300
    assert error_reason(RuntimeError("")) == "RuntimeError"


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


def _load_analyze():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "scripts" / "analyze_claim_a.py"
    spec = importlib.util.spec_from_file_location("analyze_claim_a", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _attempt(public_passed=True, changed=True):
    return {"repair_rounds": [{"public": {"passed": public_passed},
                               "source_changed": changed}]}


def test_adjudication_accepted():
    a = _load_analyze()
    assert a.attempt_outcome(_attempt(), {"hidden_passed": True}, ["t1"]) == ("accepted", 0)


def test_adjudication_public_regression_is_wrong():
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(public_passed=False, changed=True),
                               {"hidden_passed": False, "failed_cases": ["t1"]}, ["t1"])
    assert (cls, w) == ("wrong", a.W_WRONG)


def test_adjudication_changed_but_only_baseline_failures_is_miss():
    """The refinement: changed source + hidden failure is NOT automatically
    wrong. Failing exactly the seeded defect's declared tests with public
    green is a miss (weight 1), not harm (weight 3)."""
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(changed=True),
                               {"hidden_passed": False, "failed_cases": ["t1", "t2"]},
                               ["t1", "t2"])
    assert (cls, w) == ("miss", a.W_MISS)


def test_adjudication_new_hidden_failures_is_wrong():
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(changed=True),
                               {"hidden_passed": False, "failed_cases": ["t1", "t9"]},
                               ["t1"])
    assert (cls, w) == ("wrong", a.W_WRONG)


def test_adjudication_partial_fix_is_miss():
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(changed=True),
                               {"hidden_passed": False, "failed_cases": ["t1"]},
                               ["t1", "t2"])
    assert (cls, w) == ("miss", a.W_MISS)


def test_adjudication_unchanged_is_miss():
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(changed=False),
                               {"hidden_passed": False, "failed_cases": ["t1"]},
                               ["t1"])
    assert (cls, w) == ("miss", a.W_MISS)


def test_adjudication_missing_baseline_falls_back_coarse(capsys):
    a = _load_analyze()
    cls, w = a.attempt_outcome(_attempt(changed=True),
                               {"hidden_passed": False, "failed_cases": ["t1"]})
    assert (cls, w) == ("wrong", a.W_WRONG)
    assert "coarse" in capsys.readouterr().err


def test_local_arm_nonzero_cost_fails_closed(tmp_path):
    """Cost placement: the local arm must never show measured dollars."""
    from benchmark_runner.store import Store
    a = _load_analyze()
    run = tmp_path / "run"
    store = Store(run)
    attempt_id = "mr-tinydb-x-20260921--repair_workflow-1"
    store.append("attempts", {"attempt_id": attempt_id, "task_id": "mr-tinydb-x-20260921",
                             "arm": "repair_workflow", "status": "completed",
                             "repair_rounds": [{"public": {"passed": True},
                                                "source_changed": False}]})
    store.append("hidden_grades", {"attempt_id": attempt_id, "graded": True,
                                   "hidden_passed": True, "failed_cases": []})
    store.append("calls", {"attempt_id": attempt_id, "cost": "0.01"})
    (run / "freeze.json").write_text(json.dumps(
        {"tasks": {"tasks": [{"instance_id": "mr-tinydb-x-20260921",
                              "hidden_baseline_failed_cases": []}]}}))
    with pytest.raises(ValueError, match="nonzero measured cost"):
        a.per_task_losses(run, ["mr-tinydb-x-20260921"], "repair_workflow")


def test_freeze_persists_hidden_baseline(monkeypatch, tmp_path):
    """build_freeze writes the seeded defect's hidden failures per task."""
    from benchmark_runner import claim_a as ca
    fixture = {"image": "img@sha256:" + "a" * 64, "base_commit": "abc123",
               "grade": {"test_count": 4, "failed_cases": ["test_r08_a", "test_r08_b"]}}
    monkeypatch.setattr(ca, "audit_solver_image", lambda image, project: {"audit_pass": True})
    monkeypatch.setattr(ca, "run_grade_smoke", lambda cal: {"ok": True})
    monkeypatch.setattr(ca, "verify_reservation_bounds", lambda cfg: {"ok": True})
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"fixtures": [
        {"project": "tinydb", "variant": "token_alias", **fixture}]}))
    cfg = claim_a.calibration_config()
    manifest = claim_a.build_freeze(
        tmp_path / "out", cal, cfg,
        claim_a.calibration_schedule([("tinydb", "token_alias", CLAIM_A_SEED)]),
        [("tinydb", "token_alias", CLAIM_A_SEED)],
        "freeze-test", "notes", "selection")
    task = manifest["tasks"]["tasks"][0]
    assert task["hidden_baseline_failed_cases"] == ["test_r08_a", "test_r08_b"]
    assert manifest["pairs"][0]["hidden_baseline_failed_cases"] == ["test_r08_a", "test_r08_b"]


# --- Regression tests: dependent-repair scheduling guard (2026-09-22) --------
# The revised paid calibration failed on its first paid attempt: the diagnose
# arm stopped at `limit` (unknown token usage after a provider HTTPError), the
# dependent repair_ordinary attempt started anyway, _diagnostic_for raised, and
# the run loop's fail-stop killed the whole 129-attempt campaign. The repair
# arms must now fail closed per task (recorded error, run continues) instead
# of raising an unexpected exception that aborts the run.

def _diag_manifest(tmp_path, with_diagnose=True):
    from benchmark_runner.store import Store
    schedule = []
    if with_diagnose:
        schedule.append({"attempt_id": "t1--diagnose", "task_id": "t1",
                         "arm": "diagnose", "repeat": 1})
    schedule.append({"attempt_id": "t1--repair", "task_id": "t1",
                     "arm": "repair_ordinary", "repeat": 1})
    return {"schedule": schedule}, Store(tmp_path)


def test_diagnostic_for_raises_diagnostic_unavailable_on_missing_evidence(tmp_path):
    # Diagnose was scheduled but produced no diagnostic event (e.g. it stopped
    # at `limit`): this is a per-task dependency failure, not a harness bug.
    from benchmark_runner.matched_repair import DiagnosticUnavailable, _diagnostic_for
    manifest, store = _diag_manifest(tmp_path, with_diagnose=True)
    with pytest.raises(DiagnosticUnavailable, match="diagnostic evidence not recorded"):
        _diagnostic_for(store, manifest, {"instance_id": "t1"})


def test_diagnostic_for_raises_runtime_error_when_nothing_scheduled(tmp_path):
    # No diagnose attempt in the schedule at all: a manifest bug, stays loud.
    from benchmark_runner.matched_repair import _diagnostic_for
    manifest, store = _diag_manifest(tmp_path, with_diagnose=False)
    with pytest.raises(RuntimeError, match="no diagnostic attempt scheduled"):
        _diagnostic_for(store, manifest, {"instance_id": "t1"})


def test_diagnostic_for_returns_evidence_when_present(tmp_path):
    from benchmark_runner.matched_repair import _diagnostic_for
    manifest, store = _diag_manifest(tmp_path, with_diagnose=True)
    store.append("diagnostics", {"attempt_id": "t1--diagnose", "summary": {"done": True}})
    assert _diagnostic_for(store, manifest, {"instance_id": "t1"})["attempt_id"] == "t1--diagnose"


class _FakeSandbox:
    def __init__(self, image):
        self.details = {"image": image}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, cmd, timeout=None):
        return {"exit_code": 0, "stdout": "abc123"}


def _run_manifest():
    tasks = [{"instance_id": tid, "image": "img", "base_commit": "abc123"}
             for tid in ("t1", "t2")]
    schedule = []
    for tid in ("t1", "t2"):
        schedule.append({"attempt_id": f"{tid}--diagnose", "task_id": tid,
                         "arm": "diagnose", "repeat": 1})
        schedule.append({"attempt_id": f"{tid}--repair", "task_id": tid,
                         "arm": "repair_ordinary", "repeat": 1})
    return {"freeze_id": "f" * 16,
            "config": {"global_cap_usd": 100, "attempt_cap_usd": 25,
                       "purpose": "synthetic"},
            "tasks": {"tasks": tasks},
            "schedule": schedule}


def _terminal_statuses(tmp_path):
    from benchmark_runner.store import Store
    final = {}
    for e in Store(tmp_path).events("attempts"):
        final[e["attempt_id"]] = e.get("status")
    return final, {e["attempt_id"]: e.get("reason") for e in Store(tmp_path).events("attempts")}


def _patch_run_harness(monkeypatch):
    monkeypatch.setattr("benchmark_runner.runner.verify_freeze", lambda *a: None)
    monkeypatch.setattr("benchmark_runner.runner.validate_live", lambda *a: None)
    monkeypatch.setattr("benchmark_runner.runner.DockerSandbox", _FakeSandbox)
    monkeypatch.setattr("benchmark_runner.runner.make_provider",
                        lambda *a: object())


def test_run_continues_after_diagnostic_unavailable(tmp_path, monkeypatch):
    # t1's repair cannot run (no diagnostic evidence): it is recorded as an
    # error and the schedule continues with t2 instead of fail-stopping.
    from benchmark_runner.matched_repair import DiagnosticUnavailable
    from benchmark_runner.runner import run
    _patch_run_harness(monkeypatch)

    def fake_execute(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if identity["attempt_id"] == "t1--repair":
            raise DiagnosticUnavailable("diagnostic evidence not recorded for t1--diagnose")
        return {}

    monkeypatch.setattr("benchmark_runner.runner.execute_attempt", fake_execute)
    run(Path.cwd(), _run_manifest(), tmp_path)
    statuses, reasons = _terminal_statuses(tmp_path)
    assert statuses["t1--repair"] == "error"
    assert reasons["t1--repair"].startswith("repair blocked:")
    assert "diagnostic evidence not recorded" in reasons["t1--repair"]
    # The run continued: t2's attempts both started and completed.
    assert statuses["t2--diagnose"] == "completed"
    assert statuses["t2--repair"] == "completed"


def test_run_still_breaks_on_unexpected_error(tmp_path, monkeypatch):
    # A genuine unexpected exception keeps the existing fail-stop behavior.
    from benchmark_runner.runner import run
    _patch_run_harness(monkeypatch)

    def fake_execute(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
        if identity["attempt_id"] == "t1--repair":
            raise RuntimeError("simulated harness bug")
        return {}

    monkeypatch.setattr("benchmark_runner.runner.execute_attempt", fake_execute)
    run(Path.cwd(), _run_manifest(), tmp_path)
    statuses, reasons = _terminal_statuses(tmp_path)
    assert statuses["t1--repair"] == "error"
    assert reasons["t1--repair"] == "RuntimeError: simulated harness bug"
    # Fail-stop: t2 never started.
    assert "t2--diagnose" not in statuses
