"""Read-only stopped03 accounting and exact retained-snapshot grades; no inference."""
import ast
from collections import Counter
import datetime
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent / 'work/spec-kit-aee-benchmark'
RAW = ROOT / 'artifacts/current-study-03'
OUT = ROOT / 'artifacts/study03-postmortem-01'
OUT.mkdir(exist_ok=False)
sys.path.insert(0, str(ROOT / 'scripts'))
import current_local as current
from benchmark_runner.store import Store


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def inventory():
    return {p.relative_to(RAW).as_posix(): sha(p) for p in RAW.rglob('*') if p.is_file()}


def forbidden(*args, **kwargs):
    raise AssertionError('No model/provider/HTTP calls in stopped-study postmortem')


current.http = forbidden
current.runner.local_json = forbidden
runner = current.runner
freeze = json.loads((RAW / 'freeze.json').read_bytes())
assert sha(RAW / 'freeze.json') == '107b6bb7982929a4d2e3c32fb525088db6285114a8893cbecfc399e2c46819ae'
assert json.loads((ROOT / 'artifacts/current-pipeline-10.json').read_bytes())['stage'] == 'intervention_required'
assert len(freeze['schedule']) == 12 and len(freeze['hashes']) == 353
before = inventory()
for name, digest in freeze['hashes'].items():
    assert sha(RAW / 'frozen-inputs' / name) == digest
