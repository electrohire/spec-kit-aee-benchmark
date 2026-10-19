"""No stale timing or claimed-but-unobserved literal write can admit scoring."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import current_local as current


def save(path,value):
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def prepared(tmp_path):
    transport=tmp_path/'transport';transport.mkdir()
    write_sha=save(transport/'literal-write.json',dict(write={'exit_code':0},readback={'exit_code':0}))
    argv_sha=save(transport/'literal-argv.json',dict(execution={'exit_code':0}))
    checks=[dict(action=action,strict_claims_loaded=action in ('done','draft'))
            for action in ('shell','write_file','done','draft','exec')]
    checks[1].update(literal_write_verified=True,literal_write_sha256=write_sha)
    checks[4].update(literal_argv_verified=True,literal_argv_sha256=argv_sha)
    save(transport/'result.json',dict(passed=True,physical_calls=5,checks=checks))
    save(transport/'freeze.json',dict(hashes={'scripts/action_protocol.py':hashlib.sha256((current.ROOT/'scripts/action_protocol.py').read_bytes()).hexdigest()}))
    latency=tmp_path/'latency';latency.mkdir()
    save(latency/'freeze.json',dict(config=dict(action_protocol=current.CONFIG['action_protocol'])))
    receipts=[]
    for i in range(2):
        sha=save(latency/f'call-{i:04}.json',dict(request={'response_format':copy.deepcopy(current.ACTION_RESPONSE_FORMAT)},usage={'total_tokens':3}))
        receipts.append(dict(original_sha256=sha))
    save(latency/'calibration.json',dict(passed=True,records=receipts))
    return tmp_path


def test_complete_actual_grammar_binding(prepared):
    current.validate_action_readiness(prepared)


@pytest.mark.parametrize('mutation',['count','actions','claims','protocol_hash','write_flag','write_hash','argv_flag','argv_hash','latency_protocol','latency_receipt','latency_schema','latency_unknown'])
def test_changed_or_missing_action_readiness_blocked(prepared,mutation):
    if mutation.startswith('latency_'):
        if mutation=='latency_protocol':
            save(prepared/'latency/freeze.json',dict(config=dict(action_protocol='native-json-schema-v2')))
        else:
            path=prepared/'latency/call-0000.json';call=json.loads(path.read_text())
            if mutation=='latency_schema':call['request']['response_format']={}
            elif mutation=='latency_unknown':call['usage']=None
            else:call['changed']=True
            sha=save(path,call)
            if mutation!='latency_receipt':
                p=prepared/'latency/calibration.json';v=json.loads(p.read_text());v['records'][0]['original_sha256']=sha;save(p,v)
    else:
        p=prepared/'transport/result.json';v=json.loads(p.read_text())
        if mutation=='count':v['physical_calls']=3
        elif mutation=='actions':v['checks'].pop()
        elif mutation=='claims':v['checks'][2]['strict_claims_loaded']=False
        elif mutation=='write_flag':v['checks'][1]['literal_write_verified']=False
        elif mutation=='write_hash':v['checks'][1]['literal_write_sha256']='0'*64
        elif mutation=='argv_flag':v['checks'][4]['literal_argv_verified']=False
        elif mutation=='argv_hash':v['checks'][4]['literal_argv_sha256']='0'*64
        else:save(prepared/'transport/freeze.json',dict(hashes={'scripts/action_protocol.py':'0'*64}))
        save(p,v)
    with pytest.raises(ValueError):current.validate_action_readiness(prepared)
