"""One separately authorized completion episode; never mutate or resume its parent.

Uses the parent's exact frozen Provider/judge/policies. Only the loopback port in
the pinned transport AST changes to the restored worker's separately bound port.
No service operations, fallback, retries or inference at import.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

PARENT_HEAD = 'c72d54f4b876454ab2c11216d74959b123a72a09'
TRANSPORT_SHA = '82d846121d7e280c6d4d89078ab6171628013b89d820388deed58b6a141e6ecc'
MISSING = [(9, 'spec_kit'), (91, 'baseline'), (99, 'spec_kit_aee'),
           (184, 'baseline'), (160, 'spec_kit'), (72, 'spec_kit'),
           (41, 'baseline'), (110, 'baseline'), (201, 'baseline')]


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_inventory(parent, inventory):
    expected = load(inventory)
    actual = {p.relative_to(parent).as_posix() for p in parent.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError('parent file membership changed')
    for name, digest in expected.items():
        path = (parent / name).resolve()
        if not path.is_relative_to(parent.resolve()) or sha(path) != digest:
            raise ValueError('parent retained bytes changed: ' + name)
    return len(expected)


def missing_cells(state, schedule):
    seen = [(r['index'], r['arm']) for r in state['rows']]
    pairs = [(r['index'], r['arm']) for r in schedule]
    if (state.get('complete') or not state.get('error') or len(seen) != 711
        or len(set(seen)) != 711 or len(pairs) != 720
        or len(set(pairs)) != 720 or seen != pairs[:711]
        or pairs[711:] != MISSING):
        raise ValueError('parent stop/schedule is not the registered 711+9 split')
    return schedule[711:]


def transport_code(source, port):
    if hashlib.sha256(source).hexdigest() != TRANSPORT_SHA:
        raise ValueError('unregistered parent transport source')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('invalid bound loopback port')
    tree = ast.parse(source)
    counts = [0, 0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value == 50467:
            node.value = port
            counts[0] += 1
        elif isinstance(node, ast.Constant) and node.value == 'http://127.0.0.1:50467':
            node.value = 'http://127.0.0.1:' + str(port)
            counts[1] += 1
    if counts != [4, 1]:
        raise ValueError('transport literal migration shape changed')
    return compile(tree, '<registered-port-only-transport-migration>', 'exec'), counts


def install_transport(source_root, binding):
    value = load(binding)
    endpoint = value['endpoint']
    port = int(endpoint.removeprefix('http://127.0.0.1:'))
    if endpoint != f'http://127.0.0.1:{port}':
        raise ValueError('recovery requires literal IPv4 loopback')
    path = source_root / 'scripts/direct_worker_transport.py'
    code, counts = transport_code(path.read_bytes(), port)
    module = types.ModuleType('direct_worker_transport')
    exec(code, module.__dict__)
    sys.modules['direct_worker_transport'] = module
    instance = module.WorkerBinding(binding)
    return dict(port=port, parent_transport_sha256=sha(path), literal_replacements=counts,
                binding_sha256=instance.sha256)


def validate_readiness(folder, binding, controller):
    state, freeze = load(folder / 'result.json'), load(folder / 'recovery-freeze.json')
    calls = [load(p) for p in (folder / 'calls').glob('call-*.json')]
    if (not state.get('complete') or state.get('error') or not state.get('technical')
        or state.get('physical_calls') != 3 or len(calls) != 3
        or freeze['migration']['binding_sha256'] != sha(binding)
        or freeze['controller_sha256'] != sha(controller)
        or any(c.get('error') or not c.get('ended_at') or not c.get('usage') for c in calls)):
        raise ValueError('fresh exact-source/binding native readiness missing')


def execute(source_root, parent, inventory, binding, output, authorization, technical, readiness=None):
    source_root, parent = source_root.resolve(), parent.resolve()
    if parent != source_root / 'artifacts/matched-hallucinations-03':
        raise ValueError('unexpected original source/parent')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source_root, text=True).strip() != PARENT_HEAD:
        raise ValueError('parent source head changed')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source_root).strip():
        raise ValueError('parent source dirty')
    if load(authorization)['exact_user_reply'] != 'Restore worker and finish missing 9 (Recommended)':
        raise ValueError('actual one-time authorization missing')
    own = Path(__file__).resolve()
    own_sha = sha(own)
    if not technical:
        if readiness is None:
            raise ValueError('separate technical admission required before scored recovery')
        validate_readiness(readiness, binding, own)
    if sha(inventory) != 'b09e7331d58f7ebe1a57b4dd8b1364245d56dbf8efa19815a6d849c664caa1f6':
        raise ValueError('parent stop inventory changed')
    verify_inventory(parent, inventory)
    suffix = missing_cells(load(parent / 'result.json'), load(parent / 'schedule.json'))
    sys.path[:0] = [str(source_root / 'scripts'), str(source_root / 'src')]
    migration = install_transport(source_root, binding)
    import matched_hallucinations as m
    plan, cases = m.verify(parent)
    started = load(parent / 'run-started.json')
    for name, version in started['versions'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('installed baseline dependency changed: ' + name)
    if m.source_hashes() != started['source_hashes']:
        raise ValueError('parent declared source changed')
    for name, digest in started['source_hashes'].items():
        if sha(parent / 'source-archive' / name) != digest:
            raise ValueError('parent source archive changed')
    m.current.configure_worker_binding(binding)
    if any(slot.get('is_processing') for slot in m.current.http('/slots')):
        raise ValueError('worker busy; no overlap')
    if sha(m.current.WEIGHTS) != started['weights_sha256']:
        raise ValueError('weights changed')
    output.mkdir(parents=True, exist_ok=False)
    for name in ('cases.json', 'schedule.json', 'plan.json', 'input-hashes.json'):
        shutil.copyfile(parent / name, output / name)
    m.write_json(output / 'recovery-freeze.json', dict(at=m.utc(), parent=str(parent),
        parent_inventory_sha256=sha(inventory), controller_sha256=sha(own),
        controller_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=own.parents[1], text=True).strip(),
        authorization_sha256=sha(authorization), migration=migration,
        schedule=suffix, maximum_calls=3 if technical else 18, technical=technical,
        interpretation='Separate worker epoch; original03 remains stopped. No independent replication or release equivalence.'), exclusive=True)
    os.environ['SPECKIT_AEE_AUTO_INSTALL'] = '0'
    provider = m.Provider(output, {**plan, 'maximum_calls': 3 if technical else 18,
                                  'decoder_probe': technical})
    state = dict(complete=False, rows=[], physical_calls=0, error=None, technical=technical)
    m.write_json(output / 'result.json', state, exclusive=True)
    try:
        if technical:
            from matched_grammar import native_probe_contracts
            for test in native_probe_contracts():
                value, path = provider.call([
                    dict(role='system', content='Return only a JSON object matching the native decoder contract.'),
                    dict(role='user', content=test['instruction'])], test['schema'], test['output'],
                    dict(cohort='setup', dataset='native_bounds_probe', arm='baseline', phase='recovery_probe'))
                state['rows'].append(dict(call=path.name, value=value))
        else:
            for order, entry in enumerate(suffix, 711):
                index, arm = entry['index'], entry['arm']
                case = cases[index]
                policy = load(parent / 'policies' / case['dataset'] / arm / 'policy.json')['documents']
                row = m.judge(provider, output / 'judgments' / f'case-{index:04}-{arm}', arm,
                    case['dataset'], case, policy, 'scored', index)
                row.update(index=index, schedule_order=order, worker_epoch='authorized-recovery-04')
                state['rows'].append(row)
                state['physical_calls'] = provider.count
                m.write_json(output / 'result.json', state)
        if provider.count != (3 if technical else 18):
            raise ValueError('unexpected recovery physical call count')
        verify_inventory(parent, inventory)
        if sha(own) != own_sha or m.source_hashes() != started['source_hashes']:
            raise ValueError('parent source changed')
        state.update(complete=True, stage='complete_pending_independent_audit')
    except BaseException as exc:
        state.update(stage='halted', error=repr(exc))
        raise
    finally:
        state.update(ended_at=m.utc(), physical_calls=provider.count)
        m.write_json(output / 'result.json', state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('source-root', 'parent', 'inventory', 'binding', 'output', 'authorization'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--technical', action='store_true')
    parser.add_argument('--readiness', type=Path)
    args = parser.parse_args()
    execute(args.source_root, args.parent, args.inventory, args.binding, args.output, args.authorization, args.technical, args.readiness)
