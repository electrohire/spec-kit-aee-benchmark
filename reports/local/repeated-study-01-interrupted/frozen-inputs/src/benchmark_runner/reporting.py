"""All-attempt economics and paired task-cluster bootstrap, without imputation."""
import random
import statistics
from decimal import Decimal

from .accounting import TOKEN_FIELDS, unique_calls
from .experiment import ARMS
from .store import read_json


def ratio(n, d):
    return None if d == 0 or n is None else float(n/d)


def metrics(rows):
    n = len(rows)
    resolved = sum(r.get("resolved") is True for r in rows)
    costs = [r.get("cost") for r in rows]
    total = None if any(c is None for c in costs) else sum(costs, Decimal(0))
    durations = sorted(r["duration_seconds"] for r in rows if r.get("duration_seconds") is not None)
    return dict(attempts=n, resolved=resolved, resolved_rate=ratio(resolved, n),
                unknown_grades=sum(r.get("resolved") is None for r in rows),
                total_cost=float(total) if total is not None else None,
                cost_per_attempt=ratio(total, n), cost_per_resolved=ratio(total, resolved),
                cost_per_resolved_reason="no resolutions" if not resolved else ("unknown cost" if total is None else None),
                limit_hit_rate=ratio(sum(r.get("status") == "limit" for r in rows), n),
                repair_count=sum(r.get("repair_count", 0) for r in rows),
                tool_calls=sum(r.get("tool_calls", 0) for r in rows),
                latency_median=statistics.median(durations) if durations else None,
                latency_p95=durations[min(len(durations)-1, int(.95*len(durations)))] if durations else None,
                tokens={k: None if any(r[k] is None for r in rows) else sum(r[k] for r in rows) for k in TOKEN_FIELDS},
                false_acceptances=sum(r.get("assessment_outcome") in ("pass", "warn") and r.get("resolved") is False for r in rows),
                unnecessary_blocks=sum(r.get("assessment_outcome") not in (None, "pass", "warn") and r.get("resolved") is True for r in rows))


def difference(a, b):
    absolute = None if a is None or b is None else a-b
    return dict(absolute=absolute, percent=None if absolute is None or b == 0 else 100*absolute/b)


def paired_bootstrap(rows, left, right, samples=2000, seed=20260917):
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task_id"], {}).setdefault(row["arm"], []).append(row)
    # Pair complete repetition sets only; publish excluded task count, never hide it.
    paired = {t: arms for t, arms in by_task.items() if left in arms and right in arms
              and {r["repeat"] for r in arms[left]} == {r["repeat"] for r in arms[right]}}
    keys = sorted(paired)
    fields = ("resolved_rate", "total_cost", "cost_per_attempt", "cost_per_resolved")
    result = {"paired_tasks": len(keys), "excluded_tasks": len(by_task)-len(keys), "samples": samples}
    if not keys:
        return {**result, "intervals": None}
    rng, draws = random.Random(seed), {f: [] for f in fields}
    for _ in range(samples):
        sampled = rng.choices(keys, k=len(keys))
        lm = metrics([r for t in sampled for r in paired[t][left]])
        rm = metrics([r for t in sampled for r in paired[t][right]])
        for field in fields:
            if lm[field] is not None and rm[field] is not None:
                draws[field].append(lm[field]-rm[field])
    result["intervals"] = {}
    for field, values in draws.items():
        values.sort()
        result["intervals"][field] = {"low": values[int(.025*len(values))] if values else None,
                                      "high": values[min(len(values)-1, int(.975*len(values)))] if values else None,
                                      "defined_samples": len(values)}
    return result


def aggregate(store, *, synthetic=False):
    latest = {r["attempt_id"]: r for r in store.events("attempts")}
    grades = {}
    for grade in store.events("grades"):
        if grade["attempt_id"] in grades and grades[grade["attempt_id"]] != grade:
            raise ValueError("multiple differing grades; select an explicit analysis version")
        grades[grade["attempt_id"]] = grade
    calls = unique_calls(store.events("calls"))
    reservations = {e["call_id"]: e for e in store.events("budget")}
    rows = []
    for attempt in latest.values():
        usage = [c for c in calls if c["attempt_id"] == attempt["attempt_id"]]
        # No calls means measured zero model usage for a failed pre-call attempt.
        totals = {k: None if any(c[k] is None for c in usage) else sum(c[k] for c in usage) for k in TOKEN_FIELDS}
        charge = None if any(c["cost"] is None for c in usage) else sum((Decimal(c["cost"]) for c in usage), Decimal(0))
        if any(e["attempt_id"] == attempt["attempt_id"] and e["status"] == "reserved" for e in reservations.values()):
            charge = None
            totals = dict.fromkeys(TOKEN_FIELDS, None)
        rows.append({**attempt, **totals, "cost": charge,
                     "resolved": grades.get(attempt["attempt_id"], {}).get("resolved")})
    arms = {arm: metrics([r for r in rows if r["arm"] == arm]) for arm in ARMS}
    comparisons = {}
    for a, b in (("spec_kit", "baseline"), ("spec_kit_aee", "baseline"), ("spec_kit_aee", "spec_kit")):
        comparisons[f"{a}_vs_{b}"] = {"differences": {k: difference(arms[a][k], arms[b][k])
            for k in ("resolved_rate", "total_cost", "cost_per_attempt", "cost_per_resolved")},
            "task_cluster_bootstrap": paired_bootstrap(rows, a, b)}
    frozen = read_json(store.root/"freeze.json") if (store.root/"freeze.json").exists() else None
    unattempted = [s["attempt_id"] for s in frozen["schedule"] if s["attempt_id"] not in latest] if frozen else []
    return {"status": "synthetic_fixture" if synthetic else ("not_run" if not rows else "observed"),
            "unattempted_ids": unattempted, "unattempted_count": len(unattempted),
            "cost_basis": "list_price_estimate", "currency": "USD", "arms": arms,
            "comparisons": comparisons, "setup_cost": None,
            "setup_cost_reason": "controller session usage and human time not attributable",
            "amortized_cost": None, "amortized_cost_reason": "requires measured setup cost and declared reuse count"}


def article_table(report):
    lines = [f"Status: **{report['status']}**", "", "| Arm | Attempts | Resolved | Cost (USD estimate) | Cost / resolved |",
             "|---|---:|---:|---:|---:|"]
    def show(x):
        return "undefined" if x is None else str(round(x, 6)) if isinstance(x, float) else str(x)
    for arm, m in report["arms"].items():
        lines.append(f"| {arm} | {m['attempts']} | {m['resolved']} | {show(m['total_cost'])} | {show(m['cost_per_resolved'])} |")
    return "\n".join(lines)+"\n"
