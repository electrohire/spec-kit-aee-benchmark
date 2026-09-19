"""Record reproducible offline command evidence, including explicit extension execution."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from benchmark_runner.store import Store, read_json, sha, utc, write_json
from benchmark_runner.workflow import assess

root = Path(__file__).resolve().parents[1]
run_id = utc().replace(":", "").replace("+", "-")
store = Store(root/"reports"/"offline"/run_id)
command = [sys.executable, "-m", "pytest", "-q"]
start, tick = utc(), time.monotonic()
result = subprocess.run(command, cwd=root, capture_output=True,
                        env={**os.environ, "PYTHONUTF8": "1"}, timeout=180)
output = result.stdout+result.stderr
evidence = dict(command=["python", "-m", "pytest", "-q"], started_at=start, ended_at=utc(),
                duration_seconds=time.monotonic()-tick, exit_code=result.returncode,
                output=store.artifact(output), scope="offline tests; synthetic model responses, real deterministic extensions")
write_json(store.root/"tests.json", evidence, exclusive=True)
if result.returncode:
    print(output.decode(errors="replace"))
    raise SystemExit(result.returncode)
claims = read_json(root/"specs/001-benchmark/claims.json")
outcomes = {}
for phase in ("specify", "plan", "tasks", "implement"):
    composed = assess(root, claims, phase, store)
    outcomes[phase] = composed["outcome"]
    write_json(store.root/f"composed-{phase}.json", composed, exclusive=True)
write_json(root/"reports/latest-offline.json", dict(run=store.root.relative_to(root).as_posix(),
           tests=evidence, assessments=outcomes, python=sys.version, scored_attempts=0))
print(json.dumps({"evidence": str(store.root), "tests_exit": 0, "assessments": outcomes}))
