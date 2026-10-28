"""Records audit (Benchmarking Improvement Program R-5,
2026-10-25): campaign records are append-only, single-
authority, and hash-verified in transit — as machinery, not
as habits.

The known incident this catches: during the probe test, the
empty-control eval summary under a shared run id was
overwritten in place by a later leg's fresh 2-instance eval,
leaving a summary that covered 2 of the 6 control instances
the leg's own controls record lists, with no superseding
record. The audit detects that shape mechanically: a control
summary whose instance coverage falls short of the controls
record for the same run is an incident, reported as detected
— never silently repaired (corrections are append-only and
supersede by reference).
"""
import hashlib
import json
from pathlib import Path


def _summary_ids(summary, variant):
    """The instance ids a control summary covers for one
    variant of the official-eval summary format."""
    if variant == "gold":
        ids = (summary.get("resolved_ids")
               or summary.get("completed_ids") or [])
    else:
        ids = summary.get("empty_patch_ids") or []
    return set(ids)


def audit_controls(controls_record, summaries):
    """controls_record: the leg's controls record
    ({"controls": [{"variant", "instance_id",
    "control_pass", ...}]}). summaries: {variant:
    summary_dict} for the same run id. Returns detected
    incidents: any variant whose summary coverage differs
    from the controls record's instance set for that
    variant, and any control row that did not pass."""
    rows = controls_record.get("controls") or []
    expected = {}
    failed = []
    for row in rows:
        expected.setdefault(row["variant"], set()).add(
            row["instance_id"])
        if not row.get("control_pass"):
            failed.append({"variant": row["variant"],
                           "instance_id": row["instance_id"],
                           "kind": "control_not_passing"})
    incidents = list(failed)
    for variant, summary in summaries.items():
        want = expected.get(variant, set())
        got = _summary_ids(summary, variant)
        if got != want:
            incidents.append({
                "variant": variant,
                "kind": "summary_coverage_mismatch",
                "expected_ids": sorted(want),
                "summary_ids": sorted(got),
                "missing_from_summary": sorted(want - got),
                "extra_in_summary": sorted(got - want)})
    return {"incidents": incidents, "clean": not incidents,
            "expected": {k: sorted(v) for k, v in expected.items()}}


def verify_transfer(manifest, root):
    """manifest: {relative_path: sha256_hex} as recorded at
    the sending end. Recomputes every file under root and
    reports both-end agreement per file — a transfer is
    verified only when every hash matches at the receiving
    end too."""
    root = Path(root)
    results = {}
    for rel, want in manifest.items():
        path = root / rel
        if not path.is_file():
            results[rel] = False
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        results[rel] = digest == want
    return {"files": results,
            "verified": all(results.values()) and bool(results)}


def recompute_attempt_tokens(store_dir):
    """A quoted figure traces to its store, never to a status
    channel: recompute one attempt store's charged tokens
    from its calls stream (reported usage only; a call with
    unknown usage makes the figure underivable here and is
    named, not estimated)."""
    total, unknown = 0, 0
    for line in (Path(store_dir) / "calls.jsonl") \
            .read_text().splitlines():
        if not line.strip():
            continue
        call = json.loads(line)
        i, o = call.get("input_tokens"), call.get("output_tokens")
        if i is None or o is None:
            unknown += 1
        else:
            total += i + o
    return {"tokens": total, "unknown_usage_calls": unknown}
