"""Pooled-only verdicts (Benchmarking Improvement Program R-1,
2026-10-25).

The probe test taught the program, at full price, that a
single seed's verdict at small n is noise: on the identical
instrument the two seeds' verdicts disagreed, and only the
pooled record settled the claim. This module is that lesson as
machinery. It emits a verdict ONLY from a pooled design:

- at least two independent seeds;
- per-seed cells and the pooled cell reported together;
- outcome flips between seeds named, with their direction;
- a variance statement (the per-seed spread) attached to
  every verdict.

A single-seed record is reported as data with the explicit
status "single-seed: no verdict" — the tooling refuses to
call it anything else.

The verdict rule is the campaign's registered pooling rule,
named in the record. The one rule implemented here is the
probe test's pre-committed form, generalized to any two-arm
record: the treatment arm passes when its pooled cost per
resolved outcome is strictly lower than the control arm's
AND its pooled resolved count is at least the control's
(non-inferior function at lower cost — the program objective).
"""
import json


def _cell(attempts):
    tokens = sum(a["tokens"] for a in attempts)
    resolved = sum(1 for a in attempts if a["resolved"])
    return {"attempts": len(attempts), "tokens": tokens,
            "resolved": resolved,
            "tokens_per_resolved": (tokens / resolved
                                    if resolved else None)}


def _rounded(cell):
    out = dict(cell)
    tpr = cell["tokens_per_resolved"]
    out["tokens_per_resolved"] = (round(tpr) if tpr is not None
                                  else None)
    return out


def pooled_verdict(record, treatment, control):
    """Emit the pooled verdict for one two-arm campaign record.

    record: {"campaign": str, "attempts": [{"seed", "task",
    "arm", "tokens", "resolved"}, ...]}. Returns the verdict
    artifact as a dict; see the module docstring for the
    single-seed refusal form."""
    attempts = record["attempts"]
    seeds = sorted({a["seed"] for a in attempts})
    arms = sorted({a["arm"] for a in attempts})
    cells = {}
    for seed in seeds:
        cells[str(seed)] = {
            arm: _rounded(_cell([a for a in attempts
                                 if a["seed"] == seed
                                 and a["arm"] == arm]))
            for arm in arms}
    if len(seeds) < 2:
        return {"campaign": record.get("campaign"),
                "verdict": None,
                "status": "single-seed: no verdict",
                "seeds": seeds,
                "per_seed_cells": cells,
                "pooled": None,
                "flips": [],
                "variance": None}
    pooled = {arm: _rounded(_cell([a for a in attempts
                                   if a["arm"] == arm]))
              for arm in arms}
    # Flips: a (task, arm) whose resolved status differs
    # between any two seeds, named with direction relative to
    # the first and last seed.
    flips = []
    keys = sorted({(a["task"], a["arm"]) for a in attempts})
    for task, arm in keys:
        by_seed = {}
        for seed in seeds:
            rows = [a for a in attempts
                    if a["seed"] == seed and a["task"] == task
                    and a["arm"] == arm]
            if rows:
                by_seed[seed] = bool(rows[0]["resolved"])
        if len(set(by_seed.values())) > 1:
            first, last = seeds[0], seeds[-1]
            flips.append({
                "task": task, "arm": arm,
                "per_seed_resolved": {str(s): by_seed[s]
                                      for s in by_seed},
                "direction": ("resolved in seed "
                              f"{first}, not resolved in seed "
                              f"{last}"
                              if by_seed[first]
                              else f"not resolved in seed {first}, "
                                   f"resolved in seed {last}")})
    # Variance statement: per-seed resolved counts and cost
    # per resolved, per arm — the spread a reader needs to see
    # how much of the pooled figure is one seed's luck.
    variance = {}
    for arm in arms:
        per_seed = cells
        variance[arm] = {
            "resolved_by_seed": {
                s: cells[s][arm]["resolved"] for s in cells},
            "tokens_per_resolved_by_seed": {
                s: cells[s][arm]["tokens_per_resolved"]
                for s in cells},
            "resolved_range": [
                min(cells[s][arm]["resolved"] for s in cells),
                max(cells[s][arm]["resolved"] for s in cells)]}
    t, c = pooled[treatment], pooled[control]
    passed = (t["tokens_per_resolved"] is not None
              and c["tokens_per_resolved"] is not None
              and t["tokens_per_resolved"]
              < c["tokens_per_resolved"]
              and t["resolved"] >= c["resolved"])
    return {"campaign": record.get("campaign"),
            "verdict": "PASS" if passed else "FAIL",
            "status": "pooled verdict",
            "rule": "treatment pooled cost per resolved strictly "
                    "lower than control AND treatment pooled "
                    "resolved >= control resolved",
            "treatment": treatment, "control": control,
            "seeds": seeds,
            "per_seed_cells": cells,
            "pooled": pooled,
            "flips": flips,
            "variance": variance}


def verdict_json(record, treatment, control):
    return json.dumps(pooled_verdict(record, treatment, control),
                      indent=1, sort_keys=True)
