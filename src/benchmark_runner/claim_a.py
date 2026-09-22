"""Claim A campaign: local 8B + Spec-Kit/AEE vs frontier ordinary repair.

v9 measurement design, sections 1/3/4. Two phases, both offline to build:

Phase A (calibration): candidate repair variants, frontier ordinary repair
only, 2 attempts per task (1 shared diagnostic + 2 repairs). Keep the
0.2-0.8 ordinary pass band on the frontier model (with 2 attempts per task
this means exactly one of the two passes).

Phase B (main): the kept tasks, two frozen manifests sharing the task bank
and seed -- frontier ordinary vs local full-workflow. Non-inferiority margin: 10%
relative on mean expected loss; headline economic metric: dollars per
accepted task.

DESIGN GAP (resolved 2026-09-21, Option B): the local arm runs the full
Spec-Kit+AEE workflow as the `repair_workflow` treatment
(matched_repair.run_workflow_repair): the exact frozen six-phase workflow
from benchmark_runner.workflow (constitution, specify, plan, tasks,
implement, converge) with the frozen skill prompts, grounded claims, and the
AEE assess() gate at each AEE phase with bounded recovery rounds. It runs on
the matched-repair fixture sandbox with the same shared diagnostic and
public-test feedback as the frontier ordinary-repair arm, so the only
treatment difference is the repair method. The single-task local pilot is the
real-smoke gate for this treatment on the operator's server before the main
local freeze.

Cross-backend matching: the runner selects the provider from the frozen
manifest config, so a campaign can never mix backends mid-run. Claim A runs
two manifests (openai + local) over the same frozen task bank and seed; the
offline analysis in scripts/analyze_claim_a.py pairs them by task.

No model calls in this module. Paid phases run on the host behind the RUN
gate in scripts/host-setup-claim-a.sh, one typed RUN per phase.
"""

import argparse
import json
import os
from pathlib import Path

from .experiment import frozen_paths, source_hash
from .matched_repair import (
    ROOT,
    VARIANTS,
    audit_solver_image,
    calibrate_fixtures,
    run_grade_smoke,
    smoke_config,
    verify_reservation_bounds,
    OPENROUTER_LONG_CONTEXT_PRICES,
    OPENROUTER_PRICE_SNAPSHOT_ID,
    OPENROUTER_PRICE_SOURCE,
    OPENROUTER_PRICES,
)
from .provider import provider_name_from_env
from .store import canonical, read_json, sha, write_json

CLAIM_A_SEED = 20260921

