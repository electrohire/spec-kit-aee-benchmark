"""Thin admission/controller joins only; no model, Docker or upstream task scores."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from benchmark_runner.upstream_agent_adapter import AdmissionError
from benchmark_runner.upstream_task_runner import _test_integrity

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_upstream_coding as controller


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


def admission(tmp_path):
    write(tmp_path/'freeze.json',dict(source_head='frozen-fixture'))
    folder=tmp_path/'native-admission';rows=[]
    for index,command in enumerate(controller.NATIVE_COMMANDS):
        tokens=24010 if index>=2 else 100
        usage=dict(prompt_tokens=tokens,completion_tokens=12,total_tokens=tokens+12)
        receipt='model/call-%04d.json'%index;echo='echo-%02d.json'%index
        write(folder/receipt,dict(usage_validated=True,usage=usage,started_at=10.,ended_at=12.,
            preflight_input_tokens=tokens,request=dict(max_tokens=8192,seed=20261019,
                chat_template_kwargs=dict(enable_thinking=False)),
            response=dict(model='qwen3.8-27b',usage=usage,choices=[dict(finish_reason='tool_calls',
                message=dict(tool_calls=[dict(function=dict(name='bash',arguments=json.dumps(dict(command=command))))]))])))
        write(folder/echo,dict(command=command,returncode=0,output=command.removeprefix('echo ')+'\n'))
        rows.append(dict(receipt=receipt,echo_receipt=echo,native_prompt_tokens=tokens,duration_seconds=2.))
    write(folder/'resource/owned-cleanup.json',dict(observed_absent=True))
    value=dict(source_head='frozen-fixture')
    manifest=dict(source_head=value['source_head'],freeze_sha256=controller.sha(tmp_path/'freeze.json'),
        worker_binding_sha256=controller.BINDING_SHA,source_unchanged=True,calls=rows)
    refresh(folder,manifest)
    return folder,manifest,value


def refresh(folder,manifest):
    manifest['files']={p.relative_to(folder).as_posix():controller.sha(p)
        for p in folder.rglob('*') if p.is_file() and p.name!='manifest.json'}
    write(folder/'manifest.json',manifest)


def test_schedule_pairs_all_twelve_endpoints_without_replacing_failed_arms():
    rows=[dict(instance_id=str(index)) for index in range(4)]
    actual=controller.schedule(rows)
    assert len(actual)==12 and len({(r['arm'],r['index']) for r in actual})==12
    assert len({r['unit'] for r in actual})==9
    for arm in controller.ARMS:
        chain=[r for r in actual if r['arm']==arm and r['index']>=2]
        assert [r['index'] for r in chain]==[2,3]
        assert chain[0]['unit']==chain[1]['unit'] and chain[1]['dependent']
    assert all(r['native_request_attempts']==0 and r['independent_grade'] is None for r in actual)


def test_native_admission_joins_original_receipts_echo_and_cleanup(tmp_path):
    _,_,value=admission(tmp_path)
    controller.verify_native(tmp_path,value)


@pytest.mark.parametrize('fault',['usage','timing','command','echo','cleanup','extra-request','outside-path'])
def test_native_admission_refuses_rehashed_but_inconsistent_evidence(tmp_path,fault):
    folder,manifest,value=admission(tmp_path)
    if fault in ('usage','timing','command'):
        path=folder/'model/call-0002.json';record=json.loads(path.read_text())
        if fault=='usage':record['response']['usage']['prompt_tokens']=10
        if fault=='timing':record['ended_at']=701.
        if fault=='command':record['response']['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"command":"false"}'
        write(path,record)
    elif fault=='echo':write(folder/'echo-00.json',dict(command=controller.NATIVE_COMMANDS[0],returncode=0,output='wrong'))
    elif fault=='cleanup':write(folder/'resource/owned-cleanup.json',dict(observed_absent=False))
    elif fault=='extra-request':write(folder/'model/call-0004.json',dict(usage=None))
    else:
        write(tmp_path/'outside.json',dict(usage_validated=True))
        manifest['calls'][0]['echo_receipt']='../outside.json'
    refresh(folder,manifest)
    with pytest.raises(AdmissionError):controller.verify_native(tmp_path,value)


def test_test_integrity_preserves_missing_and_modified_author_tests():
    initial={'pkg/tests/test_a.py':('100644','a'),'pkg/source.py':('100644','s')}
    final={'pkg/tests/test_new.py':('100644','b'),'pkg/source.py':('100644','t')}
    result=_test_integrity(initial,final)
    assert not result['passing']
    assert result['modified_existing_author_test_paths']==['pkg/tests/test_a.py']
    assert result['added_under_author_test_directories']==['pkg/tests/test_new.py']


def test_score_requires_terminal_native_admission_before_transport(tmp_path,monkeypatch):
    monkeypatch.setattr(controller,'verify_frozen',lambda out:dict(source_head='fixture'))
    def forbidden(*args,**kwargs):raise AssertionError('must not construct transport or infer')
    monkeypatch.setattr(controller,'BoundNativeTransport',forbidden)
    with pytest.raises(FileNotFoundError):controller.score(tmp_path)


def test_older_green_ci_does_not_override_a_newer_failed_or_pending_run(monkeypatch):
    head='fixture-exact-head'
    def item(identifier,status,conclusion):return dict(id=identifier,head_sha=head,event='push',
        path='.github/workflows/ci.yml',status=status,conclusion=conclusion)
    for status,conclusion in [('completed','failure'),('in_progress',None)]:
        payload=dict(workflow_runs=[item(1,'completed','success'),item(2,status,conclusion)])
        monkeypatch.setattr(controller.subprocess,'check_output',lambda *a,**k:json.dumps(payload).encode())
        with pytest.raises(AdmissionError,match='latest exact-head'):controller.live_ci(head)


@pytest.mark.parametrize('limit',[4,16,208])
def test_phase_budget_notice_exposes_last_call_without_increasing_limits(limit):
    from benchmark_runner.upstream_task_runner import phase_budget_notice
    notice=phase_budget_notice('fixture',limit,limit-1,20,1234)
    assert notice['phase_call_limit']==limit and notice['phase_calls_remaining_including_next']==1
    assert notice['task_calls_remaining']==204 and notice['native_token_budget_remaining']==24000000-1234
    assert 'not extra calls' in notice['instruction']
