import json
import sys
import time
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from model_outcomes import model_failure,finish_stopped_stage
from report_repeated import workflow_completed


@pytest.mark.parametrize('reason',[
    'repeated identical action without changed observation',
    'phase did not complete; downstream execution withheld',
    'insufficient capacity before phase','primary call budget exhausted before phase'])
def test_model_guard_still_stops_attempt_and_counts_failure(reason):
    assert model_failure(dict(reason=reason))
    assert not model_failure(dict(reason=reason,snapshot_error='disk failed'))


@pytest.mark.parametrize('error', ['ValueError(\'invalid model JSON\')','JSONDecodeError(\'bad\')'])
def test_known_model_protocol_failure_is_contained(error):
    assert model_failure(dict(reason='consecutive action/transport failures',error=error))


@pytest.mark.parametrize('reason,error',[
    ('runtime safety/budget failure','ModelIdentityMismatch'),
    ('stale phase control in active request',''),
    ('consecutive action/transport failures','HTTPError(503)'),
    ('consecutive action/transport failures','OSError(\'disk\')'),
    ('unknown future error','')])
def test_infrastructure_or_unknown_fault_stops_entire_campaign(reason,error):
    assert not model_failure(dict(reason=reason,error=error))


def test_interrupted_and_dependent_rows_keep_source_grades_unknown_claims_and_zero_retry(tmp_path):
    folder=tmp_path/'attempt';folder.mkdir()
    snapshots=[];grades=[]
    class Box:
        def snapshot(self,path):snapshots.append(path);path.write_bytes(b'exact retained source')
    def grade(project,path,stage,public,expected):
        grades.append((stage,path.read_bytes()));return dict(passed=False,exit_code=1,cases=[],test_count=0)
    alert=dict(reason='repeated identical action without changed observation',phase='implement')
    for stage in (1,2,3):
        row=dict(project='tinydb',stage=stage,arm='baseline',phases=[],repairs=[],assessments=[])
        finish_stopped_stage(Box(),row,folder,tmp_path,grade,1,7 if stage==1 else 0,time.monotonic(),alert,dependent=stage>1)
        assert row['calls']==(7 if stage==1 else 0)
        assert row['completion_asserted'] is None and row['primary_completion_asserted'] is None
        assert row['status']==('runtime_interrupted' if stage==1 else 'not_attempted_dependent')
        assert not workflow_completed(row)
        assert row['final_snapshot'] and row['public_final']['passed'] is False
    assert len(snapshots)==6 and len(grades)==6


def test_repair_intervention_preserves_primary_declaration_but_final_is_unknown(tmp_path):
    folder=tmp_path/'attempt';folder.mkdir();primary=folder/'stage1-primary.tar';primary.write_bytes(b'primary')
    class Box:
        def snapshot(self,path):path.write_bytes(b'repaired source')
    row=dict(project='tinydb',stage=1,primary_snapshot='attempt/stage1-primary.tar',
             primary_completion_asserted=True,public_primary=dict(passed=False))
    finish_stopped_stage(Box(),row,folder,tmp_path,lambda *a:dict(passed=True),1,8,time.monotonic(),
                         dict(reason='repeated identical action without changed observation',phase='repair'))
    assert row['primary_completion_asserted'] is True
    assert row['completion_asserted'] is None and primary.read_bytes()==b'primary'
    assert row['public_final']['passed'] is True


def test_campaign_contains_model_failure_keeps_all_rows_and_continues_other_trajectory(tmp_path,monkeypatch):
    import repeated_local as r
    task=tmp_path/'tasks/tinydb';task.mkdir(parents=True)
    for stage in (1,2,3):(task/f'stage{stage}.md').write_text('fixture task')
    inputs=tmp_path/'inputs';inputs.mkdir()
    reference={f'{stage}-{mode}':dict(test_count=1) for stage in (1,2,3) for mode in ('public','hidden')}
    (inputs/'calibration.json').write_text(json.dumps(dict(passed=True,projects={'tinydb':dict(reference=reference)})))
    for name,value in [('workflow',dict(passed=True)),('latency',dict(passed=True,timeout=1)),
                       ('context',dict(passed=True,selector_sha256='0'*64))]:
        (inputs/(name+'.json')).write_text(json.dumps(value))
    assets=tmp_path/'assets';assets.mkdir()
    for name in ('hardware','server-launch','package-versions'):(assets/(name+'.json')).write_text('{}')
    class Box:
        name='fixture'
        def __init__(self,project):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stage_workflow(self):pass
        def put(self,*args):pass
        def snapshot(self,path):path.write_bytes(b'retained source')
    providers=[]
    class Provider:
        def __init__(self,*args):self.calls=[];providers.append(self)
    def phase(self,phase,instructions,spec,stage,*args):
        self.provider.calls.append(dict(stage=stage))
        self.watchdog.stop('repeated identical action without changed observation',phase=phase,stage=stage)
    monkeypatch.setattr(r,'ROOT',tmp_path);monkeypatch.setattr(r,'TASK',tmp_path/'tasks')
    monkeypatch.setattr(r,'PROJECTS',{'tinydb':dict(upstream='fixture',revision='fake',package='tinydb',module='tinydb/journal.py')})
    monkeypatch.setattr(r,'SEEDS',[1]);monkeypatch.setattr(r,'ARMS',['baseline','spec_kit'])
    monkeypatch.setattr(r,'digest',lambda *args:'0'*64)
    monkeypatch.setattr(r.subprocess,'check_output',lambda *args,**kwargs:'fake\n' if kwargs.get('text') else b'fake\n')
    monkeypatch.setattr(r,'ProjectSandbox',Box);monkeypatch.setattr(r,'Provider',Provider)
    monkeypatch.setattr(r.Session,'phase',phase)
    monkeypatch.setattr(r,'local_json',lambda *args:{})
    monkeypatch.setattr(r,'tests_for',lambda *args:b'fixture')
    monkeypatch.setattr(r,'phase_instructions',lambda *args:'fixture instructions')
    monkeypatch.setattr(r,'grade',lambda *args:dict(passed=False,exit_code=1,cases=[],test_count=0))
    out=tmp_path/'scored'
    r.campaign(out,inputs,1,workflow_preflight=inputs/'workflow.json',latency_preflight=inputs/'latency.json',
        context_preflight=inputs/'context.json',assets=assets,contain_model_failures=True)
    rows=json.loads((out/'results.json').read_text())
    assert len(rows)==6
    assert sum(row['status']=='runtime_interrupted' for row in rows)==2
    assert sum(row['status']=='not_attempted_dependent' for row in rows)==4
    assert [len(p.calls) for p in providers]==[1,1]
    assert all(not workflow_completed(row) and 'hidden_final' in row for row in rows)
    assert all(row['completion_asserted'] is None for row in rows)


