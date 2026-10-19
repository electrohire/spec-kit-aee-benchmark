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

# Preserve byte-exact process logs and verify the actual engine ledger anchors.
# A superseded audit may document composition failure; its evidence still must
# verify, and it must never be counted as a successful coupled assessment.
from aee.ledger import HashChainLedger
audit_count=0
for claims_path in Path("reports/aee-validation").glob("*/claims.json"):
    root=claims_path.parent
    for claim in json.loads(claims_path.read_text())["claims"]:
        for evidence in claim["evidence"]:
            path=Path(evidence["ref"]).resolve()
            if not path.is_relative_to(Path.cwd().resolve()) or sha(path.read_bytes())!=evidence["content_hash"]:
                raise SystemExit(f"AEE observation checksum mismatch: {claims_path}")
    ledger_paths=[root/name for name in ("ledger.jsonl", "epistemic-ledger.jsonl")
                  if (root/name).exists()]
    if len(ledger_paths)!=1 or not HashChainLedger(ledger_paths[0]).verify(require_anchor=True).valid:
        raise SystemExit(f"AEE ledger/anchor failure: {root}")
    if not (root/"REVIEW.md").exists():
        composed=json.loads((root/"composed.json").read_text())
        if composed["metadata"]["evaluator_count"]!=1 or composed["metadata"].get("no_results"):
            raise SystemExit(f"AEE result was not composed: {root}")
    audit_count+=1
print(f"Verified {audit_count} recorded AEE audits; documented superseded attempts remain separate")

from benchmark_runner.reporting import artifact_bound

STREAMS = ("attempts", "calls", "grades", "budget", "tools", "history",
           "assessments", "assessment_errors")
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