# Candidate (project, variant, seed) triples for Phase A calibration.
# Filled in from the candidate-build report; every entry must name a variant
# present in VARIANTS with hidden tests and a completed alignment note.
# Empty until the candidate build lands -- the freeze builders fail closed.
# Audited 2026-09-21: all 32 verified independently (public tests pass on the
# seeded defect, hidden failures exactly equal the declared expected set,
# unmutated reference passes everything) via /tmp/claim-a-audit.py.
# Audited 2026-09-22: 11 round-2 candidates added (4 minisched, 3 cachetools,
# 4 tinydb); all 43 verified independently via scripts/verify_new_candidates.py
# (public pass on seeded defect, declared hidden pins fail, clean reference
# passes everything, no hidden-test leakage into solver images). Spec-literal
# review and adversarial trap review completed; notes in
# benchmarks/repeated_local/claim-a-round2-review.md.
CLAIM_A_CANDIDATES = (
    # tinydb (13)
    ("tinydb", "token_ops_alias", CLAIM_A_SEED),
    ("tinydb", "empty_batch_token", CLAIM_A_SEED),
    ("tinydb", "token_conflict_shallow", CLAIM_A_SEED),
    ("tinydb", "preview_cache_alias", CLAIM_A_SEED),
    ("tinydb", "token_conflict_repr", CLAIM_A_SEED),
    ("tinydb", "stale_snapshot", CLAIM_A_SEED),
    ("tinydb", "compact_id_reuse", CLAIM_A_SEED),
    ("tinydb", "next_id_rewind", CLAIM_A_SEED),
    ("tinydb", "token_validate_late", CLAIM_A_SEED),
    # tinydb round 2 (2026-09-22): harder trap-style / cross-file candidates
    ("tinydb", "conflict_mutates_before_raise", CLAIM_A_SEED),
    ("tinydb", "stale_table_cache", CLAIM_A_SEED),
    ("tinydb", "tokens_shared_across_instances", CLAIM_A_SEED),
    ("tinydb", "next_id_not_written_back", CLAIM_A_SEED),
    # cachetools (14)
    ("cachetools", "resize_order_trap", CLAIM_A_SEED),
    ("cachetools", "invalidate_many_no_expire", CLAIM_A_SEED),
    ("cachetools", "put_no_recency_refresh", CLAIM_A_SEED),
    ("cachetools", "ttl_validation_after_mutation", CLAIM_A_SEED),
    ("cachetools", "generator_tags_reconsumed", CLAIM_A_SEED),
    ("cachetools", "maxsize_bool", CLAIM_A_SEED),
    ("cachetools", "invalid_mode_silent", CLAIM_A_SEED),
    ("cachetools", "resize_no_expire", CLAIM_A_SEED),
    ("cachetools", "put_no_pre_expire", CLAIM_A_SEED),
    ("cachetools", "all_subset_flip", CLAIM_A_SEED),
    ("cachetools", "expiry_recency_touch", CLAIM_A_SEED),
    # cachetools round 2 (2026-09-22): harder trap-style candidates
    ("cachetools", "resize_drops_expiry", CLAIM_A_SEED),
    ("cachetools", "len_no_expire", CLAIM_A_SEED),
    ("cachetools", "get_no_recency_refresh", CLAIM_A_SEED),
    # minisched (16)
    ("minisched", "or_default_trap", CLAIM_A_SEED),
    ("minisched", "retry_off_by_one", CLAIM_A_SEED),
    ("minisched", "failed_stays_listed", CLAIM_A_SEED),
    ("minisched", "lifo_order", CLAIM_A_SEED),
    ("minisched", "default_retries_value", CLAIM_A_SEED),
    ("minisched", "get_live_record", CLAIM_A_SEED),
    ("minisched", "attempts_not_stored", CLAIM_A_SEED),
    ("minisched", "hardcoded_retries", CLAIM_A_SEED),
    ("minisched", "update_reinserts_reorders", CLAIM_A_SEED),
    ("minisched", "failed_status_mismatch", CLAIM_A_SEED),
    ("minisched", "add_shallow_copy", CLAIM_A_SEED),
    ("minisched", "enqueue_eager_validation", CLAIM_A_SEED),
    # minisched round 2 (2026-09-22): harder cross-file / trap-style candidates
    ("minisched", "config_snapshot_stale", CLAIM_A_SEED),
    ("minisched", "done_status_mismatch", CLAIM_A_SEED),
    ("minisched", "list_pending_returns_live", CLAIM_A_SEED),
    ("minisched", "update_unknown_silent", CLAIM_A_SEED),
)

# Attempts per repair arm in each phase (v9 design: 2).
REPAIR_REPEATS = 2

# v9 design section 4, ratified 2026-09-21: loss weights in units of run cost.
W_WRONG = 3
W_MISS = 1

# Relative non-inferiority margin on mean expected loss, ratified 2026-09-21.
NI_MARGIN_REL = 0.10


def _budget_authorization(phase):
    return (
        f"Claim A {phase}: spend is authorized phase-by-phase by the operator's "
        f"fresh typed RUN at the host gate (scripts/host-setup-claim-a.sh), one "
        f"RUN per phase, under the standing $25/attempt and $100 global caps. "
        f"No blanket pre-authorization. Prior measured spend through v8.1: "
        f"$29.9458 against the $100 global cap ($70.0542 remaining). "
        f"Spend settles to measured usage; unknown usage is never released."
    )


