"""Free localhost exploration, with frozen inputs and Docker-only code execution.

This is deliberately separate from the paid-provider SWE-bench runner.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import io
import json
import random
import re
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
from pathlib import Path

from benchmark_runner.store import Store, utc, write_json
from benchmark_runner.workflow import assess
from local_experiment import claims, digest, extract, runtime, safe

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260917
ARMS = ['baseline', 'spec_kit_adapted', 'spec_kit_aee_adapted']
PHASES = ['constitution', 'specify', 'plan', 'tasks', 'implement', 'converge', 'final_implement']
TASKS = ['leap', 'raindrops', 'isogram', 'pangram', 'hamming', 'resistor-color']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirects forbidden for local inference')


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def local_json(route, payload=None, timeout=120):
    # No endpoint option, proxy, credentials, retry or external fallback.
    request = urllib.request.Request('http://127.0.0.1:8091' + route,
        None if payload is None else json.dumps(payload).encode(),
        {'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=timeout) as response:
        return json.load(response)


def grade(code, test_bytes, module, image, timeout=20, expected_count=None):
    """Only the generated file and unchanged tests enter an unmounted container."""
    safe(code)  # Extra filtering, NOT the security boundary.
    name = 'aee-grade-' + uuid.uuid4().hex
    flags = ['--name', name, '--network', 'none', '--read-only', '--cap-drop', 'ALL',
             '--security-opt', 'no-new-privileges', '--pids-limit', '64', '--memory', '256m',
             '--cpus', '1', '--user', '65534:65534', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
             '--workdir', '/tmp', '-i', image, 'python', '-B', '-c',
             "import sys,tarfile,subprocess; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp',filter='data'); "
             f"sys.exit(subprocess.call([sys.executable,'-B','-m','unittest','{module}_test','-v']))"]
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        for filename, content in [(module+'.py', code.encode()), (module+'_test.py', test_bytes)]:
            item = tarfile.TarInfo(filename)
            item.size, item.mode = len(content), 0o444
            tar.addfile(item, io.BytesIO(content))
    try:
        result = subprocess.run(['docker', 'run', *flags], input=archive.getvalue(),
                                capture_output=True, timeout=timeout)
        output = (result.stdout + result.stderr).decode(errors='replace')
        counts = re.findall(r'Ran (\d+) tests? in ', output)
        count = int(counts[-1]) if counts else 0
        skipped = re.search(r'skipped=(\d+)', output)
        skips = int(skipped.group(1)) if skipped else 0
        return dict(passed=result.returncode == 0 and count > 0 and skips == 0 and
                    (expected_count is None or count == expected_count), test_count=count, skipped=skips,
                    exit_code=result.returncode, output=output)
    except subprocess.TimeoutExpired:
        return dict(passed=False, test_count=None, error='grading_timeout')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)


def query(messages, maximum, timeout, path):
    payload = dict(model='local-coder', messages=messages, temperature=0, seed=SEED,
                   max_tokens=maximum, cache_prompt=False)
    record = dict(started_at=utc(), request=payload, usage=None,
                  unknown_reason='request_started_without_response', seconds=None)
    write_json(path, record, exclusive=True)
    before = time.monotonic()
    try:
        response = local_json('/v1/chat/completions', payload, timeout)
        record.update(response=response, usage=response.get('usage'), unknown_reason=None)
        if not record['usage']:
            record['unknown_reason'] = 'server_omitted_usage'
    except BaseException as exc:
        record.update(error=type(exc).__name__, unknown_reason='interrupted_or_failed_request')
        raise
    finally:
        record.update(seconds=time.monotonic()-before, ended_at=utc())
        write_json(path, record)
    choice = response['choices'][0]
    if choice.get('finish_reason') != 'stop':
        raise RuntimeError('incomplete_response:' + str(choice.get('finish_reason')))
    return choice['message']['content'], record


def source_hashes():
    import aee
    files = [Path(__file__), ROOT/'scripts/local_experiment.py', ROOT/'uv.lock',
             ROOT/'docs/gpu-experiment-protocol.md', ROOT/'.specify/memory/constitution.md']
    for base in [ROOT/'prompts/skills', ROOT/'src/benchmark_runner',
                 ROOT/'.specify/extensions/aee', ROOT/'.specify/extensions/evaluator',
                 Path(aee.__file__).parent]:
        files.extend(p for p in base.rglob('*') if p.is_file() and
                     '__pycache__' not in p.parts and p.suffix in {'.py', '.md', '.json', '.yaml', '.yml'})
    return {str(p.resolve()): digest(p) for p in sorted(set(files))}


def smoke(args):
    text, record = query([dict(role='user', content='Return only a Python code block defining hello() which returns the string hello.')],
                         256, 120, args.output/'hello-call.json')
    test = b'import unittest\nfrom hello import hello\nclass HelloTest(unittest.TestCase):\n def test_hello(self): self.assertEqual(hello(), "hello")\n'
    result = grade(extract(text), test, 'hello', args.image)
    write_json(args.output/'hello-grade.json', result)
    if not result['passed']:
        raise RuntimeError('Development smoke failed')
    print(json.dumps(dict(seconds=record['seconds'], usage=record['usage'], grade=result)), flush=True)


def freeze(args):
    task_inputs, test_hashes, test_counts = {}, {}, {}
    for task in TASKS:
        base = args.upstream/'exercises/practice'/task
        module = task.replace('-', '_')
        # Explicit allowlist; .meta/example.py and reference solutions never enter prompts.
        paths = [p for p in [base/'.docs/introduction.md', base/'.docs/instructions.md', base/(module+'.py')] if p.exists()]
        task_inputs[task] = dict(text='\n'.join(p.read_text(encoding='utf-8') for p in paths),
                                hashes={str(p): digest(p) for p in paths})
        test_hashes[task] = digest(base/(module+'_test.py'))
        tree = ast.parse((base/(module+'_test.py')).read_text(encoding='utf-8'))
        test_counts[task] = sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(tree))
    schedule = [(task, arm) for task in TASKS for arm in ARMS]
    random.Random(SEED).shuffle(schedule)
    metadata = json.loads(args.metadata.read_text(encoding='utf-8-sig'))
    data = dict(created_at=utc(), schedule=schedule, seed=SEED, task_inputs=task_inputs,
                test_hashes=test_hashes, test_counts=test_counts, source_hashes=source_hashes(), metadata=metadata,
                dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
                image=args.image, attempt_seconds=900, request_seconds=120,
                input_token_ceiling=100000, output_token_ceiling=8192,
                document_max_tokens=512, code_max_tokens=1024,
                endpoint='http://127.0.0.1:8091', api_dollars=0,
                smoke_sha256=digest(args.smoke/'hello-call.json'),
                smoke_grade_sha256=digest(args.smoke/'hello-grade.json'),
                server_props=local_json('/props'))
    if not json.loads((args.smoke/'hello-grade.json').read_text())['passed']:
        raise ValueError('Passing smoke required')
    write_json(args.output/'freeze.json', data, exclusive=True)
    print('Frozen', digest(args.output/'freeze.json'), flush=True)


def coding(args):
    frozen = json.loads((args.output/'freeze.json').read_text())
    if source_hashes() != frozen['source_hashes']:
        raise ValueError('Frozen source changed')
    if (args.output/'attempts.json').exists():
        raise ValueError('No implicit reruns; use a new campaign')
    for task, expected in frozen['test_hashes'].items():
        test = args.upstream/'exercises/practice'/task/(task.replace('-', '_')+'_test.py')
        if digest(test) != expected:
            raise ValueError('Grading source changed')
    rows = []
    for index, (task, arm) in enumerate(frozen['schedule']):
        folder = args.output/f'{index:02}-{task}-{arm}'
        folder.mkdir()
        row = dict(task=task, arm=arm, path=folder.name, calls=[], gaps=[], error=None,
                   started_at=utc(), freeze_sha256=digest(args.output/'freeze.json'))
        rows.append(row)
        write_json(args.output/'attempts.json', rows)
        history, code = [], ''
        begin = time.monotonic()
        try:
            for phase in ['solve'] if arm == 'baseline' else PHASES:
                if (args.output/'CANCEL').exists():
                    raise KeyboardInterrupt('CANCEL')
                remaining = frozen['attempt_seconds']-(time.monotonic()-begin)
                if remaining <= 0:
                    raise TimeoutError('whole_attempt_limit')
                maximum = frozen['code_max_tokens'] if phase in ('solve', 'implement', 'final_implement') else frozen['document_max_tokens']
                used_in = sum(c['usage']['prompt_tokens'] for c in row['calls'] if c.get('usage'))
                used_out = sum(c['usage']['completion_tokens'] for c in row['calls'] if c.get('usage'))
                if used_in+16384 > frozen['input_token_ceiling'] or used_out+maximum > frozen['output_token_ceiling']:
                    raise RuntimeError('token_budget_limit')
                if phase == 'solve':
                    instructions = 'Solve this exercise. Return only the complete Python implementation in a python code block.'
                else:
                    skill = 'implement' if phase == 'final_implement' else phase
                    instructions = (ROOT/f'prompts/skills/speckit-{skill}.md').read_text(encoding='utf-8')
                    instructions += '\nLOCAL DOCUMENT ADAPTER: You have no tools, repository access or test results. Produce document contents directly; do not claim execution or request clarification. '
                    if phase in ('implement', 'final_implement'):
                        instructions += 'Return only the complete final Python code in a python block, applying preceding tasks and convergence findings.'
                    elif phase == 'converge':
                        instructions += 'Review prior implementation against the generated requirements. Return only remaining tasks or a concise no-gaps report; do not write code.'
                    else:
                        instructions += 'Return a concise phase document in at most 250 words.'
                messages = [dict(role='system', content='You are a Python coding assistant. No tests have run. Follow the task and current phase instructions.'),
                    dict(role='user', content='EXERCISE\n'+frozen['task_inputs'][task]['text']+'\nPRIOR PHASE OUTPUTS\n'+'\n\n'.join(history)+'\nCURRENT PHASE '+phase+'\n'+instructions)]
                call_path = folder/(phase+'.json')
                try:
                    text, record = query(messages, maximum, min(remaining, frozen['request_seconds']), call_path)
                finally:
                    if call_path.exists():
                        record = json.loads(call_path.read_text())
                        row['calls'].append(dict(phase=phase, seconds=record['seconds'], usage=record['usage'],
                            unknown_reason=record['unknown_reason'], error=record.get('error'),
                            finish_reason=record.get('response', {}).get('choices', [{}])[0].get('finish_reason')))
                        write_json(args.output/'attempts.json', rows)
                history.append(phase+':\n'+text)
                if phase in ('solve', 'final_implement'):
                    code = extract(text)
                if arm == 'spec_kit_aee_adapted' and phase in ('specify', 'plan', 'tasks', 'implement'):
                    if frozen['attempt_seconds']-(time.monotonic()-begin) < 125:
                        raise TimeoutError('insufficient_remaining_assessment_budget')
                    evaluation = assess(ROOT, claims(1), phase, Store(folder/'evidence'))
                    row['gaps'].append(dict(phase=phase, outcome=evaluation['outcome']))
                    history.append('AEE evidence-gap feedback; this is NOT an independent test grade:\n'+json.dumps(evaluation))
            if time.monotonic()-begin > frozen['attempt_seconds']:
                raise TimeoutError('whole_attempt_limit')
        except BaseException as exc:
            row['error'] = type(exc).__name__+': '+str(exc)
            code = ''  # Never grade an earlier implementation after final-phase failure.
            if isinstance(exc, KeyboardInterrupt):
                row['seconds'] = time.monotonic()-begin
                write_json(args.output/'attempts.json', rows)
                raise
        (folder/'solution.py').write_text(code, encoding='utf-8')
        row.update(seconds=time.monotonic()-begin, ended_at=utc())
        write_json(args.output/'attempts.json', rows)
        print(f'{index+1}/{len(frozen["schedule"])} {task} {arm}: {row["error"] or "generated"}', flush=True)
    # Generation is complete for every arm before any upstream test executes.
    for row in rows:
        try:
            if row['error']:
                raise ValueError('generation_failure')
            module = row['task'].replace('-', '_')
            code = (args.output/row['path']/'solution.py').read_text(encoding='utf-8')
            test = args.upstream/'exercises/practice'/row['task']/(module+'_test.py')
            if digest(test) != frozen['test_hashes'][row['task']]:
                raise ValueError('test_hash_changed')
            row['grade'] = grade(code, test.read_bytes(), module, frozen['image'], expected_count=frozen['test_counts'][row['task']])
        except Exception as exc:
            row['grade'] = dict(passed=False, test_count=None, error=type(exc).__name__+': '+str(exc))
        write_json(args.output/'results.json', rows)
    summary = []
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        calls = [c for r in selected for c in r['calls']]
        known = [c['usage'] for c in calls if c['usage']]
        summary.append(dict(arm=arm, attempts=len(selected), passed=sum(r['grade']['passed'] for r in selected),
            calls=len(calls), input_tokens=sum(u['prompt_tokens'] for u in known) if len(known)==len(calls) else None,
            output_tokens=sum(u['completion_tokens'] for u in known) if len(known)==len(calls) else None,
            known_input_tokens=sum(u['prompt_tokens'] for u in known), known_output_tokens=sum(u['completion_tokens'] for u in known),
            unknown_usage_calls=len(calls)-len(known), seconds=sum(r['seconds'] for r in selected),
            model_seconds=sum(c['seconds'] for c in calls), failures=sum(not r['grade']['passed'] for r in selected), api_dollars=0))
    write_json(args.output/'coding-summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['smoke', 'freeze', 'coding'])
    parser.add_argument('output', type=Path)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--smoke', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    globals()[args.mode](args)
