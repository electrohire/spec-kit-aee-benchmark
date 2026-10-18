"""Claim handoffs must be representable and required before native generation."""
import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from aee.model import Claim

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from action_protocol import ACTION_RESPONSE_FORMAT, action_response_format


def claim():
    return dict(id='R01',text='A bounded requirement',kind='requirement',status='draft',
        stage='created',boundary=['fixture'],depends_on=[],conflicts_with=[],
        falsification_tests=['counterexample'],source_ref='fixture R01',
        uncertainty='insufficient_evidence',evidence=[])


@pytest.mark.parametrize('action', ['done','draft'])
def test_claim_terminals_require_engine_loadable_bundle_without_promoting_it(action):
    schema=action_response_format(True)['json_schema']['schema']
    valid=dict(action=action,claims=dict(schema_version='1.0',claims=[claim()]))
    jsonschema.validate(valid,schema)
    loaded=Claim.from_dict(valid['claims']['claims'][0])
    assert loaded.status.value=='draft' and loaded.stage.value=='created' and not loaded.evidence
    for bad in (dict(action=action),dict(action=action,claims={}),
                dict(action=action,claims=dict(schema_version='1.0',claims=[]))):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    for field in claim():
        bad=copy.deepcopy(valid);del bad['claims']['claims'][0][field]
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)


@pytest.mark.parametrize('field,value', [('kind','observed'),('status','verified'),('stage','verified'),
    ('uncertainty','certain'),('boundary','all'),('evidence',{}),('id',''),('text','')])
def test_malformed_claims_rejected_before_inference(field,value):
    item=claim();item[field]=value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(action='done',claims=dict(schema_version='1.0',claims=[item])),
                            action_response_format(True)['json_schema']['schema'])


def test_shell_is_available_without_claims_and_cannot_omit_command():
    schema=action_response_format(True)['json_schema']['schema']
    jsonschema.validate(dict(action='shell',command='python -m pytest -q'),schema)
    for bad in (dict(action='shell'),dict(action='shell',command=''),dict(action='tool_call')):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)


def test_nonclaim_schema_requires_fresh_latency_for_changed_protocol():
    root=Path(__file__).resolve().parents[1]
    assert action_response_format(False)==ACTION_RESPONSE_FORMAT
    for path in (root/'artifacts/current-latency-calibration-02').glob('call-*.json'):
        assert json.loads(path.read_text())['request']['response_format']!=action_response_format(False)
    value=action_response_format(False);value['type']='mutated'
    assert ACTION_RESPONSE_FORMAT['type']=='json_schema'


def test_session_sets_contract_for_each_phase_not_previous_phase(tmp_path):
    import repeated_local as runner
    class Provider:
        def __init__(self):self.calls=[];self.contracts=[]
        def query(self,*args):
            self.contracts.append(self.requires_claims);self.calls.append({})
            return json.dumps(dict(action='done',claims=dict(schema_version='1.0',claims=[claim()])))
    provider=Provider();session=runner.Session(None,provider,runner.Store(tmp_path/'store'),'test')
    assert session.phase('fixture','instructions','scope',1,1,100,True)['completed']
    assert session.phase('solve','instructions','scope',1,1,100,False)['completed']
    assert provider.contracts==[True,False]
