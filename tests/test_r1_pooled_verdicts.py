"""R-1 (Benchmarking Improvement Program, 2026-10-25):
pooled multi-seed verdicts are the only verdicts.

Calibration against the probe test's recorded record
(fixtures extracted from the authoritative stores and grade
records on the desktop, cross-checked at extraction: grade
tokens equal store recomputation for all 24 attempts, pooled
aggregates exact):

- the seed-1-only record must emit "single-seed: no verdict"
  and reproduce seed 1's cells as data;
- the pooled record must emit the recorded verdict exactly —
  before 537,987 per resolved (2,151,947 / 4), after 367,891
  (1,839,457 / 5), PASS — with the three recorded flips named
  with their directions, and a variance statement.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.verdicts import pooled_verdict

FIXTURE = (Path(__file__).parent / "fixtures" / "phase3"
           / "pooled_record.json")


def record():
    return json.loads(FIXTURE.read_text())


def test_seed1_only_refuses_a_verdict():
    rec = record()
    seed1 = {"campaign": rec["campaign"],
             "attempts": [a for a in rec["attempts"]
                          if a["seed"] == 1]}
    out = pooled_verdict(seed1, treatment="after",
                         control="before")
    assert out["verdict"] is None
    assert out["status"] == "single-seed: no verdict"
    assert out["pooled"] is None
    # Seed 1's cells, reproduced as data (the record: before
    # resolved 3, after resolved 2 on seed 1).
    cells = out["per_seed_cells"]["1"]
    assert cells["before"]["resolved"] == 3
    assert cells["after"]["resolved"] == 2
    assert cells["before"]["tokens"] == 1130500
    assert cells["after"]["tokens"] == 890295


def test_pooled_record_reproduces_the_recorded_verdict():
    out = pooled_verdict(record(), treatment="after",
                         control="before")
    assert out["verdict"] == "PASS"
    assert out["status"] == "pooled verdict"
    pooled = out["pooled"]
    assert pooled["before"]["tokens"] == 2151947
    assert pooled["before"]["resolved"] == 4
    assert pooled["before"]["tokens_per_resolved"] == 537987
    assert pooled["after"]["tokens"] == 1839457
    assert pooled["after"]["resolved"] == 5
    assert pooled["after"]["tokens_per_resolved"] == 367891
    # Per-seed cells reported together with the pooled cell.
    cells = out["per_seed_cells"]
    assert cells["2"]["before"]["resolved"] == 1
    assert cells["2"]["after"]["resolved"] == 3
    # The three recorded flips, named with direction.
    flips = {(f["task"], f["arm"]): f for f in out["flips"]}
    assert set(flips) == {
        ("django__django-11099", "before"),
        ("django__django-16661", "before"),
        ("django__django-16642", "after")}
    assert "not resolved in seed 2" in \
        flips[("django__django-11099", "before")]["direction"]
    assert "not resolved in seed 2" in \
        flips[("django__django-16661", "before")]["direction"]
    assert "resolved in seed 2" in \
        flips[("django__django-16642", "after")]["direction"]
    # Variance is stated, not implied.
    var = out["variance"]
    assert var["before"]["resolved_by_seed"] == {"1": 3, "2": 1}
    assert var["after"]["resolved_by_seed"] == {"1": 2, "2": 3}
    assert var["before"]["resolved_range"] == [1, 3]


def test_a_record_that_fails_the_rule_fails():
    rec = record()
    out = pooled_verdict(rec, treatment="before",
                         control="after")
    assert out["verdict"] == "FAIL"
