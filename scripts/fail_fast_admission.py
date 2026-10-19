"""Exact prospective tool/policy amendment; never authorizes historical reuse."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def matches(filename, name, before, after, preflight, kind='definitions'):
    if before == after:
        return True
    copied = preflight / 'fail-fast-amendment.json'
    if not copied.is_file():
        return False
    admission = json.loads((preflight / 'admission.json').read_text())
    version=admission.get('fail_fast_amendment','fail-fast-argv-v1')
    if version not in ('fail-fast-argv-v1','fail-fast-argv-v2'):return False
    registered=ROOT/'benchmarks/current_local'/(version+'.json')
    if copied.read_bytes()!=registered.read_bytes():return False
    if (admission.get('execution_policy') != 'fail-fast-v1'
        or admission.get('hashes', {}).get(copied.name) != hashlib.sha256(copied.read_bytes()).hexdigest()):
        return False
    entry = json.loads(copied.read_text())[kind].get(filename, {}).get(name)
    return entry == dict(before=hashlib.sha256(before.encode()).hexdigest(),
                         after=hashlib.sha256(after.encode()).hexdigest())
