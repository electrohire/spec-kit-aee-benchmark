import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from .experiment import ARMS, freeze, select, verify_freeze
from .store import Store, read_json, write_json


def preflight(root):
    commands = {}
    for name in ("git", "gh", "uv", "docker", "codex", "swebench"):
        commands[name] = shutil.which(name) is not None
    try:
        result = subprocess.run(["docker", "info", "--format", "{{json .}}"], capture_output=True, timeout=15)
        docker = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        docker = None
    free = shutil.disk_usage(root).free
    # Check connector credential availability (informational for preflight;
    # validate_live() does the fail-closed check before paid runs).
    try:
        import sys
        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        import dynamic_credentials as dc
        dc.ensure_allowed_url("https://api.openai.com/v1/models", ["api.openai.com"])
        api_credential_present = True
    except Exception:
        api_credential_present = False
    return {"python": platform.python_version(), "platform": platform.system(), "commands": commands,
            "docker_ready": docker is not None, "docker_cpu": docker.get("NCPU") if docker else None,
            "docker_memory": docker.get("MemTotal") if docker else None,
            "free_bytes": free, "storage_check": free >= 120*1024**3,
            "api_credential_present": api_credential_present,
            "paid_calls_made": False}


def parser():
    p = argparse.ArgumentParser(description="ElectroHire reproducible workflow benchmark")
    p.add_argument("--root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    s = sub.add_parser("select")
    s.add_argument("input", type=Path); s.add_argument("output", type=Path)
    s.add_argument("--count", type=int, default=20); s.add_argument("--seed", type=int, default=20260917)
    s.add_argument("--exclude", action="append", default=["sympy__sympy-20590", "django__django-11099"])
    s = sub.add_parser("freeze"); s.add_argument("output", type=Path)
    for command in ("dry-run", "run"):
        s = sub.add_parser(command); s.add_argument("manifest", type=Path)
        if command == "run":
            s.add_argument("output", type=Path); s.add_argument("--arm", choices=ARMS)
            s.add_argument("--smoke", action="store_true")
    s = sub.add_parser("grade"); s.add_argument("store", type=Path)
    s.add_argument("--task-repo", type=Path, required=True); s.add_argument("--harness-repo", type=Path, required=True)
    s = sub.add_parser("aggregate"); s.add_argument("store", type=Path); s.add_argument("output", type=Path)
    s.add_argument("--synthetic", action="store_true")
    s = sub.add_parser("article-table"); s.add_argument("report", type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight(args.root)
        elif args.command == "select":
            data = read_json(args.input)
            result = select(data, args.count, args.seed, args.exclude)
            write_json(args.output, result, exclusive=True)
        elif args.command == "freeze":
            result = freeze(args.root, args.output)
        elif args.command in ("dry-run", "run"):
            manifest = verify_freeze(args.root, read_json(args.manifest))
            if args.command == "dry-run":
                result = {"freeze_id": manifest["freeze_id"], "paid_calls_made": False, "schedule": manifest["schedule"]}
            else:
                from .runner import run
                result = run(args.root, manifest, args.output, args.arm, args.smoke)
        elif args.command == "grade":
            from .grading import grade
            versions = read_json(args.root/"manifests/versions.json")
            grade(Store(args.store), args.task_repo, args.harness_repo, versions["swebench_commit"], versions["tasks_commit"])
            result = {"status": "grading_finished"}
        elif args.command == "aggregate":
            from .reporting import aggregate
            result = aggregate(Store(args.store), synthetic=args.synthetic)
            write_json(args.output, result, exclusive=True)
        elif args.command == "article-table":
            from .reporting import article_table
            print(article_table(read_json(args.report)))
            return 0
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"error: {e}")
        return 2
