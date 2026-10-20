"""Checkpoint integrity boundaries; real filesystem/Git control is separate."""
import base64
import hashlib
import json

import pytest

from benchmark_runner.upstream_agent_adapter import AdmissionError
from benchmark_runner.upstream_snapshot import capture_snapshot


class Bridge:
    def __init__(self, result):
        self.result = result
        self.commands = []

    def execute(self, action, **kwargs):
        self.commands.append(action['command'])
        return self.result


def response(patch=b'controlled fixture patch\n'):
    return dict(returncode=0, exception_info='', output=json.dumps(dict(
        baseline_commit='a'*40, uid=999, patch_base64=base64.b64encode(patch).decode(),
        patch_bytes=len(patch), patch_sha256=hashlib.sha256(patch).hexdigest())))


def test_original_response_patch_and_reader_are_bound(tmp_path):
    bridge = Bridge(response())
    result = capture_snapshot(bridge, tmp_path/'snapshot', baseline_commit='a'*40,
                              reader_python='/usr/bin/python3')
    assert (tmp_path/'snapshot/candidate.patch').read_bytes() == b'controlled fixture patch\n'
    raw = (tmp_path/'snapshot/reader-response.json').read_bytes()
    assert result['reader_response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert "-I -S" in bridge.commands[0]
    with pytest.raises(FileExistsError):
        capture_snapshot(bridge, tmp_path/'snapshot', baseline_commit='a'*40,
                         reader_python='/usr/bin/python3')


def test_failed_reader_is_retained_without_candidate(tmp_path):
    bridge = Bridge(dict(returncode=1, exception_info='', output='reader failed'))
    with pytest.raises(AdmissionError, match='reader failed'):
        capture_snapshot(bridge, tmp_path/'snapshot', baseline_commit='a'*40,
                         reader_python='/usr/bin/python3')
    assert (tmp_path/'snapshot/reader-response.json').exists()
    assert not (tmp_path/'snapshot/candidate.patch').exists()


def test_changed_patch_hash_is_not_published(tmp_path):
    raw = response()
    value = json.loads(raw['output'])
    value['patch_sha256'] = '0'*64
    raw['output'] = json.dumps(value)
    with pytest.raises(AdmissionError, match='integrity'):
        capture_snapshot(Bridge(raw), tmp_path/'snapshot', baseline_commit='a'*40,
                         reader_python='/usr/bin/python3')
    assert (tmp_path/'snapshot/reader-response.json').exists()
    assert not (tmp_path/'snapshot/candidate.patch').exists()
