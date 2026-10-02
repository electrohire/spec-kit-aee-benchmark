"""Host dry run for the Claim A freeze wiring (offline).

Exercises the real CLI subcommands the host script calls --
freeze-calibration, freeze-pilot, freeze-main (frontier + local) -- with the
Docker-touching gates mocked. No Docker, no network, no model calls, no
spend. What is verified is the wiring Tristen's host run will execute:
manifest structure, schedules, arm selection, baselines, budget gates, and
the offline analysis band/compare path on synthetic runs.
"""
import importlib.util
import json
from pathlib import Path

import pytest

import benchmark_runner.claim_a as ca
from benchmark_runner.claim_a import CLAIM_A_SEED
from benchmark_runner.experiment import verify_freeze


def _synthetic_calibration(path):
    fixtures = []
    for project, variant, seed in ca.CLAIM_A_CANDIDATES:
        fixtures.append({
            "project": project, "variant": variant,
            "image": f"localhost:5000/mr-fixture-{project}-{variant}@sha256:" + "a" * 64,
            "base_commit": "b" * 40,
            "grade": {"test_count": 4, "failed_cases": [f"test_{variant}_hidden"]},
        })
    path.write_text(json.dumps({"fixtures": fixtures}))


@pytest.fixture()
def dryrun(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "audit_solver_image",
                        lambda image, project: {"audit_pass": True, "hidden_markers": []})
    monkeypatch.setattr(ca, "run_grade_smoke", lambda cal: {"ok": True})
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    cal = tmp_path / "calibration.json"
    _synthetic_calibration(cal)
    return tmp_path


def _freeze_cli(*argv):
    ca.main(list(argv))


def test_freeze_calibration_wiring(dryrun):
    out = dryrun / "freeze-cal"
    _freeze_cli("freeze-calibration", str(out), "--calibration", str(dryrun / "calibration.json"))
    manifest = json.loads((out / "freeze-claim-a-calibration.json").read_text())
    assert len(manifest["tasks"]["tasks"]) == len(ca.CLAIM_A_CANDIDATES)
    arms = {e["arm"] for e in manifest["schedule"]}
    assert arms == {"diagnose", "repair_ordinary"}
    # Every task carries its hidden-failure baseline for adjudication.
    for t in manifest["tasks"]["tasks"]:
        assert t["hidden_baseline_failed_cases"] == [f"test_{t['instance_id'].split('-')[2]}_hidden"]
    verify_freeze(Path(__file__).resolve().parents[1], manifest)
    # Deterministic: rebuilding yields the same freeze_id.
    out2 = dryrun / "freeze-cal2"
    _freeze_cli("freeze-calibration", str(out2), "--calibration", str(dryrun / "calibration.json"))
    m2 = json.loads((out2 / "freeze-claim-a-calibration.json").read_text())
    assert m2["freeze_id"] == manifest["freeze_id"]


def test_freeze_pilot_and_main_wiring(dryrun):
    kept = [[p, v, s] for p, v, s in ca.CLAIM_A_CANDIDATES[:3]]
    kept_path = dryrun / "kept.json"
    kept_path.write_text(json.dumps(kept))
    cal = str(dryrun / "calibration.json")

    out = dryrun / "freeze-pilot"
    _freeze_cli("freeze-pilot", str(out), "--calibration", cal, "--kept", str(kept_path))
    pilot = json.loads((out / "freeze-claim-a-pilot.json").read_text())
    assert [e["arm"] for e in pilot["schedule"]] == ["diagnose", "repair_workflow"]
    assert pilot["config"]["purpose"] == "development_smoke"
    assert pilot["config"]["real_smoke_verified"] is False

    out = dryrun / "freeze-frontier"
    _freeze_cli("freeze-main", str(out), "--calibration", cal, "--kept", str(kept_path),
                "--backend", "frontier")
    frontier = json.loads((out / "freeze-claim-a-frontier.json").read_text())
    assert {e["arm"] for e in frontier["schedule"]} == {"diagnose", "repair_ordinary"}
    assert frontier["config"]["provider_backend"] == "openai"

    out = dryrun / "freeze-local"
    _freeze_cli("freeze-main", str(out), "--calibration", cal, "--kept", str(kept_path),
                "--backend", "local", "--pilot-evidence", "pilot run ok")
    local = json.loads((out / "freeze-claim-a-local.json").read_text())
    assert {e["arm"] for e in local["schedule"]} == {"diagnose", "repair_workflow"}
    assert local["config"]["max_calls"] == 64
    assert local["config"]["real_smoke_verified"] is True
    assert local["config"]["budget_authorization"]
    for m in (pilot, frontier, local):
        verify_freeze(Path(__file__).resolve().parents[1], m)


