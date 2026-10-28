"""Separate upstream grading. Never called within the solver context."""
import json
import subprocess
import uuid
from pathlib import Path

from .store import canonical, sha, utc, write_json
from .verified_write import write_bytes_verified


def grade(store, task_repo, harness_repo, expected_commit, expected_tasks_commit):
    for path, commit in ((harness_repo, expected_commit), (task_repo, expected_tasks_commit)):
        actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True)
        if actual != commit or dirty:
            raise ValueError("upstream checkout must be clean at its frozen revision")
    attempts = {r["attempt_id"]: r for r in store.events("attempts")}
    graded = {r["attempt_id"] for r in store.events("grades")}
    for attempt in attempts.values():
        if attempt["attempt_id"] in graded or not attempt.get("patch"):
            continue
        patch_path = store.root/attempt["patch"]["path"]
        patch = patch_path.read_bytes()
        if sha(patch) != attempt["patch"]["sha256"]:
            raise ValueError("patch artifact changed")
        run_id = "bench-"+uuid.uuid4().hex  # Cache cannot reuse a changed prediction.
        working = store.root/"grading"/run_id
        working.mkdir(parents=True)
        prediction = working/"predictions.jsonl"
        # Verified write (fleet standard, 2026-10-28): this file is
        # the grader's input; a torn write would mis-grade or void
        # the attempt, so it verifies by read-back or raises.
        write_bytes_verified(prediction, canonical(dict(instance_id=attempt["task_id"],
            model_name_or_path="benchmark-agent", model_patch=patch.decode()))+b"\n")
        command = ["swebench", "eval", "verified", "-p", str(prediction.resolve()),
                   "--run-id", run_id, "--task-repo", str(Path(task_repo).resolve()),
                   "-i", attempt["task_id"], "-j", "1"]
        result = subprocess.run(command, cwd=working, capture_output=True, timeout=7200)
        log = store.artifact(result.stdout+result.stderr)
        # v5 per-instance report retains instance ID as its top-level key.
        reports = list(working.rglob("report.json"))
        values, refs = set(), []
        for path in reports:
            data = json.loads(path.read_text())
            refs.append(store.artifact(path.read_bytes()))
            value = data.get(attempt["task_id"], {}).get("resolved")
            if type(value) is bool:
                values.add(value)
        resolved, reason = _bind_resolved(values, attempt["task_id"], result.returncode)
        store.append("grades", dict(attempt_id=attempt["attempt_id"], task_id=attempt["task_id"],
                     run_id=run_id, resolved=resolved, reason=reason,
                     timestamp=utc(), grader_exit_code=result.returncode, log=log, reports=refs))


def _bind_resolved(values, task_id, grader_exit_code):
    """Bind `resolved` to one identified grader run (FR-7.6).

    Conflicting reports for the same instance are an error, never
    last-wins; a non-zero grader exit code voids any report value, so a
    failed grader run leaves the outcome unknown instead of minting a
    resolution from a stale or partial report.
    """
    if len(values) > 1:
        raise ValueError(f"conflicting grader reports for instance {task_id}")
    if grader_exit_code != 0:
        return None, f"grader exited {grader_exit_code}; report not bound to a successful run"
    if not values:
        return None, "no independent resolved field"
    return values.pop(), None
