"""Verified-write retrofit tests (fleet standard, 2026-10-28).

Fault checks simulate the VM's write pathologies in-process: a local
write attempt that never lands, and an append that lands only half
its record. The store's writers must either land the exact bytes
(via the fresh-subprocess fallback) or fail loudly with the file
rolled back. Byte-compatibility is checked against the legacy
writers reproduced inline: the retrofit changes durability, never
the bytes.
"""
import hashlib
import json
from pathlib import Path

import pytest

from benchmark_runner import verified_write
from benchmark_runner.store import Store, sha, write_json
from benchmark_runner.upstream_agent_adapter import write_exclusive
from benchmark_runner.verified_write import (
    SafeWriteError,
    write_bytes_verified,
)


def _legacy_write_json(path, value):
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def test_write_json_bytes_identical_to_legacy(tmp_path):
    value = {"z": [1, 2.5, "héllo"], "a": {"nested": True}, "n": None}
    legacy = tmp_path / "legacy.json"
    new = tmp_path / "new.json"
    _legacy_write_json(legacy, value)
    write_json(new, value)
    assert new.read_bytes() == legacy.read_bytes()


def test_write_json_exclusive_refuses_existing(tmp_path):
    target = tmp_path / "result.json"
    write_json(target, {"v": 1}, exclusive=True)
    with pytest.raises(FileExistsError):
        write_json(target, {"v": 2}, exclusive=True)
    assert json.loads(target.read_text()) == {"v": 1}


def test_write_recovers_via_child_when_local_attempts_fail(tmp_path, monkeypatch):
    src = Path(verified_write.__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(src))
    monkeypatch.setattr(verified_write, "try_write_once", lambda path, data: False)
    target = tmp_path / "record.json"
    result = write_bytes_verified(target, b'{"via": "child"}\n')
    assert result["via"].startswith("child-")
    assert target.read_bytes() == b'{"via": "child"}\n'


def test_store_append_chain_and_round_trip(tmp_path):
    store = Store(tmp_path / "store")
    store.append("attempts", {"attempt_id": "a1", "status": "completed"})
    store.append("attempts", {"attempt_id": "a2", "status": "completed"})
    events = store.events("attempts")
    assert [e["attempt_id"] for e in events] == ["a1", "a2"]
    assert store.verify_stream("attempts")["chain_verified"]


def test_store_append_rolls_back_a_torn_write(tmp_path, monkeypatch):
    store = Store(tmp_path / "store")
    store.append("attempts", {"attempt_id": "a1", "status": "completed"})
    stream_path = store.root / "attempts.jsonl"
    before = stream_path.read_bytes()

    def torn_append(path, data):
        with path.open("ab") as handle:
            handle.write(data[: len(data) // 2])
            handle.flush()

    monkeypatch.setattr(verified_write, "_append_once", torn_append)
    with pytest.raises(SafeWriteError):
        store.append("attempts", {"attempt_id": "a2", "status": "completed"})
    assert stream_path.read_bytes() == before
    assert [e["attempt_id"] for e in store.events("attempts")] == ["a1"]


def test_store_artifact_verified_and_empty(tmp_path):
    store = Store(tmp_path / "store")
    ref = store.artifact(b"grader log bytes")
    assert ref["sha256"] == sha(b"grader log bytes")
    assert (store.root / ref["path"]).read_bytes() == b"grader log bytes"
    empty = store.artifact(b"")
    assert empty["sha256"] == hashlib.sha256(b"").hexdigest()
    assert (store.root / empty["path"]).read_bytes() == b""


def test_write_exclusive_bytes_and_refusal(tmp_path):
    target = tmp_path / "receipt.json"
    write_exclusive(target, {"k": "héllo"})
    expected = (json.dumps({"k": "héllo"}, indent=2, ensure_ascii=False) + "\n").encode()
    assert target.read_bytes() == expected
    with pytest.raises(FileExistsError):
        write_exclusive(target, {"k": "again"})
