"""Exact, preregistered infrastructure-only calibration migration.

This is not a general waiver for changed solver instructions or runtime guards.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'benchmarks/current_local/infrastructure-recovery-v1.json'


def definition_matches(filename, name, before, after, preflight):
    if before == after:
        return True
    copied = preflight / 'recovery-migration.json'
    admission = json.loads((preflight / 'admission.json').read_text())
    protocol = admission.get('recovery_protocol')
    registered_manifest = MANIFEST if protocol == 'infrastructure-recovery-v1' else ROOT / 'benchmarks/current_local/direct-worker-v1.json' if protocol == 'direct-worker-v1' else None
    if registered_manifest is None or not copied.is_file() or copied.read_bytes() != registered_manifest.read_bytes():
        return False
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    if admission.get('hashes', {}).get('recovery-migration.json') != digest:
        return False
    registered = json.loads(copied.read_text())['definitions'].get(filename, {}).get(name)
    return registered == {
        'before': hashlib.sha256(before.encode()).hexdigest(),
        'after': hashlib.sha256(after.encode()).hexdigest(),
    }
