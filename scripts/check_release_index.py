"""Offline check of protected baseline/approval indices; empty means no release approval."""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from benchmark_runner.release_gate import compare, validate, canonical_sha


def check(root):
    def read(path):return json.loads(path.read_text())
    policy=read(root/'benchmarks/releases/policy-v1.json')
    policy_v2_path=root/'benchmarks/releases/policy-v2.json'
    policy_v2=read(policy_v2_path) if policy_v2_path.exists() else None
    def evidence(ref):
        name=ref['path']
        if not re.fullmatch(r'reports/releases/[A-Za-z0-9_./-]+\.json',name) or '..' in name.split('/'):
            raise ValueError('report outside release tree')
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('release report hash mismatch')
        value=read(path);validate(value,policy);return value
    def bound_file(ref,prefix):
        name=ref['path']
        if not name.startswith(prefix) or '..' in name.split('/'):
            raise ValueError('bound file outside protected tree')
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('bound file hash mismatch')
        return path
    def governance(entry,key):
        if policy_v2 is None or policy_v2.get('schema')!='release-governance-policy-v2':
            raise ValueError('governance approval without the registered governance policy')
        if entry['policy_sha256']!=canonical_sha(policy_v2):
            raise ValueError('governance approval policy changed')
        value=read(bound_file(entry['evidence'],'reports/releases/'))
        if value.get('schema')!='release-governance-evidence-v2' or value.get('standard')!='policy-v2-governance':
            raise ValueError('governance evidence schema/standard mismatch')
        if value['component']!=dict(repository=key[0],commit=key[1],artifact_sha256=key[2]):
            raise ValueError('governance evidence used another product commit/build artifact')
        record=value['governance']
        if record.get('policy')!='benchmarks/releases/policy-v2.json' or record.get('decision_record')!=policy_v2.get('decision_record'):
            raise ValueError('governance evidence not anchored to the registered policy and decision record')
        bound_file(dict(path=record['decision_record'],sha256=record['decision_record_sha256']),'benchmarks/releases/')
        bundles=value['detector_battery']['bundles']
        if len(bundles)!=5:raise ValueError('governance battery must record exactly the five frozen bundles')
        for bundle in bundles:
            for frozen in bundle['frozen_records'].values():
                bound_file(frozen,'reports/aee-validation/')
            if bundle.get('rescore_exact_match') is not True or bundle.get('rescore_fields')!=bundle.get('frozen_fields'):
                raise ValueError('recorded battery re-score is not an exact reproduction')
        return value
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
        approved.add(key)
        if entry.get('standard')=='policy-v2-governance':
            governance(entry,key);continue
        if entry.get('standard') not in (None,'policy-v1'):raise ValueError('approval declares an unknown release standard')
        candidate=evidence(entry['evidence']);baseline=baselines[entry['baseline_id']]
        if candidate['component']!=dict(repository=key[0],commit=key[1],artifact_sha256=key[2]) or candidate['component']==baseline['component']:
            raise ValueError('wrong/self-baseline artifact approval')
        if entry['policy_sha256']!=canonical_sha(policy):raise ValueError('approval policy changed')
        if not compare(baseline,candidate,policy)['release_allowed']:
            raise ValueError('committed approval does not pass registered comparison')
    return dict(accepted_baselines=len(baselines),approved_builds=len(approved),boundary='Empty indices block all releases; this is offline integrity, not executed empirical evidence.')


if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[1]),indent=2))