def test_local_main_without_pilot_evidence_is_not_runnable(dryrun):
    """The pilot gate: a local main freeze built without pilot evidence must
    carry real_smoke_verified=False, which runner.validate_live refuses."""
    kept = [[p, v, s] for p, v, s in ca.CLAIM_A_CANDIDATES[:2]]
    kept_path = dryrun / "kept.json"
    kept_path.write_text(json.dumps(kept))
    out = dryrun / "freeze-local-nopilot"
    _freeze_cli("freeze-main", str(out), "--calibration", str(dryrun / "calibration.json"),
                "--kept", str(kept_path), "--backend", "local")
    local = json.loads((out / "freeze-claim-a-local.json").read_text())
    assert local["config"]["real_smoke_verified"] is False
    from benchmark_runner.runner import validate_live
    with pytest.raises(ValueError, match="real adapter/usage smoke"):
        validate_live(local, smoke=False)


def _load_analyze():
    path = Path(__file__).resolve().parents[1] / "scripts" / "analyze_claim_a.py"
    spec = importlib.util.spec_from_file_location("analyze_claim_a", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_run(path, arm, results, cost):
    """results: task_id -> list of (hidden_passed, failed_cases)."""
    from benchmark_runner.store import Store
    store = Store(path)
    schedule = []
    for task_id, attempts in results.items():
        for i, (passed, failed) in enumerate(attempts, 1):
            aid = f"{task_id}--{arm}-{i}"
            schedule.append({"attempt_id": aid, "task_id": task_id, "arm": arm})
            store.append("attempts", {
                "attempt_id": aid, "task_id": task_id, "arm": arm, "status": "completed",
                "repair_rounds": [{"public": {"passed": True}, "source_changed": not passed}]})
            store.append("hidden_grades", {
                "attempt_id": aid, "graded": True, "hidden_passed": passed,
                "failed_cases": failed})
            if cost:
                store.append("calls", {"attempt_id": aid, "cost": cost})
    (path / "freeze.json").write_text(json.dumps({
        "schedule": schedule,
        "tasks": {"tasks": [
            {"instance_id": t, "hidden_baseline_failed_cases": ["test_hidden"]}
            for t in results]}}))


def test_band_and_compare_end_to_end(dryrun, capsys):
    a = _load_analyze()
    tasks = [f"mr-tinydb-v{i}-{CLAIM_A_SEED}" for i in range(3)]
    cal_results = {t: [(True, []), (False, ["test_hidden"])] for t in tasks}
    cal_run = dryrun / "runs-cal"
    _synthetic_run(cal_run, "repair_ordinary", cal_results, "0.50")
    kept_path = dryrun / "kept.json"
    a.cmd_band(type("A", (), {"run": cal_run, "out": kept_path})())
    kept = json.loads(kept_path.read_text())
    assert len(kept) == 3  # 1/2 pass rate is inside the 0.2-0.8 band

    kept_ids = ["mr-" + "-".join([t[0], t[1], str(t[2])]) for t in kept]
    frontier_run, local_run = dryrun / "runs-frontier", dryrun / "runs-local"
    _synthetic_run(frontier_run, "repair_ordinary",
                   {t: [(True, []), (False, ["test_hidden"])] for t in kept_ids}, "0.50")
    _synthetic_run(local_run, "repair_workflow",
                   {t: [(True, []), (True, [])] for t in kept_ids}, "0")
    a.cmd_compare(type("A", (), {"frontier": frontier_run, "local": local_run,
                                 "kept": kept_path})())
    out = capsys.readouterr().out
    assert "NON-INFERIOR" in out
    assert "dollars per accepted" in out
