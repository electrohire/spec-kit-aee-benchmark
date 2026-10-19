"""Use the pinned upstream loader; publish IDs/hashes rather than dataset contents."""
import argparse
import hashlib
import importlib.util
import subprocess
from pathlib import Path

from benchmark_runner.experiment import select
from benchmark_runner.store import read_json, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("harness", type=Path)
p.add_argument("task_repo", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--include-issues", action="store_true", help="local-only hydrated manifest")
args = p.parse_args()
versions = read_json("manifests/versions.json")
for path, key in ((args.harness, "swebench_commit"), (args.task_repo, "tasks_commit")):
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != versions[key]:
        raise ValueError("upstream revision mismatch")
spec = importlib.util.spec_from_file_location("upstream_task_repo", args.harness/"swebench/task/repo.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tasks = module.published_tasks(args.task_repo, ["SWE-bench/SWE-bench_Verified"])["SWE-bench/SWE-bench_Verified"]["test"]
manifest = select(tasks, 20, 20260917, ["sympy__sympy-20590", "django__django-11099"])
for task in manifest["tasks"]:
    task["problem_statement_sha256"] = hashlib.sha256(task["problem_statement"].encode()).hexdigest()
    if not args.include_issues:
        task["problem_statement"] = "REHYDRATE_FROM_PINNED_UPSTREAM_BEFORE_LIVE_FREEZE"
manifest["dataset"] = "SWE-bench/SWE-bench_Verified"
manifest["eligible_count"] = len(tasks)
write_json(args.output, manifest, exclusive=True)
print(f"Selected {len(manifest['tasks'])} of {len(tasks)} Verified tasks")
