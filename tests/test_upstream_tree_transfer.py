"""Thin transfer failure/accounting boundaries; real Dask control is separate."""
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from benchmark_runner.upstream_agent_adapter import AdmissionError
from benchmark_runner.upstream_docker_transport import PREFIX
from benchmark_runner.upstream_tree_transfer import export_tree, import_tree


def environment():
    return SimpleNamespace(config=SimpleNamespace(interpreter=PREFIX+['/bin/bash','-c'],
        forward_env=[], executable='docker'), container_id='controlled-fixture-container')


def test_corrupt_transfer_pack_never_starts_receiver(tmp_path, monkeypatch):
    import benchmark_runner.upstream_tree_transfer as module
    raw=b'PACK controlled fixture'
    exported=tmp_path/'export';exported.mkdir()
    (exported/'export.json').write_text(json.dumps(dict(tree='a'*40,returncode=0,
        pack_sha256=hashlib.sha256(raw).hexdigest(),pack_bytes=len(raw))))
    (exported/'tree.pack').write_bytes(raw+b'changed')
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:pytest.fail('receiver must not run'))
    with pytest.raises(AdmissionError,match='changed'):
        import_tree(environment(),exported,tmp_path/'receiver',
                    reader_python='/opt/miniconda3/envs/testbed/bin/python')
    assert not (tmp_path/'receiver').exists()


def test_timeout_retains_original_partial_bytes_without_retry(tmp_path,monkeypatch):
    import benchmark_runner.upstream_tree_transfer as module
    calls=[]
    def fail(argv,**kwargs):
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv,180,output=b'PACK partial',stderr=b'original diagnostic')
    monkeypatch.setattr(module.subprocess,'run',fail)
    with pytest.raises(subprocess.TimeoutExpired):
        export_tree(environment(),tmp_path/'export',tree='a'*40,
                    reader_python='/opt/miniconda3/envs/testbed/bin/python')
    assert len(calls)==1
    assert (tmp_path/'export/export-partial-stdout.bin').read_bytes()==b'PACK partial'
    assert (tmp_path/'export/export-partial-stderr.bin').read_bytes()==b'original diagnostic'
    assert json.loads((tmp_path/'export/export-failure.json').read_text())['retries']==0
