"""Offline verification for the Claim B condensation experiment.

Covers (all offline, no model calls):
- summarizer: determinism, budget compliance, constraint-id coverage, and
  fail-closed behavior for all 10 tasks at all 3 levels;
- task schema: task.yaml constraint ids match spec.md ids; every task has
  >= 2 subtle and >= 1 negative kinds;
- references pass hidden + public tests; traps pass public and fail hidden;
- the alignment gate passes on all 10 tasks;
- the mock campaign pipeline runs end to end: phase 1 -> condense ->
  6 cells -> offline grading produces the expected metric shapes
  (reference solver: full retention, zero hallucinations;
   trap solver: retention < 100% on trapped tasks).
"""
import json
import os
import re
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_ROOT = os.path.join(REPO, "benchmarks", "condensation")
sys.path.insert(0, os.path.join(REPO, "scripts"))
from condense import parse_spec, summarize_phase1  # noqa: E402

TASKS = sorted(d for d in os.listdir(TASK_ROOT)
               if os.path.isdir(os.path.join(TASK_ROOT, d)))
LEVELS = ["intact", "light", "aggressive"]


def task_dir(name):
    return os.path.join(TASK_ROOT, name)


def read(name, fname):
    with open(os.path.join(task_dir(name), fname)) as f:
        return f.read()


def yaml_field(name, field):
    for line in read(name, "task.yaml").splitlines():
        if line.strip().startswith(field + ":"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{name}: task.yaml missing {field}")


def yaml_kinds(name):
    kinds = {}
    in_c = False
    for line in read(name, "task.yaml").splitlines():
        if line.startswith("constraints:"):
            in_c = True
            continue
        if in_c:
            m = re.match(r"\s+(C\d+):\s*(\S+)", line)
            if m:
                kinds[m.group(1)] = m.group(2)
            elif line.strip() and not line.startswith(" "):
                break
    return kinds


def spec_ids(name):
    return re.findall(r"^## (C\d+):", read(name, "spec.md"), re.M)


TRANSCRIPT = [("user", "Read the full specification and write planning notes."),
              ("assistant", "Notes: implement per spec; watch subtle constraints."),
              ("assistant", "Additional note: run public tests after.")]


# --- summarizer ---

@pytest.mark.parametrize("task", TASKS)
def test_summarizer_deterministic(task):
    spec = read(task, "spec.md")
    for level in LEVELS:
        a = summarize_phase1(TRANSCRIPT, spec, level)
        b = summarize_phase1(TRANSCRIPT, spec, level)
        assert a == b


@pytest.mark.parametrize("task", TASKS)
def test_summarizer_budgets(task):
    spec = read(task, "spec.md")
    spec_words = len(spec.split())
    light = summarize_phase1(TRANSCRIPT, spec, "light")
    aggressive = summarize_phase1(TRANSCRIPT, spec, "aggressive")
    assert len(light.split()) <= 0.5 * spec_words
    assert len(aggressive.split()) <= 0.2 * spec_words


@pytest.mark.parametrize("task", TASKS)
def test_summarizer_id_coverage(task):
    spec = read(task, "spec.md")
    ids = spec_ids(task)
    assert ids, f"{task}: no constraints parsed"
    for level in ("light", "aggressive"):
        summary = summarize_phase1(TRANSCRIPT, spec, level)
        for cid in ids:
            assert cid in summary, f"{task}/{level}: {cid} missing"


@pytest.mark.parametrize("task", TASKS)
def test_summarizer_intact_verbatim(task):
    spec = read(task, "spec.md")
    out = summarize_phase1(TRANSCRIPT, spec, "intact")
    assert out == "\n".join(f"[{r}] {c}" for r, c in TRANSCRIPT)


def test_summarizer_fail_closed_on_bloated_spec():
    # A spec whose first sentences are too long must raise, not be
    # accommodated.
    long_sentence = "This requirement statement goes on and on " * 40 + "."
    spec = ("# T\n\nPreamble paragraph here.\n\n## C01: title\n" + long_sentence
            + "\n")
    with pytest.raises(ValueError):
        summarize_phase1(TRANSCRIPT, spec, "light")


def test_summarizer_unknown_level():
    with pytest.raises(ValueError):
        summarize_phase1(TRANSCRIPT, read(TASKS[0], "spec.md"), "vapor")


# --- task schema ---

@pytest.mark.parametrize("task", TASKS)
def test_task_ids_match(task):
    assert spec_ids(task) == sorted(spec_ids(task)), f"{task}: ids not ordered"
    assert set(yaml_kinds(task)) == set(spec_ids(task)), \
        f"{task}: task.yaml ids != spec.md ids"


@pytest.mark.parametrize("task", TASKS)
def test_task_kind_coverage(task):
    kinds = yaml_kinds(task)
    assert sum(1 for k in kinds.values() if k == "subtle") >= 2, \
        f"{task}: needs >= 2 subtle constraints"
    assert sum(1 for k in kinds.values() if k == "negative") >= 1, \
        f"{task}: needs >= 1 negative constraint"


@pytest.mark.parametrize("task", TASKS)
def test_phase2_template_has_context_block(task):
    assert "{context_block}" in read(task, "phase2.md")


# --- reference / trap behavior (via the alignment gate's own checks) ---

def _run_gate(task):
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts",
                                      "check_condensation_alignment.py"),
         "--task", task],
        capture_output=True, text=True, timeout=300)
    return proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("task", TASKS)
def test_alignment_gate_passes(task):
    ok, out = _run_gate(task)
    assert ok, f"{task}: alignment gate failed\n{out[-2000:]}"


# --- end-to-end mock campaign ---

def _mock_campaign(solver_mode, tmpdir):
    from run_condensation import MockSolver, run_campaign
    from grade_condensation import grade_run
    run_dir = os.path.join(str(tmpdir), f"run-{solver_mode}")
    run_campaign(MockSolver(solver_mode), run_dir)
    return grade_run(run_dir), run_dir


def test_mock_campaign_reference_full_retention(tmp_path):
    grades, run_dir = _mock_campaign("reference", tmp_path)
    assert len(grades["cells"]) == 10 * 6
    for cell in grades["cells"]:
        assert cell["tests"]["passed"] == cell["tests"]["total"], cell
        assert cell["retention_overall"]["retained"] == \
            cell["retention_overall"]["total"], cell
        assert cell["hallucinations"] == {"invented_requirements": 0,
                                         "phantom_fixes": 0}, cell
    # treatment isolation: summary arm never receives spec/plan files
    for task in TASKS:
        for level in LEVELS:
            files = json.load(open(os.path.join(
                run_dir, "cells", task, f"{level}_summary", "files.json")))
            assert files == ["/work/tests_public.py"], (task, level)
            files = json.load(open(os.path.join(
                run_dir, "cells", task, f"{level}_artifacts", "files.json")))
            assert sorted(files) == ["/task/plan.md", "/task/spec.md",
                                     "/work/tests_public.py"], (task, level)


def test_mock_campaign_trap_degrades(tmp_path):
    grades, _ = _mock_campaign("trap", tmp_path)
    degraded = [c for c in grades["cells"]
                if c["retention_overall"]["retained"]
                < c["retention_overall"]["total"]]
    assert degraded, "trap solver should lose retention somewhere"
    # every task's trap fails at least one hidden test (gate invariant)
    by_task = {}
    for c in degraded:
        by_task.setdefault(c["task"], []).append(c["cell"])
    assert len(by_task) == 10, f"traps must bite on all 10 tasks: {by_task}"
