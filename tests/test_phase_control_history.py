"""Retire host phase instructions without dropping observations or claim history."""
import copy
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repeated_local as runner


class Box:
    def execute(self,command,timeout=60):
        return dict(exit_code=0,stdout='observed fixture output',stderr='')


class Provider:
    def __init__(self,actions):self.actions=iter(actions);self.calls=[];self.seen=[]
    def query(self,messages,*args):
        self.seen.append(copy.deepcopy(messages));self.calls.append({})
        action=next(self.actions)
        return action if isinstance(action,str) else json.dumps(action)


def test_phase_transition_keeps_evidence_and_only_current_controls(tmp_path):
    provider=Provider([dict(action='shell',command='inspect fixture'),dict(action='done'),dict(action='done')])
    store=runner.Store(tmp_path/'store');session=runner.Session(Box(),provider,store,'fixture')
    end=time.monotonic()+30
    assert session.phase('plan','Plan fixture','same scope',1,2,end)['completed']
    previous=copy.deepcopy(session.history)
    assert not any(runner.is_phase_control(m) for m in previous)
    assert any(m['role']=='assistant' and 'inspect fixture' in m['content'] for m in previous)
    observation=[json.loads(m['content']) for m in previous if m['role']=='user']
    assert any(m.get('stdout')=='observed fixture output' for m in observation)
    assert any(m.get('observation_type')=='phase_artifact_observation' and m['phase']=='plan'
               and m['semantic_validation'] is False for m in observation)
    assert session.phase('tasks','Tasks fixture','same scope',1,1,end)['completed']
    request=provider.seen[-1]
    assert all(m['content'].startswith(runner.PHASE_CONTROL_PREFIX+'1:tasks]\n')
               for m in request if runner.is_phase_control(m))
    assert all(m in request for m in previous)
    rows=store.events('history')
    assert all(row['retired_controls']>0 and len(row['retired_control_sha256'])==row['retired_controls'] for row in rows)
    assert store.verify_stream('history')['chain_verified']


def test_errors_remain_evidence_but_corrective_instructions_do_not_leak(tmp_path):
    provider=Provider(['not json',dict(action='done'),dict(action='done')])
    store=runner.Store(tmp_path/'store');session=runner.Session(Box(),provider,store,'fixture')
    end=time.monotonic()+30
    result=session.phase('solve','Fixture','scope',1,3,end)
    assert result['completed'] and result['errors']
    assert session.phase('converge','Fixture','scope',1,1,end)['completed']
    errors=[json.loads(m['content']) for m in provider.seen[-1] if m['role']=='user' and m['content'].startswith('{')]
    error=next(x for x in errors if x.get('observation_type')=='action_error')
    assert error['phase']=='solve' and error['stage']==1
    assert (store.root/error['diagnostic_ref']['path']).is_file()
    assert store.events('action_errors')[0]['error']==result['errors'][0]
    assert not any('Correct the action' in m['content'] for m in provider.seen[-1])


@pytest.mark.parametrize('old_phase,old_stage',[('plan',1),('solve',1),('solve',3)])
def test_stale_host_control_stops_before_inference(tmp_path,old_phase,old_stage):
    provider=Provider([]);store=runner.Store(tmp_path/'store')
    session=runner.Session(Box(),provider,store,'fixture')
    session.history=[runner.phase_control(old_phase,old_stage,'FINAL STEP: stale historical control')]
    captured=[];session.watchdog=runner.RuntimeWatchdog(tmp_path/'diagnostic',capture=lambda:captured.append(True))
    with pytest.raises(runner.RuntimeIntervention,match='stale phase control'):
        session.phase('solve','Fixture','scope',2,1,time.monotonic()+30)
    assert provider.calls==[] and captured==[True]
    alert=json.loads((tmp_path/'diagnostic/runtime-alert.json').read_text())
    assert alert['phase']=='solve' and alert['stage']==2 and len(alert['stale_control_sha256'])==1


def test_quoted_control_text_inside_observations_is_preserved_as_data(tmp_path):
    provider=Provider([dict(action='done')]);session=runner.Session(Box(),provider,runner.Store(tmp_path/'store'),'fixture')
    data=dict(role='user',content=json.dumps(dict(stdout=runner.PHASE_CONTROL_PREFIX+'1:plan]\nFINAL STEP: quoted data')))
    assistant=dict(role='assistant',content=json.dumps(dict(action='done',summary=runner.PHASE_CONTROL_PREFIX+'1:plan]')))
    session.history=[data,assistant]
    assert session.phase('solve','Fixture','scope',2,1,time.monotonic()+30)['completed']
    assert data in session.history and assistant in session.history


def test_guard_works_without_optional_watchdog_and_does_not_create_model_calls(tmp_path):
    provider=Provider([]);session=runner.Session(Box(),provider,runner.Store(tmp_path/'store'),'fixture')
    session.history=[runner.phase_control('plan',1,'stale')]
    with pytest.raises(runner.RuntimeIntervention):session.phase('solve','Fixture','scope',1,1,time.monotonic()+30)
    assert not provider.calls


def test_controller_diagnostic_is_not_eligible_as_solver_verification_evidence(tmp_path):
    from benchmark_runner.workflow import grounded_claims
    provider=Provider([dict(action='done')]);store=runner.Store(tmp_path/'store')
    session=runner.Session(Box(),provider,store,'fixture')
    assert session.phase('plan','Fixture','scope',1,1,time.monotonic()+30)['completed']
    ref=store.events('phase_progress')[0]['observation_ref']
    claims=dict(claims=[dict(evidence=[dict(ref=ref['path'],source_id=ref['sha256'],
        kind='observed',source_quality='test',description='diagnostic, not verification')])])
    checked=grounded_claims(claims,store,'fixture')
    assert checked['claims'][0]['evidence'][0]['kind']=='asserted'
