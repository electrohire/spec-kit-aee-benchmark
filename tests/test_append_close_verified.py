"""Verified-append equivalence + fault proof for the program
ledger's ``append_close`` (fleet verified-writes standard,
2026-10-28; transplanted from the staged needle-modeling
package after the Window 6 close-out).

Proves, against fixture ledgers built in temp dirs:
1. A close sequence written through the current (verified)
   ``append_close`` is BYTE-IDENTICAL to the same sequence
   written through a faithful copy of the pre-transplant
   bare-write implementation embedded below.
2. Refusals (invalid ledger, opening mismatch) return the
   legacy implementation's exact dicts and write nothing.
3. A torn append (simulated by truncating the landed bytes
   mid-write via a patched opener) raises RuntimeError and
   rolls the ledger back to its pre-append bytes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner import ledger
from benchmark_runner.ledger import append_close, verify_ledger


def _legacy_append_close(path, campaign, opening, spend, metrics,
                         source):
    """The pre-transplant append_close, verbatim in behavior:
    same refusal dicts and entry construction, bare
    ``open("a")`` write with no fsync and no read-back."""
    state = verify_ledger(path)
    if not state["ok"]:
        return {"appended": False, "reason": "ledger_invalid",
                "problems": state["problems"]}
    if opening != state["last_close"]:
        return {"appended": False,
                "reason": "opening_differs_from_last_close",
                "ledger_last_close": state["last_close"]}
    entries = ledger.read_entries(path)
    entry = {"seq": len(entries) + 1, "kind": "campaign_close",
             "campaign": campaign, "opening": opening,
             "spend": spend, "close": opening + spend,
             "metrics": metrics, "source": source,
             "prev": entries[-1]["hash"] if entries
             else ledger.GENESIS}
    entry["hash"] = ledger._hash(entry)
    with Path(path).open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return {"appended": True, "entry": entry}


METRICS = {"arm_cost_per_resolved": {"champion": 100.5,
                                     "router": "undefined"}}
CLOSES = [
    ("window-a", 1_000, 250),
    ("window-b", 1_250, 500),
    ("window-c", 1_750, 125),
]


def _seed(path: Path) -> None:
    genesis = {
        "seq": 1,
        "kind": "founding",
        "campaign": "founding",
        "opening": 0,
        "spend": 1_000,
        "close": 1_000,
        "metrics": {},
        "source": "fixture",
        "prev": ledger.GENESIS,
    }
    genesis["hash"] = ledger._hash(genesis)
    path.write_text(json.dumps(genesis, sort_keys=True) + "\n",
                    encoding="utf-8")


def _run_sequence(module_append, path: Path) -> list[dict]:
    _seed(path)
    results = []
    opening = 1_000
    for campaign, expected_opening, spend in CLOSES:
        assert opening == expected_opening
        results.append(
            module_append(path, campaign, opening, spend,
                          METRICS, "fixture")
        )
        opening += spend
    return results


def test_byte_identical_to_legacy(tmp_path):
    legacy_path = tmp_path / "legacy.jsonl"
    verified_path = tmp_path / "verified.jsonl"
    legacy_results = _run_sequence(_legacy_append_close,
                                   legacy_path)
    verified_results = _run_sequence(append_close, verified_path)
    assert all(r["appended"] for r in verified_results)
    assert verified_results == legacy_results
    assert verified_path.read_bytes() == legacy_path.read_bytes()
    assert verify_ledger(verified_path)["ok"]


def test_refusals_match_legacy_and_write_nothing(tmp_path):
    for impl in (_legacy_append_close, append_close):
        path = tmp_path / f"ledger-{impl.__name__}.jsonl"
        _seed(path)
        before = path.read_bytes()
        refusal = impl(path, "window-x", 999_999, 1, METRICS,
                       "fixture")
        assert refusal["appended"] is False
        assert refusal["reason"] == \
            "opening_differs_from_last_close"
        assert refusal["ledger_last_close"] == 1_000
        assert path.read_bytes() == before


def test_torn_append_raises_and_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "ledger.jsonl"
    _seed(path)
    before = path.read_bytes()

    real_open = Path.open

    class TornFile:
        def __init__(self, handle):
            self._handle = handle

        def write(self, data):
            return self._handle.write(data[: len(data) // 2])

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._handle.__exit__(*exc)

    def torn_open(self, mode="r", *args, **kwargs):
        handle = real_open(self, mode, *args, **kwargs)
        if self == path and "a" in mode:
            return TornFile(handle)
        return handle

    monkeypatch.setattr(Path, "open", torn_open)
    try:
        append_close(path, "window-a", 1_000, 250, METRICS,
                     "fixture")
        raised = False
    except RuntimeError:
        raised = True
    finally:
        monkeypatch.undo()
    assert raised
    assert path.read_bytes() == before
    assert verify_ledger(path)["ok"]
