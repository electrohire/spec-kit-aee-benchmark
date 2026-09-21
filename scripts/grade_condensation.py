"""Offline grading for Claim B condensation runs.

For every cell snapshot in runs/<run-id>/cells/<task>/<level>_<arm>/, stages
the solution as <module>.py with the task's hidden tests and runs them
offline (no model calls). Computes:

- per-test pass/fail (append-only record)
- constraint retention: a constraint is retained iff ALL its pinning tests
  pass (pins from tests_hidden.py PINS); reported overall and per kind
- hallucination counts (v9 operational definition):
    invented_requirements: failed tests pinned to negative-kind constraints
    phantom_fixes:         failed tests pinned to phantom-kind constraints
  Counting rule: per failed TEST. A test pinned to two kinds counts once in
  each kind's tally; retention is per constraint and never double-counts.

Writes runs/<run-id>/grades.json. The analysis (paired differences,
bootstrap CI) follows the paid campaign; this records the raw outcomes.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_ROOT = os.path.join(REPO, "benchmarks", "condensation")

_RESULT_RE = re.compile(r"^(\S+)::(\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)")


def task_yaml_constraints(task_dir):
    kinds = {}
    in_constraints = False
    with open(os.path.join(task_dir, "task.yaml")) as f:
        for line in f:
            if line.startswith("constraints:"):
                in_constraints = True
                continue
            if in_constraints:
                m = re.match(r"\s+(C\d+):\s*(\S+)", line)
                if m:
                    kinds[m.group(1)] = m.group(2)
                elif line.strip() and not line.startswith(" "):
                    break
    return kinds


def pins_and_tests(task_dir):
    src = open(os.path.join(task_dir, "tests_hidden.py")).read()
    tree = ast.parse(src)
    names = [n.name for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("test_")]
    pins = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PINS" for t in n.targets):
            pins = ast.literal_eval(n.value)
    if pins is None:
        raise ValueError(f"{task_dir}: no PINS dict")
    return names, pins


def module_name(task_dir):
    with open(os.path.join(task_dir, "task.yaml")) as f:
        for line in f:
            if line.strip().startswith("module:"):
                return line.split(":", 1)[1].strip()
    raise ValueError(f"{task_dir}: no module in task.yaml")


def run_hidden_tests(task_dir, solution_path):
    module = module_name(task_dir)
    test_names, _ = pins_and_tests(task_dir)
    with tempfile.TemporaryDirectory(prefix="cond-grade-") as tmp:
        shutil.copy(solution_path, os.path.join(tmp, f"{module}.py"))
        shutil.copy(os.path.join(task_dir, "tests_hidden.py"),
                    os.path.join(tmp, "test_hidden.py"))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=no",
             "-p", "no:cacheprovider", "test_hidden.py"],
            cwd=tmp, capture_output=True, text=True, timeout=120)
        outcomes = {}
        for line in proc.stdout.splitlines():
            m = _RESULT_RE.match(line.strip())
            if m:
                outcomes[m.group(2)] = m.group(3)
        for t in test_names:
            outcomes.setdefault(t, "ERROR")
        return outcomes


def grade_run(run_dir):
    grades = {"cells": []}
    cells_root = os.path.join(run_dir, "cells")
    for task in sorted(os.listdir(cells_root)):
        task_dir = os.path.join(TASK_ROOT, task)
        kinds = task_yaml_constraints(task_dir)
        test_names, pins = pins_and_tests(task_dir)
        by_constraint = {}
        for t in test_names:
            for cid in pins.get(t, []):
                by_constraint.setdefault(cid, []).append(t)
        for cell in sorted(os.listdir(os.path.join(cells_root, task))):
            cell_dir = os.path.join(cells_root, task, cell)
            module = module_name(task_dir)
            solution = os.path.join(cell_dir, f"{module}.py")
            outcomes = run_hidden_tests(task_dir, solution)
            retention = {}
            for cid, tests in by_constraint.items():
                retention[cid] = all(outcomes[t] == "PASSED" for t in tests)
            failed = [t for t in test_names if outcomes[t] != "PASSED"]
            invented = sum(1 for t in failed
                           if any(kinds.get(c) == "negative"
                                   for c in pins.get(t, [])))
            phantom = sum(1 for t in failed
                          if any(kinds.get(c) == "phantom"
                                  for c in pins.get(t, [])))
            n_ret = sum(1 for v in retention.values() if v)
            by_kind = {}
            for kind in ("requirement", "subtle", "negative", "phantom"):
                cids = [c for c in by_constraint if kinds.get(c) == kind]
                if cids:
                    by_kind[kind] = {
                        "retained": sum(1 for c in cids if retention[c]),
                        "total": len(cids),
                    }
            grades["cells"].append({
                "task": task, "cell": cell,
                "tests": {"passed": sum(1 for t in test_names
                                        if outcomes[t] == "PASSED"),
                          "total": len(test_names)},
                "test_outcomes": outcomes,
                "constraint_retention": retention,
                "retention_overall": {"retained": n_ret,
                                      "total": len(retention)},
                "retention_by_kind": by_kind,
                "hallucinations": {"invented_requirements": invented,
                                   "phantom_fixes": phantom},
            })
    with open(os.path.join(run_dir, "grades.json"), "w") as f:
        json.dump(grades, f, indent=2)
    return grades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    args = ap.parse_args()
    grades = grade_run(args.run_dir)
    n = len(grades["cells"])
    print(f"graded {n} cells -> {os.path.join(args.run_dir, 'grades.json')}")


if __name__ == "__main__":
    main()
