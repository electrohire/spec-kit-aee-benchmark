import json
from pathlib import Path

import pytest

from benchmark_runner.experiment import ARMS, freeze, schedule, select, verify_freeze
from benchmark_runner.isolation import docker_args
from benchmark_runner.runner import validate_live
from benchmark_runner.store import RunLock, Store, read_json, sha


def tasks(n=24):
    return [dict(instance_id=f"r__r-{i}", repo=f"r{i%4}/r", base_commit="a"*40,
                 problem_statement="SYNTHETIC issue", patch="HIDDEN", test_patch="HIDDEN") for i in range(n)]


def test_selection_stratification_redaction_schedule():
    selected = select(tasks())
    assert selected == select(list(reversed(tasks())))
    assert len(selected["tasks"]) == 20
    assert all("patch" not in t and "test_patch" not in t for t in selected["tasks"])
    scheduled = schedule(selected["tasks"], 3, 123)
    assert len(scheduled) == len({r["attempt_id"] for r in scheduled}) == 180
    assert {arm: sum(r["arm"] == arm for r in scheduled) for arm in ARMS} == dict.fromkeys(ARMS, 60)
    with pytest.raises(ValueError):
        select(tasks()+tasks())


def test_no_mounts_network_or_secret_env():
    args = docker_args("example/image@sha256:"+"a"*64, "test")
    assert "--network=none" in args
    assert not any(x in args for x in ("-v", "--volume", "--mount", "-e", "--env", "--privileged"))
    with pytest.raises(ValueError):
        docker_args("floating:latest", "test")


def test_store_immutable_and_lock(tmp_path):
    store = Store(tmp_path)
    ref = store.artifact(b"synthetic Bearer secret-token")
    assert sha((tmp_path/ref["path"]).read_bytes()) == ref["sha256"]
    assert b"secret-token" not in (tmp_path/ref["path"]).read_bytes()
    assert store.artifact(b"synthetic Bearer secret-token") == ref
    with RunLock(tmp_path):
        with pytest.raises(RuntimeError):
            with RunLock(tmp_path):
                pass


def test_live_fails_closed_without_budget():
    with pytest.raises(ValueError, match="model"):
        validate_live({"config": {}})


def test_freeze_detects_tampering(tmp_path):
    (tmp_path/"configs").mkdir(); (tmp_path/"manifests").mkdir(); (tmp_path/"docs").mkdir()
    (tmp_path/"configs/experiment.yaml").write_text("repeats: 3\nseed: 1\n")
    (tmp_path/"manifests/tasks.json").write_text(json.dumps({"tasks": tasks(1)}))
    (tmp_path/"manifests/versions.json").write_text("{}")
    (tmp_path/"docs/protocol.md").write_text("SYNTHETIC")
    (tmp_path/"uv.lock").write_text("SYNTHETIC")
    result = freeze(tmp_path, tmp_path/"freeze.json")
    assert verify_freeze(tmp_path, result) == result
    with pytest.raises(FileExistsError):
        freeze(tmp_path, tmp_path/"freeze.json")
    (tmp_path/"docs/protocol.md").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_freeze(tmp_path, result)
