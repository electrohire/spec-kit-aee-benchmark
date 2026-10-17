"""Claim B condensation runner: shared phase 1 -> condense -> phase 2 (6 cells).

For each task:
  phase 1: solver receives the full spec.md, writes planning notes.
           Transcript is frozen (no phase-1 output is graded).
  condense: the phase-1 transcript is condensed at intact/light/aggressive
           via scripts/condense.py (deterministic, offline).
  phase 2: six cells = 3 levels x {artifacts, summary} arms.
           artifacts arm: sandbox holds /task/spec.md + /task/plan.md and the
             prompt instructs re-reading them first.
           summary arm: no spec/plan files; the prompt carries only the
             condensed summary.
           Both arms get identical public tests and the identical target.
           Hidden tests never enter any solver sandbox (treatment isolation).

Solver interface: an object with
  run_phase1(task) -> transcript (list of (role, content))
  run_phase2(task, prompt, files) -> (module_source, transcript, calls)
where files maps sandbox path -> content. Real model solvers plug in here;
this build ships mock solvers (reference/trap) for offline validation only.
No paid calls are made by this build.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from condense import summarize_phase1

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_ROOT = os.path.join(REPO, "benchmarks", "condensation")
LEVELS = ["intact", "light", "aggressive"]
ARMS = ["artifacts", "summary"]

ARTIFACTS_PREAMBLE = (
    "Before starting, re-read /task/spec.md and /task/plan.md: they are the "
    "authoritative specification and plan for this task.\n\n"
)


class Task:
    def __init__(self, name):
        self.name = name
        self.dir = os.path.join(TASK_ROOT, name)
        with open(os.path.join(self.dir, "task.yaml")) as f:
            self.meta = _parse_simple_yaml(f.read())
        self.module = self.meta["module"].strip()
        self.spec = _read(self.dir, "spec.md")
        self.plan = _read(self.dir, "plan.md")
        self.phase2_template = _read(self.dir, "phase2.md")
        self.tests_public = _read(self.dir, "tests_public.py")
        self.reference = _read(self.dir, "reference.py")
        self.trap = _read(self.dir, "trap.py")


def _read(d, fname):
    with open(os.path.join(d, fname)) as f:
        return f.read()


def _parse_simple_yaml(text):
    out = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def list_tasks():
    return sorted(
        d for d in os.listdir(TASK_ROOT)
        if os.path.isdir(os.path.join(TASK_ROOT, d))
    )


class MockSolver:
    """Offline validation solver. mode=reference returns reference.py in
    phase 2; mode=trap returns trap.py. Phase 1 returns a canned transcript."""

    def __init__(self, mode):
        assert mode in ("reference", "trap")
        self.mode = mode

    def run_phase1(self, task):
        transcript = [
            ("user", f"Read the full specification for {task.name} and write "
                     f"brief planning notes."),
            ("assistant", f"Planning notes for {task.name}: implement "
                          f"{task.module} per spec.md; watch the subtle "
                          f"constraints; run the public tests."),
        ]
        return transcript, 1

    def run_phase2(self, task, prompt, files):
        source = task.reference if self.mode == "reference" else task.trap
        transcript = [("user", prompt[:200] + "..."),
                      ("assistant", f"Implemented {task.module}.py.")]
        return source, transcript, 1


def run_campaign(solver, run_dir, tasks=None):
    os.makedirs(run_dir, exist_ok=True)
    manifest = {"solver": getattr(solver, "mode", type(solver).__name__),
                "levels": LEVELS, "arms": ARMS, "cells": []}
    for name in (tasks or list_tasks()):
        task = Task(name)
        # Phase 1 (shared).
        transcript, p1_calls = solver.run_phase1(task)
        p1_dir = os.path.join(run_dir, "phase1", name)
        os.makedirs(p1_dir, exist_ok=True)
        with open(os.path.join(p1_dir, "transcript.json"), "w") as f:
            json.dump([{"role": r, "content": c} for r, c in transcript], f,
                      indent=2)
        summaries = {lvl: summarize_phase1(transcript, task.spec, lvl)
                     for lvl in LEVELS}
        # Phase 2 (six cells).
        for level in LEVELS:
            for arm in ARMS:
                prompt = task.phase2_template.replace("{context_block}",
                                                      summaries[level])
                files = {"/work/tests_public.py": task.tests_public}
                if arm == "artifacts":
                    prompt = ARTIFACTS_PREAMBLE + prompt
                    files["/task/spec.md"] = task.spec
                    files["/task/plan.md"] = task.plan
                source, p2_transcript, p2_calls = solver.run_phase2(
                    task, prompt, files)
                cell = f"{level}_{arm}"
                cell_dir = os.path.join(run_dir, "cells", name, cell)
                os.makedirs(cell_dir, exist_ok=True)
                with open(os.path.join(cell_dir, f"{task.module}.py"), "w") as f:
                    f.write(source)
                with open(os.path.join(cell_dir, "transcript.json"), "w") as f:
                    json.dump([{"role": r, "content": c}
                               for r, c in p2_transcript], f, indent=2)
                with open(os.path.join(cell_dir, "prompt.md"), "w") as f:
                    f.write(prompt)
                with open(os.path.join(cell_dir, "files.json"), "w") as f:
                    json.dump(sorted(files), f, indent=2)
                with open(os.path.join(cell_dir, "summary.md"), "w") as f:
                    f.write(summaries[level])
                manifest["cells"].append({
                    "task": name, "level": level, "arm": arm,
                    "phase1_calls": p1_calls, "phase2_calls": p2_calls,
                })
    with open(os.path.join(run_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return run_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver", choices=["reference", "trap"],
                    default="reference")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--task", action="append", default=None)
    args = ap.parse_args()
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or os.path.join(
        REPO, "runs", f"condensation-{args.solver}-{ts}")
    solver = MockSolver(args.solver)
    run_campaign(solver, run_dir, tasks=args.task)
    print(f"campaign complete: {run_dir}")


if __name__ == "__main__":
    main()
