"""Verify every committed content-addressed offline object after checkout.

Extended to the event streams (Spec 003 FR-7.1): any committed run store
(attempts/calls/grades/budget JSONL under the evidence roots) has its
hash chains verified, and its grades are counted against the grader-
artifact binding aggregate() enforces. Historical stores predate the
binding, so unbound historical grades are disclosed, not fatal; a
broken chain is fatal everywhere.
"""
from pathlib import Path
import json
from benchmark_runner.store import Store, sha

objects = list(Path("reports/offline").glob("*/objects/*/*"))
objects += list(Path("reports/local").glob("**/objects/*/*"))
for path in objects:
    if sha(path.read_bytes()) != path.name:
        raise SystemExit(f"Evidence checksum mismatch: {path}")
manifests = list(Path('reports/local').glob('**/files-sha256.json'))
for manifest in manifests:
    for name, expected in json.loads(manifest.read_text(encoding='utf-8')).items():
        path = manifest.parent/name
        if sha(path.read_bytes()) != expected:
            raise SystemExit(f'Evidence manifest mismatch: {path}')
print(f"Verified {len(objects)} immutable evidence objects and {len(manifests)} file manifests")

from benchmark_runner.reporting import artifact_bound

STREAMS = ("attempts", "calls", "grades", "budget")
stream_files = [p for root in (Path("reports/offline"), Path("reports/local"))
                for name in STREAMS for p in root.glob(f"**/{name}.jsonl")]
stores = sorted({p.parent for p in stream_files})
checked_streams = chained = legacy = grades = unbound = 0
for root in stores:
    store = Store(root)
    for name in STREAMS:
        if not (root/f"{name}.jsonl").exists():
            continue
        try:
            summary = store.verify_stream(name)
        except ValueError as e:
            raise SystemExit(f"Evidence stream integrity failure: {e}")
        checked_streams += 1
        chained += summary["chained"]
        legacy += summary["legacy_records"]
        if name == "grades":
            for grade in store.events("grades"):
                grades += 1
                if not artifact_bound(store, grade):
                    unbound += 1
print(f"Verified {checked_streams} event streams in {len(stores)} committed stores "
      f"({chained} chained records, {legacy} legacy records); "
      f"{grades} grades, {unbound} without a bound grader artifact (disclosed, historical)")
