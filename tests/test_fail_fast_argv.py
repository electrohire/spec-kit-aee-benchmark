"""Prospective fail-fast policy and literal argv; no model inference."""
import json
import shlex
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from action_protocol import action_command, action_response_format
from runtime_checks import RuntimeIntervention, RuntimeWatchdog
import repeated_local as runner


def test_exec_preserves_quoted_arguments_without_shell_expansion(tmp_path):
    values = ['"quoted phrase"', 'a b', '$(touch BAD)', '; touch BAD', '\n', 'λ']
    action = dict(action='exec', argv=[sys.executable, '-c',
        'import json,sys;print(json.dumps(sys.argv[1:]))', *values])
    for claims in (False, True):
        jsonschema.validate(action, action_response_format(claims)['json_schema']['schema'])
    args = shlex.split(action_command(action)); args[0] = sys.executable
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == values
    assert not (tmp_path / 'BAD').exists()


@pytest.mark.parametrize('argv', [None, [], [''], ['echo', None], ['echo', 'a\x00b'], ['x'] * 129, ['echo', 'x' * 65536]])
def test_exec_rejects_malformed_or_unbounded_arguments(argv):
    with pytest.raises(ValueError):
        action_command(dict(action='exec', argv=argv))


@pytest.mark.parametrize('exit_code', [1, 2, -9, None, True])
def test_failed_tool_stops_on_first_observation(tmp_path, exit_code):
    guard = RuntimeWatchdog(tmp_path, fail_fast=True)
    with pytest.raises(RuntimeIntervention, match='tool execution failed'):
        guard.tool('fixture', dict(exit_code=exit_code, stdout='', stderr='failure'), 'specify', 1)
    alert = json.loads((tmp_path / 'runtime-alert.json').read_text())
    assert alert['exit_code'] == exit_code


def test_invalid_action_stops_before_second_model_call(tmp_path):
    class Provider:
        def __init__(self): self.calls = []
        def query(self, *args):
            self.calls.append({})
            return 'not JSON'
    provider = Provider()
    session = runner.Session(None, provider, runner.Store(tmp_path / 'store'), 'fixture')
    session.watchdog = RuntimeWatchdog(tmp_path / 'run', fail_fast=True)
    with pytest.raises(RuntimeIntervention):
        session.phase('specify', 'fixture', 'requirements', 1, 20, 100)
    assert len(provider.calls) == 1


def test_second_identical_successful_action_stops(tmp_path):
    guard = RuntimeWatchdog(tmp_path, fail_fast=True)
    guard.tool('fixture', dict(exit_code=0, stdout='same'), 'plan', 1)
    with pytest.raises(RuntimeIntervention, match='identical action'):
        guard.tool('fixture', dict(exit_code=0, stdout='same'), 'plan', 1)


def test_missing_grep_operand_receipt_retained_and_no_second_query(tmp_path):
    class Provider:
        def __init__(self): self.calls = []
        def query(self, *args):
            self.calls.append({})
            return json.dumps(dict(action='shell', command='cd /testbed && grep -n '))
    class Box:
        def execute(self, *args):
            return dict(exit_code=2, stdout='', stderr='Usage: grep PATTERNS [FILE]...')
    provider = Provider()
    session = runner.Session(Box(), provider, runner.Store(tmp_path / 'store'), 'fixture')
    session.watchdog = RuntimeWatchdog(tmp_path / 'run', fail_fast=True)
    with pytest.raises(RuntimeIntervention, match='tool execution failed'):
        session.phase('specify', 'fixture', 'requirements', 1, 20, 100)
    assert len(provider.calls) == 1
    assert len((tmp_path / 'store/tools.jsonl').read_text().splitlines()) == 1
