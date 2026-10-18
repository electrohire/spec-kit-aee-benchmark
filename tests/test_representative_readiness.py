"""Offline adversarial checks for the new project-sized admission gate."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from action_protocol import ACTION_RESPONSE_FORMAT
from readiness_gate import validate_representative
import current_local
import repeated_local as runner


def fixture(tmp_path):
    config={k:current_local.CONFIG[k] for k in ('model','context','max_output','stage_seconds','primary_calls','enable_thinking','action_protocol')}
    cases=[]
    for project in runner.PROJECTS:
        for arm in runner.ARMS:
            name=project+'-'+arm;folder=tmp_path/name;folder.mkdir()
            value=dict(passed=True,project=project,arm=arm,before_repair=dict(passed=True),after_repair=dict(passed=True),
                injected_failure=dict(passed=False),repair=dict(calls=1),elapsed_seconds=600,
                allowed_seconds=config['stage_seconds'],phases=[dict(phase=p,completed=True,calls=1) for p in runner.phase_plan(arm,1)],
                assessments=[dict(phase=p) for p in ('specify','plan','tasks','implement')] if arm=='spec_kit_aee' else [])
            (folder/'result.json').write_text(json.dumps(value))
            (folder/'freeze.json').write_text(json.dumps(dict(config=config,hashes={'controller':'same'})))
            cases.append(dict(project=project,arm=arm,folder=name,result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()))
    (tmp_path/'result.json').write_text(json.dumps(dict(passed=True,cases=cases)))
    return config


def test_all_six_actual_workflows_and_repairs_required(tmp_path):
    cfg=fixture(tmp_path)
    assert validate_representative(tmp_path,cfg,runner.PROJECTS,runner.ARMS)['passed']
    summary=json.loads((tmp_path/'result.json').read_text());summary['cases'].pop()
    (tmp_path/'result.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='incomplete'):validate_representative(tmp_path,cfg,runner.PROJECTS,runner.ARMS)


@pytest.mark.parametrize('change', ['zero_implementation','no_repair','over_budget','tamper','controller_drift','wrong_role','wrong_order'])
def test_bad_readiness_cannot_admit_scoring(tmp_path,change):
    cfg=fixture(tmp_path);summary=json.loads((tmp_path/'result.json').read_text());case=next(c for c in summary['cases'] if c['arm']=='spec_kit');folder=tmp_path/case['folder']
    value=json.loads((folder/'result.json').read_text())
    if change=='zero_implementation':value['phases'][4]['calls']=0
    if change=='no_repair':value['repair']['calls']=0
    if change=='over_budget':value['elapsed_seconds']=cfg['stage_seconds']+1
    if change=='wrong_role':value['arm']='baseline'
    if change=='wrong_order':value['phases'].reverse()
    if change=='controller_drift':
        freeze=json.loads((folder/'freeze.json').read_text());freeze['hashes']['controller']='different';(folder/'freeze.json').write_text(json.dumps(freeze))
    (folder/'result.json').write_text(json.dumps(value))
    if change!='tamper':
        case['result_sha256']=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()
        (tmp_path/'result.json').write_text(json.dumps(summary))
    else:(folder/'result.json').write_text('{}')
    with pytest.raises(ValueError):validate_representative(tmp_path,cfg,runner.PROJECTS,runner.ARMS)


def test_native_action_schema_and_cap_cover_full_phase_schedule():
    schema=ACTION_RESPONSE_FORMAT['json_schema']['schema']
    for value in (dict(action='shell',command='printf "hello\\n"'),dict(action='done',completion_asserted=None),
                  dict(action='draft',claims=dict(schema_version='1.0',claims=[dict(id='R01')]))):
        jsonschema.validate(value,schema)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(dict(action='tool_call',command='ls'),schema)
    assert sum(runner.PHASE_LIMITS.values())+16<=current_local.CONFIG['primary_calls']
    assert current_local.CONFIG['enable_thinking'] is False


def test_same_phase_instructions_used_for_readiness_and_scoring():
    text=runner.phase_instructions('cachetools','spec_kit','implement','fixture requirements','fixture completion')
    assert '/testbed/src/cachetools' in text and 'fixture requirements' in text
    assert runner.phase_plan('baseline',1)==['solve']


def test_corrected_supervisor_stops_before_children_on_failed_preparation(tmp_path,monkeypatch):
    import run_corrected_study as supervisor
    monkeypatch.setattr(supervisor,'ROOT',tmp_path)
    monkeypatch.setattr(supervisor.subprocess,'run',lambda *a,**k:pytest.fail('no child/model command allowed'))
    for name,file in (('latency','calibration.json'),('context','result.json'),('transport','result.json')):
        folder=tmp_path/name;folder.mkdir();(folder/file).write_text(json.dumps(dict(passed=name!='transport')))
    status=tmp_path/'status.json'
    with pytest.raises(ValueError,match='preparation failed'):
        supervisor.execute(status,tmp_path/'latency',tmp_path/'context',tmp_path/'transport')
    state=json.loads(status.read_text())
    assert state['stage']=='intervention_required' and not state['complete'] and state['commands']==[]


def test_successful_child_exit_cannot_bypass_missing_readiness_artifacts(tmp_path,monkeypatch):
    import run_corrected_study as supervisor
    from types import SimpleNamespace
    monkeypatch.setattr(supervisor,'ROOT',tmp_path)
    monkeypatch.setattr(supervisor.current,'validate_action_readiness',lambda *a,**k:None)
    commands=[]
    def child(argv,**kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(supervisor.subprocess,'run',child)
    for name,file in (('latency','calibration.json'),('context','result.json'),('transport','result.json')):
        folder=tmp_path/name;folder.mkdir();(folder/file).write_text(json.dumps(dict(passed=True)))
    status=tmp_path/'status.json'
    with pytest.raises(FileNotFoundError):
        supervisor.execute(status,tmp_path/'latency',tmp_path/'context',tmp_path/'transport')
    assert len(commands)==3 and not any('scripts/current_local.py' in c and 'run' in c for c in commands)
    assert json.loads(status.read_text())['stage']=='intervention_required'


def test_stale_action_calibration_stops_before_any_child(tmp_path,monkeypatch):
    import run_corrected_study as supervisor
    monkeypatch.setattr(supervisor,'ROOT',tmp_path)
    monkeypatch.setattr(supervisor.subprocess,'run',lambda *a,**k:pytest.fail('no child before grammar validation'))
    for name,file in (('latency','calibration.json'),('context','result.json'),('transport','result.json')):
        folder=tmp_path/name;folder.mkdir();(folder/file).write_text(json.dumps(dict(passed=True)))
    def reject(*a,**k):raise ValueError('stale grammar')
    monkeypatch.setattr(supervisor.current,'validate_action_readiness',reject)
    with pytest.raises(ValueError,match='stale grammar'):
        supervisor.execute(tmp_path/'status.json',tmp_path/'latency',tmp_path/'context',tmp_path/'transport',6)
    assert json.loads((tmp_path/'status.json').read_text())['commands']==[]


@pytest.mark.parametrize('name',['current-grade-calibration-03','current-image-audit-03.json'])
def test_all_preparation_paths_checked_before_any_child_or_status(tmp_path,monkeypatch,name):
    import run_corrected_study as supervisor
    monkeypatch.setattr(supervisor,'ROOT',tmp_path)
    monkeypatch.setattr(supervisor.subprocess,'run',lambda *a,**k:pytest.fail('must stop before child commands'))
    (tmp_path/'artifacts').mkdir();(tmp_path/'artifacts'/name).touch()
    with pytest.raises(FileExistsError,match=name):
        supervisor.execute(tmp_path/'status.json',tmp_path/'latency',tmp_path/'context',tmp_path/'transport',3)
    assert not (tmp_path/'status.json').exists()
