"""Regression tests for the matched-repair cloud port (offline only)."""
import json
import subprocess

import pytest

from benchmark_runner.matched_repair import (
    MATCHED_ARMS,
    PROJECTS,
    PYTEST_CMD,
    VARIANTS,
    VARIANT_FILES,
    _terminal_done,
    git_clean,
    pair_of,
    run_public_tests,
    smoke_config,
    tests_for as mr_tests_for,
    variant_files,
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
            files = variant_files(project, variant)
            # Multi-edit variants pass a list of (before, after) pairs as
            # `before` with `after=None`; edits apply in order. Phase-2
            # cross-file edits may be (path, before, after) triples.
            edits = before if isinstance(before, list) else [(before, after)]
            default_path = VARIANT_FILES.get((project, variant),
                                             PROJECTS[project]["module"])
            applied = []
            for edit in edits:
                if len(edit) == 3:
                    path, b, a = edit
                else:
                    b, a = edit
                    path = default_path
                applied.append((path, b, a))
            if any(b for _, b, _ in applied):
                for path, b, a in applied:
                    if not b:
                        continue
                    src = files[path].decode()
                    if a:
                        # seeded edit applied exactly once (some `after`
                        # strings contain `before` as a substring, so only
                        # assert the applied form)
                        assert src.count(a) == 1, (project, variant, path, b)
                    else:
                        # removal edit: the anchor must be gone
                        assert b not in src, (project, variant, path, b)
                assert reqs
            else:
                # clean control: no edits applied, files equal the reference
                from pathlib import Path as _Path
                from benchmark_runner import matched_repair as _mr
                meta = PROJECTS[project]
                if meta.get("synthetic"):
                    refdir = (_Path(_mr.__file__).resolve().parents[2] / "benchmarks"
                              / "repeated_local" / project / "reference")
                    prefix = meta["package"] + "/"
                    for path, data in files.items():
                        rel = path[len(prefix):]
                        assert data == (refdir / rel).read_bytes(), (project, variant, path)
                else:
                    clean = variant_source(project, variant).decode()
                    assert "deepcopy" in clean


def test_multi_edit_variant_applies_edits_in_order():
    from benchmark_runner import matched_repair as mr
    src = mr.variant_source("cachetools", "coupled").decode()
    assert "now > entry[2]" in src
    assert "now >= entry[2]" not in src
    assert "if not tags:" not in src
    assert mr.VARIANTS["cachetools"]["coupled"][2] == ["R07", "R08", "R04"]


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


def test_scored_v6_pairs_excludes_smoke_pair():
    """Freeze v6 must cover every variant at the scored seed except the smoke
    pair; clean variants stay in as negative controls."""
    from benchmark_runner import matched_repair as mr
    pairs = mr.SCORED_PAIRS_V6
    assert len(pairs) == 7, pairs
    assert all(s == 20260918 for _, _, s in pairs)
    assert ("tinydb", "bool_id", 20260918) not in pairs
    assert mr.SMOKE_PAIR not in pairs
    # Reruns the v5 pair so grading is in the mix for the whole set.
    assert ("tinydb", "token_alias", 20260918) in pairs
    # Clean negative controls are included, not silently dropped.
    assert ("tinydb", "clean", 20260918) in pairs
    assert ("cachetools", "clean", 20260918) in pairs
    assert len(set(pairs)) == 7


def test_scored_v6_schedule_is_deterministic_and_complete():
    """21 attempts: diagnose first per pair, both repair arms, unique ids,
    deterministic across calls (pure function, no Docker)."""
    from benchmark_runner import matched_repair as mr
    sched = mr.scored_v6_schedule()
    assert sched == mr.scored_v6_schedule()
    assert len(sched) == 21
    ids = [s["attempt_id"] for s in sched]
    assert len(set(ids)) == 21
    by_pair = {}
    for s in sched:
        by_pair.setdefault(s["task_id"], []).append(s["arm"])
    assert len(by_pair) == 7
    for pair_id, arms in by_pair.items():
        assert arms[0] == "diagnose", pair_id
        assert sorted(arms[1:]) == ["repair_guided", "repair_ordinary"], pair_id
        for s in sched:
            if s["task_id"] == pair_id:
                assert s["attempt_id"] == f"{pair_id}--{s['arm']}"
    assert not any("bool_id" in p for p in by_pair)


def test_scored_v6_config_grounds_real_smoke():
    """v6 config keeps the scored caps and grounds real_smoke_verified on the
    completed v4 smoke AND the completed v5 scored run."""
    import inspect
    from benchmark_runner import matched_repair as mr
    cfg = mr.scored_config_v6()
    assert cfg["purpose"] == "scored_comparison"
    assert cfg["seed"] == 20260918
    assert cfg["model"] == "gpt-6-astra"
    assert cfg["global_cap_usd"] == 100 and cfg["attempt_cap_usd"] == 25
    assert cfg["real_smoke_verified"] is True
    assert "2026-09-21" in cfg["budget_authorization"]
    assert "freeze v6" in cfg["budget_authorization"].lower()
    assert "v4" in cfg["real_smoke_evidence"] and "v5" in cfg["real_smoke_evidence"]
    src = inspect.getsource(mr.build_scored_freeze_v6)
    assert 'freeze-v6-scored.json' in src
    assert 'hidden_test_count' in src
    assert 'not in set(SCORED_PAIRS_V6)' in src


def test_scored_v7_pairs_hard_set():
    """Freeze v7: token_alias anchor, five hard pairs, both clean controls.
    v6-only single-defect variants are excluded."""
    from benchmark_runner import matched_repair as mr
    pairs = mr.SCORED_PAIRS_V7
    assert len(pairs) == 8, pairs
    assert all(s == 20260918 for _, _, s in pairs)
    assert ("tinydb", "token_alias", 20260918) in pairs
    for hard in ("empty_tags", "token_reserve", "expiry_retain",
                 "storage_alias", "coupled"):
        assert any(v == hard for _, v, _ in pairs), hard
    assert ("tinydb", "clean", 20260918) in pairs
    assert ("cachetools", "clean", 20260918) in pairs
    for dropped in ("bool_id", "partial_commit", "value_alias",
                    "boolean_ttl", "expiry_boundary"):
        assert not any(v == dropped for _, v, _ in pairs), dropped
    assert len(set(pairs)) == 8


def test_scored_v7_schedule_is_deterministic_and_complete():
    """24 attempts: diagnose first per pair, both repair arms, unique ids,
    deterministic across calls (pure function, no Docker)."""
    from benchmark_runner import matched_repair as mr
    sched = mr.scored_v7_schedule()
    assert sched == mr.scored_v7_schedule()
    assert len(sched) == 24
    ids = [s["attempt_id"] for s in sched]
    assert len(set(ids)) == 24
    by_pair = {}
    for s in sched:
        by_pair.setdefault(s["task_id"], []).append(s["arm"])
    assert len(by_pair) == 8
    for pair_id, arms in by_pair.items():
        assert arms[0] == "diagnose", pair_id
        assert sorted(arms[1:]) == ["repair_guided", "repair_ordinary"], pair_id
        for s in sched:
            if s["task_id"] == pair_id:
                assert s["attempt_id"] == f"{pair_id}--{s['arm']}"


def test_scored_v7_config_unauthorized_build_only():
    """v7 config keeps the scored caps, grounds real_smoke_verified on the
    completed v4/v5/v6 runs, and records Tristen's 2026-09-21 campaign
    authorization."""
    import inspect
    from benchmark_runner import matched_repair as mr
    cfg = mr.scored_config_v7()
    assert cfg["purpose"] == "scored_comparison"
    assert cfg["seed"] == 20260918
    assert cfg["model"] == "gpt-6-astra"
    assert cfg["global_cap_usd"] == 100 and cfg["attempt_cap_usd"] == 25
    assert cfg["real_smoke_verified"] is True
    assert "2026-09-21" in cfg["budget_authorization"]
    assert "authorized" in cfg["budget_authorization"]
    assert "v4" in cfg["real_smoke_evidence"] and "v6" in cfg["real_smoke_evidence"]
    src = inspect.getsource(mr.build_scored_freeze_v7)
    assert 'freeze-v7-scored.json' in src
    assert 'hidden_test_count' in src
    assert 'not in set(SCORED_PAIRS_V7)' in src


def test_variant_files_multi_file_and_cross_file_edits():
    """Phase-2 machinery: minisched variants return one entry per package
    file; single-edit variants seed the right file; the cross-file coupled
    variant applies edits in two files; variant_source still works for
    single-file projects and refuses multi-file ones."""
    from benchmark_runner import matched_repair as mr
    files = mr.variant_files("minisched", "clean")
    assert set(files) == {"minisched/__init__.py", "minisched/config.py",
                          "minisched/store.py", "minisched/scheduler.py"}
    assert b"DEFAULT_MAX_RETRIES = 3" in files["minisched/config.py"]
    cfg = mr.variant_files("minisched", "config_default")
    assert b"DEFAULT_MAX_RETRIES = 0" in cfg["minisched/config.py"]
    assert b'"payload": deepcopy(payload)' in cfg["minisched/store.py"]
    store = mr.variant_files("minisched", "store_add_alias")
    assert b'"payload": payload' in store["minisched/store.py"]
    assert b"DEFAULT_MAX_RETRIES = 3" in store["minisched/config.py"]
    coupled = mr.variant_files("minisched", "coupled_xfile")
    assert b"DEFAULT_MAX_RETRIES = 0" in coupled["minisched/config.py"]
    assert b'"payload": payload' in coupled["minisched/store.py"]
    # single-file projects still go through variant_source unchanged
    src = mr.variant_source("tinydb", "token_alias").decode()
    assert "self.tokens[token] = (deepcopy(operations), inserted)" in src
    with pytest.raises(ValueError):
        mr.variant_source("minisched", "clean")


def test_scored_v8_pairs_cross_file_set():
    """Freeze v8: four minisched cross-file pairs at the scored seed."""
    from benchmark_runner import matched_repair as mr
    pairs = mr.SCORED_PAIRS_V8
    assert len(pairs) == 4, pairs
    assert all(p == "minisched" for p, _, _ in pairs)
    assert all(s == 20260918 for _, _, s in pairs)
    for v in ("config_default", "store_add_alias", "coupled_xfile", "clean"):
        assert (("minisched", v, 20260918) in pairs), v
    assert len(set(pairs)) == 4


def test_scored_v8_schedule_is_deterministic_and_complete():
    """12 attempts: diagnose first per pair, both repair arms, unique ids,
    deterministic across calls (pure function, no Docker)."""
    from benchmark_runner import matched_repair as mr
    sched = mr.scored_v8_schedule()
    assert sched == mr.scored_v8_schedule()
    assert len(sched) == 12
    ids = [s["attempt_id"] for s in sched]
    assert len(set(ids)) == 12
    by_pair = {}
    for s in sched:
        by_pair.setdefault(s["task_id"], []).append(s["arm"])
    assert len(by_pair) == 4
    for pair_id, arms in by_pair.items():
        assert arms[0] == "diagnose", pair_id
        assert sorted(arms[1:]) == ["repair_guided", "repair_ordinary"], pair_id
        for s in sched:
            if s["task_id"] == pair_id:
                assert s["attempt_id"] == f"{pair_id}--{s['arm']}"


def test_scored_v8_config_authorized():
    """v8 config keeps the scored caps, grounds real_smoke_verified on the
    completed v4/v5/v6/v7 runs, and records Tristen's 2026-09-21 phase-2
    campaign authorization."""
    import inspect
    from benchmark_runner import matched_repair as mr
    cfg = mr.scored_config_v8()
    assert cfg["purpose"] == "scored_comparison"
    assert cfg["seed"] == 20260918
    assert cfg["model"] == "gpt-6-astra"
    assert cfg["global_cap_usd"] == 100 and cfg["attempt_cap_usd"] == 25
    assert cfg["real_smoke_verified"] is True
    assert "2026-09-21" in cfg["budget_authorization"]
    assert "authorized" in cfg["budget_authorization"]
    assert "phase-2" in cfg["budget_authorization"]
    assert "v7" in cfg["real_smoke_evidence"]
    src = inspect.getsource(mr.build_scored_freeze_v8)
    assert 'freeze-v8-scored.json' in src
    assert 'hidden_test_count' in src
    assert 'not in set(SCORED_PAIRS_V8)' in src


def test_scored_v8_1_schedule_matches_v8():
    """v8.1 reruns the exact same 12-attempt schedule as v8: same pairs, seed,
    arm order. Only the frozen spec text (R01 wording) changed."""
    from benchmark_runner import matched_repair as mr
    assert mr.SCORED_PAIRS_V8_1 == mr.SCORED_PAIRS_V8
    assert mr.SCORED_SEED_V8_1 == mr.SCORED_SEED_V8 == 20260918
    sched = mr.scored_v8_1_schedule()
    assert sched == mr.scored_v8_schedule()
    assert len(sched) == 12


def test_scored_v8_1_config_authorized():
    """v8.1 config keeps the scored caps, grounds real_smoke_verified on the
    completed v8 run, and records Tristen's 2026-09-21 rerun authorization."""
    import inspect
    from benchmark_runner import matched_repair as mr
    cfg = mr.scored_config_v8_1()
    assert cfg["purpose"] == "scored_comparison"
    assert cfg["seed"] == 20260918
    assert cfg["model"] == "gpt-6-astra"
    assert cfg["global_cap_usd"] == 100 and cfg["attempt_cap_usd"] == 25
    assert cfg["real_smoke_verified"] is True
    assert "2026-09-21" in cfg["budget_authorization"]
    assert "rerun" in cfg["budget_authorization"]
    assert "v8" in cfg["real_smoke_evidence"]
    src = inspect.getsource(mr.build_scored_freeze_v8_1)
    assert 'freeze-v8-1-scored.json' in src
    assert 'not in set(SCORED_PAIRS_V8_1)' in src


def test_stage1_r01_matches_hidden_r03_contract():
    """Regression test for the v8 validity defect: stage1.md R01 must state
    that a non-callable 'fn' is a job failure handled under the retry rule,
    never raised to the caller -- exactly what hidden test_R03_bad_payload
    pins. The pre-v8.1 wording ('raises ValueError when executed') generated
    phantom defects in all 8 v8 repair arms."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent
            / "benchmarks" / "repeated_local" / "minisched" / "stage1.md").read_text()
    assert "never raising to the caller" in text
    assert "job failure, not a caller error" in text
    assert "raises ValueError when executed" not in text


def test_graded_comparison_reports_hidden_pass_rate():
    """graded_comparison adds per-arm hidden pass-rate (primary metric for
    hard pairs where partial passes are expected)."""
    import json
    from pathlib import Path
    from benchmark_runner import matched_repair as mr
    from benchmark_runner.store import Store
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp))
        store.append("hidden_grades", {
            "attempt_id": "mr-tinydb-empty_tags-20260918--repair_ordinary",
            "task_id": "mr-tinydb-empty_tags-20260918",
            "arm": "repair_ordinary", "graded": True,
            "hidden_passed": False, "test_count": 16,
            "failed_cases": ["test_R04_intersection_empty"]})
        store.append("hidden_grades", {
            "attempt_id": "mr-tinydb-empty_tags-20260918--repair_guided",
            "task_id": "mr-tinydb-empty_tags-20260918",
            "arm": "repair_guided", "graded": True,
            "hidden_passed": True, "test_count": 16,
            "failed_cases": []})
        pairs = mr.graded_comparison(tmp)
    row = pairs["mr-tinydb-empty_tags-20260918"]
    assert row["repair_ordinary"]["hidden_pass_rate"] == 15 / 16
    assert row["repair_guided"]["hidden_pass_rate"] == 1.0
    assert row["repair_ordinary"]["hidden_passed"] is False
    assert row["repair_guided"]["hidden_passed"] is True


def _snapshot_artifact(store, data: bytes):
    return store.artifact(data)


def test_grade_run_records_hidden_grades_and_is_idempotent(tmp_path):
    """grade_run grades each completed repair snapshot with the hidden tests,
    records hidden_grades events, and skips already-graded attempts on re-run."""
    from benchmark_runner import matched_repair as mr
    from benchmark_runner.store import Store, sha, utc, write_json
    run = tmp_path / "run"
    run.mkdir()
    store = Store(run)
    write_json(run / "freeze.json", {
        "freeze_id": "41179513d89ea34de",
        "config": {"purpose": "scored_comparison"},
        "tasks": {"tasks": [
            {"instance_id": "mr-tinydb-token_alias-20260918",
             "image": "localhost:5000/mr-fixture-tinydb-token_alias@sha256:abc",
             "hidden_test_count": 16}]},
    })
    snap = _snapshot_artifact(store, b"fake-snapshot-bytes")
    attempt_id = "mr-tinydb-token_alias-20260918--repair_guided"
    store.append("attempts", {"attempt_id": attempt_id, "task_id": "mr-tinydb-token_alias-20260918",
                             "arm": "repair_guided", "status": "started", "timestamp": utc()})
    store.append("attempts", {"attempt_id": attempt_id, "task_id": "mr-tinydb-token_alias-20260918",
                             "arm": "repair_guided", "status": "completed",
                             "package_snapshot": snap, "timestamp": utc()})
    # Diagnose attempts are never graded.
    store.append("attempts", {"attempt_id": "mr-tinydb-token_alias-20260918--diagnose",
                             "task_id": "mr-tinydb-token_alias-20260918",
                             "arm": "diagnose", "status": "completed", "timestamp": utc()})
    seen = {}

    def fake_grade(image, data, project, expected):
        seen["args"] = (image, data, project, expected)
        return {"passed": True, "test_count": 16, "expected": 16,
                "failed_cases": [], "cases": [], "output": "ok"}

    results = mr.grade_run(run, grade_fn=fake_grade)
    assert results == [(attempt_id, True)]
    assert seen["args"][0].endswith("@sha256:abc")
    assert seen["args"][1] == b"fake-snapshot-bytes"
    assert seen["args"][2] == "tinydb" and seen["args"][3] == 16
    grades = store.events("hidden_grades")
    assert len(grades) == 1
    g = grades[0]
    assert g["graded"] is True and g["hidden_passed"] is True
    assert g["test_count"] == 16 and g["failed_cases"] == []
    assert (store.root / g["grade_artifact"]["path"]).exists()
    # Idempotent: second run grades nothing new.
    assert mr.grade_run(run, grade_fn=fake_grade) == []
    assert len(store.events("hidden_grades")) == 1
    # graded_comparison surfaces the pair row honestly.
    comp = mr.graded_comparison(run)
    assert comp["mr-tinydb-token_alias-20260918"]["repair_guided"]["hidden_passed"] is True


def test_grade_run_fails_closed_on_missing_snapshot(tmp_path):
    """A completed repair attempt without a package snapshot is a hard error,
    not a silent skip."""
    import pytest
    from benchmark_runner import matched_repair as mr
    from benchmark_runner.store import Store, utc, write_json
    run = tmp_path / "run"
    run.mkdir()
    store = Store(run)
    write_json(run / "freeze.json", {
        "freeze_id": "41179513d89ea34de",
        "config": {"purpose": "scored_comparison"},
        "tasks": {"tasks": [
            {"instance_id": "mr-tinydb-token_alias-20260918",
             "image": "img", "hidden_test_count": 16}]},
    })
    store.append("attempts", {"attempt_id": "mr-tinydb-token_alias-20260918--repair_ordinary",
                             "task_id": "mr-tinydb-token_alias-20260918",
                             "arm": "repair_ordinary", "status": "completed", "timestamp": utc()})
    with pytest.raises(ValueError, match="no package_snapshot"):
        mr.grade_run(run, grade_fn=lambda *a: {})
    assert store.events("hidden_grades") == []


def test_grade_run_skips_uncompleted_attempts_honestly(tmp_path):
    """Non-completed repair attempts get an explicit ungraded event with the
    reason, not a fabricated grade."""
    from benchmark_runner import matched_repair as mr
    from benchmark_runner.store import Store, utc, write_json
    run = tmp_path / "run"
    run.mkdir()
    store = Store(run)
    write_json(run / "freeze.json", {
        "freeze_id": "41179513d89ea34de",
        "config": {"purpose": "scored_comparison"},
        "tasks": {"tasks": [
            {"instance_id": "mr-tinydb-token_alias-20260918",
             "image": "img", "hidden_test_count": 16}]},
    })
    store.append("attempts", {"attempt_id": "mr-tinydb-token_alias-20260918--repair_ordinary",
                             "task_id": "mr-tinydb-token_alias-20260918",
                             "arm": "repair_ordinary", "status": "limit",
                             "reason": "global cap", "timestamp": utc()})
    results = mr.grade_run(run, grade_fn=lambda *a: (_ for _ in ()).throw(AssertionError("must not grade")))
    assert results == [("mr-tinydb-token_alias-20260918--repair_ordinary", "skipped")]
    grades = store.events("hidden_grades")
    assert len(grades) == 1
    assert grades[0]["graded"] is False
    assert "limit" in grades[0]["reason"]


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