def calibration_config():
    """Frozen config for Phase A: frontier ordinary-repair calibration.

    The frontier provider is selected by the BENCH_PROVIDER environment
    variable at freeze time ("openai" default, "openrouter" for the
    OpenRouter-served arm) and recorded in the frozen manifest, so the
    choice is tamper-evident and can never change mid-campaign.
    """
    cfg = smoke_config()
    provider_name = provider_name_from_env()
    if provider_name == "openrouter":
        # Identical model, identical list prices (verified 2026-09-22); only
        # the endpoint, the API model string, and the price snapshot identity
        # change. The reservation gate accepts the OpenRouter model string
        # explicitly (matched_repair.ASTRA_MODEL_IDS).
        cfg.update({
            "model": "openai/gpt-6-astra",
            "provider": {"name": "openrouter"},
            "price_snapshot_id": OPENROUTER_PRICE_SNAPSHOT_ID,
            "price_source": OPENROUTER_PRICE_SOURCE,
            "prices": dict(OPENROUTER_PRICES),
            "long_context_prices": dict(OPENROUTER_LONG_CONTEXT_PRICES),
        })
    cfg.update({
        "purpose": "claim_a_calibration",
        "seed": CLAIM_A_SEED,
        "repeats": REPAIR_REPEATS,
        "provider_backend": "openai",
        "budget_authorization": _budget_authorization("calibration"),
        # Grounded on the completed v4/v5/v6/v7/v8/v8.1 paid runs: the
        # OpenAI adapter/usage path is proven end to end.
        "real_smoke_verified": True,
        "real_smoke_evidence": (
            "Freeze v4 development smoke (3/3, $1.4831), v5 scored (3/3, "
            "$1.5029), v6 full campaign (21/21, $8.8870), v7 hard-pair campaign "
            "(24/24, $11.0133), v8.1 rerun (12/12, $3.1833): the paid model "
            "path is proven end to end on gpt-6-astra."
        ),
    })
    return cfg


def main_config_frontier(kept):
    """Frozen config for Phase B frontier arm: ordinary repair, OpenAI."""
    cfg = calibration_config()
    cfg.update({
        "purpose": "claim_a_main",
        "budget_authorization": _budget_authorization("main comparison (frontier arm)"),
    })
    return cfg


def main_config_local(kept, real_smoke_evidence=None):
    """Frozen config for Phase B local arm: full Spec-Kit+AEE workflow, local backend.

    Model identity comes from the operator environment (LOCAL_MODEL_NAME /
    LOCAL_MODEL_BASE_URL) and is fail-closed verified by check_local_server()
    before any attempt; cfg["model"] records the value seen at freeze time.
    real_smoke_evidence must cite the completed local pilot run; without it
    the config is not runnable (validate_live fails closed).

    Attempt call budget: the workflow treatment runs six phases at up to
    WORKFLOW_CALLS_PER_PHASE=8 actions each (48) plus bounded AEE recovery
    rounds, versus 16 repair actions for the frontier ordinary arm. The
    attempt-level max_calls is therefore 64 for the local manifest. This is a
    treatment-inherent difference, not a thumb on the scale: local calls have
    zero marginal dollars, so they do not inflate the local arm's expected
    loss -- the loss counts measured dollars, and the local arm's measured
    cost is $0 by construction (LocalProvider settles every call at $0).
    Per-attempt call counts are recorded in telemetry for transparency, and
    the workflow must earn non-inferior quality on that free footing; the
    economic claim is carried by dollars per accepted task, reported
    separately.
    """
    cfg = calibration_config()
    model = os.environ.get("LOCAL_MODEL_NAME")
    if not model:
        raise ValueError("LOCAL_MODEL_NAME is not set: refusing to freeze a "
                         "local manifest against an unidentified model")
    cfg.update({
        "purpose": "claim_a_main",
        "provider_backend": "local",
        "model": model,
        "max_calls": 64,
        # reasoning_effort is OpenAI-only; LocalProvider must not receive it.
        "price_snapshot_id": "local-inference",
        "prices": {"input": 0.0, "cached_input": 0.0, "output": 0.0},
        "budget_authorization": _budget_authorization("main comparison (local arm)"),
        "real_smoke_verified": real_smoke_evidence is not None,
    })
    cfg.pop("reasoning_effort", None)
    if real_smoke_evidence:
        cfg["real_smoke_evidence"] = real_smoke_evidence
    return cfg


