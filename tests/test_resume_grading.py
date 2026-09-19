import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmark_runner.runner import run
from benchmark_runner.grading import grade
from benchmark_runner.store import Store, write_json


def test_resume_matching_config_retains_interrupted_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark_runner.runner.verify_freeze", lambda *a: None)
    monkeypatch.setattr("benchmark_runner.runner.validate_live", lambda *a: None)
    manifest = {"freeze_id": "frozen", "config": {"global_cap_usd": 3, "attempt_cap_usd": 1, "purpose": "synthetic"},
                "tasks": {"tasks": [{"instance_id": "t"}]},
                "schedule": [{"attempt_id": "a", "task_id": "t", "arm": "baseline", "repeat": 1}]}
    store = Store(tmp_path)
    store.append("attempts", {"attempt_id": "a", "status": "started"})
    write_json(tmp_path/"freeze.json", manifest)
    run(Path.cwd(), manifest, tmp_path)
    assert store.events("attempts")[-1]["status"] == "infrastructure_failure"
    count = len(store.events("attempts"))
    run(Path.cwd(), manifest, tmp_path)
    assert len(store.events("attempts")) == count
    changed = {**manifest, "freeze_id": "changed"}
    with pytest.raises(ValueError, match="mismatch"):
        run(Path.cwd(), changed, tmp_path)


def test_grader_uses_explicit_task_unique_run_and_schema(tmp_path, monkeypatch):
    store = Store(tmp_path)
    patch = store.artifact(b"SYNTHETIC PATCH")
    for i in (1, 2):
        store.append("attempts", {"attempt_id": f"a{i}", "task_id": "repo__repo-1", "patch": patch})
    monkeypatch.setattr("benchmark_runner.grading.subprocess.check_output",
                        lambda args, **kw: "" if "status" in args else "pinned\n")
    commands = []
    def fake(args, cwd, **kwargs):
        commands.append(args)
        predictions = json.loads(Path(args[args.index("-p")+1]).read_text())
        assert set(predictions) == {"instance_id", "model_name_or_path", "model_patch"}
        assert args[args.index("-i")+1] == "repo__repo-1"
        write_json(cwd/"report.json", {"repo__repo-1": {"resolved": True}})
        return SimpleNamespace(returncode=0, stdout=b"SYNTHETIC", stderr=b"")
    monkeypatch.setattr("benchmark_runner.grading.subprocess.run", fake)
    grade(store, tmp_path/"tasks", tmp_path/"harness", "pinned", "pinned")
    assert len(commands) == 2
    assert commands[0][commands[0].index("--run-id")+1] != commands[1][commands[1].index("--run-id")+1]
    assert all(e["resolved"] is True for e in store.events("grades"))
