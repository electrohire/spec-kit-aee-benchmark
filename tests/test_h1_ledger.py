"""H-1 + H-4 (Benchmarking Improvement Program, 2026-10-25):
one ledger, continuous across campaigns, with cost per
resolved outcome entered at every close.

The founding artifact (benchmarks/program-ledger.jsonl) must
carry the recorded chain exactly — 23,237,750 → 52,654,187 →
53,954,521 → 54,717,194 → 54,947,139 → 56,952,934 — verify
its hash chain and continuity, and reproduce §2's founding
metric figures, including "undefined" for Stage B's workflow
path (zero deliveries). A doctored opening must be refused,
in admission and in append alike; a campaign close without
its metric entry must be flagged by the audit.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.ledger import (
    admit_opening, append_close, metric_audit, read_entries,
    verify_ledger)

LEDGER = (Path(__file__).parents[1] / "benchmarks"
          / "program-ledger.jsonl")
CHAIN = [23237750, 52654187, 53954521, 54717194, 54947139,
         56952934]


def test_founding_chain_is_exact_and_verifies():
    state = verify_ledger(LEDGER)
    assert state["ok"], state["problems"]
    assert state["entries"] == 6
    assert state["last_close"] == 56952934
    entries = read_entries(LEDGER)
    assert [e["close"] for e in entries] == CHAIN
    assert entries[0]["opening"] == 0


def test_founding_metrics_reproduce_section_2():
    entries = read_entries(LEDGER)
    stage_b = entries[1]["metrics"]
    assert stage_b["workflow_cost_per_resolved"] == "undefined"
    assert stage_b["workflow_deliveries"] == 0
    assert stage_b["stage_b_legs_tokens"] == {
        "candidate": 8237868, "baseline": 9180472}
    probe = entries[4]["metrics"]
    assert probe["attempt_cost"] == 229945
    assert probe["workflow_cost_per_resolved"] == "undefined"
    pooled = entries[5]["metrics"]
    assert pooled["probe_cost_per_resolved"] == {
        "protocol_off": 537987, "protocol_on": 367891}


def test_metric_audit_passes_the_founding_artifact():
    assert metric_audit(LEDGER)["ok"]


def test_doctored_opening_is_refused(tmp_path):
    copy = tmp_path / "ledger.jsonl"
    copy.write_text(LEDGER.read_text())
    assert not admit_opening(copy, 56952934 - 1)["admitted"]
    assert admit_opening(copy, 56952934)["admitted"]
    out = append_close(copy, "doctored campaign", 1, 100,
                       {"x_cost_per_resolved": 5}, "drill")
    assert not out["appended"]
    # Nothing was written by the refusal.
    assert len(read_entries(copy)) == 6


def test_close_appends_with_metrics_and_verifies(tmp_path):
    copy = tmp_path / "ledger.jsonl"
    copy.write_text(LEDGER.read_text())
    out = append_close(
        copy, "drill campaign", 56952934, 12345,
        {"drill_cost_per_resolved": "undefined"}, "test drill")
    assert out["appended"]
    state = verify_ledger(copy)
    assert state["ok"] and state["last_close"] == 56952934 + 12345
    assert metric_audit(copy)["ok"]


def test_close_without_metrics_is_flagged(tmp_path):
    copy = tmp_path / "ledger.jsonl"
    copy.write_text(LEDGER.read_text())
    out = append_close(copy, "bare campaign", 56952934, 10,
                       {}, "test drill")
    assert out["appended"]
    audit = metric_audit(copy)
    assert not audit["ok"]
    assert audit["findings"][0]["kind"] == "missing_metrics"


def test_tampered_entry_breaks_verification(tmp_path):
    copy = tmp_path / "ledger.jsonl"
    lines = LEDGER.read_text().splitlines()
    entry = json.loads(lines[2])
    entry["spend"] += 1
    lines[2] = json.dumps(entry, sort_keys=True)
    copy.write_text("\n".join(lines) + "\n")
    state = verify_ledger(copy)
    assert not state["ok"]
