"""Regression tests for the matched-repair cloud port (offline only)."""
import json
import subprocess

import pytest

from benchmark_runner.matched_repair import (
    MATCHED_ARMS,
    PYTEST_CMD,
    VARIANTS,
    _terminal_done,
    git_clean,
    pair_of,
    run_public_tests,
    smoke_config,
    tests_for as mr_tests_for,
    variant_source,
    verify_reservation_bounds,
)


def test_pair_of_parses_smoke_pair():
    assert pair_of("mr-tinydb-bool_id-20260918") == ("tinydb", "bool_id", 20260918)


def test_pair_of_rejects_unknown():
    with pytest.raises(ValueError):
        pair_of("mr-tinydb-nope-20260918")
    with pytest.raises(ValueError):
        pair_of("sympy__sympy-20590")


def test_variant_anchors_unique():
    for project, variants in VARIANTS.items():
        for variant, (before, after, reqs) in variants.items():
            src = variant_source(project, variant).decode()
            if before:
                # seeded bug applied exactly once (some `after` strings contain
                # `before` as a substring, so only assert the applied form)
                assert src.count(after) == 1, (project, variant)
                assert reqs
            else:
                clean = variant_source(project, variant).decode()
                assert "deepcopy" in clean


def test_smoke_config_has_all_live_gates():
    cfg = smoke_config()
    for key in ("model", "reasoning_effort", "price_snapshot_id", "price_source",
                "budget_authorization", "global_cap_usd", "attempt_cap_usd",
                "max_input_tokens", "max_output_tokens", "token_cap"):
        assert cfg.get(key), f"missing {key}"
    assert cfg["purpose"] == "development_smoke"
    assert cfg["global_cap_usd"] == 100 and cfg["attempt_cap_usd"] == 25
    assert cfg["budget_authorization"] == (
        "On 2026-09-20 Tristen authorized a 3-attempt development smoke with "
        "attempt_cap_usd=25 and global_cap_usd=100.")


def test_reservation_bounds_within_caps():
    cfg = smoke_config()
    worst = verify_reservation_bounds(cfg)
    assert float(worst["repair_attempt_usd"]) <= cfg["attempt_cap_usd"]
    assert float(worst["diagnostic_attempt_usd"]) <= cfg["attempt_cap_usd"]


def test_reservation_bounds_reject_oversize_attempt():
    cfg = smoke_config()
    cfg["attempt_cap_usd"] = 1
    with pytest.raises(ValueError):
        verify_reservation_bounds(cfg)


def test_terminal_done_without_draft_records_nontermination():
    done = _terminal_done("diagnose", 8, None)
    assert done["action"] == "done"
    assert done["terminal_synthesized"] is True
    claims = done["claims"]["claims"]
    assert len(claims) == 1 and claims[0]["id"] == "DIAG-NONTERMINATION-01"
    assert claims[0]["status"] == "unsupported"


def test_terminal_done_adopts_valid_draft():
    draft = {"schema_version": "1.0", "claims": [{
        "id": "D01", "text": "draft claim", "kind": "hypothesis", "status": "unsupported",
        "boundary": ["diagnose"], "depends_on": [], "conflicts_with": [],
        "falsification_tests": ["rerun"], "source_ref": "transcript",
        "uncertainty": "high", "evidence": []}]}
    done = _terminal_done("diagnose", 8, draft)
    assert done["claims"]["claims"][0]["id"] == "D01"


def test_tests_for_public_filters_hidden():
    public = mr_tests_for("tinydb", 3, True).decode()
    assert "test_public_basic" in public
    assert "test_R02_retained_cache" not in public
    hidden = mr_tests_for("tinydb", 3, False).decode()
    assert "test_R02_retained_cache" in hidden


def test_matched_arms_distinct_from_workflow_arms():
    from benchmark_runner.experiment import ARMS
    assert not set(MATCHED_ARMS) & set(ARMS)