def _pair_id(project, variant, seed):
    return f"mr-{project}-{variant}-{seed}"


def calibration_schedule(candidates):
    """Deterministic schedule: per candidate, one shared diagnostic followed
    by REPAIR_REPEATS ordinary repairs. Pure function (no Docker, no calls)."""
    schedule = []
    for project, variant, seed in candidates:
        pair_id = _pair_id(project, variant, seed)
        schedule.append(dict(task_id=pair_id, arm="diagnose", repeat=1,
                             attempt_id=f"{pair_id}--diagnose"))
        for r in range(1, REPAIR_REPEATS + 1):
            schedule.append(dict(task_id=pair_id, arm="repair_ordinary", repeat=r,
                                 attempt_id=f"{pair_id}--repair_ordinary-{r}"))
    return schedule


def main_schedule(kept, repair_arm):
    """Deterministic schedule for one Phase B arm: per kept task, one shared
    diagnostic followed by REPAIR_REPEATS repairs with repair_arm."""
    assert repair_arm in ("repair_ordinary", "repair_workflow")
    schedule = []
    for project, variant, seed in kept:
        pair_id = _pair_id(project, variant, seed)
        schedule.append(dict(task_id=pair_id, arm="diagnose", repeat=1,
                             attempt_id=f"{pair_id}--diagnose"))
        for r in range(1, REPAIR_REPEATS + 1):
            schedule.append(dict(task_id=pair_id, arm=repair_arm, repeat=r,
                                 attempt_id=f"{pair_id}--{repair_arm}-{r}"))
    return schedule


def pilot_schedule(kept):
    """One-task local pilot: a single diagnostic + full-workflow repair, used as the
    real-smoke gate for the local backend and the workflow treatment before the
    main local freeze."""
    project, variant, seed = kept[0]
    pair_id = _pair_id(project, variant, seed)
    return [
        dict(task_id=pair_id, arm="diagnose", repeat=1,
             attempt_id=f"{pair_id}--diagnose"),
        dict(task_id=pair_id, arm="repair_workflow", repeat=1,
             attempt_id=f"{pair_id}--repair_workflow-1"),
    ]


def problem_statement(pair_id, project):
    return (
        f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
        f"in the {project} package -- possibly spanning modules, with the "
        f"symptom surfacing in a different file than the cause (or it may be a clean negative "
        f"control). Protocol: (1) a read-only diagnostic attempt reviews the implementation "
        f"and public test feedback and returns grounded requirement claims with explicit "
        f"uncertainty; (2) repair attempts start from the same pristine snapshot and run one "
        f"of two repair treatments: direct repair rounds (frontier arm), or the full six-phase "
        f"Spec-Kit+AEE workflow with per-phase AEE assessment gates (local arm). After all runs, "
        f"the final package snapshots are graded with hidden acceptance tests; hidden outcomes "
        f"are never fed back to any attempt.")


