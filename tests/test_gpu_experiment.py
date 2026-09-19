"""Regression checks for observed hazards in the unvalidated local draft."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import gpu_experiment as gpu


def test_failed_call_is_durable_and_unknown(tmp_path, monkeypatch):
    def fail(*args):
        raise TimeoutError('fixture')
    monkeypatch.setattr(gpu, 'local_json', fail)
    path = tmp_path/'call.json'
    with pytest.raises(TimeoutError):
        gpu.query([], 10, 1, path)
    record = json.loads(path.read_text())
    assert record['usage'] is None
    assert record['unknown_reason'] == 'interrupted_or_failed_request'
    assert record['seconds'] >= 0
    assert record['request']['max_tokens'] == 10


def test_truncation_preserves_usage_but_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu, 'local_json', lambda *a: dict(
        usage=dict(prompt_tokens=20, completion_tokens=10),
        choices=[dict(finish_reason='length', message=dict(content='partial'))]))
    with pytest.raises(RuntimeError, match='incomplete_response'):
        gpu.query([], 10, 1, tmp_path/'call.json')
    assert json.loads((tmp_path/'call.json').read_text())['usage']['completion_tokens'] == 10


@pytest.mark.parametrize('output,expected,passed', [
    ('Ran 0 tests in 0.0s\nOK', 1, False),
    ('Ran 1 test in 0.0s\nOK (skipped=1)', 1, False),
    ('Ran 1 test in 0.0s\nOK', 2, False),
    ('Ran 2 tests in 0.0s\nOK', 2, True),
])
def test_grading_requires_expected_real_tests(monkeypatch, output, expected, passed):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return Mock(returncode=0, stdout=b'', stderr=output.encode())
    monkeypatch.setattr(gpu.subprocess, 'run', run)
    result = gpu.grade('def hello(): return "hello"', b'', 'hello', 'python@sha256:fixture', expected_count=expected)
    assert result['passed'] is passed
    assert '--network' in calls[0] and 'none' in calls[0]
    assert '--read-only' in calls[0] and '--cap-drop' in calls[0]
    assert '--mount' not in calls[0] and '-v' not in calls[0]
    assert calls[-1][:3] == ['docker', 'rm', '-f']


def test_redirect_is_forbidden():
    with pytest.raises(ValueError, match='Redirects forbidden'):
        gpu.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')
