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


# Event streams are append-only hash chains (Spec 003 FR-7.1, reusing the
# engine ledger pattern): every record appended through Store.append carries
# prev_hash/chain_hash, so editing or deleting a chained record is detectable
# at read time. Records written before chaining existed are a legacy prefix:
# they are returned as-is but reported as unverified by verify_stream().
GENESIS_HASH = "0" * 64
CHAIN_FIELDS = ("prev_hash", "chain_hash")


def _chain_hash(record):
    return sha(canonical({k: v for k, v in record.items() if k != "chain_hash"}))


def _verify_chain(stream, records):
    """Return an integrity summary; raise ValueError on a broken chain."""
    chained = legacy = 0
    previous = GENESIS_HASH
    for record in records:
        if all(field in record for field in CHAIN_FIELDS):
            if record["prev_hash"] != previous or record["chain_hash"] != _chain_hash(record):
                raise ValueError(f"event stream {stream!r} hash chain is broken")
            previous = record["chain_hash"]
            chained += 1
        elif chained:
            raise ValueError(f"event stream {stream!r} hash chain is broken")
        else:
            legacy += 1
    return {"records": len(records), "chained": chained, "legacy_records": legacy,
            "chain_verified": chained > 0}


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

    def _records(self, stream):
        path = self.root / f"{stream}.jsonl"
        if not path.exists():
            return []
        # A torn final write fails closed rather than silently losing a charge.
        return [json.loads(line) for line in path.read_text().splitlines()]

    def _last_chain_hash(self, stream):
        records = self._records(stream)
        for record in reversed(records):
            if "chain_hash" in record:
                return record["chain_hash"]
        return GENESIS_HASH

    def append(self, stream, event):
        if not re.fullmatch(r"[a-z_]+", stream):
            raise ValueError("invalid stream")
        record = {**event, "prev_hash": self._last_chain_hash(stream)}
        record["chain_hash"] = _chain_hash(record)
        with (self.root / f"{stream}.jsonl").open("ab") as f:
            f.write(canonical(record) + b"\n")
            f.flush()
            os.fsync(f.fileno())

    def verify_stream(self, stream):
        """Integrity summary for one event stream (FR-7.1).

        Raises ValueError if a chained record was edited, removed, or
        followed by an unchained record. Legacy (pre-chaining) records are
        counted, never silently treated as verified.
        """
        return _verify_chain(stream, self._records(stream))

    def events(self, stream):
        records = self._records(stream)
        _verify_chain(stream, records)
        return [{k: v for k, v in record.items() if k not in CHAIN_FIELDS}
                for record in records]


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
