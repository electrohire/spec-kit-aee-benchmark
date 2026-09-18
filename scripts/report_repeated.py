"""Export repeated-study evidence without native reasoning; preserve all failures."""
import argparse
import collections
import hashlib
import json
import shutil
from pathlib import Path
from benchmark_runner.store import write_json,canonical
from report_long_horizon import usage,runtime,source_digest

ROOT=Path(__file__).resolve().parents[1]


def calls(folder):
    return [json.loads(p.read_text(encoding='utf-8-sig')) for p in sorted(folder.glob('call-*.json'))]


def accounting(records):
    value=usage(records)
    value['budget_reservation_total']=sum((r.get('usage') or {}).get('total_tokens',r.get('preflight_input_tokens',0)+r.get('max_output',0)) for r in records)
    value['native_runtime']=runtime(records)
    return value


def export(raw,dest):
    dest.mkdir(parents=True,exist_ok=False)
    for p in raw.rglob('*'):
        if not p.is_file() or 'mini-config' in p.parts:continue
        target=dest/p.relative_to(raw);target.parent.mkdir(parents=True,exist_ok=True)
        if p.name.startswith('call-') and p.suffix=='.json':
            obj=json.loads(p.read_text(encoding='utf-8-sig'))
            obj['original_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            request=obj.pop('request',None)
            if request is not None:obj['request_sha256']=hashlib.sha256(canonical(request)).hexdigest()
            for choice in obj.get('response',{}).get('choices',[]):
                message=choice.get('message',{})
                reasoning=message.pop('reasoning_content',None)
                if reasoning:message['reasoning_sha256']=hashlib.sha256(reasoning.encode()).hexdigest()
            write_json(target,obj)
        elif p.suffix in ('.json','.jsonl','.tar','.md','.py') or p.name=='CANCEL' or 'objects' in p.parts:
            shutil.copyfile(p,target)
    freeze=json.loads((raw/'freeze.json').read_text())
    frozen={}
    for name,sha in freeze['hashes'].items():
        src=ROOT/name
        assert hashlib.sha256(src.read_bytes()).hexdigest()==sha, 'Frozen input changed: '+name
        target=dest/'frozen-inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
        frozen[name]={'sha256':sha,'file':target.relative_to(dest).as_posix()}
    for project in ('tinydb','cachetools'):
        for name in ('LICENSE','LICENSE.rst','LICENSE.txt'):
            src=ROOT/'artifacts'/f'{project}-upstream'/name
            if src.is_file():
                target=dest/'licenses'/f'{project}-{name}';target.parent.mkdir(exist_ok=True);shutil.copyfile(src,target)
    write_json(dest/'frozen-input-map.json',frozen)


def summarize_study(raw,dest):
    rows=json.loads((raw/'results.json').read_text())
    summary={'scope':'12 project trajectories; 36 dependent checkpoints, not independent tasks','arms':{},'cases':len(rows)}
    for arm in ('baseline','spec_kit','spec_kit_aee'):
        subset=[r for r in rows if r['arm']==arm]
        records=[c for folder in raw.glob('*-'+arm) if folder.is_dir() for c in calls(folder)]
        economics=accounting(records)
        accepted=sum(r['hidden_final']['passed'] for r in subset)
        changed=sum(x['source_changed'] for r in subset for x in r['repairs'])
        completed=sum(({'solve'} if arm=='baseline' else ({'constitution'} if r['stage']==1 else set()) | {'specify','plan','tasks','implement','converge','final_implement'}) <= {p['phase'] for p in r['phases'] if p['completed']} for r in subset)
        regressions=[]
        for r in subset:
            if r['stage']==1:continue
            previous=next(x for x in subset if x['project']==r['project'] and x['seed']==r['seed'] and x['stage']==r['stage']-1)
            before={c['name']:c['passed'] for c in previous['hidden_final']['cases']}
            regressions.extend(dict(project=r['project'],seed=r['seed'],stage=r['stage'],case=c['name']) for c in r['hidden_final']['cases'] if before.get(c['name']) is True and not c['passed'])
        summary['arms'][arm]=dict(economics=economics,primary_accepted=sum(r['hidden_primary']['passed'] for r in subset),final_accepted=accepted,milestones=len(subset),
            projects_accepted=sum(all(x['hidden_final']['passed'] for x in subset if x['project']==r['project'] and x['seed']==r['seed']) for r in subset if r['stage']==3),
            final_projects_accepted=sum(r['stage']==3 and r['hidden_final']['passed'] for r in subset),projects=4,tokens_per_accepted=None if not accepted or economics['total_tokens'] is None else economics['total_tokens']/accepted,
            lower_bound_tokens_per_accepted=economics['known_total_tokens']/accepted if accepted else None,
            wall_seconds=sum(r['seconds'] for r in subset),repair_rounds=sum(len(r['repairs']) for r in subset),source_changing_repairs=changed,
            public_fixed=sum(not r['public_primary']['passed'] and r['public_final']['passed'] for r in subset),
            hidden_fixed=sum(not r['hidden_primary']['passed'] and r['hidden_final']['passed'] for r in subset),
            completed_milestone_workflows=completed,assessments=sum(len(r['assessments']) for r in subset),
            assessment_errors=sum('error' in a for r in subset for a in r['assessments']),
            evidence_rework_rounds=sum(p['phase']=='evidence_rework' for r in subset for p in r['phases']),planning_source_edits=[dict(project=r['project'],seed=r['seed'],stage=r['stage'],phase=p['phase']) for r in subset for p in r['phases'] if p['phase'] in ('constitution','specify','plan','tasks') and p.get('source_changed')],regressions=regressions)
    write_json(dest/'summary.json',summary)
    text='# Repeated two-project local comparison\n\n'+summary['scope']+'. All inference is local. API expenditure $0; hardware, energy and controller work unpriced.\n\n'
    text+='| Arm | Primary /12 | Final /12 | Entire trajectories /4 | Known tokens | Unknown calls | Tokens/accepted | Repair rounds | Completed milestone workflows |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    for arm,v in summary['arms'].items():
        e=v['economics'];ratio=v['tokens_per_accepted']
        text+=f"| {arm} | {v['primary_accepted']} | {v['final_accepted']} | {v['projects_accepted']} | {e['known_total_tokens']:,} | {e['unknown_calls']} | {ratio if ratio is not None else 'undefined'} | {v['repair_rounds']} | {v['completed_milestone_workflows']} |\n"
    text+='\n## Paired project/seed outcomes\n\n| Project | Seed | Arm | Stage | Public final | Hidden primary → final | Completed phases | Repair rounds |\n|---|---|---|---:|---|---|---:|---:|\n'
    for r in sorted(rows,key=lambda x:(x['project'],x['seed'],x['arm'],x['stage'])):
        text+=f"| {r['project']} | {r['seed']} | {r['arm']} | {r['stage']} | {r['public_final']['passed']} | {r['hidden_primary']['passed']} → {r['hidden_final']['passed']} | {sum(p['completed'] for p in r['phases'])}/{len(r['phases'])} | {len(r['repairs'])} |\n"
    text+='\nRead the frozen protocol and summary.json for cached/uncached/generated tokens, native timing, stage wall time, regressions and workflow completion. Public repair feedback is not hidden grading. Hidden cases were controller-authored; projects were convenience selected. Two seeds are not statistical proof. Raw requests/native reasoning stay local with hashes; exact public prompt replay is unavailable. Earlier failures and calibration work are reported separately, never erased.\n'
    (dest/'README.md').write_text(text,encoding='utf-8')


def summarize_repair(raw,dest):
    rows=json.loads((raw/'results.json').read_text());summary={'arms':{},'pairs':16,'cases_per_arm':16}
    diagnostics=[c for f in raw.glob('*/diagnostic') for c in calls(f)]
    summary['shared_diagnostic_physical_work']=accounting(diagnostics)
    findings=[]
    for p in sorted(raw.glob('*/pair.json')):
        meta=json.loads(p.read_text());evaluation=meta.get('evaluation') or {}
        for finding in evaluation.get('findings',[]):
            # Candidate mapping is not automatic adjudication of a concrete defect.
            subject=finding.get('subject','')
            findings.append(dict(pair=p.parent.name,project=meta['project'],variant=meta['variant'],seed=meta['seed'],finding=finding,
                seeded_requirements=meta['seeded_requirements'],subject_matches_seed=any(x in subject for x in meta['seeded_requirements']),
                adjudication='pending_manual_review'))
    write_json(dest/'findings-to-adjudicate.json',findings)
    for arm in ('ordinary_repair','aee_guided_repair'):
        subset=[r for r in rows if r['arm']==arm]
        records=[c for f in raw.glob('*/'+arm) for c in calls(f)]
        economics=accounting(records); attributed=accounting(diagnostics+records)
        fixes=sum(r['fixed'] for r in subset); successes=sum(r['hidden_final']['passed'] for r in subset)
        summary['arms'][arm]=dict(repair_only=economics,with_shared_diagnostic_attributed=attributed,fixed=fixes,buggy_cases=12,
            final_accepted=successes,total_cases=16,clean_regressions=sum(r['regressed'] for r in subset),
            clean_code_changes=sum(any(x['source_changed'] for x in r['repairs']) for r in subset if r['variant']=='clean'),
            repair_rounds=sum(len(r['repairs']) for r in subset),source_changing_rounds=sum(x['source_changed'] for r in subset for x in r['repairs']),
            first_round_fixes=sum(not r['hidden_before']['passed'] and r['repairs'][0]['hidden']['passed'] for r in subset),
            tokens_per_fixed=attributed['total_tokens']/fixes if fixes and attributed['total_tokens'] is not None else None,
            wall_seconds=sum(r['seconds'] for r in subset))
    write_json(dest/'summary.json',summary)
    text='# Matched ordinary versus AEE-guided repair\n\n16 identical-start pairs: two projects × (three seeded defects + one clean control) × two seeds. Shared diagnostic input goes to both arms; only guided receives its actual AEE findings. Not a full Spec Kit workflow comparison.\n\n'
    text+='| Arm | Bugs fixed /12 | Final accepted /16 | Clean regressions /4 | Clean cases changed | Repair tokens | Tokens incl. shared diagnostic | Tokens/fix |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for arm,v in summary['arms'].items():
        text+=f"| {arm} | {v['fixed']} | {v['final_accepted']} | {v['clean_regressions']} | {v['clean_code_changes']} | {v['repair_only']['known_total_tokens']:,} | {v['with_shared_diagnostic_attributed']['known_total_tokens']:,} | {v['tokens_per_fixed'] if v['tokens_per_fixed'] is not None else 'undefined'} |\n"
    text+='\nShared diagnostic tokens are charged equally in treatment comparisons but counted once in the physical-work ledger. Unknown native usages remain null; reservation totals are not measured token totals. Findings require manual adjudication: subject overlap alone is not proof of defect detection. See findings-to-adjudicate.json and the final adjudication report.\n'
    (dest/'README.md').write_text(text,encoding='utf-8')


def manifest(dest):
    files={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file() and p.name!='files-sha256.json'}
    write_json(dest/'files-sha256.json',files)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['study','repair']);parser.add_argument('raw',type=Path);parser.add_argument('dest',type=Path);a=parser.parse_args()
    export(a.raw,a.dest)
    (summarize_study if a.kind=='study' else summarize_repair)(a.raw,a.dest)
    manifest(a.dest)
