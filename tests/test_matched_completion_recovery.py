"""Thin recovery admission tests: no model, gold answers or service operations."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT / 'scripts/matched_completion_recovery.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def fixture():
    suffix = [dict(index=i, arm=a) for i, a in r.MISSING]
    prefix = [dict(index=i, arm='baseline') for i in range(1000, 1711)]
    return dict(complete=False, error='connection_reset', rows=copy.deepcopy(prefix)), prefix + suffix


def test_only_registered_suffix():
    state, schedule = fixture()
    assert r.missing_cells(state, schedule) == schedule[711:]


@pytest.mark.parametrize('change', ['completed', 'noerror', 'duplicate', 'reorder', 'extra', 'wrongarm'])
def test_changed_parent_refused(change):
    state, schedule = fixture()
    if change == 'completed': state['complete'] = True
    if change == 'noerror': state['error'] = None
    if change == 'duplicate': state['rows'][1] = state['rows'][0]
    if change == 'reorder': schedule[-1], schedule[-2] = schedule[-2], schedule[-1]
    if change == 'extra': schedule.append(dict(index=9999, arm='baseline'))
    if change == 'wrongarm': schedule[-1]['arm'] = 'spec_kit'
    with pytest.raises(ValueError): r.missing_cells(state, schedule)


def test_original_transport_pin_and_ast_only_port():
    source = (ROOT / 'scripts/direct_worker_transport.py').read_bytes()
    code, counts = r.transport_code(source, 52301)
    assert counts == [4, 1]
    namespace = {}
    exec(code, namespace)
    assert namespace['ENDPOINT'] == 'http://127.0.0.1:52301'
    binding = dict(protocol='existing-qwen-worker-v1', endpoint=namespace['ENDPOINT'],
        model='qwen3.8-27b', weights='C:/Models/qwen3.8-27b.gguf', pid=123,
        creation_filetime=456, executable='C:/LLM/llama/llama-server.exe')
    namespace['validate_observation'](binding, {**binding, 'listeners': [dict(address='127.0.0.1', port=52301, pid=123)]})
    with pytest.raises(RuntimeError):
        namespace['validate_observation'](binding, {**binding, 'listeners': [dict(address='127.0.0.1', port=50467, pid=123)]})
    # Disassembly constant graph preserves every other value/function; source pin
    # prevents expanding the migration to a changed historical transport.
    original, _ = r.transport_code(source, 50467)
    def constants(c):
        return [(x.co_name, constants(x)) if hasattr(x, 'co_consts') else
                50467 if type(x) is int and x == 52301 else
                'http://127.0.0.1:50467' if x == 'http://127.0.0.1:52301' else x
                for x in c.co_consts]
    assert constants(code) == constants(original)
    with pytest.raises(ValueError): r.transport_code(source + b'\n', 52301)


@pytest.mark.parametrize('port', [True, 0, 80, 65536, '52301'])
def test_bad_port_refused(port):
    with pytest.raises(ValueError): r.transport_code((ROOT / 'scripts/direct_worker_transport.py').read_bytes(), port)


def test_inventory_membership_and_mutation(tmp_path):
    parent = tmp_path / 'parent'; parent.mkdir(); p = parent / 'retained'; p.write_bytes(b'old')
    inv = tmp_path / 'inventory.json'; inv.write_text(json.dumps({'retained': r.sha(p)}))
    assert r.verify_inventory(parent, inv) == 1
    p.write_bytes(b'changed')
    with pytest.raises(ValueError): r.verify_inventory(parent, inv)
    p.write_bytes(b'old'); (parent / 'new').write_bytes(b'new')
    with pytest.raises(ValueError): r.verify_inventory(parent, inv)


@pytest.mark.parametrize('fault', ['binding', 'controller', 'incomplete', 'unknown', 'error'])
def test_bad_readiness_refused(tmp_path, fault):
    binding = tmp_path / 'binding'; binding.write_text('binding')
    controller = tmp_path / 'controller'; controller.write_text('controller')
    freeze = dict(migration=dict(binding_sha256=r.sha(binding)), controller_sha256=r.sha(controller))
    state = dict(complete=True, error=None, technical=True, physical_calls=3)
    calls = [dict(ended_at='now', usage=dict(total_tokens=1)) for _ in range(3)]
    if fault == 'binding': freeze['migration']['binding_sha256'] = 'wrong'
    if fault == 'controller': freeze['controller_sha256'] = 'wrong'
    if fault == 'incomplete': state['complete'] = False
    if fault == 'unknown': calls[0]['usage'] = None
    if fault == 'error': calls[0]['error'] = 'failed'
    (tmp_path / 'calls').mkdir()
    (tmp_path / 'result.json').write_text(json.dumps(state))
    (tmp_path / 'recovery-freeze.json').write_text(json.dumps(freeze))
    for i, c in enumerate(calls): (tmp_path / 'calls' / f'call-{i}.json').write_text(json.dumps(c))
    with pytest.raises(ValueError): r.validate_readiness(tmp_path, binding, controller)
