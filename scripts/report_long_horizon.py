"""Export and audit the separately frozen staged-project campaign."""
import argparse
import collections
import hashlib
import json
import shutil
import statistics
from pathlib import Path

from benchmark_runner.store import canonical, write_json

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def omit_reasoning(record):
    for choice in record.get('response',{}).get('choices',[]):
        message=choice.get('message',{})
        if 'reasoning_content' in message:
            reasoning=message.pop('reasoning_content') or ''
            message['reasoning_sha256']=hashlib.sha256(reasoning.encode()).hexdigest()
    return record

def usage(calls):
    known=all(c.get('usage') is not None for c in calls)
    return dict(calls=len(calls),input_tokens=sum(c['usage']['prompt_tokens'] for c in calls) if known else None,
        output_tokens=sum(c['usage']['completion_tokens'] for c in calls) if known else None,
        total_tokens=sum(c['usage']['total_tokens'] for c in calls) if known else None,
        cached_tokens=sum(c['usage'].get('prompt_tokens_details',{}).get('cached_tokens',0) for c in calls) if known else None,
        http_seconds=sum(c.get('seconds',0) for c in calls),unknown_calls=sum(c.get('usage') is None for c in calls))

def runtime(calls):
    timings=[c['response']['timings'] for c in calls if c.get('response',{}).get('timings')]
    prompt_ms=sum(t['prompt_ms'] for t in timings);decode_ms=sum(t['predicted_ms'] for t in timings)
    latency=[c['seconds'] for c in calls if 'seconds' in c]
    return dict(native_timing_calls=len(timings),prompt_tokens=sum(t['prompt_n'] for t in timings),
        prompt_seconds=prompt_ms/1000,decode_tokens=sum(t['predicted_n'] for t in timings),decode_seconds=decode_ms/1000,
        weighted_prompt_tokens_per_second=sum(t['prompt_n'] for t in timings)/(prompt_ms/1000) if prompt_ms else None,
        weighted_decode_tokens_per_second=sum(max(t['predicted_n']-1,0) for t in timings)/(decode_ms/1000) if decode_ms else None,
        median_http_seconds=statistics.median(latency) if latency else None,
        p95_http_seconds=statistics.quantiles(latency,n=100,method='inclusive')[94] if len(latency)>1 else None,
        note='Decode excludes the first token per request, matching native predicted_n-1 timing semantics. HTTP time is not TTFT. Energy and peak device utilization were not sampled.')

