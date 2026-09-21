#!/usr/bin/env python3
"""Claim A offline analysis: calibration band + main comparison.

No model calls, no spend. Reads the append-only event streams written by the
campaign runs and the grade-run hidden grades.

    analyze_claim_a.py band --run RUN_DIR --out kept.json
        Phase A: per-task frontier ordinary pass rate; keep the 0.2-0.8
        discriminative band (with 2 attempts per task: exactly one passes).

    analyze_claim_a.py compare --frontier RUN_DIR --local RUN_DIR \\
        --kept kept.json
        Phase B: per-task per-arm expected loss, paired difference, percentile
        bootstrap 95% CI, 10%-relative non-inferiority verdict, and dollars
        per accepted task.

Expected loss (v9 measurement design, ratified 2026-09-21): per attempt
    L = 3*P(wrong/harmful) + 1*P(miss) + measured run cost,
where a graded attempt is
    wrong/harmful  if it fails hidden acceptance AND (breaks public tests
                   green on the reference, i.e. regression, OR changed the
                   source without fixing the defect),
    miss           if it fails hidden acceptance without changing the source,
    accepted       if it passes hidden acceptance (loss = run cost only).
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from benchmark_runner.store import Store  # noqa: E402

W_WRONG = 3
W_MISS = 1
NI_MARGIN_REL = 0.10
BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 20260921


def load_grades(run_dir):
    """attempt_id -> hidden grade event (latest per attempt)."""
    store = Store(Path(run_dir))
    grades = {}
    for e in store.events("hidden_grades"):
        grades[e["attempt_id"]] = e
    return grades


def load_attempts(run_dir):
    store = Store(Path(run_dir))
    latest = {}
    for e in store.events("attempts"):
        latest[e["attempt_id"]] = e
    return latest


def load_costs(run_dir):
    """attempt_id -> total measured dollars from the calls stream."""
    store = Store(Path(run_dir))
    costs = defaultdict(Decimal)
    for e in store.events("calls"):
        costs[e["attempt_id"]] += Decimal(str(e.get("cost", "0")))
    return costs


def attempt_outcome(attempt, grade):
    """(class, loss_extra) for one graded repair attempt.

    class in {"accepted", "wrong", "miss"}; loss_extra is the loss weight
    before adding the measured run cost.
    """
    rounds = attempt.get("repair_rounds") or []
    public_ok = bool(rounds) and bool((rounds[-1].get("public") or {}).get("passed"))
    changed = bool(rounds) and bool(rounds[-1].get("source_changed"))
    if grade.get("hidden_passed"):
        return "accepted", 0
    if not public_ok:
        return "wrong", W_WRONG  # regression: broke public tests green on the reference
    if changed:
        return "wrong", W_WRONG  # changed code but did not fix the defect
    return "miss", W_MISS  # did not change the source, defect still present


def cmd_band(args):
    grades = load_grades(args.run)
    attempts = load_attempts(args.run)
    per_task = defaultdict(list)
    for attempt_id, attempt in attempts.items():
        if attempt.get("arm") != "repair_ordinary":
            continue
        if attempt.get("status") != "completed":
            continue
        g = grades.get(attempt_id)
        if not g or not g.get("graded"):
            print(f"WARN: {attempt_id} completed but not graded; excluded", file=sys.stderr)
            continue
        per_task[attempt["task_id"]].append(bool(g["hidden_passed"]))
    kept = []
    rows = []
    for task_id in sorted(per_task):
        outcomes = per_task[task_id]
        rate = sum(outcomes) / len(outcomes)
        keep = 0.2 < rate < 0.8
        rows.append((task_id, f"{sum(outcomes)}/{len(outcomes)}", rate, keep))
        if keep:
            kept.append(task_id)
    print(f"{'task_id':45s} {'pass':8s} {'rate':6s} keep")
    for task_id, frac, rate, keep in rows:
        print(f"{task_id:45s} {frac:8s} {rate:<6.2f} {'YES' if keep else 'no'}")
    print(f"\nkept {len(kept)}/{len(rows)} tasks in the 0.2-0.8 band")
    if len(kept) < 5:
        print("WARN: fewer than 5 kept tasks; the Phase B comparison will have wide CIs",
              file=sys.stderr)
    kept_triples = []
    for task_id in kept:
        # task_id format: mr-<project>-<variant>-<seed>
        rest = task_id[len("mr-"):]
        project, rest = rest.split("-", 1)
        seed = int(rest.rsplit("-", 1)[1])
        variant = rest.rsplit("-", 1)[0]
        kept_triples.append([project, variant, seed])
    Path(args.out).write_text(json.dumps(kept_triples, indent=2) + "\n")
    print(f"wrote {args.out}")


def per_task_losses(run_dir, kept, repair_arm):
    """task_id -> (mean loss, n_attempts, class counts, total cost)."""
    grades = load_grades(run_dir)
    attempts = load_attempts(run_dir)
    costs = load_costs(run_dir)
    kept_set = set(kept)
    per_task = defaultdict(list)
    for attempt_id, attempt in attempts.items():
        if attempt.get("task_id") not in kept_set:
            continue
        if attempt.get("arm") != repair_arm:
            continue
        if attempt.get("status") != "completed":
            continue
        g = grades.get(attempt_id)
        if not g or not g.get("graded"):
            print(f"WARN: {attempt_id} completed but not graded; excluded", file=sys.stderr)
            continue
        cls, extra = attempt_outcome(attempt, g)
        cost = costs.get(attempt_id, Decimal("0"))
        per_task[attempt["task_id"]].append((extra + float(cost), cls, float(cost)))
    summary = {}
    for task_id, rows in per_task.items():
        losses = [r[0] for r in rows]
        counts = defaultdict(int)
        for _, cls, _ in rows:
            counts[cls] += 1
        summary[task_id] = {
            "mean_loss": sum(losses) / len(losses),
            "n": len(rows),
            "counts": dict(counts),
            "total_cost": sum(r[2] for r in rows),
        }
    return summary


def bootstrap_ci(diffs, b=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, alpha=0.05):
    rng = random.Random(seed)
    n = len(diffs)
    stats = []
    for _ in range(b):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        stats.append(sum(sample) / n)
    stats.sort()
    lo = stats[int((alpha / 2) * b)]
    hi = stats[int((1 - alpha / 2) * b) - 1]
    return lo, hi


def cmd_compare(args):
    kept = ["mr-" + "-".join([t[0], t[1], str(t[2])]) for t in json.loads(Path(args.kept).read_text())]
    frontier = per_task_losses(args.frontier, kept, "repair_ordinary")
    local = per_task_losses(args.local, kept, "repair_workflow")
    common = sorted(set(frontier) & set(local))
    missing = sorted(set(kept) - set(common))
    for t in missing:
        print(f"WARN: {t} missing a graded arm in one run; excluded from pairing",
              file=sys.stderr)
    if len(common) < 5:
        print(f"WARN: only {len(common)} paired tasks; CIs will be wide", file=sys.stderr)
    if not common:
        raise SystemExit("no paired tasks: nothing to compare")

    diffs = [local[t]["mean_loss"] - frontier[t]["mean_loss"] for t in common]
    mean_f = sum(frontier[t]["mean_loss"] for t in common) / len(common)
    mean_l = sum(local[t]["mean_loss"] for t in common) / len(common)
    mean_diff = sum(diffs) / len(diffs)
    lo, hi = bootstrap_ci(diffs)
    margin = NI_MARGIN_REL * mean_f
    non_inferior = hi < margin

    acc_local = sum(local[t]["counts"].get("accepted", 0) for t in common)
    n_local = sum(local[t]["n"] for t in common)
    acc_front = sum(frontier[t]["counts"].get("accepted", 0) for t in common)
    n_front = sum(frontier[t]["n"] for t in common)
    cost_front = sum(frontier[t]["total_cost"] for t in common)
    cost_local = sum(local[t]["total_cost"] for t in common)

    print(f"{'task_id':45s} {'frontier':>9s} {'local':>9s} {'diff':>9s}")
    for t in common:
        print(f"{t:45s} {frontier[t]['mean_loss']:9.4f} {local[t]['mean_loss']:9.4f} "
              f"{local[t]['mean_loss'] - frontier[t]['mean_loss']:9.4f}")
    print()
    print(f"paired tasks:            {len(common)}")
    print(f"mean expected loss:      frontier {mean_f:.4f}   local {mean_l:.4f}")
    print(f"paired diff (local-frontier): {mean_diff:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"non-inferiority margin:  10% relative = {margin:.4f}")
    print(f"verdict:                 {'NON-INFERIOR' if non_inferior else 'NOT non-inferior'} "
          f"(CI upper {hi:+.4f} {'<' if non_inferior else '>='} margin {margin:.4f})")
    print()
    print(f"acceptance:              frontier {acc_front}/{n_front}   local {acc_local}/{n_local}")
    print(f"total measured cost:     frontier ${cost_front:.4f}   local ${cost_local:.4f}")
    dpa_f = cost_front / acc_front if acc_front else float("inf")
    dpa_l = cost_local / acc_local if acc_local else float("inf")
    print(f"dollars per accepted:    frontier ${dpa_f:.4f}   local ${dpa_l:.4f}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Claim A offline analysis (v9 design)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("band", help="Phase A: discriminative band selection")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("compare", help="Phase B: local vs frontier comparison")
    p.add_argument("--frontier", type=Path, required=True)
    p.add_argument("--local", type=Path, required=True)
    p.add_argument("--kept", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "band":
        cmd_band(args)
    elif args.command == "compare":
        cmd_compare(args)
    else:
        raise ValueError(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
