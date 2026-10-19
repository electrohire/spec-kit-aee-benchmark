"""Exact prospective tool/policy amendment; never authorizes historical reuse."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def matches(filename, name, before, after, preflight, kind='definitions'):
    if before == after:
        return True
    copied = preflight / 'fail-fast-amendment.json'
    registered = ROOT / 'benchmarks/current_local/fail-fast-argv-v1.json'
    if not copied.is_file() or copied.read_bytes() != registered.read_bytes():
        return False
    admission = json.loads((preflight / 'admission.json').read_text())
    if (admission.get('execution_policy') != 'fail-fast-v1'
        or admission.get('hashes', {}).get(copied.name) != hashlib.sha256(copied.read_bytes()).hexdigest()):
        return False
    entry = json.loads(copied.read_text())[kind].get(filename, {}).get(name)
    return entry == dict(before=hashlib.sha256(before.encode()).hexdigest(),
                         after=hashlib.sha256(after.encode()).hexdigest())
