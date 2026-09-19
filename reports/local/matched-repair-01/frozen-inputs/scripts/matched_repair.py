"""Paired identical-start repairs with seeded defects and clean negative controls."""
import argparse
import json
import random
import time
from pathlib import Path

from repeated_local import (ROOT,TASK,PROJECTS,SEEDS,Provider,ProjectSandbox,Session,
                            Store,CONFIG,grade,tests_for,assess,grounded_claims,
                            compact_assessment,write_json,digest,utc)
from report_long_horizon import source_digest

VARIANTS={
 'tinydb':{
  'bool_id':("type(ident) is not int", "not isinstance(ident, int)",['R04']),
  'token_alias':("self.tokens[token] = (deepcopy(operations), deepcopy(inserted))", "self.tokens[token] = (deepcopy(operations), inserted)",['R08']),
  'partial_commit':("docs[next_id] = deepcopy(op['document'])", "docs[next_id] = deepcopy(op['document']); self.db.storage.write({'_default':docs})",['R02','R05']),
  'clean':(None,None,[]),
 },
 'cachetools':{
  'expiry_boundary':("now >= entry[2]", "now > entry[2]",['R07','R08']),
  'value_alias':("return deepcopy(self._cache[key][0])", "return self._cache[key][0]",['R01','R06']),
  'boolean_ttl':("isinstance(ttl, bool) or not isinstance(ttl, (int,float))", "not isinstance(ttl, (int,float))",['R07']),
  'clean':(None,None,[]),
 }
}


def variant_source(project,variant):
    text=(TASK/project/'reference.py').read_text()
    before,after,_=VARIANTS[project][variant]
    if before:
        assert text.count(before)==1
        text=text.replace(before,after)
    return text.encode()


def calibration(out,preflight):
    out.mkdir(parents=True,exist_ok=False)
    expected=json.loads((preflight/'calibration.json').read_text())
    rows=[]
    for project,variants in VARIANTS.items():
        for variant in variants:
            snap=out/f'{project}-{variant}.tar'
            with ProjectSandbox(project) as box:
                box.put({PROJECTS[project]['module']:variant_source(project,variant)})
                box.snapshot(snap)
            grade_result=grade(project,snap,3,False,expected['projects'][project]['reference']['3-hidden']['test_count'])
            assert grade_result['passed']==(variant=='clean'),(project,variant,grade_result['output'])
            failed=[c['name'] for c in grade_result['cases'] if not c['passed']]
            rows.append(dict(project=project,variant=variant,seeded_requirements=VARIANTS[project][variant][2],snapshot=snap.name,source_hash=source_digest(snap),grade=grade_result,failed_cases=failed))
            write_json(out/'calibration.json',dict(passed=False,variants=rows))
    write_json(out/'calibration.json',dict(passed=True,variants=rows))
    print('MATCHED REPAIR FIXTURE CALIBRATION PASS',flush=True)


