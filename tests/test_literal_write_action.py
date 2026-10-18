"""Literal file data never becomes shell/Python source; loop guard still applies."""
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from action_protocol import action_command,action_response_format,MAX_WRITE_BYTES
from runtime_checks import RuntimeIntervention,RuntimeWatchdog


def run_literal(action,root):
    argv=shlex.split(action_command(action));argv[0]=sys.executable
    result=subprocess.run(argv,cwd=root,capture_output=True,text=True,encoding='utf-8')
    return dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)


@pytest.mark.parametrize('content',[
    '**Input**: User description: "quoted"\nit\'s literal\n',
    '""" + triple quotes \'\'\' and \\n escapes',
    '$(touch BAD) `touch BAD` ; exit 9\nPYEOF\nUnicode: λ 😀\n',
    '', 'no final newline',
])
def test_write_literal_bytes_with_hostile_quoting(tmp_path,content):
    action=dict(action='write_file',path='nested/spec.md',content=content)
    result=run_literal(action,tmp_path)
    assert result['exit_code']==0,result
    assert (tmp_path/'nested/spec.md').read_bytes()==content.encode()
    assert not (tmp_path/'BAD').exists()
    assert json.loads(result['stdout'])['bytes']==len(content.encode())


@pytest.mark.parametrize('path',[None,'','/tmp/out','../out','tests/../out','C:/out','a\\b','a//b','./file','a/./b','a\x00b'])
def test_invalid_paths_refused_before_tool_execution(path):
    with pytest.raises(ValueError):action_command(dict(action='write_file',path=path,content='x'))


@pytest.mark.parametrize('content',[None,{},'x'*(MAX_WRITE_BYTES+1),'λ'*MAX_WRITE_BYTES],ids=['null','mapping','ascii-limit','utf8-limit'])
def test_bounded_utf8_content(content):
    with pytest.raises(ValueError):action_command(dict(action='write_file',path='file',content=content))


def test_shell_compatibility_and_unsupported_actions():
    assert action_command(dict(action='shell',command='python -m pytest'))=='python -m pytest'
    for action in ({'action':'shell','command':''},{'action':'done'},{'action':'unknown'}):
        with pytest.raises(ValueError):action_command(action)


@pytest.mark.parametrize('claims',[True,False])
def test_native_schema_allows_literal_write_in_every_phase(claims):
    schema=action_response_format(claims)['json_schema']['schema']
    jsonschema.validate(dict(action='write_file',path='source.py',content='literal'),schema)
    if claims:
        for missing in ('content','path'):
            action=dict(action='write_file',path='source.py',content='literal');del action[missing]
            with pytest.raises(jsonschema.ValidationError):jsonschema.validate(action,schema)


def test_repeated_writes_still_trigger_unchanged_guard(tmp_path):
    watchdog=RuntimeWatchdog(tmp_path/'audit')
    action=dict(action='write_file',path='source.py',content='x')
    command=action_command(action)
    for _ in range(2):watchdog.tool(command,run_literal(action,tmp_path),'specify',1)
    with pytest.raises(RuntimeIntervention,match='repeated identical'):
        watchdog.tool(command,run_literal(action,tmp_path),'specify',1)
    assert json.loads((tmp_path/'audit/runtime-alert.json').read_text())['repeated_actions']==3


def test_symlinked_destination_cannot_escape_sandbox(tmp_path):
    outside=tmp_path.parent/(tmp_path.name+'-outside');outside.mkdir()
    try:(tmp_path/'link').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('host has no symlink creation privilege')
    result=run_literal(dict(action='write_file',path='link/source.py',content='must not escape'),tmp_path)
    assert result['exit_code']!=0 and not (outside/'source.py').exists()


def test_maximum_literal_data_stays_under_linux_argument_bounds():
    command=action_command(dict(action='write_file',path='λ'*4096,content='\x00'*MAX_WRITE_BYTES))
    assert len(command.encode())<131072
    assert all(len(argument.encode())<131072 for argument in shlex.split(command))


def test_session_executes_write_and_retains_exact_action(tmp_path):
    import repeated_local as runner
    actions=[dict(action='write_file',path='note.md',content='literal "quotes"'),dict(action='done')]
    class Provider:
        def __init__(self):self.calls=[]
        def query(self,*args):
            action=actions[len(self.calls)];self.calls.append({});return json.dumps(action)
    class Box:
        def execute(self,command,timeout):
            assert command==action_command(actions[0])
            return run_literal(actions[0],tmp_path)
    store=runner.Store(tmp_path/'evidence')
    session=runner.Session(Box(),Provider(),store,'literal-fixture')
    result=session.phase('solve','complete fixture','scope',1,3,time.monotonic()+30)
    assert result['completed'] and result['calls']==2
    row=json.loads((store.root/'tools.jsonl').read_text().splitlines()[0])
    artifact=store.root/row['artifact']['path']
    assert json.loads(artifact.read_bytes())['action']==actions[0]
