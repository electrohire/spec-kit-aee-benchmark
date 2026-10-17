"""Audit and export the local campaign without redistributing task prompt text."""
import argparse
import ast
import collections
import hashlib
import json
import shutil
import statistics
import sys
from pathlib import Path

from benchmark_runner.store import canonical, write_json
from gpu_experiment import grade
from local_experiment import extract


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(source, target, smoke, assets, upstream):
    frozen = read(source/'freeze.json')
    results = read(source/'results.json')
    summary = read(source/'coding-summary.json')
    assert len(results) == len(frozen['schedule']) == 18
    assert [(r['task'], r['arm']) for r in results] == [tuple(x) for x in frozen['schedule']]
    freeze_hash = digest(source/'freeze.json')
    for filename, expected in frozen['source_hashes'].items():
        assert digest(filename) == expected, filename
    target.mkdir(parents=True, exist_ok=False)
    all_calls = []
    timings = collections.defaultdict(lambda: dict(prompt_tokens=0, prompt_ms=0, decode_tokens=0, decode_ms=0))
    for row in results:
        assert row['freeze_sha256'] == freeze_hash
        folder = target/row['path']
        folder.mkdir()
        shutil.copy2(source/row['path']/'solution.py', folder/'solution.py')
        for call in row['calls']:
            original = source/row['path']/(call['phase']+'.json')
            raw = read(original)
            assert call['usage'] == raw['usage']
            assert call['seconds'] == raw['seconds']
            all_calls.append(call)
            native = raw.get('response', {}).get('timings', {})
            for field, key in [('prompt_tokens','prompt_n'),('prompt_ms','prompt_ms'),('decode_tokens','predicted_n'),('decode_ms','predicted_ms')]:
                timings[row['arm']][field] += native.get(key, 0)
            request = raw.pop('request')
            raw.update(request_sha256=hashlib.sha256(canonical(request)).hexdigest(),
                       original_record_sha256=digest(original),
                       request_omission='Task text omitted; regenerate from frozen upstream inputs and runner.')
            write_json(folder/(call['phase']+'.json'), raw)
        if row['grade']['passed']:
            assert not row['error']
            assert row['grade']['test_count'] == frozen['test_counts'][row['task']] > 0
            assert row['grade']['skipped'] == 0
            assert row['calls'][-1]['phase'] in ('solve', 'final_implement')
            assert row['calls'][-1]['finish_reason'] == 'stop'
        evidence = source/row['path']/'evidence'
        if evidence.exists():
            for p in (evidence/'objects').glob('*/*'):
                assert digest(p) == p.name
            shutil.copytree(evidence, folder/'evidence')
        row['rework'] = dict(test_feedback_rounds=0, retries=0, aee_recovery_loops=0,
            implementation_calls=sum(c['phase'] in ('solve','implement','final_implement') for c in row['calls']),
            scheduled_revision_calls=sum(c['phase']=='final_implement' for c in row['calls']),
            convergence_reviews=sum(c['phase']=='converge' and c['finish_reason']=='stop' for c in row['calls']),
            initial_grade=None, text_changed=None, ast_changed=None, transition=None)
        initial = source/row['path']/'implement.json'
        if initial.exists():
            raw = read(initial)
            response = raw.get('response', {})
            choice = response.get('choices', [{}])[0]
            if choice.get('finish_reason') == 'stop':
                initial_code = extract(choice['message']['content'])
                module = row['task'].replace('-', '_')
                test = upstream/'exercises/practice'/row['task']/(module+'_test.py')
                assert digest(test) == frozen['test_hashes'][row['task']]
                try:
                    first_grade = grade(initial_code, test.read_bytes(), module, frozen['image'], expected_count=frozen['test_counts'][row['task']])
                except Exception as exc:
                    first_grade = dict(passed=False, test_count=None, error=type(exc).__name__+': '+str(exc))
                row['rework']['initial_grade'] = first_grade
                row['rework']['transition'] = ('pass' if first_grade['passed'] else 'fail')+' -> '+('pass' if row['grade']['passed'] else 'fail')
                final_code = (source/row['path']/'solution.py').read_text(encoding='utf-8')
                if final_code.strip():
                    row['rework']['text_changed'] = initial_code.strip() != final_code.strip()
                    try:
                        row['rework']['ast_changed'] = ast.dump(ast.parse(initial_code)) != ast.dump(ast.parse(final_code))
                    except SyntaxError:
                        row['rework']['ast_changed'] = None
    for item in summary:
        selected = [r for r in results if r['arm'] == item['arm']]
        calls = [c for r in selected for c in r['calls']]
        assert item['passed'] == sum(r['grade']['passed'] for r in selected)
        assert item['attempts'] == len(selected) == 6
        assert item['calls'] == len(calls)
        known = [c['usage'] for c in calls if c['usage']]
        for field, native in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens')]:
            expected = sum(u[native] for u in known) if len(known) == len(calls) else None
            assert item[field] == expected
        assert abs(item['seconds']-sum(r['seconds'] for r in selected)) < 1e-6
        item['median_attempt_seconds'] = statistics.median(r['seconds'] for r in selected)
        item['cached_input_tokens'] = sum(u.get('prompt_tokens_details', {}).get('cached_tokens', 0) for u in known)
        item['aee_assessments'] = sum(len(r['gaps']) for r in selected)
        item['generation_errors'] = [dict(task=r['task'], error=r['error']) for r in selected if r['error']]
        item['total_tokens'] = None if item['input_tokens'] is None or item['output_tokens'] is None else item['input_tokens']+item['output_tokens']
        for label, denominator in [('per_attempt', len(selected)), ('per_correct_answer', item['passed'])]:
            for numerator in ['input_tokens','output_tokens','total_tokens','seconds','model_seconds']:
                item[numerator+'_'+label] = item[numerator]/denominator if denominator and item[numerator] is not None else None
        failed_calls = [c for r in selected if not r['grade']['passed'] for c in r['calls']]
        item['tokens_on_failed_attempts'] = sum(c['usage']['prompt_tokens']+c['usage']['completion_tokens'] for c in failed_calls) if all(c['usage'] for c in failed_calls) else None
        item['truncated_calls'] = sum(c['finish_reason']=='length' for c in calls)
        item['native_runtime'] = timings[item['arm']]
        for label in ('prompt','decode'):
            t = item['native_runtime']
            t[label+'_tokens_per_second'] = t[label+'_tokens']/(t[label+'_ms']/1000) if t[label+'_ms'] else None
        item['rework'] = {key:sum(r['rework'][key] for r in selected) for key in
            ('test_feedback_rounds','retries','aee_recovery_loops','implementation_calls','scheduled_revision_calls','convergence_reviews')}
        item['rework'].update(text_changed=sum(r['rework']['text_changed'] is True for r in selected),
            ast_changed=sum(r['rework']['ast_changed'] is True for r in selected),
            comparable_code_pairs=sum(r['rework']['text_changed'] is not None for r in selected),
            initial_grades_available=sum(r['rework']['initial_grade'] is not None for r in selected),
            transitions=dict(collections.Counter(r['rework']['transition'] for r in selected if r['rework']['transition'])))
        item['phase_totals'] = {}
        for phase in dict.fromkeys(c['phase'] for c in calls):
            phase_calls = [c for c in calls if c['phase']==phase]
            item['phase_totals'][phase] = dict(calls=len(phase_calls),seconds=sum(c['seconds'] for c in phase_calls),
                input_tokens=sum(c['usage']['prompt_tokens'] for c in phase_calls) if all(c['usage'] for c in phase_calls) else None,
                output_tokens=sum(c['usage']['completion_tokens'] for c in phase_calls) if all(c['usage'] for c in phase_calls) else None,
                truncations=sum(c['finish_reason']=='length' for c in phase_calls))
    # Keep original local freeze digest, plus a labeled sanitized view with task text removed.
    for task in frozen['task_inputs'].values():
        task['text_sha256'] = hashlib.sha256(task.pop('text').encode()).hexdigest()
    frozen['original_freeze_sha256'] = freeze_hash
    frozen['sanitized'] = True
    write_json(target/'freeze-sanitized.json', frozen)
    write_json(target/'results.json', results)
    write_json(target/'coding-summary.json', summary)
    shutil.copytree(smoke, target/'development-smoke')
    for name in ['machine-metadata.json', 'server-launch.json', 'server-ready.json', 'server.stderr.log', 'MODEL-LICENSE']:
        shutil.copy2(assets/name, target/name)
    if (source/'gpu-telemetry.csv').exists():
        shutil.copy2(source/'gpu-telemetry.csv', target/'gpu-telemetry.csv')
    checks = dict(original_freeze_sha256=freeze_hash, attempts=18, tasks=6,
                  calls=len(all_calls), source_hashes_verified=True,
                  grade_counts_verified=True, usage_totals_recomputed=True,
                  evidence_objects_verified=True, api_dollars=0,
                  independence='Upstream test authors differ from controller; controller/runner review is not external replication.')
    write_json(target/'audit.json', checks)
    write_json(target/'files-sha256.json', {p.relative_to(target).as_posix():digest(p)
               for p in sorted(target.rglob('*')) if p.is_file()})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.target, args.smoke, args.assets, args.upstream)
