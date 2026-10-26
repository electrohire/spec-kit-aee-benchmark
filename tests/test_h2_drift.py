"""H-2 (Benchmarking Improvement Program, 2026-10-25):
drift is a frozen test, not a surprise.

The baselines pinned in Phase 0, checked against the live
tree: the constitution template's hash (template-identical
content was 50.7% of an era's traffic — its drift is a cost
event), the filled constitution, the scaffold/prompt texts,
and the engine version floor. The drills prove the checks
can fail: a single byte changed in a copy of any pinned file
must be caught, and an engine below the floor must be caught.
Choosing new baselines is a registration act, never a silent
edit of this file's pins.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.preflight import PAIR_D_RECIPE

ROOT = Path(__file__).parents[1]

# Phase 0 pins (SHA-256), captured 2026-10-25.
PINNED_FILES = {
    ".specify/templates/constitution-template.md":
        "ce7549540fa45543cca797a150201d868e64495fdff39dc38246fb"
        "17bd4024b3",
    ".specify/memory/constitution.md":
        "cb17878b51bf26b5ad7e025d11c1d1c7e2ad7ba0324fc1e058607"
        "ab41a4920d4",
    "prompts/common.md":
        "403aeba91aa2328bb2a37718d4dc4d8fb158ead984e04c656ebe5"
        "91cbbee0d4d",
    "prompts/adapter.md":
        "a3f2bab949867884b1bb309359120905e803c7a3d34486b4951042"
        "ff28cc4c0f",
    "prompts/probe-solve.md":
        "55d0bc892ca1fe52877a3a080ce550b9d4d7df7c6d20f7e3ec6484"
        "7d0d4b4c4e",
}

ENGINE_VERSION_FLOOR = (1, 6, 0)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def drifted(path):
    """Files under root whose hash differs from their pin."""
    return [rel for rel, want in PINNED_FILES.items()
            if sha256(Path(path) / rel) != want]


def version_below_floor(version_text):
    parts = tuple(int(p) for p in
                  version_text.split("-")[0].split(".")[:3])
    return parts < ENGINE_VERSION_FLOOR


def test_pinned_files_match_the_live_tree():
    assert drifted(ROOT) == []


def test_drill_one_byte_of_drift_is_caught(tmp_path):
    for rel in PINNED_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (ROOT / rel).read_bytes()
        target.write_bytes(data + b" ")
    assert sorted(drifted(tmp_path)) == sorted(PINNED_FILES)


def test_serving_fingerprint_pin_is_the_frozen_recipe():
    # The R-3 recipe is the drift pin for serving identity:
    # Pair D, Stage A (re-checked here so a silent edit of the
    # table itself is a visible test change, not drift).
    assert PAIR_D_RECIPE["weights_sha256"] == (
        "8601193d3d5760c37fb8ce1b43afebc69df5fb24e1fbc5a547"
        "c32e2200305276")
    assert PAIR_D_RECIPE["context_size"] == 65536
    assert PAIR_D_RECIPE["max_input_tokens"] == 57344
    assert PAIR_D_RECIPE["max_output_tokens"] == 8192
    assert PAIR_D_RECIPE["preserve_thinking"] is True
    assert PAIR_D_RECIPE["grammar"] is False


def test_engine_version_floor():
    import importlib.metadata as md
    try:
        installed = md.version("aee")
    except md.PackageNotFoundError:
        installed = None
    if installed is not None:
        assert not version_below_floor(installed), installed
    # The drill half always runs: below-floor is caught,
    # at/above floor passes.
    assert version_below_floor("1.5.3")
    assert not version_below_floor("1.6.0")
    assert not version_below_floor("1.7.2")
