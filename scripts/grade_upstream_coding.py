"""Offline upstream checkpoint grading after the sole solver episode has ended.

Never invokes an inference transport. Original submitted patch and retained
non-test workspace projection are distinct measurements; no gold substitution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from benchmark_runner.upstream_agent_adapter import AdmissionError, safe_upstream, write_exclusive
from benchmark_runner.upstream_resources import TaskResource, _remove_owned
from benchmark_runner.upstream_tree_transfer import make_grader_patch
from run_upstream_coding import sha, stamp, verify_frozen

GRADERS={'FeatureBench':'sha256:d62c9102f060d774fcb2ab8c25854829c827ecf4049e9c31e351d69e9555fcf8',
         'SWE-EVO':'sha256:a0806176038aae4b4beccd0236e68a3bb53eb2b6ea808783cfda6a3b2b40d972'}
READER='/opt/miniconda3/envs/testbed/bin/python'


def grade_one(bundle,patch,out,item,inputs,purpose):
    """One independent upstream grader invocation, no retry or candidate edits."""
    out.mkdir(parents=True,exist_ok=False);(out/'results').mkdir()
    kind=item['kind'];script='upstream_grade_featurebench.py' if kind=='FeatureBench' else 'upstream_grade_swe.py'
    for source,name in [(ROOT/'scripts'/script,'run.py'),(bundle/'controller-full-row.json','input.json'),
            (patch,'candidate.patch'),(inputs/'grader'/('featurebench-package.json' if kind=='FeatureBench' else 'swe-package.json'),'expected-grader-package.json')]:
        shutil.copyfile(source,out/name)
    row=json.loads((out/'input.json').read_text())
    if kind=='SWE-EVO':shutil.copyfile(inputs/'grader/official_merge_patches.py',out/'official_merge_patches.py')
    plan=dict(control_id=purpose,instance_id=item['instance_id'],image=item['image_id'],
        grader_image_id=GRADERS[kind],input_sha256=sha(out/'input.json'),
        controller_sha256=sha(out/'run.py'),candidate_sha256=sha(out/'candidate.patch'),
        timeout_seconds=1800,model_calls=0,source_projection='See bound candidate provenance; no gold/candidate changes.')
    if kind=='SWE-EVO':
        def labels(value):return json.loads(value) if isinstance(value,str) else value
        plan['expected_test_counts']=[len(labels(row[n])) for n in ('FAIL_TO_PASS','PASS_TO_PASS')]
    if item['index']==1:
        plan.update(resource_path='/opt/miniconda3/envs/testbed/lib/python3.11/site-packages/astropy_iers_data/data/Leap_Second.dat',
            resource_sha256='6cb6f5d4b819f2e568e25db4b0b26d89dedf031fdffb18bc94d40f4e94e268d7')
    write_exclusive(out/'plan.json',plan)
    argv=['docker','run','--rm','--name',purpose+'-controller','--label','purpose='+purpose,
        '--pull=never','--network=none','--cpus=1','--memory=2g','--pids-limit=256',
        '--entrypoint','python','--mount','type=bind,source='+out.as_posix()+',target=/control,readonly',
        '--mount','type=bind,source='+(out/'results').as_posix()+',target=/results',
        '--mount','type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
        '--workdir','/results',GRADERS[kind],'/control/run.py']
    write_exclusive(out/'argv.json',argv)
    original=None;started=time.time()
    from benchmark_runner.upstream_resources import _inspect
    if _inspect(purpose+'-controller') is not None:
        raise AdmissionError('grader controller name collision; no existing resource mutation')
    try:
        with (out/'controller.log').open('xb') as handle:
            process=subprocess.run(argv,stdout=handle,stderr=subprocess.STDOUT,timeout=1950)
        result=json.loads((out/'results/result.json').read_text())
        write_exclusive(out/'controller-ended.json',dict(returncode=process.returncode,
            elapsed_seconds=time.time()-started,result_sha256=sha(out/'results/result.json')))
        if process.returncode or not result.get('grade_execution_complete'):
            raise AdmissionError('upstream grader incomplete; original output retained, no retry')
        return result
    except BaseException as exc:
        original=exc
        raise
    finally:
        try:_remove_owned(purpose+'-controller',purpose)
        except BaseException as cleanup:
            if original is not None:raise BaseExceptionGroup('Original grader and cleanup failure',[original,cleanup])
            raise


def run(study,destination):
    value=verify_frozen(study)
    if not (study/'generation-ended.json').is_file():
        raise AdmissionError('generation must be terminal before hidden grading')
    ended=json.loads((study/'generation-ended.json').read_text())
    if not ended['source_still_matches']:raise AdmissionError('solver source binding changed')
    destination.mkdir(parents=True,exist_ok=False)
    write_exclusive(destination/'started.json',dict(at=stamp(),freeze_sha256=sha(study/'freeze.json'),
        generation_ended_sha256=sha(study/'generation-ended.json'),model_calls=0))
    upstream=safe_upstream();inputs=study/'inputs';original=json.loads((inputs/'manifest.json').read_text())
    records=[];cache={};error=None
    try:
        for row in value['rows']:
            execution=study/'trajectories'/('%02d'%row['sequence'])/'execution'
            if not (execution/'task-result.json').is_file():
                records.append(dict(sequence=row['sequence'],arm=row['arm'],instance_id=row['instance_id'],
                    status='unattempted_or_preparation_failed',grade=None,accepted_delivery=None));continue
            task=json.loads((execution/'task-result.json').read_text());item=original['rows'][row['index']]
            bundle=inputs/('case-%02d'%row['index']);case=destination/('%02d'%row['sequence']);case.mkdir()
            purpose='coding-grade-'+sha(study/'freeze.json')[:10]+'-'+str(row['sequence'])
            package=inputs/'grader/featurebench-package.json'
            checks=[]
            with TaskResource(upstream=upstream,source_root=ROOT,out=case/'resource',
                    row_path=bundle/'controller-full-row.json',row_sha256=item['controller_row_sha256'],
                    expected_featurebench_package=package,package_manifest_sha256=sha(package),
                    image_id=item['image_id'],kind=item['kind'],purpose=purpose+'-projection') as resource:
                for name in ['initial','after-planning','implementation-016','implementation-032','implementation-064','implementation-128','final','stopped']:
                    pack=execution/'checkpoints'/name/'literal-tree-pack'
                    if not pack.exists():
                        checks.append(dict(checkpoint=name,status='not_reached',grade=None));continue
                    converted=case/'projections'/name
                    proof=make_grader_patch(resource.environment,pack,converted,
                        registered_grade_base_tree=resource.initial['candidate_tree'],reader_python=READER,
                        projection='non_test_submission')
                    key=(row['index'],proof['patch_sha256'])
                    if key in cache:
                        reused=cache[key]
                        grade=dict(checkpoint=name,status='identical_patch_grade_reuse',
                            grade_path=reused['grade_path'],grade_result_sha256=reused['grade_result_sha256'],
                            projection_sha256=sha(converted/'conversion.json'),model_calls=0)
                    else:
                        grade_path=case/'grades'/name
                        grade_one(bundle,converted/'candidate.patch',grade_path,item,inputs,purpose+'-'+name)
                        grade=dict(checkpoint=name,status='independently_graded',
                            grade_path=grade_path.relative_to(destination).as_posix(),
                            grade_result_sha256=sha(grade_path/'results/result.json'),
                            projection_sha256=sha(converted/'conversion.json'),model_calls=0)
                        cache[key]=grade
                    checks.append(grade)
            proposal=execution/'submitted.patch';submission=None
            if proposal.is_file():
                submission=dict(bytes=proposal.stat().st_size,sha256=sha(proposal),empty=not bool(proposal.read_bytes().strip()))
                if not submission['empty']:
                    path=case/'grades/original-submitted-patch'
                    grade_one(bundle,proposal,path,item,inputs,purpose+'-original-submission')
                    submission.update(grade_path=path.relative_to(destination).as_posix(),grade_result_sha256=sha(path/'results/result.json'))
            records.append(dict(sequence=row['sequence'],arm=row['arm'],instance_id=row['instance_id'],
                generation_status=task['status'],checkpoints=checks,original_submission=submission,
                accepted_delivery=False if submission and submission['empty'] else None,
                boundary='Grades require independent log/author-ID audit. Retained workspace correctness never substitutes for an empty/incomplete submitted proposal.'))
            write_exclusive(case/'summary.json',records[-1]);print(json.dumps(records[-1]),flush=True)
    except BaseException as exc:error=repr(exc);raise
    finally:
        write_exclusive(destination/'ended.json',dict(at=stamp(),error=error,records=records,
            model_calls=0,mission_complete=False,scope='Offline original upstream grades, not an independent human replication or release approval.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.study_root.resolve(),a.out.resolve())
