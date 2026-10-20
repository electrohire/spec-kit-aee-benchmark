"""Thin provider/credential guards only; canned replies are not benchmark scores."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from benchmark_runner.upstream_agent_adapter import AdmissionError, BoundNativeTransport, Limits, NativeToolModel, ReceiptEnvironment, ToolFailure, native_usage, safe_upstream


def response():
    return dict(model='qwen3.8-27b',usage=dict(prompt_tokens=5,completion_tokens=2,total_tokens=7,
        prompt_tokens_details=dict(cached_tokens=0)),choices=[dict(finish_reason='tool_calls',
        message=dict(role='assistant',content='Inspect workspace.',tool_calls=[dict(id='one',type='function',
            function=dict(name='bash',arguments='{"command":"pwd"}'))]))])


class Wire:
    def __init__(self, value=None, failure=False, busy=False):
        self.value=response() if value is None else value;self.failure=failure;self.busy=busy;self.generations=0
    def __call__(self, route, payload, timeout):
        if route=='/slots':return [dict(is_processing=self.busy)]
        if route=='/apply-template':return dict(prompt='native template includes tools')
        if route=='/tokenize':return dict(tokens=[1]*5)
        assert route=='/v1/chat/completions';self.generations+=1
        if self.failure:raise OSError('synthetic connection reset')
        return copy.deepcopy(self.value)


def model(tmp_path, wire, limits=None):
    # Real pinned parser/Docker/agent integration is separately validated in a
    # credential-isolated child; these fixtures isolate transport/accounting.
    upstream=SimpleNamespace(tool=dict(type='function',function=dict(name='bash')),
        parse=lambda calls,**kw:[dict(command=json.loads(c.function.arguments)['command'],tool_call_id=c.id) for c in calls],
        observe=lambda **kw:[dict(role='tool',content='fixture observation')])
    return NativeToolModel(wire,tmp_path/'calls',upstream,limits or Limits(), 'fixture',dict(cohort='synthetic_adapter_test'))


def test_receipt_hash_binds_finalized_bytes(tmp_path):
    m=model(tmp_path,Wire());out=m.query([dict(role='user',content='public task',extra=dict(controller='not sent'))])
    path=Path(out['extra']['receipt']);saved=json.loads(path.read_text())
    assert out['extra']['receipt_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert saved['ended_at'] and saved['usage']['total_tokens']==7
    assert 'extra' not in saved['request']['messages'][0]
    assert m.tokens==7 and m.n_calls==1


def test_failed_generation_halts_without_retry_or_zero_usage(tmp_path):
    wire=Wire(failure=True);m=model(tmp_path,wire)
    with pytest.raises(OSError):m.query([dict(role='user',content='public task')])
    assert wire.generations==1
    c=json.loads((m.out/'call-0000.json').read_text());assert c['usage'] is None and c['unknown_reason'] and c['ended_at']
    with pytest.raises(AdmissionError):m.query([dict(role='user',content='do not retry')])
    assert wire.generations==1


def test_busy_slot_starts_zero_generation_and_latches(tmp_path):
    wire=Wire(busy=True);m=model(tmp_path,wire)
    with pytest.raises(AdmissionError):m.query([dict(role='user',content='public task')])
    assert wire.generations==0 and m.n_calls==0
    wire.busy=False
    with pytest.raises(AdmissionError):m.query([dict(role='user',content='do not retry')])
    assert wire.generations==0


@pytest.mark.parametrize('fault',['identity','finish','noaction','multiple','usage','cache'])
def test_protocol_errors_retain_known_usage_and_halt(tmp_path,fault):
    value=response()
    if fault=='identity':value['model']='other'
    if fault=='finish':value['choices'][0]['finish_reason']='length'
    if fault=='noaction':value['choices'][0]['message']['tool_calls']=[]
    if fault=='multiple':value['choices'][0]['message']['tool_calls']*=2
    if fault=='usage':value['usage']=None
    if fault=='cache':value['usage']['prompt_tokens_details']['cached_tokens']=6
    wire=Wire(value);m=model(tmp_path,wire)
    with pytest.raises(AdmissionError):m.query([dict(role='user',content='task')])
    c=json.loads((m.out/'call-0000.json').read_text());assert c['error'] and c['ended_at']
    assert c['usage']==value['usage']


@pytest.mark.parametrize('limits',[Limits(maximum_calls=0),Limits(context=8196),Limits(native_token_cap=8196)])
def test_caps_stop_before_generation_without_truncation(tmp_path,limits):
    wire=Wire();m=model(tmp_path,wire,limits)
    with pytest.raises(AdmissionError):m.query([dict(role='user',content='task')])
    assert wire.generations==0


@pytest.mark.parametrize('bad',[None,{},dict(prompt_tokens=True,completion_tokens=2,total_tokens=3),dict(prompt_tokens=5,completion_tokens=2,total_tokens=8)])
def test_native_usage_is_not_invented(bad):
    with pytest.raises(AdmissionError):native_usage(dict(usage=bad))


def test_upstream_import_requires_explicit_safe_launch(monkeypatch):
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED',raising=False)
    with pytest.raises(AdmissionError):safe_upstream()


def test_container_system_facts_do_not_query_or_leak_windows_host(tmp_path):
    class Environment:
        config=SimpleNamespace(model_dump=lambda:dict(cwd='/testbed'))
        def get_template_vars(self,**kwargs):raise AssertionError('Windows host uname must not be queried')
    env=ReceiptEnvironment(Environment(),tmp_path/'tools',dict(system='Linux',machine='x86_64'))
    assert env.get_template_vars()==dict(cwd='/testbed',system='Linux',machine='x86_64')


def test_transport_never_allows_load_unload_or_management_endpoints():
    transport=object.__new__(BoundNativeTransport)
    for route in ('/models/load','/models/unload','https://outside.example','/slots/0?action=erase'):
        with pytest.raises(AdmissionError):transport(route,{},1)


def test_unapproved_worker_json_is_not_authority(tmp_path):
    path=tmp_path/'binding.json';path.write_text(json.dumps(dict(endpoint='http://127.0.0.1:8081',pid=64756)))
    with pytest.raises(AdmissionError):BoundNativeTransport(path,hashlib.sha256(path.read_bytes()).hexdigest(),'unused')


def test_original_failure_survives_secondary_persistence_failure(tmp_path,monkeypatch):
    wire=Wire(failure=True);m=model(tmp_path,wire)
    def fail_write(*args,**kwargs):raise OSError('synthetic ENOSPC receipt flush')
    monkeypatch.setattr(Path,'write_text',fail_write)
    with pytest.raises(BaseExceptionGroup) as exc:m.query([dict(role='user',content='task')])
    assert 'connection reset' in str(exc.value.exceptions[0])
    assert 'ENOSPC' in str(exc.value.exceptions[1])
    assert wire.generations==1 and m.halted and m.unknown_usage==1


def test_original_tool_failure_survives_secondary_persistence_failure(tmp_path,monkeypatch):
    environment=SimpleNamespace(execute=lambda *a,**k:dict(returncode=1,output='original tool failure',exception_info=''))
    wrapped=ReceiptEnvironment(environment,tmp_path/'tools',{})
    monkeypatch.setattr(Path,'write_text',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic receipt ENOSPC')))
    with pytest.raises(BaseExceptionGroup) as exc:wrapped.execute(dict(command='false'))
    assert isinstance(exc.value.exceptions[0],ToolFailure)
    assert 'ENOSPC' in str(exc.value.exceptions[1]) and wrapped.halted


def test_expired_task_starts_no_worker_requests(tmp_path):
    wire=Wire();m=model(tmp_path,wire);m.deadline=0
    with pytest.raises(AdmissionError,match='wall budget'):m.query([dict(role='user',content='task')])
    assert wire.generations==0 and m.n_calls==0 and m.halted
    receipt=json.loads((m.out/'before-call-0000.json').read_text())
    assert receipt['generation_requests_started']==0