def run(out,preflight,timeout):
    out.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((preflight/'calibration.json').read_text());assert fixture['passed']
    study_freeze=json.loads((ROOT/'artifacts/repeated-study-01/freeze.json').read_text())
    hashes=dict(study_freeze['hashes'])
    for name,sha in hashes.items():
        assert digest(ROOT/name)==sha, 'Changed frozen input: '+name
    hashes[str(Path(__file__).resolve().relative_to(ROOT))]=digest(__file__)
    for item in preflight.glob('*'):
        if item.is_file():hashes[str(item.resolve().relative_to(ROOT))]=digest(item)
    schedule=[(r,s) for r in fixture['variants'] for s in SEEDS]
    random.Random(SEEDS[1]).shuffle(schedule)
    write_json(out/'freeze.json',dict(timestamp=utc(),schedule=[(r['project'],r['variant'],s) for r,s in schedule],timeout=timeout,
        diagnostic_calls=8,repair_rounds=2,calls_per_round=8,stage_seconds=1200,config=CONFIG,
        hashes=hashes,projects=PROJECTS,study_freeze_sha256=digest(ROOT/'artifacts/repeated-study-01/freeze.json'),
        pairing='Shared read-only diagnostic and raw claims, identical start/feedback/tools; only guided receives actual AEE findings. Shared model cost charged equally per arm for comparison and once in physical-work ledger.'))
    rows=[]
    for reference,seed in schedule:
        project,variant=reference['project'],reference['variant'];pair=f'{project}-{variant}-{seed}'
        folder=out/pair;folder.mkdir();source=preflight/reference['snapshot']
        spec='\n\n'.join((TASK/project/f'stage{i}.md').read_text() for i in (1,2,3))
        public=grade(project,source,3,True)
        diagnostic=Provider(folder/'diagnostic',seed,timeout);store=Store(folder/'diagnostic/evidence')
        with ProjectSandbox(project) as box:
            box.put_archive(source.read_bytes(),'/testbed')
            box.put({'acceptance_public.py':tests_for(project,3,True)})
            session=Session(box,diagnostic,store,pair)
            summary=session.phase('diagnose','Read-only review of the implementation and public test feedback. It may be correct or contain defects. Do not edit source. Inspect relevant code/tests, then return grounded requirement claims, explicit uncertainty and concrete suspected defects if any. Do not invent observations.\nPublic feedback:\n'+public['output'][-10000:],spec,3,8,time.monotonic()+1200,True)
            check=folder/'after-diagnostic.tar';box.snapshot(check)
            diagnostic_changed=source_digest(check)!=source_digest(source)
        if summary['done'] and not diagnostic_changed:
            claims=grounded_claims(summary['done']['claims'],store,pair)
            assessment_begin=time.monotonic()
            evaluation=assess(ROOT,claims,'implement',store)
            assessment_seconds=time.monotonic()-assessment_begin
        else:
            claims=None;evaluation=None;assessment_seconds=0
        pair_meta=dict(project=project,variant=variant,seed=seed,diagnostic=summary,diagnostic_changed_source=diagnostic_changed,claims=claims,evaluation=evaluation,
                       assessment_seconds=assessment_seconds,source_hash=reference['source_hash'],public_before=public,seeded_requirements=reference['seeded_requirements'])
        write_json(folder/'pair.json',pair_meta)
        arms=['ordinary_repair','aee_guided_repair'];random.Random(seed+len(variant)).shuffle(arms)
        for arm in arms:
            armfolder=folder/arm;provider=Provider(armfolder,seed,timeout);armstore=Store(armfolder/'evidence')
            row=dict(pair=pair,project=project,variant=variant,seed=seed,arm=arm,repairs=[],started_at=utc(),diagnostic_valid=claims is not None)
            rows.append(row);begin=time.monotonic()
            with ProjectSandbox(project) as box:
                box.put_archive(source.read_bytes(),'/testbed');box.put({'acceptance_public.py':tests_for(project,3,True)})
                session=Session(box,provider,armstore,pair+'-'+arm)
                current=public
                for iteration in (1,2):
                    instruction='Review and repair if necessary using requirements, source and public feedback. This may be a clean negative control: do not change correct code without a concrete reason. Preserve existing APIs and tests.\nShared diagnostic (assertions are not proof):\n'+json.dumps(summary['done'])+'\nPublic feedback:\n'+current['output'][-10000:]
                    if arm=='aee_guided_repair':
                        instruction+='\nActual AEE/Evaluator findings (not hidden test results):\n'+json.dumps(compact_assessment(evaluation) if evaluation else {'error':'Shared diagnostic incomplete; no valid assessment'})
                    before=source if iteration==1 else armfolder/'repair1.tar'
                    repaired=session.phase('repair',instruction,spec,3,8,begin+1200)
                    snap=armfolder/f'repair{iteration}.tar';box.snapshot(snap)
                    current=grade(project,snap,3,True)
                    repaired.update(round=iteration,source_changed=source_digest(snap)!=source_digest(before),snapshot=str(snap.relative_to(out)),public=current)
                    row['repairs'].append(repaired)
                    # Same fixed two opportunities for every case/control; a public pass alone
                    # does not establish all requirements, so allow the second review too.
                final=armfolder/'final.tar';box.snapshot(final)
                row.update(final_snapshot=str(final.relative_to(out)),seconds=time.monotonic()-begin,calls=len(provider.calls),ended_at=utc())
                write_json(out/'attempts.json',rows)
                print('REPAIR CHECKPOINT',pair,arm,row['calls'],flush=True)
    # Never feed hidden outcomes back to either treatment or shared diagnostic.
    for row in rows:
        reference=next(r for r in fixture['variants'] if r['project']==row['project'] and r['variant']==row['variant'])
        row['hidden_before']=reference['grade']
        row['hidden_final']=grade(row['project'],out/row['final_snapshot'],3,False,reference['grade']['test_count'])
        for repair in row['repairs']:
            repair['hidden']=grade(row['project'],out/repair['snapshot'],3,False,reference['grade']['test_count'])
        row['fixed']=not row['hidden_before']['passed'] and row['hidden_final']['passed']
        row['regressed']=row['hidden_before']['passed'] and not row['hidden_final']['passed']
        write_json(out/'results.json',rows)
    print('MATCHED REPAIR COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['calibrate','run']);parser.add_argument('out',type=Path);parser.add_argument('--preflight',type=Path,required=True);parser.add_argument('--timeout',type=int,default=180);a=parser.parse_args()
    if a.mode=='calibrate':calibration(a.out,a.preflight)
    else:run(a.out,a.preflight,a.timeout)
