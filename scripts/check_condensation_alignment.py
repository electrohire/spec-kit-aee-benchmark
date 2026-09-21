#!/usr/bin/env python3
"""Grader-spec alignment gate for condensation tasks (offline, no model calls).

This is the SAME gate that must pass before any paid Claim B campaign; there
is no separate "test version". Per task it checks:

1. spec.md parses under the strict constraint format; task.yaml ids match.
2. reference.py passes ALL hidden tests and ALL public tests.
3. Every hidden test function has a PINS entry; every pin names a real
   constraint id; every constraint id has >= 1 pinning hidden test.
4. trap.py (the canonical attractive wrong implementation) PASSES all public
   tests and FAILS at least one hidden test -- proving the trap is genuinely
   available: public tests do not catch it, hidden tests do.

The human spec-literal review (every hidden test follows from the written
spec with no extra inference; public tests do not exercise subtle/negative/
phantom constraints; plan.md resolves every named ambiguity) is recorded in
each task's alignment.md and is NOT automated -- this script verifies the
automatable checks only.

Usage: python3 scripts/check_condensation_alignment.py [--task NAME]
Exit 0 iff every checked task passes the gate.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "benchmarks" / "condensation"

CONSTRAINT_RE = re.compile(r"^## (C\d+): (.+)$")


def parse_constraints(spec_path):
    """-> (preamble, [(id, title, detail), ...]). Raises on malformed specs."""
    text = spec_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    ids, titles, details, current = [], [], [], None
    preamble_lines = []
    seen_preamble_end = False
    for line in lines:
        m = CONSTRAINT_RE.match(line)
        if m:
            seen_preamble_end = True
            if current is not None:
                ids.append(current[0]); titles.append(current[1])
                details.append("\n".join(current[2]).strip())
            current = [m.group(1), m.group(2).strip(), []]
        elif current is not None:
            current[2].append(line)
        elif not seen_preamble_end:
            preamble_lines.append(line)
    if current is not None:
        ids.append(current[0]); titles.append(current[1])
        details.append("\n".join(current[2]).strip())
    if not ids:
        raise ValueError(f"{spec_path}: no constraints parsed")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{spec_path}: duplicate constraint ids")
    return "\n".join(preamble_lines).strip(), list(zip(ids, titles, details))


def load_task_yaml(task_dir):
    """Minimal YAML subset parser (no dependency): flat key: value plus a
    constraints block of `  C01: kind` lines and simple lists."""
    data, constraints, in_constraints, in_list, list_key = {}, {}, False, False, None
    for raw in (task_dir / "task.yaml").read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^[A-Za-z_]+:", line):
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key == "constraints":
                in_constraints, in_list = True, False
                continue
            in_constraints = False
            if val.startswith("["):
                data[key] = [v.strip() for v in val.strip("[]").split(",") if v.strip()]
                in_list, list_key = False, None
            elif val == "":
                in_list, list_key, data[key] = True, key, []
            else:
                data[key], in_list = val, False
        elif in_constraints and re.match(r"^\s+C\d+:", line):
            cid, _, kind = line.strip().partition(":")
            constraints[cid.strip()] = kind.strip()
        elif in_list and line.strip().startswith("- "):
            data[list_key].append(line.strip()[2:])
    data["constraints"] = constraints
    return data


def hidden_tests_and_pins(task_dir):
    """-> (test_names, PINS dict) via AST; never imports untrusted code here."""
    src = (task_dir / "tests_hidden.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = [n.name for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    pins = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PINS" for t in n.targets):
            pins = ast.literal_eval(n.value)
    if pins is None:
        raise ValueError(f"{task_dir}: tests_hidden.py has no PINS dict")
    return names, pins


def run_pytest(tmp, test_file):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test_file],
        cwd=tmp, capture_output=True, text=True, timeout=120)
    return proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-1000:]


def stage(tmp, task_dir, impl, module):
    """Copy impl (reference.py or trap.py) as <module>.py plus both test files."""
    shutil.copy(task_dir / impl, tmp / f"{module}.py")
    shutil.copy(task_dir / "tests_hidden.py", tmp / "test_hidden.py")
    shutil.copy(task_dir / "tests_public.py", tmp / "test_public.py")


def check_task(name):
    task_dir = TASKS / name
    errors = []
    meta = load_task_yaml(task_dir)
    module = meta["module"]
    preamble, constraints = parse_constraints(task_dir / "spec.md")
    spec_ids = [c[0] for c in constraints]
    if set(meta["constraints"]) != set(spec_ids):
        errors.append(f"task.yaml ids {sorted(meta['constraints'])} != spec.md ids {sorted(spec_ids)}")
    if not preamble:
        errors.append("empty preamble")
    kinds = set(meta["constraints"].values())
    if not any(k == "subtle" for k in kinds):
        errors.append("no subtle constraint (need >= 1 stated-once constraint)")
    if not any(k in ("negative", "phantom") for k in kinds):
        errors.append("no negative/phantom constraint (need >= 1 hallucination pin)")

    names, pins = hidden_tests_and_pins(task_dir)
    for t in names:
        if t not in pins:
            errors.append(f"hidden test {t} has no PINS entry")
    for t, ids in pins.items():
        if t not in names:
            errors.append(f"PINS entry {t} names no test function")
        for cid in ids:
            if cid not in spec_ids:
                errors.append(f"PINS {t} references unknown constraint {cid}")
    pinned = {cid for ids in pins.values() for cid in ids}
    for cid in spec_ids:
        if cid not in pinned:
            errors.append(f"constraint {cid} has no pinning hidden test")

    with tempfile.TemporaryDirectory(prefix="cond-align-") as tmp:
        tmp = Path(tmp)
        stage(tmp, task_dir, "reference.py", module)
        ok_h, out_h = run_pytest(tmp, "test_hidden.py")
        ok_p, out_p = run_pytest(tmp, "test_public.py")
        if not ok_h:
            errors.append("reference.py FAILS hidden tests:\n" + out_h)
        if not ok_p:
            errors.append("reference.py FAILS public tests:\n" + out_p)
        stage(tmp, task_dir, "trap.py", module)
        tok_p, _ = run_pytest(tmp, "test_public.py")
        tok_h, out_th = run_pytest(tmp, "test_hidden.py")
        if not tok_p:
            errors.append("trap.py fails public tests: trap is not genuinely available (public must not catch it)")
        if tok_h:
            errors.append("trap.py PASSES all hidden tests: trap is decoration, not a trap")

    return errors


def main():
    only = sys.argv[sys.argv.index("--task") + 1] if "--task" in sys.argv else None
    names = sorted(p.name for p in TASKS.iterdir() if p.is_dir()) if not only else [only]
    failed = 0
    for name in names:
        errors = check_task(name)
        if errors:
            failed += 1
            print(f"GATE FAIL {name}:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"GATE PASS {name}")
    print(f"\n{len(names) - failed}/{len(names)} tasks pass the alignment gate")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
