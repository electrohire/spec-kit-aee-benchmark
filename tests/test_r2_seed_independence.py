"""R-2 (Benchmarking Improvement Program, 2026-10-25): seed
independence is proven before spend, by machinery.

Two halves, both calibrated on the probe test's recorded
proof:

- Empirical: over the two existing probe-test seeds' stores
  (the fixtures carry each store's verbatim first call
  record), all 12 (arm, task) pairs must show byte-identical
  call-1 requests and different call-1 responses — the
  recorded 12/12.
- Code-level: the module that builds the provider payload
  (local_provider.py) contains no seed reference at all —
  the seed is a campaign label stamped into manifests, never
  a sampler input. A doctored source that consumes a seed
  must be caught.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.preflight import (
    seed_independence_empirical, seed_references)

ROOT = Path(__file__).parents[1]
CALL1 = ROOT / "tests" / "fixtures" / "phase3" / "call1"


def fixture_stores():
    stores = {}
    for seed_dir in sorted(CALL1.iterdir()):
        seed = int(seed_dir.name.replace("seed", ""))
        stores[seed] = {}
        for f in sorted(seed_dir.iterdir()):
            arm, task = f.name[:-6].split("--", 1)
            stores[seed][(arm, task)] = f
    return stores


def test_empirical_proof_reproduces_the_recorded_12_of_12():
    proof = seed_independence_empirical(fixture_stores())
    assert proof["pairs_checked"] == 12
    assert proof["ok"]
    assert all(p["request_identical"] for p in proof["pairs"])
    assert all(p["response_differs"] for p in proof["pairs"])


def test_empirical_proof_catches_identical_responses(tmp_path):
    stores = fixture_stores()
    # Doctor seed 2's django-11099 before record to carry seed
    # 1's response hash: the proof must fail on that pair. The
    # doctored copy lives in tmp_path — the fixture tree is
    # read-only evidence and is never written to.
    import json
    path = stores[2][("before", "django__django-11099")]
    rec = json.loads(path.read_text().splitlines()[0])
    seed1 = json.loads(
        stores[1][("before", "django__django-11099")]
        .read_text().splitlines()[0])
    rec["artifacts"]["response"] = \
        seed1["artifacts"]["response"]
    doctored = tmp_path / "doctored.jsonl"
    doctored.write_text(json.dumps(rec) + "\n")
    stores[2][("before", "django__django-11099")] = doctored
    proof = seed_independence_empirical(stores)
    assert not proof["ok"]
    bad = [p for p in proof["pairs"]
           if p["task"] == "django__django-11099"
           and p["arm"] == "before"]
    assert bad and not bad[0]["response_differs"]


def test_code_level_payload_builder_has_no_seed_reference():
    source = (ROOT / "src" / "benchmark_runner"
              / "local_provider.py").read_text()
    assert seed_references(source) == []


def test_code_level_check_catches_a_seed_consumer():
    doctored = ('payload = {"model": m, "seed": 42,\n'
                '           "messages": msgs}\n')
    assert seed_references(doctored)
