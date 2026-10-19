"""Offline check of protected baseline/approval indices; empty means no release approval."""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from benchmark_runner.release_gate import compare, validate


def check(root):
    def read(path):return json.loads(path.read_text())
    policy=read(root/'benchmarks/releases/policy-v1.json')
    def evidence(ref):
        name=ref['path']
        if not re.fullmatch(r'reports/releases/[A-Za-z0-9_./-]+\.json',name) or '..' in name.split('/'):
            raise ValueError('report outside release tree')
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('release report hash mismatch')
        value=read(path);validate(value,policy);return value
    baselines={}
    for entry in read(root/'benchmarks/releases/accepted-baselines.json')['baselines']:
        if entry['id'] in baselines:raise ValueError('duplicate accepted baseline')
        value=evidence(entry['evidence'])
        if value['component']['repository']!=entry['repository']:raise ValueError('baseline repository mismatch')
        baselines[entry['id']]=value
    approved=set()
    for entry in read(root/'benchmarks/releases/approvals.json')['approvals']:
        key=entry['repository'],entry['commit'],entry['artifact_sha256']
        if key in approved:raise ValueError('duplicate exact-build approval')
        approved.add(key);candidate=evidence(entry['evidence']);baseline=baselines[entry['baseline_id']]
        if candidate['component']!=dict(repository=key[0],commit=key[1],artifact_sha256=key[2]) or candidate['component']==baseline['component']:
            raise ValueError('wrong/self-baseline artifact approval')
        if not compare(baseline,candidate,policy)['release_allowed']:
            raise ValueError('committed approval does not pass registered comparison')
    return dict(accepted_baselines=len(baselines),approved_builds=len(approved),boundary='Empty indices block all releases; this is offline integrity, not executed empirical evidence.')


if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[1]),indent=2))