old = ast.parse((RAW / 'frozen-inputs/scripts/repeated_local.py').read_text())
nodes = {n.name: n for n in old.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
bindings = {}
for name in ('tests_for', 'ProjectSandbox', 'grade'):
    actual = ast.parse(inspect.getsource(getattr(runner, name))).body[0]
    text = ast.dump(actual, include_attributes=False)
    assert text == ast.dump(nodes[name], include_attributes=False)
    bindings[name] = hashlib.sha256(text.encode()).hexdigest()
assert runner.PROJECTS == freeze['projects'] and runner.IMAGE == freeze['image']
assert subprocess.check_output(['docker', 'image', 'inspect', runner.IMAGE, '--format', '{{.Id}}'], text=True).strip() == runner.IMAGE
for project, meta in runner.PROJECTS.items():
    assert subprocess.check_output(['git', '-C', str(ROOT / meta['upstream']), 'rev-parse', 'HEAD'], text=True).strip() == meta['revision']
    for stage in (1, 2, 3):
        for public in (True, False):
            mode = 'public' if public else 'hidden'
            assert hashlib.sha256(runner.tests_for(project, stage, public)).hexdigest() == freeze['calibration']['projects'][project]['reference'][f'{stage}-{mode}']['grader_source_sha256']
streams = []
for directory in RAW.glob('*/evidence'):
    store = Store(directory)
    for file in directory.glob('*.jsonl'):
        streams.append(dict(path=file.relative_to(RAW).as_posix(), verification=store.verify_stream(file.stem)))
attempts = json.loads((RAW / 'attempts.json').read_bytes())
by_key = {(r['project'], r['seed'], r['arm'], r['stage']): r for r in attempts}
calls = [(p, json.loads(p.read_bytes())) for p in RAW.glob('*/call-*.json')]
assert len(calls) == 98 and all(r.get('ended_at') and r.get('usage') for _, r in calls)
counts = Counter((p.parent.name, r['stage']) for p, r in calls)
state = dict(complete=False, started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    purpose='Stopped03 postmortem; exact retained source, no resume, model calls or repair',
    freeze_sha256=sha(RAW / 'freeze.json'), controller_sha256=sha(Path(__file__)),
    source_freeze='deb5723c5431a13b94a4aac25f4c4307fcc13685', frozen_input_count=353,
    grader_function_ast_hashes=bindings, streams=streams, generation_calls=len(calls),
    known_prompt_tokens=sum(r['usage']['prompt_tokens'] for _, r in calls),
    known_completion_tokens=sum(r['usage']['completion_tokens'] for _, r in calls),
    generation_usage_unknown=0, rows=[], grades=[], inference_requests=0)
state['known_total_tokens'] = state['known_prompt_tokens'] + state['known_completion_tokens']
write('run.json', state)
try:
    for project, seed, arm in freeze['schedule']:
        trajectory = f'{project}-{seed}-{arm}'
        for stage in (1, 2, 3):
            recorded = by_key.get((project, seed, arm, stage))
            row = dict(project=project, seed=seed, arm=arm, stage=stage,
                generation_calls=counts.get((trajectory, stage), 0),
                completion_asserted=recorded.get('completion_asserted') if recorded else None,
                accepted_project_delivery='not_observed', assessments=len(recorded.get('assessments', [])) if recorded else 0,
                grade_status='ungraded', final_proxy_eligible=False)
            snapshot = None
            if recorded is None:
                row['status'] = 'not_attempted_infrastructure_halt'
            elif recorded.get('status') == 'not_attempted_dependent':
                row['status'] = 'not_attempted_dependent'
            elif recorded.get('final_snapshot'):
                row['status'] = recorded.get('status') or 'recorded_checkpoint'
                snapshot = RAW / recorded['final_snapshot']
                row['snapshot_kind'] = 'retained_final_after_model_intervention'
            else:
                row['status'] = 'infrastructure_interrupted_partial'
                candidate = RAW / trajectory / 'runtime-stopped.tar'
                if candidate.is_file():
                    snapshot = candidate
                    row['snapshot_kind'] = 'partial_at_infrastructure_halt_not_submitted_final'
            if snapshot is not None:
                row.update(snapshot=snapshot.relative_to(RAW).as_posix(), snapshot_sha256=sha(snapshot), grades={})
                complete_inventory = True
                for public in (True, False):
                    mode = 'public' if public else 'hidden'
                    gold = freeze['calibration']['projects'][project]['reference'][f'{stage}-{mode}']
                    grade = current.bound_grade(project, snapshot, stage, public, gold['test_count'])
                    assert grade['source_sha256'] == row['snapshot_sha256']
                    assert grade['grader_source_sha256'] == gold['grader_source_sha256']
                    assert grade['grader_function_sha256'] == gold['grader_function_sha256']
                    identities = lambda cases: Counter((c.get('file'), c['name']) for c in cases)
                    complete = identities(grade['cases']) == identities(gold['cases']) and grade['exit_code'] in (0, 1) and not any(f['kind'] in ('error', 'skipped') for c in grade['cases'] for f in c.get('failures', []))
                    complete_inventory &= complete
                    name = f'grade-{trajectory}-stage{stage}-{mode}.json'
                    write(name, grade)
                    value = dict(path=name, sha256=sha(OUT / name), passed=grade['passed'],
                        test_count=grade['test_count'], expected_test_count=gold['test_count'], exit_code=grade['exit_code'],
                        complete_inventory=complete)
                    row['grades'][mode] = value
                    state['grades'].append(dict(project=project, seed=seed, arm=arm, stage=stage, mode=mode, **value))
                row.update(grade_status='complete_test_inventory' if complete_inventory else 'incomplete_test_inventory',
                    complete_test_inventory=bool(complete_inventory),
                    final_proxy_eligible=bool(complete_inventory and recorded.get('final_snapshot')),
                    checkpoint_code_tests_passed=complete_inventory and all(g['passed'] for g in row['grades'].values()))
            if row['status'].startswith('not_attempted'):
                assert row['generation_calls'] == 0
            state['rows'].append(row)
            write('run.json', state)
    eligible = [r for r in state['rows'] if r['final_proxy_eligible']]
    state.update(complete=True, stopped_artifacts_unchanged=inventory() == before,
        statuses=dict(Counter(r['status'] for r in state['rows'])),
        attempted_checkpoints=sum(not r['status'].startswith('not_attempted') for r in state['rows']),
        unattempted_checkpoints=sum(r['status'].startswith('not_attempted') for r in state['rows']),
        scored_actual_AEE_assessments=sum(r['assessments'] for r in state['rows']),
        final_completion_proxy=dict(positive=sum(r['completion_asserted'] is True for r in eligible),
            negative=sum(r['completion_asserted'] is False for r in eligible),
            unknown=sum(r['completion_asserted'] is None for r in eligible), ungraded=36-len(eligible)),
        accepted_final_delivery=0, paired_efficacy='unmeasured; infrastructure-censored incomplete campaign',
        hallucination_rate=None, detector_precision=None, detector_recall=None,
        local_API_spend=0, cost_boundary='Scored03 only; setup/older failed campaigns separate. Excludes hardware, energy and labor.')
    assert len(state['rows']) == 36 and sum(r['generation_calls'] for r in state['rows']) == 98
    assert state['stopped_artifacts_unchanged']
    write('stopped-input-sha256.json', before)
    write('checkpoint-rows.json', state['rows'])
except BaseException as exc:
    state['error'] = repr(exc)
    raise
finally:
    state['ended_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write('run.json', state)
print(json.dumps({k: v for k, v in state.items() if k not in ('rows', 'grades', 'streams')}, indent=2))