def build_freeze(output, calibration_path, cfg, schedule, pairs, freeze_name,
                 notes, selection):
    """Generic Claim A freeze builder. Offline: no model calls, no spend.

    Runs the same gates as the v8.1 builder: reservation bounds, per-fixture
    solver image audit, independent grader smoke. Fails closed otherwise.
    """
    calibration = read_json(Path(calibration_path))
    fixtures = {}
    for project, variant, seed in pairs:
        try:
            fixtures[(project, variant)] = next(
                f for f in calibration["fixtures"]
                if (f["project"], f["variant"]) == (project, variant))
        except StopIteration:
            raise ValueError(f"no calibrated fixture for {project}/{variant}; "
                             f"run the claim-a calibration step first")
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    tasks = []
    for project, variant, seed in pairs:
        pair_id = _pair_id(project, variant, seed)
        fixture = fixtures[(project, variant)]
        # The seeded defect's hidden failures are the adjudication baseline:
        # an attempt that fails hidden tests without introducing NEW failures
        # beyond this set is a miss, not harm. Persisted per task so the
        # offline analysis never has to guess it.
        baseline_failed = fixture["grade"].get("failed_cases")
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"],
                      "hidden_baseline_failed_cases": baseline_failed})
    pair_set = set((p, v, s) for p, v, s in pairs)
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": selection,
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p]
                                       for s in (CLAIM_A_SEED,) if (p, v, CLAIM_A_SEED) not in pair_set),
                  "tasks": tasks},
        "schedule": schedule,
        "pairing": ("One read-only diagnostic per task, shared by that task's repair attempts; "
                    "identical start/feedback/tools. The frontier arm runs direct repair rounds; the "
                    "local arm runs the full six-phase Spec-Kit+AEE workflow (constitution, specify, "
                    "plan, tasks, implement, converge) with AEE assessment gates at each AEE phase. "
                    "The diagnostic summary is a matched covariate for both repair treatments "
                    "(assertions, not proof). Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots "
                    "happens after all runs and is never fed back. "
                    "Frontier and local manifests share the frozen task bank and seed; the "
                    "offline analysis pairs them by task_id."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"],
                   "hidden_baseline_failed_cases":
                       fixtures[(p, v)]["grade"].get("failed_cases")}
                  for p, v, s in pairs],
        "notes": notes,
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / f"{freeze_name}.json", manifest, exclusive=True)
    return manifest


def cmd_calibrate(args):
    """Offline fixture calibration for the Claim A candidate set + clean controls."""
    from .matched_repair import ensure_registry
    ensure_registry()
    pairs = [(p, v) for p, v, _ in CLAIM_A_CANDIDATES]
    for project in sorted({p for p, _ in pairs}):
        pairs.append((project, "clean"))
    calibrate_fixtures(Path(args.out), pairs)


def _load_candidates():
    if not CLAIM_A_CANDIDATES:
        raise ValueError("CLAIM_A_CANDIDATES is empty: the candidate build has not landed yet")
    return list(CLAIM_A_CANDIDATES)


def cmd_freeze_calibration(args):
    candidates = _load_candidates()
    cfg = calibration_config()
    manifest = build_freeze(
        args.out, args.calibration, cfg, calibration_schedule(candidates), candidates,
        "freeze-claim-a-calibration",
        ("Freeze claim-a-calibration: Phase A task-bank calibration for Claim A (v9 design §3). "
         f"{len(candidates)} candidate variants, frontier ordinary repair only, {REPAIR_REPEATS} "
         "attempts per task. Keeps the 0.2-0.8 ordinary pass band; the kept set feeds the "
         "Phase B manifests. All prior freezes and evidence untouched."),
        (f"Claim A calibration bank: {len(candidates)} candidate repair variants "
         "(real-issue-derived, ambiguous-spec, attractive-trap) at seed "
         f"{CLAIM_A_SEED}; clean negative controls calibrated but excluded from the schedule."),
    )
    print("FREEZE", manifest["freeze_id"])