def export(source,target):
    frozen=read(source/'freeze.json');rows=read(source/'results.json')
    assert len(rows)==9
    assert [(r['arm'],r['stage']) for r in rows]==[(a,s) for a in frozen['schedule'] for s in (1,2,3)]
    for name,digest in frozen['hashes'].items():
        assert sha(Path(name))==digest,name
    target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(source/'freeze.json',target/'freeze.json')
    shutil.copy2(source/'results.json',target/'results.json')
    shutil.copy2(source/'workflow-input-provenance.json',target/'workflow-input-provenance.json')
    allcalls=[];armstats={};stages=[];phase_stats={}
    for arm in frozen['schedule']:
        folder=target/arm;folder.mkdir()
        shutil.copytree(source/arm/'evidence',folder/'evidence')
        for p in (source/arm).glob('*.tar'):shutil.copy2(p,folder/p.name)
        calls=[]
        for p in sorted((source/arm).glob('call-*.json')):
            c=read(p);request=c.pop('request');omit_reasoning(c)
            c.update(request_sha256=hashlib.sha256(canonical(request)).hexdigest(),original_sha256=sha(p),
                request_omission='Regenerate from frozen inputs, model responses, and tool evidence; original retained locally.')
            write_json(folder/p.name,c);calls.append(c)
        allcalls.extend(calls)
        own=[r for r in rows if r['arm']==arm]
        u=usage(calls);primary=usage([c for c in calls if c['phase']!='repair']);repairs=usage([c for c in calls if c['phase']=='repair'])
        primary_pass=sum(r['hidden_primary']['passed'] for r in own)
        final_pass=sum(r['hidden_final']['passed'] for r in own)
        outcomes=collections.Counter(a.get('outcome','adapter_error') for r in own for a in r['assessments'])
        armstats[arm]=dict(**u,runtime=runtime(calls),primary=primary,repair=repairs,hidden_primary_passes=primary_pass,hidden_final_passes=final_pass,
            final_project_pass=own[-1]['hidden_final']['passed'],
            tokens_per_accepted_milestone=u['total_tokens']/final_pass if final_pass and u['total_tokens'] is not None else None,
            primary_tokens_per_accepted_milestone=primary['total_tokens']/primary_pass if primary_pass and primary['total_tokens'] is not None else None,
            repair_rounds=sum(len(r['repairs']) for r in own),
            hidden_repairs_fixed=sum(not r['hidden_primary']['passed'] and r['hidden_final']['passed'] for r in own),
            tool_calls=sum(r['tool_calls'] for r in own),stage_seconds=sum(r['seconds'] for r in own),assessment_outcomes=dict(outcomes),
            workflow_errors=[dict(stage=r['stage'],error=r['error']) for r in own if r['error']])
        for phase in sorted({c['phase'] for c in calls}):phase_stats[arm+'/'+phase]=usage([c for c in calls if c['phase']==phase])
        previous={}
        for r in own:
            now={c['name']:c['passed'] for c in r['hidden_final']['cases']}
            regressions=[name for name,passed in previous.items() if passed and name in now and not now[name]]
            previous=now
            stages.append(dict(arm=arm,stage=r['stage'],**usage([c for c in calls if c['stage']==r['stage']]),
                public_primary=r['public_primary']['passed'],public_final=r['public_final']['passed'],
                hidden_primary=r['hidden_primary']['passed'],hidden_final=r['hidden_final']['passed'],
                hidden_cases_passed=r['hidden_final']['passed_count'],hidden_cases_total=r['hidden_final']['test_count'],
                feature_cases_passed=sum(c['passed'] for c in r['hidden_final']['cases'] if 'test_acceptance' in c['file']),
                feature_cases_total=sum('test_acceptance' in c['file'] for c in r['hidden_final']['cases']),
                regressions_from_previous_stage=regressions,repair_rounds=len(r['repairs']),error=r['error']))
    summary=dict(freeze_sha256=sha(source/'freeze.json'),arms=armstats,stages=stages,phases=phase_stats,total=usage(allcalls),
        api_expenditure_usd=0,compute_cost='unpriced',denominator='Three dependent milestones per arm, one project and one trajectory per arm.')
    write_json(target/'summary.json',summary)
    assets=Path('artifacts/long-assets');preflight=target/'preflight';preflight.mkdir()
    for name in ('metadata.json','calibration.json','calibrate.py','smoke.py','smoke-v2.py','smoke-v3.py','smoke-v4.py','smoke-v5.py','smoke-v6.py','smoke-v7.py','smoke-v8.py','server-launch.json','server-ready.json','server.stderr.log','docker-build.log'):
        shutil.copy2(assets/name,preflight/name)
    setup=[]
    for number in range(1,9):
        shutil.copytree(Path(f'artifacts/long-smoke-{number:02}'),preflight/f'smoke-{number:02}')
        originals=[read(p) for p in Path(f'artifacts/long-smoke-{number:02}').glob('call-*.json')]
        result_path=Path(f'artifacts/long-smoke-{number:02}/result.json')
        setup.append(dict(smoke=number,**usage(originals),passed=read(result_path)['passed'] if result_path.exists() else False,
            scope='code-only' if number==1 else 'constitution plus code',
            result_available=result_path.exists()))
        for p in (preflight/f'smoke-{number:02}').glob('call-*.json'):
            record=read(p);record['original_sha256']=sha(p);omit_reasoning(record);write_json(p,record)
    aborted=read(Path('reports/local/long-horizon-01-interrupted/summary.json'))['usage']
    write_json(target/'setup-accounting.json',dict(smokes=setup,aborted_scored_run=aborted,
        setup_plus_aborted_tokens=sum(s['total_tokens'] for s in setup)+aborted['total_tokens'],
        completed_campaign_tokens=summary['total']['total_tokens'],
        note='Setup and aborted work are separate from comparable arm economics, never erased. No paid inference.'))
    shutil.copy2(Path('artifacts/tinydb-upstream/LICENSE'),target/'TINYDB-LICENSE')
    lines=['# Staged TinyDB local study','',
        'One real repository, three cumulative milestones, one trajectory per arm. These are dependent checkpoints, not nine independent tasks. Hidden cases were withheld from solver feedback but authored by this study. See the frozen protocol and full traces.','',
        '| Arm | Hidden primary / 3 | Hidden after repairs / 3 | All tokens | Tokens / accepted milestone | Repair rounds | Stage wall seconds |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm,s in armstats.items():
        ratio=f"{s['tokens_per_accepted_milestone']:,.1f}" if s['tokens_per_accepted_milestone'] is not None else 'undefined'
        total=f"{s['total_tokens']:,}" if s['total_tokens'] is not None else 'unknown'
        lines.append(f"| {arm} | {s['hidden_primary_passes']} | {s['hidden_final_passes']} | {total} | {ratio} | {s['repair_rounds']} | {s['stage_seconds']:.1f} |")
    lines+=['','All model phases, failed calls with known usage, and repairs count. API expenditure: $0; hardware, electricity and controller labor unpriced. Functional grading does not prove workflow completion.','',
        '| Arm | Stage | Public primary → final | Hidden primary → final | Hidden feature cases final | Regressions | Error |',
        '|---|---:|---|---|---:|---:|---|']
    for s in stages:
        lines.append(f"| {s['arm']} | {s['stage']} | {s['public_primary']} → {s['public_final']} | {s['hidden_primary']} → {s['hidden_final']} | {s['feature_cases_passed']}/{s['feature_cases_total']} | {len(s['regressions_from_previous_stage'])} | {s['error'] or 'none'} |")
    lines+=['','## Evidence and limits','',
        '- `summary.json` includes input/output/cache tokens, phase accounting, repairs, tool calls, time, assessment outcomes and stage regressions.',
        '- `results.json` retains every test case and failure, public repair feedback, model phase completions and AEE results.',
        '- Per-arm folders retain generated source snapshots, workflow artifacts, response/usage records and content-addressed shell evidence. Full prompts remain local with recorded hashes.',
        '- Calibration passed all six test combinations; unchanged upstream failed new features. Smoke is separate and excluded from scored economics.',
        '- A fixed sampling seed is not a guarantee of bitwise deterministic GPU execution. One shuffled run does not remove order effects or establish statistical significance.',
        '- Limited context, call/time ceilings, single-model and adapter behavior constrain interpretation. The previous smaller-model exploration remains separate.',
        '- The first staged run and seven preliminary smokes exposed integration failures; all costs remain in the separate setup ledger. Run 02 follows a revised freeze. This is iterative benchmark development, not a single pristine preregistered experiment.',
        '- Individual hashes for workflow scripts/templates and adapter were added after generation started; they match the pre-run tracked commit. See workflow-input-provenance.json for this freeze-coverage limitation.',
        '- ElectroHire maintains AEE/Evaluator and the benchmark. No external replication or blinded independent test authorship is claimed.','']
    (target/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    write_json(target/'files-sha256.json',{p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()})
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('target',type=Path)
    args=parser.parse_args();export(args.source,args.target)