def admission_fixture(tmp_path):
    import hashlib
    from model_outcomes import validate_admission
    workflow=tmp_path/'workflow';(workflow/'calls').mkdir(parents=True)
    (tmp_path/'grade').mkdir()
    value=dict(project='tinydb',passed=False,allowed_seconds=60,
        phases=[dict(phase=p,completed=True,calls=1) for p in ('constitution','specify','plan','tasks','implement','converge','final_implement')],
        assessments=[dict(phase=p) for p in ('specify','plan','tasks','implement')],
        before_repair=dict(passed=True),injected_failure=dict(passed=False))
    (workflow/'result.json').write_text(json.dumps(value));(workflow/'freeze.json').write_text('{}')
    (workflow/'runtime-stopped.tar').write_bytes(b'exact source')
    (workflow/'runtime-alert.json').write_text(json.dumps(dict(reason='repeated identical action without changed observation')))
    (workflow/'calls/call-0000.json').write_text(json.dumps(dict(phase='repair',started_at='2026-10-18T00:00:00+00:00',ended_at='2026-10-18T00:00:01+00:00',usage=dict(total_tokens=1))))
    proof=dict(passed=True,exit_code=0,test_count=1,cases=[dict(name='test_fixture',file='fixture',passed=True)],
        source_sha256=hashlib.sha256(b'exact source').hexdigest(),grader_source_sha256='a'*64,grader_function_sha256='b'*64)
    (tmp_path/'repair-verification.json').write_text(json.dumps(proof))
    (tmp_path/'grade/calibration.json').write_text(json.dumps(dict(projects=dict(tinydb=dict(reference={'1-public':proof})))))
    def bind():
        files=[p for p in tmp_path.rglob('*') if p.is_file() and p.name!='admission.json']
        (tmp_path/'admission.json').write_text(json.dumps(dict(protocol='inclusive-model-outcomes-v1',hashes={p.relative_to(tmp_path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})))
    bind()
    return workflow,tmp_path/'admission.json',bind,validate_admission


def test_admission_binds_genuine_workflow_and_independent_repair_proof(tmp_path):
    workflow,path,_,validate=admission_fixture(tmp_path)
    assert validate(workflow,path,dict(stage_seconds=60))['protocol']=='inclusive-model-outcomes-v1'
    (tmp_path/'repair-verification.json').write_text('{}')
    with pytest.raises(ValueError,match='hash'):validate(workflow,path,dict(stage_seconds=60))


@pytest.mark.parametrize('change',['infra','missing-phase','unknown-usage','wrong-source','wrong-grader','failed-repair','over-budget'])
def test_admission_cannot_hide_infrastructure_or_unverified_proof(tmp_path,change):
    workflow,path,bind,validate=admission_fixture(tmp_path)
    if change=='infra':
        (workflow/'runtime-alert.json').write_text(json.dumps(dict(reason='runtime safety/budget failure')))
    elif change=='missing-phase':
        p=workflow/'result.json';v=json.loads(p.read_text());v['phases'].pop();p.write_text(json.dumps(v))
    elif change=='unknown-usage':
        p=workflow/'calls/call-0000.json';v=json.loads(p.read_text());v['usage']=None;p.write_text(json.dumps(v))
    elif change=='over-budget':pass
    else:
        p=tmp_path/'repair-verification.json';v=json.loads(p.read_text())
        if change=='wrong-source':v['source_sha256']='f'*64
        elif change=='wrong-grader':v['grader_function_sha256']='f'*64
        else:v['passed']=False
        p.write_text(json.dumps(v))
    bind()
    with pytest.raises(ValueError):validate(workflow,path,dict(stage_seconds=0 if change=='over-budget' else 60))
