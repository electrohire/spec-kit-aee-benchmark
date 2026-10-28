"""One continuous program ledger (Benchmarking Improvement
Program H-1 and H-4, 2026-10-25).

The program ledger is a single append-only artifact — a
hash-chained JSONL file (benchmarks/program-ledger.jsonl) —
not a figure re-derived per campaign. Each entry records a
campaign's opening total, its spend, and its close; a new
campaign is admitted only when its opening equals the
ledger's last close, and the admission check is this module,
not a habit. Corrections are new entries; no entry is ever
edited (the chain hash makes an edit visible).

Every campaign close also carries its per-outcome metrics
(H-4): cost per resolved outcome per arm or path — the
string "undefined" when there were no resolved outcomes,
never a silent omission — so the program's yield is as
auditable as its spend.
"""
import hashlib
import json
import os
from pathlib import Path

GENESIS = "GENESIS"


def _hash(entry):
    body = {k: v for k, v in entry.items() if k != "hash"}
    canon = json.dumps(body, sort_keys=True,
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def read_entries(path):
    entries = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def verify_ledger(path):
    """Chain integrity + continuity: every entry's hash
    recomputes, every opening equals the previous close, and
    every close equals opening + spend."""
    entries = read_entries(path)
    prev_hash, prev_close = GENESIS, None
    problems = []
    for entry in entries:
        if entry.get("prev") != prev_hash:
            problems.append({"seq": entry.get("seq"),
                             "kind": "chain_break"})
        if _hash(entry) != entry.get("hash"):
            problems.append({"seq": entry.get("seq"),
                             "kind": "hash_mismatch"})
        if prev_close is not None \
                and entry.get("opening") != prev_close:
            problems.append({"seq": entry.get("seq"),
                             "kind": "continuity_break",
                             "opening": entry.get("opening"),
                             "previous_close": prev_close})
        if entry.get("close") != entry.get("opening", 0) \
                + entry.get("spend", 0):
            problems.append({"seq": entry.get("seq"),
                             "kind": "arithmetic_break"})
        prev_hash = entry.get("hash")
        prev_close = entry.get("close")
    return {"entries": len(entries), "problems": problems,
            "ok": not problems,
            "last_close": prev_close}


def admit_opening(path, opening):
    """The H-1 admission gate: a campaign whose registration
    names an opening total different from the ledger's last
    close is refused before any spend."""
    state = verify_ledger(path)
    if not state["ok"]:
        return {"admitted": False, "reason": "ledger_invalid",
                "problems": state["problems"]}
    if opening != state["last_close"]:
        return {"admitted": False,
                "reason": "opening_differs_from_last_close",
                "ledger_last_close": state["last_close"],
                "named_opening": opening}
    return {"admitted": True, "ledger_last_close": opening}


def _fsync_dir(directory):
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _append_line_verified(path, line, expected_hash):
    """Append one serialized entry line with proof of landing
    (transplanted from the staged verified-writes package,
    2026-10-28). Records the pre-append size, appends +
    fsyncs, then reads back the appended range: it must equal
    the line exactly, and the file's final line must carry
    ``expected_hash``. On any mismatch the file is truncated
    back to its pre-append size and ``RuntimeError`` is
    raised — the append is never blind-retried, so an entry
    can never land twice."""
    size_before = path.stat().st_size if path.exists() else 0
    try:
        with path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(path.parent)
        with path.open("rb") as handle:
            handle.seek(size_before)
            landed = handle.read()
        if landed != line:
            raise RuntimeError(
                f"ledger append read-back mismatch at {path}: "
                f"expected {len(line)} bytes (sha256 "
                f"{hashlib.sha256(line).hexdigest()}), read back "
                f"{len(landed)} bytes"
            )
        last = json.loads(landed.decode("utf-8"))
        if last.get("hash") != expected_hash:
            raise RuntimeError(
                f"ledger append hash mismatch at {path}: final "
                f"line carries {last.get('hash')}, expected "
                f"{expected_hash}"
            )
    except BaseException:
        try:
            with path.open("r+b") as handle:
                handle.truncate(size_before)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass
        raise


def append_close(path, campaign, opening, spend, metrics,
                 source):
    """Append one campaign close. Refuses (returns the
    refusal, writes nothing) when the ledger does not verify
    or the opening is not the last close — append-only means
    the refusal is the enforcement. The append itself is
    verified — fsync plus a read-back hash check (fleet
    verified-writes standard, 2026-10-28) — and a write that
    cannot be proven landed raises RuntimeError with the
    file rolled back to its pre-append size, rather than
    returning success."""
    state = verify_ledger(path)
    if not state["ok"]:
        return {"appended": False, "reason": "ledger_invalid",
                "problems": state["problems"]}
    if opening != state["last_close"]:
        return {"appended": False,
                "reason": "opening_differs_from_last_close",
                "ledger_last_close": state["last_close"]}
    entries = read_entries(path)
    entry = {"seq": len(entries) + 1, "kind": "campaign_close",
             "campaign": campaign, "opening": opening,
             "spend": spend, "close": opening + spend,
             "metrics": metrics, "source": source,
             "prev": entries[-1]["hash"] if entries else GENESIS}
    entry["hash"] = _hash(entry)
    line = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
    _append_line_verified(Path(path), line, entry["hash"])
    return {"appended": True, "entry": entry}


def metric_audit(path):
    """H-4: every campaign close carries its per-outcome
    metric entry. Founding entries (kind "founding") predate
    the discipline and are checked by the frozen test against
    the recorded figures instead; a campaign_close without a
    metrics block, or with a cost_per_resolved that is
    neither a number nor the explicit string "undefined",
    is a finding."""
    findings = []
    for entry in read_entries(path):
        if entry.get("kind") != "campaign_close":
            continue
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            findings.append({"seq": entry.get("seq"),
                             "kind": "missing_metrics"})
            continue
        for key, value in metrics.items():
            if "cost_per_resolved" in key:
                ok = isinstance(value, (int, float)) \
                    or value == "undefined" \
                    or (isinstance(value, dict) and all(
                        isinstance(v, (int, float))
                        or v == "undefined"
                        for v in value.values()))
                if not ok:
                    findings.append({"seq": entry.get("seq"),
                                     "kind": "bad_metric_value",
                                     "field": key})
    return {"findings": findings, "ok": not findings}
