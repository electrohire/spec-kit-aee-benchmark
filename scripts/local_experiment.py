"""Separate, explicitly adapted local experiment; see local-benchmark-protocol.md."""
import argparse
import ast
import hashlib
import json
import platform
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from aee.engine import AEEEngine
from aee.model import Claim
from benchmark_runner.store import Store, utc, write_json
from benchmark_runner.workflow import assess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path('D:/Development/benchmark-upstreams/exercism-python')
TOOLS = Path('D:/Development/benchmark-tools')
TASKS = ['leap', 'raindrops', 'isogram']
PHASES = ['constitution', 'specify', 'plan', 'tasks', 'implement', 'converge']
SEED = 20260917


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def claims(n, text='The proposed implementation satisfies the exercise requirements.'):
    return {'schema_version': '1.0', 'claims': [dict(
        id=f'REQ-{i:04}', text=text + f' Requirement {i}.', kind='requirement',
        status='supported', boundary=['This exercise only'], depends_on=[],
        conflicts_with=[], falsification_tests=['An independent upstream test fails'],
        source_ref='model-response', uncertainty='high', evidence=[dict(
            ref='model-response', kind='asserted', direction='supports',
            source_quality='model', description='Unverified model proposal')]) for i in range(n)]}


def runtime(out):
    store = Store(out / 'evidence')
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        cases = [('engine', n) for n in (10, 100, 1000)] + [('pipeline', n) for n in (10, 100)] + [('triage', n) for n in (1000, 10000, 100000)]
        inputs = {}
        for kind, n in cases:
            if kind == 'triage':
                p = folder / f'{n}.csv'
                p.write_text('asset_id,vibration_mm_s,temperature_c\n' + ''.join(f'A{i:07},{i%10},{60+i%30}\n' for i in range(n)), encoding='utf-8')
                inputs[n] = p
        order = [(kind, n, rep) for rep in range(8) for kind, n in cases]
        # Warmups first; independent shuffled measured cases afterward.
        warm, measured = order[:len(cases)], order[len(cases):]
        random.Random(SEED).shuffle(measured)
        for kind, n, rep in warm + measured:
            payload = claims(n)
            parsed = [Claim.from_dict(c) for c in payload['claims']]
            before = time.perf_counter_ns()
            if kind == 'engine':
                result = AEEEngine(threshold=.7).assess(parsed, project='local-runtime', phase='after_plan')
                outcome = result.outcome
            elif kind == 'pipeline':
                outcome = assess(ROOT, payload, 'plan', store)['outcome']
            else:
                target = folder / 'output.json'
                subprocess.run([sys.executable, '-c', 'from benchmark_runner.triage import main; raise SystemExit(main())', str(inputs[n]), str(target)], check=True, capture_output=True)
                outcome = 'completed'
            elapsed = (time.perf_counter_ns() - before) / 1e6
            extra = {}
            if kind == 'triage':
                data = json.loads(target.read_text())
                assert len(data) == n and data[0]['asset_id'] == 'A0000000'
                assert sum(x['flagged'] for x in data) == sum(i%10 >= 8 or 60+i%30 >= 80 for i in range(n))
                extra = dict(input_sha256=digest(inputs[n]), output_sha256=digest(target))
            rows.append(dict(kind=kind, size=n, repetition=rep, warmup=rep == 0, milliseconds=elapsed, outcome=outcome, **extra))
            write_json(out / 'runtime.json', dict(timestamp=utc(), python=sys.version, platform=platform.platform(), samples=rows))
            print(f'{kind} {n} rep {rep}: {elapsed:.3f}ms', flush=True)
    summary = []
    for kind, n in cases:
        values = [r['milliseconds'] for r in rows if r['kind'] == kind and r['size'] == n and not r['warmup']]
        summary.append(dict(kind=kind, size=n, median_ms=statistics.median(values), min_ms=min(values), max_ms=max(values), repetitions=len(values)))
    write_json(out / 'runtime-summary.json', summary)


