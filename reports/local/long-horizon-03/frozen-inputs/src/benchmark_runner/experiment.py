"""Deterministic selection, immutable configuration and interleaved schedules."""
import random
import re
from pathlib import Path

import yaml

from .store import canonical, read_json, sha, write_json

ARMS = ("baseline", "spec_kit", "spec_kit_aee")
SAFE_TASK_FIELDS = {"instance_id", "repo", "base_commit", "problem_statement", "image", "language"}


def source_hash(path):
    """Frozen inputs are text; normalize Git's platform line endings to LF."""
    return sha(Path(path).read_bytes().replace(b"\r\n", b"\n"))


def safe_task(task):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", task["instance_id"]):
        raise ValueError("unsafe task ID")
    for key in ("repo", "base_commit", "problem_statement"):
        if not isinstance(task.get(key), str) or not task[key]:
            raise ValueError(f"task missing {key}")
    return {k: task[k] for k in SAFE_TASK_FIELDS if k in task}


def select(tasks, count=20, seed=20260917, exclude=()):
    ids = [t["instance_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task IDs")
    rng = random.Random(seed)
    buckets, excluded = {}, []
    for task in sorted(tasks, key=lambda t: t["instance_id"]):
        if task["instance_id"] in exclude or task.get("language", "python").lower() != "python":
            excluded.append(task["instance_id"])
        else:
            buckets.setdefault(task["repo"], []).append(safe_task(task))
    for bucket in buckets.values():
        rng.shuffle(bucket)
    repos = sorted(buckets)
    rng.shuffle(repos)
    chosen = []
    while len(chosen) < count and any(buckets.values()):
        for repo in repos:
            if buckets[repo] and len(chosen) < count:
                chosen.append(buckets[repo].pop())
    if len(chosen) != count:
        raise ValueError("insufficient eligible tasks")
    selected_ids = {t["instance_id"] for t in chosen}
    return dict(schema_version=1, seed=seed, selection="seeded repository round-robin",
                exclusions=sorted(excluded), unselected=sorted(set(ids)-selected_ids-set(excluded)),
                tasks=chosen)


def schedule(tasks, repeats, seed):
    rng = random.Random(seed)
    result = [dict(task_id=t["instance_id"], arm=arm, repeat=repeat,
                   attempt_id=f'{t["instance_id"]}--{arm}--r{repeat}')
              for t in tasks for repeat in range(1, repeats+1) for arm in ARMS]
    rng.shuffle(result)
    return result


def frozen_paths(root):
    paths = ["configs/experiment.yaml", "manifests/tasks.json", "manifests/versions.json",
             "docs/protocol.md", "uv.lock"]
    for directory in ("configs/arms", "prompts", "src/benchmark_runner", ".specify/scripts/python", ".specify/templates", ".specify/extensions/aee", ".specify/extensions/evaluator"):
        paths += [p.relative_to(root).as_posix() for p in (root/directory).rglob("*")
                  if p.is_file() and not any(x in p.parts for x in ("__pycache__", "assessments", "results", "reports", "ledger", ".pytest_cache"))]
    return sorted(paths)


def freeze(root, output):
    root = Path(root).resolve()
    files = {name: source_hash(root/name) for name in frozen_paths(root)}
    config = yaml.safe_load((root/"configs/experiment.yaml").read_text())
    tasks = read_json(root/"manifests/tasks.json")
    result = dict(schema_version=1, files=files, config=config, tasks=tasks,
                  schedule=schedule(tasks["tasks"], config["repeats"], config["seed"]))
    result["freeze_id"] = sha(canonical(result))
    write_json(output, result, exclusive=True)
    return result


def verify_freeze(root, manifest):
    digest = manifest["freeze_id"]
    if sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"})) != digest:
        raise ValueError("freeze manifest was modified")
    for name, expected in manifest["files"].items():
        path = (Path(root)/name).resolve()
        if not path.is_relative_to(Path(root).resolve()) or source_hash(path) != expected:
            raise ValueError(f"frozen file changed: {name}")
    return manifest
