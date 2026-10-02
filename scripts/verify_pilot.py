"""Fidelity verification for Claim A local-backend runs.

Persisted, governed version of the 2026-09-24 /tmp/verify_pilot.py pilot
gate, carrying the silent-fidelity hardening that caught the context-window
failure: a recorded phase whose every model call failed is a harness/backend
failure, not a workflow execution, and must fail the gate.

Usage:
    python3 scripts/verify_pilot.py RUN_DIR [--manifest MANIFEST]

Without --manifest: legacy single-task pilot mode. Requires exactly the two
final attempts (diagnose + repair_workflow), both completed; the workflow
attempt must have all six workflow phases recorded with real model
responses, plus AEE assessments attributed to it. Prints PILOT_FIDELITY_OK.

With --manifest: campaign mode. Every attempt in the manifest schedule must
be present with status "completed"; every repair_workflow attempt must have
all six workflow phases with real model responses and at least one AEE
assessment attributed to it. Prints CAMPAIGN_FIDELITY_OK.

Exit codes: 0 fidelity OK; 1 fidelity FAIL; 2 incomplete (still running or
missing records -- rerun later).
"""
import argparse
import json
import sys
from pathlib import Path

WORKFLOW_PHASES = (
    "workflow_constitution",
    "workflow_specify",
    "workflow_plan",
    "workflow_tasks",
    "workflow_implement",
    "workflow_converge",
)


def _read_jsonl(path):
    recs = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def _check_workflow_attempt(root, phases_by_attempt, assess_by_attempt, attempt_id):
    """Fidelity gates for one repair_workflow attempt.

    Returns an error string on failure, None on success.
    """
    phase_recs = phases_by_attempt.get(attempt_id, {})
    missing = [p for p in WORKFLOW_PHASES if p not in phase_recs]
    if missing:
        return (f"fidelity FAIL: workflow attempt {attempt_id} missing phases "
                f"{missing}; incomplete run")
    for phase in WORKFLOW_PHASES:
        rec = phase_recs[phase]
        if not rec.get("completed"):
            return (f"fidelity FAIL: phase {phase} of {attempt_id} not completed "
                    f"(calls={rec.get('calls')}); backend/timeout failure, "
                    f"not a workflow run")
        art = rec.get("artifact") or {}
        apath = root / art.get("path", "")
        if not apath.exists():
            return f"fidelity FAIL: phase {phase} of {attempt_id} artifact missing at {apath}"
        detail = json.loads(apath.read_text())
        errors = detail.get("errors") or []
        # Silent-fidelity hole (2026-09-24): a phase can be recorded while
        # every model call in it failed with ProviderError, so the model
        # never responded once. That is a harness/backend failure, not a
        # workflow execution.
        if detail.get("done") is None and errors and all(
                str(e).startswith("ProviderError") for e in errors):
            return (f"fidelity FAIL: phase {phase} of {attempt_id} got zero model "
                    f"responses ({len(errors)}x ProviderError); backend/context "
                    f"failure, not a workflow run")
        if detail.get("done") is None:
            return (f"fidelity FAIL: phase {phase} of {attempt_id} has no done "
                    f"record; cannot confirm a model response")
    if not assess_by_attempt.get(attempt_id):
        return (f"fidelity FAIL: no AEE assessments recorded for workflow "
                f"attempt {attempt_id}")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Claim A local-run fidelity verification")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--manifest", type=Path, default=None,
                    help="freeze manifest for campaign mode")
    args = ap.parse_args(argv)
    root = args.run_dir

    attempts = _read_jsonl(root / "attempts.jsonl")
    if not attempts:
        print("run has no attempts.jsonl yet")
        return 2
    final = {}
    for a in attempts:
        final[a["attempt_id"]] = a

    if args.manifest is None:
        expected = None
        if len(final) != 2:
            print(f"pilot has {len(final)}/2 attempts recorded; still running or incomplete")
            return 2
    else:
        manifest = json.loads(args.manifest.read_text())
        expected = [e["attempt_id"] for e in manifest["schedule"]]
        missing = [aid for aid in expected if aid not in final]
        if missing:
            print(f"campaign has {len(final)}/{len(expected)} attempts recorded; "
                  f"missing {len(missing)} (e.g. {missing[0]}); still running or incomplete")
            return 2

    bad = {aid: a.get("status") for aid, a in final.items()
           if (expected is None or aid in expected) and a.get("status") != "completed"}
    if bad:
        print(f"attempts not completed: {bad}")
        return 1

    phases_by_attempt = {}
    for rec in _read_jsonl(root / "phases.jsonl"):
        phases_by_attempt.setdefault(rec.get("attempt_id"), {})[rec.get("phase")] = rec
    assess_by_attempt = {}
    for rec in _read_jsonl(root / "assessments.jsonl"):
        assess_by_attempt.setdefault(rec.get("attempt_id"), []).append(rec)

    wf_ids = [aid for aid, a in final.items()
              if a.get("arm") == "repair_workflow"
              and (expected is None or aid in expected)]
    if not wf_ids:
        print("fidelity FAIL: no repair_workflow attempt recorded")
        return 1
    for wid in sorted(wf_ids):
        err = _check_workflow_attempt(root, phases_by_attempt,
                                      assess_by_attempt, wid)
        if err:
            print(err)
            return 1
    if args.manifest is None:
        print("pilot OK: 2/2 attempts completed on the local backend")
        print("PILOT_FIDELITY_OK")
    else:
        print(f"campaign OK: {len(wf_ids)} workflow attempts, all six phases with "
              f"real model responses and AEE assessments, on the local backend")
        print("CAMPAIGN_FIDELITY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
