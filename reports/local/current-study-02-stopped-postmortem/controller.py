"""Independent postmortem of retained snapshots; never resumes a campaign.

No provider or model request is permitted. Outputs are outside stopped artifacts.
"""
import ast
from collections import Counter
import datetime
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
sys.path.insert(0, str(root/'scripts'))
import current_local as current
from benchmark_runner.store import Store

raw = root/'artifacts/current-study-02'
out = root/'artifacts/study02-postmortem-01'
out.mkdir(exist_ok=False)
freeze_sha = 'e2d4e0e644328e03ea99f5f8af24dbe781e7a5d41f709437a065425881036c0b'
freeze = json.loads((raw/'freeze.json').read_bytes())
assert hashlib.sha256((raw/'freeze.json').read_bytes()).hexdigest() == freeze_sha
assert len(freeze['hashes']) == 348 and len(freeze['schedule']) == 12
assert json.loads((root/'artifacts/current-pipeline-09.json').read_bytes())['stage'] == 'intervention_required'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (out/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

def inventory():
    return {p.relative_to(raw).as_posix():sha(p) for p in raw.rglob('*') if p.is_file()}

before = inventory()
for name, digest in freeze['hashes'].items():
    assert sha(raw/'frozen-inputs'/name) == digest, name

def forbidden(*args, **kwargs):
    raise AssertionError('Postmortem cannot make provider/HTTP/model calls')

current.http = forbidden
current.runner.local_json = forbidden
runner = current.runner
assert runner.IMAGE == freeze['image'] and runner.PROJECTS == freeze['projects']
actual_image = subprocess.check_output(['docker','image','inspect',runner.IMAGE,'--format','{{.Id}}'], text=True).strip()
assert actual_image == runner.IMAGE
old = ast.parse((raw/'frozen-inputs/scripts/repeated_local.py').read_text())
old_nodes = {n.name: n for n in old.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
function_bindings = {}
for name in ('tests_for','ProjectSandbox','grade'):
    now = ast.parse(inspect.getsource(getattr(runner, name))).body[0]
    assert ast.dump(now, include_attributes=False) == ast.dump(old_nodes[name], include_attributes=False), name
    function_bindings[name] = hashlib.sha256(ast.dump(now, include_attributes=False).encode()).hexdigest()
for name in ('scripts/long_horizon.py','scripts/gpu_experiment.py'):
    assert sha(root/name) == freeze['hashes'][name], name
for project, value in runner.PROJECTS.items():
    assert subprocess.check_output(['git','-C',str(root/value['upstream']),'rev-parse','HEAD'], text=True).strip() == value['revision']
    name = 'benchmarks/repeated_local/'+project+'/tests.py'
    assert sha(root/name) == freeze['hashes'][name]

streams = []
for directory in raw.glob('*/evidence'):
    store = Store(directory)
    for path in directory.glob('*.jsonl'):
        streams.append(dict(path=path.relative_to(raw).as_posix(), verification=store.verify_stream(path.stem)))
assert len(streams) == 7
attempts = json.loads((raw/'attempts.json').read_bytes())
assert len(attempts) == 5
by_key = {(r['project'],r['seed'],r['arm'],r['stage']):r for r in attempts}
calls = []
for path in raw.glob('*/call-*.json'):
    value = json.loads(path.read_bytes())
    assert value['usage'] is not None
    calls.append((path, value))
assert len(calls) == 192
prompt = sum(v['usage']['prompt_tokens'] for _,v in calls)
completion = sum(v['usage']['completion_tokens'] for _,v in calls)
assert (prompt,completion) == (4089695,82529)
counts = Counter((p.parent.name,v['stage']) for p,v in calls)
cached = [v['usage'].get('prompt_tokens_details',{}).get('cached_tokens') for _,v in calls]
assert all(x is None or type(x) is int and x>=0 for x in cached)
state = dict(complete=False, purpose='Stopped-study postmortem only; no campaign resume or generation',
    started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), freeze_sha256=freeze_sha,
    source_freeze='0fb1098106ddc0867778911e76b5df629caae7f9', frozen_input_count=348,
    controller_sha256=sha(Path(__file__)), grader_function_ast_hashes=function_bindings,
    streams=streams, generation_calls=192, known_prompt_tokens=prompt,
    known_completion_tokens=completion, known_total_tokens=prompt+completion,
    generation_usage_unknown=0, native_cached_tokens=sum(x for x in cached if x is not None),
    cached_usage_unknown_calls=sum(x is None for x in cached),
    cache_accounting='Cached tokens are a subset of prompt tokens, not additional tokens or bills.',
    rows=[], grades=[])
write('run.json', state)
try:
    for project,seed,arm in freeze['schedule']:
        trajectory = f'{project}-{seed}-{arm}'
        for stage in (1,2,3):
            recorded = by_key.get((project,seed,arm,stage))
            row = dict(project=project, seed=seed, arm=arm, stage=stage,
                       generation_calls=counts.get((trajectory,stage),0),
                       completion_asserted=None, grade_status='ungraded',
                       accepted_project_delivery='not_observed', assessments=0)
            if recorded is None:
                row.update(status='not_attempted_infrastructure_halt', reason='Campaign stopped before this scheduled checkpoint')
            else:
                row.update(recorded_status=recorded.get('status'),
                           completion_asserted=recorded.get('completion_asserted'),
                           raw_handoff=recorded.get('handoff'),
                           assessments=len(recorded.get('assessments',[])),
                           recorded_repairs=len(recorded.get('repairs',[])))
                if recorded.get('status') == 'not_attempted_dependent':
                    row.update(status='not_attempted_dependent',reason=recorded['blocked_reason'])
                elif not recorded.get('final_snapshot'):
                    row.update(status='infrastructure_interrupted_partial', reason='No final submitted snapshot retained')
                else:
                    row.update(status=recorded.get('status') or 'recorded_checkpoint',
                               final_snapshot=recorded['final_snapshot'])
                    snapshot = raw/recorded['final_snapshot']
                    row['snapshot_sha256'] = sha(snapshot)
                    assert row['snapshot_sha256'] == sha(raw/recorded['primary_snapshot'])
                    row['phase_workflow_complete'] = bool(recorded['phases']) and all(p['completed'] for p in recorded['phases']) and not recorded.get('runtime_intervention')
                    row['grades'] = {}
                    for public in (True, False):
                        mode = 'public' if public else 'hidden'
                        grade = current.bound_grade(project,snapshot,stage,public)
                        assert grade['source_sha256'] == row['snapshot_sha256']
                        name = f'grade-{trajectory}-stage{stage}-{mode}.json'
                        write(name, grade)
                        row['grades'][mode] = dict(path=name, sha256=sha(out/name), passed=grade['passed'], test_count=grade['test_count'], exit_code=grade['exit_code'])
                        state['grades'].append(dict(project=project,seed=seed,arm=arm,stage=stage,mode=mode,**row['grades'][mode]))
                        write('run.json', state)
                    row['grade_status'] = 'exact_retained_snapshot_graded'
                    row['checkpoint_code_tests_passed'] = all(g['passed'] for g in row['grades'].values())
                    # This is an intermediate checkpoint. No stage3 project delivery occurred.
            if row['status'].startswith('not_attempted'):
                assert row['generation_calls'] == 0
            state['rows'].append(row)
            write('run.json', state)
    assert len(state['rows']) == 36 and sum(r['generation_calls'] for r in state['rows']) == 192
    assert len(state['grades']) == 4
    graded = [r for r in state['rows'] if r['grade_status'] != 'ungraded']
    assert len(graded)==2 and all(r['completion_asserted'] is None for r in graded)
    state.update(complete=True, stopped_artifacts_unchanged=inventory()==before,
        statuses=dict(Counter(r['status'] for r in state['rows'])),
        declaration_denominators=dict(positive=0,negative=0,unknown_graded=2,ungraded=34),
        false_completion_rate=None, detector_precision=None, detector_recall=None,
        comparison='No matched arm pairs; infrastructure-censored campaign, not a valid completed-workflow study.',
        scored_actual_AEE_assessments=sum(r['assessments'] for r in state['rows']),
        local_API_spend=0, cost_boundary='Excludes hardware, energy and labor; historical setup/failed cohorts remain separate in cost audit03; not final all-history economics.')
    assert state['stopped_artifacts_unchanged']
    write('checkpoint-rows.json', state['rows'])
    write('stopped-input-sha256.json', before)
except BaseException as exc:
    state['error'] = repr(exc)
    raise
finally:
    state['ended_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write('run.json', state)
print(json.dumps({k:v for k,v in state.items() if k not in ('rows','grades','streams')}, indent=2))
