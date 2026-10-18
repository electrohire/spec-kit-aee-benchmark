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
    if sys.platform=='win32' and action['action']=='shell':
        # Windows quoting into Git Bash differs from the actual Linux solver.
        # Run this small shell fixture in its real pinned image; expose only the
        # fresh test directory, never a repository or credentials.
        import shutil
        if not shutil.which('docker'):pytest.skip('Linux solver shell needs Docker on Windows')
        argv[0]='python'
        script='import json,subprocess\nr=subprocess.run('+repr(argv)+',capture_output=True,text=True)\nprint(json.dumps(dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)))'
        result=subprocess.run(['docker','run','--rm','-i','--network','none','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2',
            '--user','1000:1000','--mount','type=bind,source='+str(root.resolve())+',target=/testbed',
            'sha256:adc751293f079d2ed0a459cbeb36e2b746ef8382e23d0b04c1fa282b8cb2a120','python','-'],
            input=script,capture_output=True,text=True,encoding='utf-8',timeout=45)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
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
    argv=shlex.split(action_command(dict(action='shell',command='python -m pytest')))
    import base64
    assert base64.b64decode(argv[-1]).decode()=='python -m pytest'
    for action in ({'action':'shell','command':''},{'action':'done'},{'action':'unknown'}):
        with pytest.raises(ValueError):action_command(action)


@pytest.mark.parametrize('command',['x\x00y','λ'*MAX_WRITE_BYTES],ids=['nul','utf8-limit'])
def test_invalid_shell_transport_bounds(command):
    with pytest.raises(ValueError):action_command(dict(action='shell',command=command))


@pytest.mark.parametrize('command',[
    "printf damaged > before; cat > plan.md << 'EOF'",
    "printf damaged > before; cat > plan.md << 'EOF' && cat > research.md << 'EOF2'",
    "printf damaged > before; printf 'unterminated",
    'printf damaged > before; if true; then echo incomplete',
    'printf damaged > before; echo $(touch SUBSTITUTION; echo unfinished',
])
def test_shell_syntax_rejected_before_any_effect(tmp_path,command):
    plan=tmp_path/'plan.md';plan.write_text('preserve original')
    result=run_literal(dict(action='shell',command=command),tmp_path)
    assert result['exit_code']==2 and 'ShellSyntaxRejected' in result['stderr']
    assert plan.read_text()=='preserve original'
    assert not (tmp_path/'before').exists()
    assert not (tmp_path/'SUBSTITUTION').exists()
    assert not (tmp_path/'research.md').exists()


def test_shell_valid_heredoc_and_exit_status_preserved(tmp_path):
    result=run_literal(dict(action='shell',command="cat > plan.md << 'EOF'\nliteral $(touch BAD)\nEOF\nexit 7"),tmp_path)
    assert result['exit_code']==7
    assert (tmp_path/'plan.md').read_text()=='literal $(touch BAD)\n'
    assert not (tmp_path/'BAD').exists()


@pytest.mark.parametrize('claims',[True,False])
def test_native_schema_allows_literal_write_in_every_phase(claims):
    schema=action_response_format(claims)['json_schema']['schema']
    jsonschema.validate(dict(action='write_file',path='source.py',content='literal'),schema)
    for missing in ('content','path'):
        action=dict(action='write_file',path='source.py',content='literal');del action[missing]
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(action,schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(action='write_file',path='source.py',summary='not actual file content'),schema)


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


def test_phase_progress_observes_artifact_without_extra_model_calls(tmp_path):
    import repeated_local as runner
    actions=[dict(action='shell',command='inspect') for _ in range(8)]
    actions[4]=dict(action='write_file',path=runner.PHASE_ARTIFACTS['plan'],content='complete plan '*20)
    actions[7]=dict(action='done',summary='fixture only')
    class Provider:
        def __init__(self):self.calls=[];self.messages=[]
        def query(self,messages,*args):
            self.messages.extend(m['content'] for m in messages if 'PHASE PROGRESS:' in m['content'])
            action=actions[len(self.calls)];self.calls.append({});return json.dumps(action)
    class Box:
        present=False
        def execute(self,command,timeout=60):
            if command==runner.phase_artifact_check(runner.PHASE_ARTIFACTS['plan']):
                return dict(exit_code=0 if self.present else 1,stdout='',stderr='')
            if command==action_command(actions[4]):self.present=True
            return dict(exit_code=0,stdout='',stderr='')
    provider=Provider();store=runner.Store(tmp_path/'evidence')
    result=runner.Session(Box(),provider,store,'progress-fixture').phase('plan','fixture','scope',1,8,time.monotonic()+30)
    assert result['completed'] and result['calls']==8
    observations=[json.loads(x) for x in (store.root/'phase_progress.jsonl').read_text().splitlines()]
    assert [x['state'] for x in observations]==['missing_or_scaffold','present_basic_check_only']
    assert any('missing_or_scaffold' in m for m in provider.messages)
    assert any('present_basic_check_only' in m for m in provider.messages)
