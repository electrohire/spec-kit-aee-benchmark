"""Fail-closed local route checks; native Windows observation tested separately."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import direct_worker_transport as direct
import launch_benchmark_mission as mission


def binding():
    return dict(protocol='existing-qwen-worker-v1', endpoint=direct.ENDPOINT,
                model=direct.MODEL, weights=direct.WEIGHTS, pid=123,
                creation_filetime=456, executable='C:/LLM/llama/llama-server.exe')


def observation():
    return dict(pid=123, creation_filetime=456, executable='C:/LLM/llama/llama-server.exe',
                listeners=[dict(address='127.0.0.1', port=50467, pid=123)])


@pytest.mark.parametrize('key,value', [('endpoint', 'http://example.com'), ('model', 'other'),
    ('weights', 'C:/Models/other.gguf'), ('pid', True), ('pid', -1),
    ('creation_filetime', '456'), ('executable', 'C:/other.exe')])
def test_binding_refuses_other_routes_or_identity(key, value):
    item = binding(); item[key] = value
    with pytest.raises(ValueError):
        direct.validate_binding(item)


@pytest.mark.parametrize('change', [dict(pid=124), dict(creation_filetime=457),
    dict(executable='C:/other.exe'), dict(listeners=[]),
    dict(listeners=[dict(address='127.0.0.1', port=50467, pid=124)]),
    dict(listeners=[dict(address='0.0.0.0', port=50467, pid=123)])])
def test_pid_reuse_port_reassignment_and_unavailable_worker_halt(change):
    item = observation(); item.update(change)
    with pytest.raises(RuntimeError):
        direct.validate_observation(binding(), item)


def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(direct, 'native_observation', lambda pid: observation())
    path = tmp_path / 'worker-binding.json'; path.write_text(json.dumps(binding()))
    return direct.WorkerBinding(path)


def test_binding_bytes_must_remain_unchanged(tmp_path, monkeypatch):
    pin = worker(tmp_path, monkeypatch)
    pin.check()
    pin.path.write_text(json.dumps(binding()) + '\n')
    with pytest.raises(RuntimeError, match='bytes changed'):
        pin.check()


def test_model_and_weights_rechecked(tmp_path, monkeypatch):
    pin = worker(tmp_path, monkeypatch)
    models = dict(data=[dict(id=direct.MODEL)])
    pin.check_model(models, dict(model_path=direct.WEIGHTS))
    for changed, props in [(dict(data=[dict(id='other')]), dict(model_path=direct.WEIGHTS)),
                           (models, dict(model_path='C:/other.gguf'))]:
        with pytest.raises(RuntimeError):
            pin.check_model(changed, props)


def test_route_requires_bound_prospective_admission_and_both_fresh_probes(tmp_path, monkeypatch):
    pin = worker(tmp_path, monkeypatch)
    admission = dict(recovery_protocol='direct-worker-v1', hashes={'worker-binding.json': pin.sha256})
    (tmp_path / 'admission.json').write_text(json.dumps(admission))
    proof = dict(passed=True, generation_requests=0, binding_sha256=pin.sha256,
                 rows=[dict(source=str(i), original_count=10, direct_count=10) for i in range(98)])
    (tmp_path / 'direct-route-proof.json').write_text(json.dumps(proof))
    for name in ('transport', 'latency'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'freeze.json').write_text(json.dumps(dict(worker_binding_sha256=pin.sha256, config=dict(url=direct.ENDPOINT))))
    direct.admit_route(tmp_path, pin, 'http://127.0.0.1:8081', direct.ENDPOINT)
    (tmp_path / 'latency/freeze.json').write_text('{}')
    with pytest.raises(ValueError, match='fresh direct-worker'):
        direct.admit_route(tmp_path, pin, 'http://127.0.0.1:8081', direct.ENDPOINT)
    admission['recovery_protocol'] = 'infrastructure-recovery-v1'
    (tmp_path / 'admission.json').write_text(json.dumps(admission))
    with pytest.raises(ValueError, match='unregistered route'):
        direct.admit_route(tmp_path, pin, 'http://127.0.0.1:8081', direct.ENDPOINT)


def test_route_proof_cannot_relabel_changed_counts_as_equivalent(tmp_path, monkeypatch):
    pin = worker(tmp_path, monkeypatch)
    proof = dict(passed=True, generation_requests=0, binding_sha256=pin.sha256,
                 rows=[dict(source=str(i), original_count=10, direct_count=10) for i in range(98)])
    proof['rows'][-1]['direct_count'] = 11
    path = tmp_path / 'proof.json'; path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match='equivalence proof'):
        direct.validate_route_proof(path, pin)


def test_serial_direct_plan_uses_corrected_corpus_without_changing_old_plan(tmp_path):
    p = mission.paths(tmp_path, 11, 4)
    original = mission.plan(p)
    assert all('--worker-binding' not in argv for _, argv in original)
    updated = mission.plan(p, tmp_path / 'binding.json')
    for stage, argv in updated:
        assert ('--worker-binding' in argv) == (stage != 'image')
        if stage == 'hallucination':
            assert argv[-2:] == ['--corpus-version', '2']
    assert len(updated) == 6


def test_http_guard_failure_prevents_any_network_request(tmp_path, monkeypatch):
    import current_local as current
    class Refusal:
        def check(self):
            raise RuntimeError('process changed')
    monkeypatch.setattr(current, 'WORKER_BINDING', Refusal())
    monkeypatch.setattr(current.urllib.request, 'build_opener', lambda *a: pytest.fail('network after refused binding'))
    with pytest.raises(RuntimeError, match='process changed'):
        current.http('/v1/chat/completions', {})
