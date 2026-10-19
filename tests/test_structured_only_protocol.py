import json
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from action_protocol import action_command,action_response_format
import repeated_local as runner
import current_local as current
from runtime_checks import RuntimeIntervention,RuntimeWatchdog


@pytest.mark.parametrize('claims',[False,True])
def test_current_native_grammar_rejects_command_strings_but_accepts_literal_argv(claims):
    schema=action_response_format(claims,structured=True)['json_schema']['schema']
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(action='shell',command='grep -n '),schema)
    jsonschema.validate(dict(action='exec',argv=['grep','-n','search text','relative/file.txt']),schema)
    assert current.Provider.structured_actions is True
    if not claims:assert current.ACTION_RESPONSE_FORMAT==action_response_format(False,structured=True)


@pytest.mark.parametrize('action',[
    dict(action='shell',command='grep -n '),
    dict(action='exec',argv=['bash','-lc','grep -n ']),
    dict(action='exec',argv=['sh','-c','grep -n ']),
    dict(action='exec',argv=['/bin/bash','-xc','grep -n ']),
    dict(action='exec',argv=['env','PYTHONPATH=src:.','bash','-lc','grep -n ']),
    dict(action='exec',argv=['env','-S','bash -lc grep']),
    dict(action='exec',argv=['bash'])])
def test_executor_rejects_command_string_escape_before_execution(action):
    with pytest.raises(ValueError):action_command(action,allow_shell=False)


def test_named_bash_scripts_and_python_helpers_still_supported():
    assert action_command(dict(action='exec',argv=['bash','.specify/scripts/bash/create-new-feature.sh','--json']),allow_shell=False)
    assert action_command(dict(action='exec',argv=['python','helper.py']),allow_shell=False)
    assert action_command(dict(action='exec',argv=['env','PYTHONPATH=src:.','python','helper.py']),allow_shell=False)
    assert action_command(dict(action='exec',argv=['bash','script.sh','-c','literal script argument']),allow_shell=False)


def test_schema_escape_response_cannot_reach_sandbox_or_second_query(tmp_path):
    class Provider:
        structured_actions=True
        def __init__(self):self.calls=[]
        def query(self,*args):
            self.calls.append({})
            return json.dumps(dict(action='shell',command='grep -n '))
    class Box:
        def execute(self,*args):pytest.fail('no tool execution allowed')
    provider=Provider()
    session=runner.Session(Box(),provider,runner.Store(tmp_path/'store'),'fixture')
    session.watchdog=RuntimeWatchdog(tmp_path/'run',fail_fast=True)
    with pytest.raises(RuntimeIntervention):session.phase('specify','fixture','scope',1,20,100)
    assert len(provider.calls)==1
