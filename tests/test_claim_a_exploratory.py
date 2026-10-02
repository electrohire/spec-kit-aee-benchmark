"""Offline tests for the exploratory Claim A campaign tooling.

No Docker, no network, no model calls: schedule/config wiring plus the
persisted fidelity verifier (scripts/verify_pilot.py), loaded from the file
path so the scripts/ directory needs no package structure.
"""
import importlib.util
import json
from pathlib import Path

import pytest

import benchmark_runner.claim_a as claim_a
from benchmark_runner.claim_a import (
    CLAIM_A_SEED,
    exploratory_config_local,
    exploratory_schedule,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_pilot", SCRIPTS_DIR / "verify_pilot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exploratory_schedule_one_repeat_per_task():
    kept = [("tinydb", "token_ops_alias", CLAIM_A_SEED),
            ("cachetools", "maxsize_bool", CLAIM_A_SEED)]
    sched = exploratory_schedule(kept)
    assert len(sched) == 4
    assert [e["arm"] for e in sched] == ["diagnose", "repair_workflow"] * 2
    assert sched[0]["attempt_id"] == "mr-tinydb-token_ops_alias-20260921--diagnose"
    assert sched[1]["attempt_id"] == "mr-tinydb-token_ops_alias-20260921--repair_workflow-1"
    assert sched[2]["task_id"] == "mr-cachetools-maxsize_bool-20260921"
    # deterministic: pure function of the kept list
    assert exploratory_schedule(kept) == sched


def test_exploratory_schedule_full_bank_scales():
    kept = [(f"p{i}", f"v{i}", CLAIM_A_SEED) for i in range(43)]
    sched = exploratory_schedule(kept)
    assert len(sched) == 86
    assert len({e["attempt_id"] for e in sched}) == 86


def test_exploratory_config_local_smoke_purpose(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)
    with pytest.raises(ValueError, match="LOCAL_MODEL_NAME"):
        exploratory_config_local([])
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3-8b-local")
    cfg = exploratory_config_local([("tinydb", "x", CLAIM_A_SEED)])
    assert cfg["purpose"] == "development_smoke"  # runnable under --smoke
    assert cfg["provider_backend"] == "local"
    assert cfg["model"] == "qwen3-8b-local"
    assert cfg["prices"]["output"] == 0.0
    assert "reasoning_effort" not in cfg  # OpenAI-only; LocalProvider must not receive it
    assert cfg["max_calls"] == 64
    assert cfg["real_smoke_verified"] is False
    cfg2 = exploratory_config_local([("tinydb", "x", CLAIM_A_SEED)],
                                    real_smoke_evidence="/runs/pilot")
    assert cfg2["real_smoke_verified"] is True
    assert cfg2["real_smoke_evidence"] == "/runs/pilot"


def _write_run(tmp_path, attempts, phases, assessments):
    root = tmp_path / "run"
    root.mkdir()
    (root / "attempts.jsonl").write_text(
        "\n".join(json.dumps(a) for a in attempts) + "\n")
    (root / "phases.jsonl").write_text(
        "\n".join(json.dumps(p) for p in phases) + "\n")
    (root / "assessments.jsonl").write_text(
        "\n".join(json.dumps(a) for a in assessments) + "\n")
    return root


def _good_run(tmp_path, wid="t--repair_workflow-1", did="t--diagnose"):
    phases = []
    root = tmp_path / "run"
    root.mkdir()
    for i, phase in enumerate(("workflow_constitution", "workflow_specify",
                               "workflow_plan", "workflow_tasks",
                               "workflow_implement", "workflow_converge")):
        detail = {"phase": phase, "done": {"action": "done", "summary": "ok"},
                  "errors": []}
        apath = root / f"phase{i}.json"
        apath.write_text(json.dumps(detail))
        phases.append({"attempt_id": wid, "phase": phase, "completed": True,
                       "calls": 3, "artifact": {"path": f"phase{i}.json"}})
    attempts = [
        {"attempt_id": did, "arm": "diagnose", "status": "completed"},
        {"attempt_id": wid, "arm": "repair_workflow", "status": "completed"},
    ]
    (root / "attempts.jsonl").write_text(
        "\n".join(json.dumps(a) for a in attempts) + "\n")
    (root / "phases.jsonl").write_text(
        "\n".join(json.dumps(p) for p in phases) + "\n")
    (root / "assessments.jsonl").write_text(
        json.dumps({"attempt_id": wid, "score": 1}) + "\n")
    return root


def test_verifier_pilot_ok(tmp_path, capsys):
    mod = _load_verifier()
    root = _good_run(tmp_path)
    assert mod.main([str(root)]) == 0
    assert "PILOT_FIDELITY_OK" in capsys.readouterr().out


def test_verifier_rejects_all_provider_error_phase(tmp_path, capsys):
    mod = _load_verifier()
    root = _good_run(tmp_path)
    bad = {"phase": "workflow_specify", "done": None,
           "errors": ["ProviderError: TimeoutError"] * 8}
    (root / "phase1.json").write_text(json.dumps(bad))
    assert mod.main([str(root)]) == 1
    assert "zero model responses" in capsys.readouterr().out


def test_verifier_rejects_incomplete_phase(tmp_path, capsys):
    mod = _load_verifier()
    root = _good_run(tmp_path)
    recs = [json.loads(l) for l in (root / "phases.jsonl").read_text().splitlines()]
    recs[2]["completed"] = False
    (root / "phases.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    assert mod.main([str(root)]) == 1
    assert "not completed" in capsys.readouterr().out


def test_verifier_rejects_missing_assessments(tmp_path, capsys):
    mod = _load_verifier()
    root = _good_run(tmp_path)
    (root / "assessments.jsonl").write_text("")
    assert mod.main([str(root)]) == 1
    assert "no AEE assessments" in capsys.readouterr().out


def test_verifier_pilot_incomplete_is_exit_2(tmp_path, capsys):
    mod = _load_verifier()
    root = tmp_path / "run"
    root.mkdir()
    (root / "attempts.jsonl").write_text(
        json.dumps({"attempt_id": "t--diagnose", "arm": "diagnose",
                    "status": "completed"}) + "\n")
    assert mod.main([str(root)]) == 2


def test_verifier_campaign_mode(tmp_path, capsys):
    mod = _load_verifier()
    root = _good_run(tmp_path, wid="t1--repair_workflow-1", did="t1--diagnose")
    manifest = {"schedule": [
        {"attempt_id": "t1--diagnose", "arm": "diagnose", "task_id": "t1"},
        {"attempt_id": "t1--repair_workflow-1", "arm": "repair_workflow",
         "task_id": "t1"},
    ]}
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest))
    assert mod.main([str(root), "--manifest", str(mpath)]) == 0
    assert "CAMPAIGN_FIDELITY_OK" in capsys.readouterr().out
    # a scheduled attempt missing from the run -> incomplete, exit 2
    manifest["schedule"].append({"attempt_id": "t2--diagnose", "arm": "diagnose",
                                 "task_id": "t2"})
    mpath.write_text(json.dumps(manifest))
    assert mod.main([str(root), "--manifest", str(mpath)]) == 2