def call(messages, maximum):
    payload = dict(model='local-qwen', messages=messages, temperature=0, seed=SEED, max_tokens=maximum, cache_prompt=False)
    request = urllib.request.Request('http://127.0.0.1:8091/v1/chat/completions', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.load(response)
    return payload, result, time.perf_counter() - start


def extract(text):
    blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', text, re.S)
    return blocks[-1].strip() + '\n' if blocks else text.strip() + '\n'


def safe(code):
    tree = ast.parse(code)
    banned = {'eval', 'exec', 'open', 'compile', 'input', '__import__', 'getattr', 'setattr', 'globals', 'locals', 'vars', 'breakpoint', 'help'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if any(n not in {'math', 're', 'string', 'collections'} for n in names):
                raise ValueError('restricted import')
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise ValueError('restricted attribute')
        if isinstance(node, ast.Name) and (node.id in banned or node.id.startswith('__')):
            raise ValueError('restricted name')


def coding(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'freeze.json').exists():
        raise ValueError('Use a fresh output directory; no implicit reruns')
    schedule = [(task, arm) for task in TASKS for arm in ('baseline', 'spec_kit_adapted', 'spec_kit_aee_adapted')]
    random.Random(SEED).shuffle(schedule)
    paths = [Path(__file__), ROOT/'docs/local-benchmark-protocol.md', *sorted((ROOT/'prompts/skills').glob('*.md'))]
    task_inputs = {}
    for task in TASKS:
        base = UPSTREAM/'exercises/practice'/task
        docs = sorted((base/'.docs').glob('*.md'))
        starter = base/(task.replace('-', '_')+'.py')
        test = base/(task.replace('-', '_')+'_test.py')
        paths.extend([*docs, starter, test])
        task_inputs[task] = '\n'.join(p.read_text(encoding='utf-8') for p in docs) + '\nStarter:\n' + starter.read_text()
    model = TOOLS/'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf'
    write_json(out/'freeze.json', dict(timestamp=utc(), schedule=schedule, hashes={str(p):digest(p) for p in paths}, model_sha256=digest(model), binary_zip_sha256=digest(TOOLS/'llama-b11026.zip'), seed=SEED))
    # Development smoke is unscored and excluded from comparative totals.
    payload, response, elapsed = call([dict(role='user', content='Return only Python code for def hello(): returning the string hello.')], 128)
    smoke_code = extract(response['choices'][0]['message']['content'])
    safe(smoke_code)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/'smoke.py'
        p.write_text(smoke_code + '\nassert hello() == "hello"\n')
        smoke = subprocess.run([sys.executable, '-I', str(p)], capture_output=True, timeout=10)
    write_json(out/'smoke.json', dict(request=payload, response=response, seconds=elapsed, exit_code=smoke.returncode))
    if smoke.returncode:
        raise RuntimeError('Unscored development smoke failed')
    results = []
    for index, (task, arm) in enumerate(schedule):
        attempt = out/f'{index:02}-{task}-{arm}'
        attempt.mkdir()
        history, calls, gaps = [], [], []
        code, error = '', None
        start = time.perf_counter()
        for phase in (['solve'] if arm == 'baseline' else PHASES):
            try:
                instructions = 'Solve the exercise correctly. Return only the complete Python implementation in a python code block.'
                if phase != 'solve':
                    instructions = (ROOT/f'prompts/skills/speckit-{phase}.md').read_text(encoding='utf-8')
                    instructions += '\nLOCAL ADAPTER: No tools or repository access are available. Produce the requested document contents directly. Do not claim to have run commands or tests. Do not request clarification. Use the exercise facts. '
                    instructions += 'Return only complete final Python implementation in a python code block.' if phase in ('implement', 'converge') else 'Return a concise phase document in at most 200 words.'
                context = '\n\n'.join(history)
                messages = [dict(role='system', content='You are a Python coding assistant. Follow the supplied task and phase instructions. No tests have been run.'), dict(role='user', content=f'EXERCISE\n{task_inputs[task]}\nPRIOR PHASE OUTPUTS\n{context}\nCURRENT PHASE {phase}\n{instructions}')]
                payload, response, seconds = call(messages, 768 if phase in ('solve', 'implement', 'converge') else 256)
                text = response['choices'][0]['message']['content']
                record = dict(phase=phase, request=payload, response=response, seconds=seconds)
                write_json(attempt/f'{phase}.json', record)
                calls.append(dict(phase=phase, seconds=seconds, usage=response.get('usage'), finish_reason=response['choices'][0].get('finish_reason')))
                history.append(f'{phase}:\n{text}')
                if phase in ('solve', 'implement', 'converge'):
                    code = extract(text)
                if arm == 'spec_kit_aee_adapted' and phase in ('specify', 'plan', 'tasks', 'implement'):
                    evaluation = assess(ROOT, claims(1), phase, Store(attempt/'evidence'))
                    gaps.append(dict(phase=phase, outcome=evaluation['outcome']))
                    history.append('Independent evidence gate (no upstream tests available during generation):\n' + json.dumps(evaluation))
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                break
        (attempt/'solution.py').write_text(code, encoding='utf-8')
        results.append(dict(task=task, arm=arm, path=attempt.name, seconds=time.perf_counter()-start, calls=calls, gaps=gaps, error=error))
        write_json(out/'attempts.json', results)
        print(f'Completed {index+1}/9 {task} {arm}: {error or "generated"}', flush=True)
    # Independent grading occurs only after every generation has finished.
    for row in results:
        name = row['task'].replace('-', '_')
        code = (out/row['path']/'solution.py').read_text(encoding='utf-8')
        try:
            if row['error'] or not code.strip():
                raise ValueError('generation failed or empty')
            safe(code)
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                (folder/f'{name}.py').write_text(code, encoding='utf-8')
                (folder/f'{name}_test.py').write_bytes((UPSTREAM/f'exercises/practice/{row["task"]}/{name}_test.py').read_bytes())
                result = subprocess.run([sys.executable, '-m', 'unittest', f'{name}_test', '-v'], cwd=folder, capture_output=True, timeout=10)
            row['grade'] = dict(passed=result.returncode == 0, exit_code=result.returncode, output=(result.stdout+result.stderr).decode(errors='replace'))
        except Exception as exc:
            row['grade'] = dict(passed=False, error=f'{type(exc).__name__}: {exc}')
    write_json(out/'results.json', results)
    summary = []
    for arm in ('baseline', 'spec_kit_adapted', 'spec_kit_aee_adapted'):
        selected = [r for r in results if r['arm'] == arm]
        usage = [c['usage'] for r in selected for c in r['calls']]
        summary.append(dict(arm=arm, passed=sum(r['grade']['passed'] for r in selected), attempts=len(selected), input_tokens=sum(u['prompt_tokens'] for u in usage) if all(usage) else None, output_tokens=sum(u['completion_tokens'] for u in usage) if all(usage) else None, seconds=sum(r['seconds'] for r in selected), api_dollars=0))
    write_json(out/'coding-summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['runtime', 'coding'])
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    {'runtime':runtime, 'coding':coding}[args.mode](args.output)
