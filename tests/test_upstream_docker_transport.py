"""Lossless large-command transport and UID/deadline guards, no model calls."""
from types import SimpleNamespace
import pytest
from benchmark_runner.upstream_agent_adapter import AdmissionError
from benchmark_runner.upstream_docker_transport import StdinDockerBridge,PREFIX,DECODER


def fixture():
    return SimpleNamespace(config=SimpleNamespace(interpreter=PREFIX+['/bin/bash','-c'],forward_env=[],
        timeout=30,executable='docker',cwd='/testbed',env={}),container_id='controlled-id',
        _check_finished=lambda output:None)


def test_large_command_is_exact_stdin_never_argv(monkeypatch):
    import benchmark_runner.upstream_docker_transport as m
    seen=[]
    def run(argv,**kwargs):seen.append((argv,kwargs));return SimpleNamespace(stdout=b'ok\n',returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    bridge=StdinDockerBridge(fixture(),reader_python='/usr/bin/python3')
    command='printf '+('x'*70000)+'\n'
    out=bridge.execute(dict(command=command))
    argv,kwargs=seen[0]
    assert command not in argv and kwargs['input']==command.encode('utf-8')
    assert argv[-1]==DECODER and argv[argv.index('controlled-id')+1:][:5]==PREFIX
    assert out['returncode']==0 and out['output']=='ok\n'


def test_untrusted_interpreter_is_not_accepted():
    env=fixture();env.config.interpreter=['bash','-c']
    with pytest.raises(AdmissionError):StdinDockerBridge(env,reader_python='/usr/bin/python3')


def test_no_forwarded_host_environment():
    env=fixture();env.config.forward_env=['EXAMPLE']
    with pytest.raises(AdmissionError):StdinDockerBridge(env,reader_python='/usr/bin/python3')


def test_expired_wall_budget_starts_no_process(monkeypatch):
    import benchmark_runner.upstream_docker_transport as m
    monkeypatch.setattr(m.subprocess,'run',lambda *args,**kwargs:pytest.fail('must not execute'))
    bridge=StdinDockerBridge(fixture(),reader_python='/usr/bin/python3',deadline=0)
    with pytest.raises(AdmissionError):bridge.execute(dict(command='pwd'))