# ---------------------------------------------------------------------------
# Regression tests: arm isolation, schedule, and protocol invariants
# ---------------------------------------------------------------------------

def test_matched_arms_are_three_distinct():
    from benchmark_runner.matched_repair import MATCHED_ARMS
    assert MATCHED_ARMS == ("diagnose", "repair_ordinary", "repair_guided")
    assert len(set(MATCHED_ARMS)) == 3


def test_guided_flag_only_for_guided_arm():
    """The AEE assessment injection must be gated on arm == 'repair_guided'."""
    import inspect
    from benchmark_runner import matched_repair as mr
    src = inspect.getsource(mr.run_repair)
    # The guided flag is derived solely from the arm name.
    assert 'guided = arm == "repair_guided"' in src
    # The assessment note is appended only when guided is True.
    assert 'if guided:' in src
    assert 'Actual AEE/Evaluator findings' in src


def test_repair_arms_share_diagnostic_but_not_assessment():
    """Both repair arms see the shared diagnostic summary; only guided sees
    the AEE assessment. Verified structurally: the diagnostic summary is in
    the base instruction, the assessment is in the guided-only branch."""
    import inspect
    from benchmark_runner import matched_repair as mr
    src = inspect.getsource(mr.run_repair)
    # Base instruction includes shared diagnostic for both arms.
    assert 'Shared diagnostic (assertions are not proof)' in src
    # Assessment appears only inside the `if guided:` block.
    guided_block_start = src.index('if guided:')
    assert 'Actual AEE/Evaluator findings' in src[guided_block_start:guided_block_start + 500]


def test_schedule_diagnose_first_and_both_repairs():
    """Schedule must run diagnose first, then both repair arms (order of the
    two repairs is shuffled deterministically by seed)."""
    import inspect
    from benchmark_runner import matched_repair as mr
    src = inspect.getsource(mr.build_smoke_freeze)
    assert 'ordered_arms = ["diagnose"] + arms' in src
    assert 'arms = ["repair_ordinary", "repair_guided"]' in src
    # Shuffle is seeded deterministically.
    assert 'random.Random(seed + len(variant)).shuffle(arms)' in src


def test_attempt_ids_unique_per_arm():
    """Each arm gets a distinct attempt_id so results cannot be confused."""
    import inspect
    from benchmark_runner import matched_repair as mr
    src = inspect.getsource(mr.build_smoke_freeze)
    assert 'attempt_id=f"{pair_id}--{arm}"' in src


def test_scored_freeze_excludes_smoke_pair():
    """Freeze v5 must run on a fresh pair, never the smoke pair, and must be
    a scored (not smoke) manifest with the real-smoke gate grounded."""
    import inspect
    from benchmark_runner import matched_repair as mr
    assert mr.SCORED_PAIR == ("tinydb", "token_alias", 20260918)
    assert mr.SCORED_PAIR != mr.SMOKE_PAIR
    cfg = mr.scored_config()
    assert cfg["purpose"] == "scored_comparison"
    assert cfg["seed"] == 20260918
    assert cfg["model"] == "gpt-6-astra"
    assert cfg["real_smoke_verified"] is True
    assert "2026-09-21" in cfg["budget_authorization"]
    src = inspect.getsource(mr.build_scored_freeze)
    assert 'freeze-v5-scored.json' in src
    assert 'if (p, v, s) != SCORED_PAIR' in src
    assert 'ordered_arms = ["diagnose"] + arms' in src


def test_long_tier_formally_unreachable():
    """Reservation must fail closed if max_input_tokens could reach the
    long-context tier; otherwise only verified short-tier prices are used."""
    from benchmark_runner.matched_repair import smoke_config, verify_reservation_bounds
    cfg = smoke_config()
    assert cfg["max_input_tokens"] < cfg["long_context_threshold"]
    # Mutating the config to reach the long tier must raise.
    bad = dict(cfg)
    bad["max_input_tokens"] = cfg["long_context_threshold"]
    try:
        verify_reservation_bounds(bad)
    except ValueError as e:
        assert "long-context tier" in str(e)
    else:
        raise AssertionError("expected ValueError for long-tier input")


