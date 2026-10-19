import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import fail_fast_admission as admission


def test_registered_amendment_matches_current_definitions_and_bindings():
    registered=json.loads((ROOT/'benchmarks/current_local/fail-fast-argv-v1.json').read_text())
    assert registered['execution_policy']=='fail-fast-v1'
    for kind in ('definitions','bindings'):
        for filename,entries in registered[kind].items():
            found={}
            for node in ast.parse((ROOT/filename).read_text()).body:
                if kind=='definitions' and isinstance(node,(ast.FunctionDef,ast.ClassDef)):
                    found[node.name]=ast.dump(node,include_attributes=False)
                if kind=='bindings' and isinstance(node,ast.Assign):
                    for target in node.targets:
                        if isinstance(target,ast.Name):found[target.id]=ast.dump(node.value,include_attributes=False)
            for name,entry in entries.items():
                assert hashlib.sha256(found[name].encode()).hexdigest()==entry['after']


@pytest.mark.parametrize('tamper',['none','policy','hash','bytes','definition','unregistered'])
def test_amendment_is_exact_and_requires_bound_prospective_policy(tmp_path,monkeypatch,tamper):
    root=tmp_path/'repo';directory=root/'benchmarks/current_local';directory.mkdir(parents=True)
    entry={key:hashlib.sha256(value.encode()).hexdigest() for key,value in [('before','old'),('after','new')]}
    registered=directory/'fail-fast-argv-v1.json'
    registered.write_text(json.dumps(dict(definitions={'fixture.py':{'function':entry}})))
    copied=tmp_path/'fail-fast-amendment.json';copied.write_bytes(registered.read_bytes())
    value=dict(execution_policy='fail-fast-v1',hashes={copied.name:hashlib.sha256(copied.read_bytes()).hexdigest()})
    if tamper=='policy':value['execution_policy']='model-outcomes-v1'
    if tamper=='hash':value['hashes'][copied.name]='0'*64
    if tamper=='bytes':copied.write_text('{}')
    (tmp_path/'admission.json').write_text(json.dumps(value))
    monkeypatch.setattr(admission,'ROOT',root)
    assert admission.matches('fixture.py','other' if tamper=='unregistered' else 'function',
        'old','new changed' if tamper=='definition' else 'new',tmp_path)==(tamper=='none')
