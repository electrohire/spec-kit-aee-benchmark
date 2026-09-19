"""Separate upstream grading. Never called within the solver context."""
import json
import subprocess
import uuid
from pathlib import Path

from .store import canonical, sha, utc, write_json


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
        prediction.write_bytes(canonical(dict(instance_id=attempt["task_id"],
            model_name_or_path="benchmark-agent", model_patch=patch.decode()))+b"\n")
        command = ["swebench", "eval", "verified", "-p", str(prediction.resolve()),
                   "--run-id", run_id, "--task-repo", str(Path(task_repo).resolve()),
                   "-i", attempt["task_id"], "-j", "1"]
        result = subprocess.run(command, cwd=working, capture_output=True, timeout=7200)
        log = store.artifact(result.stdout+result.stderr)
        # v5 per-instance report retains instance ID as its top-level key.
        reports = list(working.rglob("report.json"))
        resolved, refs = None, []
        for path in reports:
            data = json.loads(path.read_text())
            refs.append(store.artifact(path.read_bytes()))
            value = data.get(attempt["task_id"], {}).get("resolved")
            if type(value) is bool:
                resolved = value
        store.append("grades", dict(attempt_id=attempt["attempt_id"], task_id=attempt["task_id"],
                     run_id=run_id, resolved=resolved, reason=None if resolved is not None else "no independent resolved field",
                     timestamp=utc(), grader_exit_code=result.returncode, log=log, reports=refs))