def cmd_freeze_main(args):
    kept = [tuple(t) for t in read_json(Path(args.kept))]
    if not kept:
        raise ValueError("kept task list is empty: calibration kept nothing in the 0.2-0.8 band")
    if args.backend == "frontier":
        cfg = main_config_frontier(kept)
        schedule = main_schedule(kept, "repair_ordinary")
        freeze_name = "freeze-claim-a-frontier"
        notes = (f"Freeze claim-a-frontier: Phase B frontier arm for Claim A (v9 design §1). "
                 f"{len(kept)} kept tasks x (1 diagnostic + {REPAIR_REPEATS} ordinary repairs) on "
                 f"{cfg['model']} via the {(cfg.get('provider') or {}).get('name', 'openai')} backend. "
                 f"Matched against freeze-claim-a-local over "
                 f"the same task bank and seed {CLAIM_A_SEED}.")
    elif args.backend == "local":
        cfg = main_config_local(kept, real_smoke_evidence=args.pilot_evidence)
        schedule = main_schedule(kept, "repair_workflow")
        freeze_name = "freeze-claim-a-local"
        notes = (f"Freeze claim-a-local: Phase B local arm for Claim A (v9 design §1). "
                 f"{len(kept)} kept tasks x (1 diagnostic + {REPAIR_REPEATS} full-workflow repairs) on "
                 f"the local backend (model {cfg['model']}). repair_workflow treatment: the frozen "
                 f"six-phase Spec-Kit+AEE workflow (constitution, specify, plan, tasks, implement, "
                 f"converge) with AEE assessment gates, attempt call budget 64 (6 phases x 8 actions "
                 f"+ recovery headroom); zero marginal dollar cost. Matched "
                 f"against freeze-claim-a-frontier over the same task bank and seed {CLAIM_A_SEED}.")
    else:
        raise ValueError(f"unknown backend {args.backend}")
    manifest = build_freeze(
        args.out, args.calibration, cfg, schedule, kept, freeze_name, notes,
        (f"Claim A Phase B kept bank: {len(kept)} tasks in the calibrated 0.2-0.8 frontier "
         f"ordinary pass band, seed {CLAIM_A_SEED}."),
    )
    print("FREEZE", manifest["freeze_id"])


def cmd_freeze_pilot(args):
    kept = [tuple(t) for t in read_json(Path(args.kept))]
    if not kept:
        raise ValueError("kept task list is empty")
    cfg = main_config_local(kept)
    # Pilot is a development smoke: it does not need prior real-smoke evidence.
    cfg.update({"purpose": "development_smoke", "real_smoke_verified": False})
    cfg.pop("real_smoke_evidence", None)
    manifest = build_freeze(
        args.out, args.calibration, cfg, pilot_schedule(kept), [tuple(kept[0])],
        "freeze-claim-a-pilot",
        ("Freeze claim-a-pilot: single-task local-backend smoke for Claim A. Exercises the "
         "full diagnose + Spec-Kit/AEE workflow-repair path against the operator's llama.cpp server "
         "before the main local freeze is built. Free; no spend."),
        "Claim A local pilot: first kept task only, development smoke.",
    )
    print("FREEZE", manifest["freeze_id"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Claim A campaign (v9 design)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("calibrate"); p.add_argument("out", type=Path)
    p = sub.add_parser("freeze-calibration"); p.add_argument("out", type=Path)
    p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-main"); p.add_argument("out", type=Path)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--kept", type=Path, required=True)
    p.add_argument("--backend", choices=("frontier", "local"), required=True)
    p.add_argument("--pilot-evidence", default=None)
    p = sub.add_parser("freeze-pilot"); p.add_argument("out", type=Path)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--kept", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "calibrate":
        cmd_calibrate(args)
    elif args.command == "freeze-calibration":
        cmd_freeze_calibration(args)
    elif args.command == "freeze-main":
        cmd_freeze_main(args)
    elif args.command == "freeze-pilot":
        cmd_freeze_pilot(args)
    else:
        raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