def test_budget_authorization_exact_text():
    """Freeze authorization must be exactly the authorized sentence."""
    from benchmark_runner.matched_repair import smoke_config
    cfg = smoke_config()
    assert cfg["budget_authorization"] == (
        "On 2026-09-20 Tristen authorized a 3-attempt development smoke with "
        "attempt_cap_usd=25 and global_cap_usd=100.")


def test_evidence_flags_fail_closed():
    """Evidence flags default to False; they are set True only from preserved,
    successful verification evidence, never by default."""
    from benchmark_runner.matched_repair import smoke_config
    cfg = smoke_config()
    assert cfg["reservation_bound_verified"] is False
    assert cfg["grader_smoke_verified"] is False
    assert cfg["solver_image_audit_verified"] is False
    assert cfg["real_smoke_verified"] is False


class _LocalSandbox:
    """Runs sandbox.execute commands as local subprocesses in a given cwd,
    emulating the shell env-prefix form used by PYTEST_CMD."""

    def __init__(self, cwd):
        self.cwd = str(cwd)

    def execute(self, cmd, timeout=30):
        out = subprocess.run(cmd, shell=True, cwd=self.cwd,
                             capture_output=True, text=True, timeout=timeout)
        return {"exit_code": out.returncode, "stdout": out.stdout, "stderr": out.stderr}


def _clean_git_repo(path):
    path.mkdir()
    (path / "acceptance_public.py").write_text("def test_ok():\n    assert True\n")
    for args in (["git", "init"], ["git", "config", "user.email", "t@t"],
                 ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                 ["git", "commit", "-m", "init"]):
        subprocess.run(args, cwd=path, check=True, capture_output=True)
    return _LocalSandbox(path)


def test_pytest_cmd_disables_bytecode_writes():
    """Regression guard: without PYTHONDONTWRITEBYTECODE=1, run_public_tests
    writes untracked __pycache__/ dirs and git_clean() false-positives."""
    assert "PYTHONDONTWRITEBYTECODE=1" in PYTEST_CMD


def test_public_tests_keep_clean_worktree_clean(tmp_path, monkeypatch):
    """run_public_tests against a clean fixture repo must leave it clean so
    diagnostic claims survive instead of being discarded."""
    sandbox = _clean_git_repo(tmp_path / "testbed")
    import sys
    local_cmd = (PYTEST_CMD.replace("/testbed/acceptance_public.py", "acceptance_public.py")
                 .replace("/tmp/grade.xml", str(tmp_path / "grade.xml"))
                 .replace("python -m pytest", sys.executable + " -m pytest"))
    monkeypatch.setattr("benchmark_runner.matched_repair.PYTEST_CMD", local_cmd)
    # also point the grade.xml read at the local file
    orig_execute = sandbox.execute

    def execute(cmd, timeout=30):
        return orig_execute(cmd.replace("/tmp/grade.xml", str(tmp_path / "grade.xml")), timeout)
    sandbox.execute = execute

    assert git_clean(sandbox), "fixture repo should start clean"
    public = run_public_tests(sandbox)
    assert public["passed"] is True, public["output"][-500:]
    assert git_clean(sandbox), "public tests must not dirty a clean fixture worktree"


def test_git_clean_still_detects_real_source_edits(tmp_path):
    """The bytecode fix must not blind the worktree guard to genuine edits."""
    sandbox = _clean_git_repo(tmp_path / "testbed")
    assert git_clean(sandbox)
    (tmp_path / "testbed" / "acceptance_public.py").write_text(
        "def test_ok():\n    assert False\n")
    assert not git_clean(sandbox), "modified source files must still be detected"
