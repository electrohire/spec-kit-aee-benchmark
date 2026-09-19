import importlib.util
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('repeated_local',ROOT/'scripts/repeated_local.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def test_unknown_usage_reservation_does_not_impute_native_tokens():
    call=dict(usage=None,preflight_input_tokens=100,max_output=20)
    assert runner.reservation(call)==120
    assert call['usage'] is None
    known=dict(usage={'total_tokens':45},preflight_input_tokens=100,max_output=20)
    assert sum(map(runner.reservation,[call,known]))==165


def test_public_tests_exclude_withheld_requirements():
    public=runner.tests_for('tinydb',3,True).decode()
    assert 'test_public_idempotent' in public
    assert 'test_R07_conflict' not in public
    assert 'test_R07_conflict' in runner.tests_for('tinydb',3,False).decode()
    assert 'test_public_idempotent' not in runner.tests_for('tinydb',1,True).decode()


def test_compact_assessment_retains_findings_and_recovery():
    value={'outcome':'iterate','findings':[{'id':'f','message':'conflict'}],
           'next_action':{'kind':'repair'},'metadata':{'nested_copy':'large'}}
    compact=runner.compact_assessment(value)
    assert compact['findings']==value['findings']
    assert compact['next_action']==value['next_action']
    assert 'metadata' not in compact

def test_failed_request_keeps_unknown_usage_but_allows_reserved_followup(tmp_path,monkeypatch):
    import time
    attempts=[]
    def local(route,payload=None,timeout=120):
        if route=='/apply-template':return {'prompt':'x'}
        if route=='/tokenize':return {'tokens':[1,2,3]}
        if route=='/slots':return [{'is_processing':False}]
        assert route=='/v1/chat/completions'
        attempts.append(payload)
        if len(attempts)==1:raise TimeoutError('synthetic dropped response')
        return {'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7},
                'choices':[{'finish_reason':'stop','message':{'content':'{"action":"done"}'}}]}
    monkeypatch.setattr(runner,'local_json',local)
    provider=runner.Provider(tmp_path/'attempt',1,5)
    messages=[{'role':'system','content':'test'},{'role':'user','content':'test'}]
    import pytest
    with pytest.raises(TimeoutError):provider.query(messages,'solve',1,time.monotonic()+100)
    assert provider.calls[0]['usage'] is None
    assert provider.calls[0]['budget_debit']==3+runner.CONFIG['max_output']
    assert provider.query(messages,'solve',1,time.monotonic()+100)=='{"action":"done"}'
    assert provider.calls[1]['usage']['total_tokens']==7


def test_repair_fixtures_have_nonempty_single_fault_changes():
    import matched_repair
    for project,variants in matched_repair.VARIANTS.items():
        reference=(runner.TASK/project/'reference.py').read_text().encode()
        for variant in variants:
            value=matched_repair.variant_source(project,variant)
            if variant=='clean':assert value==reference
            else:assert value!=reference


def test_session_reserved_final_action_and_honest_completion(tmp_path):
    class FakeProvider:
        def __init__(self):self.calls=[];self.messages=[]
        def query(self,messages,phase,stage,deadline):
            self.messages.append(list(messages));self.calls.append({})
            return '{"action":"done","summary":"No changes were needed"}'
    provider=FakeProvider()
    session=runner.Session(None,provider,runner.Store(tmp_path/'store'),'fixture')
    value=session.phase('solve','Review','Requirements',1,1,100)
    assert value['completed'] and value['calls']==1
    assert 'last allocated action' in provider.messages[0][-1]['content']
