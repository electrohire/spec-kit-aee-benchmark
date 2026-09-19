"""Durable immutable artifacts and serialized append-only event streams."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def redact(text):
    text = re.sub(r"(?i)(?:Bearer\s+)[A-Za-z0-9._-]+", "Bearer [REDACTED]", text)
    return re.sub(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,})", "[REDACTED]", text)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def artifact(self, data: bytes, *, sensitive=False):
        # Raw sensitive data is never stored by this public-evidence interface.
        if sensitive:
            raise ValueError("sensitive artifacts require a separate local vault")
        data = redact(data.decode("utf-8", errors="replace")).encode("utf-8")
        digest = sha(data)
        path = self.root / "objects" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        elif sha(path.read_bytes()) != digest:
            raise ValueError("artifact hash mismatch")
        return {"path": path.relative_to(self.root).as_posix(), "sha256": digest}

    def append(self, stream, event):
        if not re.fullmatch(r"[a-z_]+", stream):
            raise ValueError("invalid stream")
        with (self.root / f"{stream}.jsonl").open("ab") as f:
            f.write(canonical(event) + b"\n")
            f.flush()
            os.fsync(f.fileno())

    def events(self, stream):
        path = self.root / f"{stream}.jsonl"
        if not path.exists():
            return []
        # A torn final write fails closed rather than silently losing a charge.
        return [json.loads(line) for line in path.read_text().splitlines()]


class RunLock:
    """OS releases the advisory lock on crashes; never delete another process's lock."""
    def __init__(self, root):
        self.path = Path(root) / "run.lock"

    def __enter__(self):
        self.file = self.path.open("a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("another runner holds this experiment lock")
        return self

    def __exit__(self, *exc):
        self.file.close()
