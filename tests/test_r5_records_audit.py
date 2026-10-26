"""R-5 (Benchmarking Improvement Program, 2026-10-25):
records are append-only, single-authority, and hash-verified
in transit — audited by machinery.

Calibration fixtures are the probe test's actual records:
the leg-1 controls record (gold 6 + empty 6 rows, all
passing), the empty-control summary as snapshotted after it
was overwritten in place by a later leg's 2-instance eval
(the known incident — the audit must DETECT it, naming the
four missing instances), the restored empty summary now on
disk (clean), and the gold summary (clean).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.records_audit import (
    audit_controls, recompute_attempt_tokens, verify_transfer)

FIX = Path(__file__).parent / "fixtures" / "phase3" / "r5"


def load(name):
    return json.loads((FIX / name).read_text())


def test_overwritten_empty_summary_is_detected():
    out = audit_controls(
        load("controls-probetest.json"),
        {"empty": load("empty-summary-overwritten.json")})
    assert not out["clean"]
    incidents = [i for i in out["incidents"]
                 if i["kind"] == "summary_coverage_mismatch"]
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["variant"] == "empty"
    assert inc["summary_ids"] == ["django__django-16642",
                                  "django__django-16661"]
    assert inc["missing_from_summary"] == [
        "django__django-11099", "django__django-11740",
        "pydata__xarray-3305", "pytest-dev__pytest-5809"]


def test_clean_ranges_pass():
    controls = load("controls-probetest.json")
    gold = audit_controls(controls,
                          {"gold": load("gold-summary.json")})
    assert gold["clean"], gold["incidents"]
    current = audit_controls(
        controls, {"empty": load("empty-summary-current.json")})
    assert current["clean"], current["incidents"]


def test_transfer_verification_both_ends(tmp_path):
    payload = tmp_path / "tool.py"
    payload.write_text("print('x')\n")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    ok = verify_transfer({"tool.py": digest}, tmp_path)
    assert ok["verified"]
    payload.write_text("print('tampered')\n")
    bad = verify_transfer({"tool.py": digest}, tmp_path)
    assert not bad["verified"]
    missing = verify_transfer({"nope.py": digest}, tmp_path)
    assert not missing["verified"]


def test_figures_recompute_from_the_store(tmp_path):
    # A minimal store whose calls sum to a known figure; the
    # audit's recomputation must find exactly that figure
    # (status channels are never evidence).
    store = tmp_path / "store"
    store.mkdir()
    rows = [{"input_tokens": 100, "output_tokens": 5},
            {"input_tokens": 250, "output_tokens": 10}]
    (store / "calls.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    out = recompute_attempt_tokens(store)
    assert out == {"tokens": 365, "unknown_usage_calls": 0}
