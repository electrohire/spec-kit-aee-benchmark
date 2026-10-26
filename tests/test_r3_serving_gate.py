"""R-3 (Benchmarking Improvement Program, 2026-10-25):
serving identity is a gate in code, not a checklist.

Stubbed-server drills: the fingerprint is a dict of the kind
a driver assembles from the server itself (router read-back
plus the loaded model's file identity). A wrong weights
hash, a wrong context size, or grammar flipped on must each
refuse admission and record the refusal; the matching
fingerprint must admit. Refusal is at zero scored spend by
construction — the gate runs before any call exists.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.preflight import PAIR_D_RECIPE, verify_serving


def matching():
    return dict(PAIR_D_RECIPE)


def test_matching_fingerprint_admits():
    out = verify_serving(matching(), PAIR_D_RECIPE)
    assert out["admitted"]
    assert all(out["checks"].values())


def test_wrong_weights_hash_refuses():
    fp = matching()
    fp["weights_sha256"] = "0" * 64
    out = verify_serving(fp, PAIR_D_RECIPE)
    assert not out["admitted"]
    assert out["checks"]["weights_sha256"] is False
    # The refusal record names the field that failed.
    assert out["fingerprint"]["weights_sha256"] == "0" * 64


def test_wrong_context_refuses():
    fp = matching()
    fp["context_size"] = 131072  # the incumbent's context
    out = verify_serving(fp, PAIR_D_RECIPE)
    assert not out["admitted"]
    assert out["checks"]["context_size"] is False


def test_grammar_on_refuses():
    fp = matching()
    fp["grammar"] = True
    out = verify_serving(fp, PAIR_D_RECIPE)
    assert not out["admitted"]
    assert out["checks"]["grammar"] is False


def test_wire_cap_drift_refuses():
    fp = matching()
    fp["max_input_tokens"] = 65536
    out = verify_serving(fp, PAIR_D_RECIPE)
    assert not out["admitted"]
    assert out["checks"]["max_input_tokens"] is False


def test_missing_field_refuses():
    fp = matching()
    del fp["preserve_thinking"]
    out = verify_serving(fp, PAIR_D_RECIPE)
    assert not out["admitted"]
