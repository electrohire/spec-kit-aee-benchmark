"""Freeze or execute the registered upstream coding pilot; never resume a run.

Freezing is offline/model-free except live GitHub CI readback. Scoring requires
fresh native admission receipts for the exact head and the already restored
worker. Hidden grading/publication remain separate after generation ends.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import tarfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from benchmark_runner.upstream_agent_adapter import AdmissionError, BoundNativeTransport, safe_upstream, write_exclusive
from benchmark_runner.upstream_resources import TaskResource
from benchmark_runner.upstream_task_runner import run_task
from benchmark_runner.upstream_tree_transfer import import_tree

REPO='electrohire/spec-kit-aee-benchmark'
BINDING_SHA='7920ce6c8cb34c30970a38ede24743dddf649aefd5d243219c67b62ca15e4b6a'
WEIGHTS_SHA='322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482'
ARMS=('baseline','spec_kit','spec_kit_aee')
NATIVE_COMMANDS=tuple('echo NATIVE_ADMISSION_%02d'%i for i in range(1,5))


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def stamp():return datetime.now(timezone.utc).isoformat()


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def clean_head():
    if git('status','--porcelain'):raise AdmissionError('clean committed source required; no inference')
    return git('rev-parse','HEAD')


def live_ci(head):
    raw=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/runs?head_sha={head}&per_page=100'])
    runs=json.loads(raw)['workflow_runs']
    found={}
    for event in ('push','pull_request'):
        candidates=[r for r in runs if r['head_sha']==head and r['event']==event
                    and r['path']=='.github/workflows/ci.yml']
        if not candidates:raise AdmissionError('exact-head hosted CI missing for '+event)
        latest=max(candidates,key=lambda r:r['id'])
        if latest['status']!='completed' or latest['conclusion']!='success':
            raise AdmissionError('latest exact-head hosted CI is not green for '+event)
        found[event]=latest
    return found


def source_files():
    return {name:sha(ROOT/name) for name in git('ls-files').splitlines() if (ROOT/name).is_file()}


def runtime_files():
    values={}
    names={'mini-swe-agent','jsonschema','jsonschema-specifications','referencing','rpds-py','attrs'}|set(importlib.metadata.packages_distributions().get('aee',[]))
    for name in sorted(names):
        distribution=importlib.metadata.distribution(name)
        for item in distribution.files or []:
            p=Path(distribution.locate_file(item)).resolve()
            if p.is_file() and p.suffix!='.pyc' and '__pycache__' not in p.parts and not p.name.startswith('.env'):
                values[str(p)]=sha(p)
    if (importlib.metadata.version('mini-swe-agent')!='2.4.6' or
            importlib.metadata.version('applied-epistemic-engineering')!='1.5.3' or
            importlib.metadata.version('jsonschema')!='4.26.0'):
        raise AdmissionError('registered baseline agent/engine/schema version changed')
    return values


def schedule(rows):
    units=[dict(arm=arm,indices=indices) for arm in ARMS for indices in ([0],[1],[2,3])]
    random.Random(20261019).shuffle(units)
    ordered=[]
    for unit,group in enumerate(units):
        for release,index in enumerate(group['indices'],1):
            row=rows[index]
            ordered.append(dict(sequence=len(ordered),unit=unit,arm=group['arm'],index=index,
                instance_id=row['instance_id'],release=release,dependent=(release>1),
                status='unattempted',native_request_attempts=0,known_native_tokens=0,
                usage_unknown=0,completion_declaration='unknown',independent_grade=None))
    return ordered


def freeze(inputs,out,binding):
    head=clean_head();ci=live_ci(head)
    original=json.loads((inputs/'manifest.json').read_text())
    if original['source_head']!=head or original.get('source_was_dirty'):
        raise AdmissionError('prepare inputs from this exact clean head after CI')
    if original['source_script_sha256']!=sha(ROOT/'scripts/prepare_upstream_coding_inputs.py'):
        raise AdmissionError('input preparer source differs')
    if sha(binding)!=BINDING_SHA:raise AdmissionError('not the explicitly restored worker binding')
    out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(inputs,out/'inputs')
    shutil.copyfile(binding,out/'worker-binding.json')
    with (out/'source.tar').open('xb') as handle:
        subprocess.run(['git','archive','--format=tar',head],cwd=ROOT,stdout=handle,check=True)
    # Git archive is canonical repository bytes. Also retain the exact local
    # declared bytes used on this host (including pre-existing checkout EOLs).
    with tarfile.open(out/'declared-source.tar','x') as archive:
        for name in source_files():archive.add(ROOT/name,arcname=name,recursive=False)
    input_hashes={p.relative_to(out/'inputs').as_posix():sha(p) for p in (out/'inputs').rglob('*') if p.is_file()}
    ordered=schedule(original['rows'])
    assert len(ordered)==12 and len({(r['arm'],r['index']) for r in ordered})==12
    value=dict(schema='upstream-coding-pilot-v1',created_at=stamp(),source_root=str(ROOT),source_head=head,
        source_archive_sha256=sha(out/'source.tar'),declared_source_archive_sha256=sha(out/'declared-source.tar'),
        source_files=source_files(),runtime_files=runtime_files(),
        input_files=input_hashes,worker_binding_sha256=BINDING_SHA,weights_sha256=WEIGHTS_SHA,
        ci=ci,rows=ordered,registration=json.loads((out/'inputs/registration-draft.json').read_text()),
        scope='Two FeatureBench cold starts and an adapted two-release Dask source sequence per arm; selected subset, one seed, not full official leaderboard or an independent replication.',
        rules='First failure halts. No retries, source edits, hidden-grade feedback, model/service changes or implicit restoration. All future rows remain explicit unknown/unattempted with zero new calls.')
    write_exclusive(out/'freeze.json',value)
    write_exclusive(out/'state.json',dict(stage='frozen_pending_native_admission',at=stamp(),rows=ordered,
        source_head=head,freeze_sha256=sha(out/'freeze.json'),mission_complete=False))
    print(json.dumps(dict(frozen=str(out),source_head=head,freeze_sha256=sha(out/'freeze.json'),rows=12,generation_requests=0)))


def verify_frozen(out):
    value=json.loads((out/'freeze.json').read_text())
    if clean_head()!=value['source_head'] or source_files()!=value['source_files']:
        raise AdmissionError('frozen controller source changed')
    if runtime_files()!=value['runtime_files']:raise AdmissionError('declared installed runtime bytes changed')
    if sha(out/'source.tar')!=value['source_archive_sha256']:raise AdmissionError('source archive changed')
    if sha(out/'declared-source.tar')!=value['declared_source_archive_sha256']:
        raise AdmissionError('declared local source archive changed')
    for name,digest in value['input_files'].items():
        if sha(out/'inputs'/name)!=digest:raise AdmissionError('frozen upstream input changed')
    live_ci(value['source_head'])
    return value


def verify_native(out,value):
    folder=(out/'native-admission').resolve()
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['source_head']!=value['source_head'] or manifest['freeze_sha256']!=sha(out/'freeze.json'):
        raise AdmissionError('native admission is not bound to this source/freeze')
    if manifest.get('source_unchanged') is not True:
        raise AdmissionError('native admission source comparison missing')

    def evidence(name):
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or path.is_symlink() or not path.is_file():
            raise AdmissionError('native evidence outside admission scope or missing')
        if manifest['files'].get(name)!=sha(path):
            raise AdmissionError('native admission evidence changed/unbound')
        return path

    for name in manifest['files']:evidence(name)
    calls=manifest['calls']
    if len(calls)!=4 or manifest['worker_binding_sha256']!=BINDING_SHA:
        raise AdmissionError('four native original-tool admission calls required')
    receipts={p.relative_to(folder).as_posix() for p in (folder/'model').glob('call-*.json')}
    if receipts!={row['receipt'] for row in calls}:
        raise AdmissionError('native request inventory does not match admission rows')
    from benchmark_runner.upstream_agent_adapter import native_usage
    for index,row in enumerate(calls):
        record=json.loads(evidence(row['receipt']).read_text())
        response=record.get('response',{})
        choices=response.get('choices',[])
        tools=choices[0].get('message',{}).get('tool_calls',[]) if len(choices)==1 else []
        if len(tools)!=1 or tools[0]['function']['name']!='bash':
            raise AdmissionError('original native bash tool result required')
        arguments=json.loads(tools[0]['function']['arguments'])
        usage=native_usage(response)
        duration=record['ended_at']-record['started_at']
        request=record['request']
        if (not record['usage_validated'] or record.get('error') or record['usage']!=usage or
                choices[0]['finish_reason']!='tool_calls' or response['model']!='qwen3.8-27b' or
                arguments!={'command':NATIVE_COMMANDS[index]} or
                record['preflight_input_tokens']+request['max_tokens']>32768 or
                request['max_tokens']!=8192 or request['seed']!=20261019 or
                request['chat_template_kwargs']!={'enable_thinking':False} or
                row['native_prompt_tokens']!=usage['prompt_tokens'] or
                row['duration_seconds']!=duration or not 0<duration<600):
            raise AdmissionError('native tool/usage/context/timing admission failed')
        echo=json.loads(evidence(row['echo_receipt']).read_text())
        if (echo['command']!=NATIVE_COMMANDS[index] or echo['returncode']!=0 or
                echo['output'].strip()!=NATIVE_COMMANDS[index].removeprefix('echo ')):
            raise AdmissionError('actual native action delivery did not match its literal output')
        if index>=2 and not 24000<=usage['prompt_tokens']<=24576:
            raise AdmissionError('fresh two-sample native timing admission missing')
    if not json.loads(evidence('resource/owned-cleanup.json').read_text())['observed_absent']:
        raise AdmissionError('native admission resource cleanup not verified')


def score(out):
    value=verify_frozen(out);verify_native(out,value)
    if (out/'scoring-started.json').exists():raise AdmissionError('existing scoring episode; never resume/retry')
    transport=BoundNativeTransport(out/'worker-binding.json',BINDING_SHA,WEIGHTS_SHA)
    if any(s.get('is_processing') for s in transport('/slots',None,30)):
        raise AdmissionError('worker busy; no overlap')
    upstream=safe_upstream()
    write_exclusive(out/'scoring-started.json',dict(at=stamp(),pid=os.getpid(),freeze_sha256=sha(out/'freeze.json')))
    rows=json.loads(json.dumps(value['rows']));previous={};failure=None

    def state(stage):
        temporary=out/'state.pending.json'
        temporary.write_text(json.dumps(dict(stage=stage,at=stamp(),pid=os.getpid(),rows=rows,
            failure=failure,source_head=value['source_head'],freeze_sha256=sha(out/'freeze.json'),
            mission_complete=False),indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,out/'state.json')
    state('scoring')
    try:
        for row in rows:
            row.update(status='preparing',started_at=stamp());state('scoring')
            case=out/'trajectories'/('%02d'%row['sequence']);case.mkdir(parents=True,exist_ok=False)
            item=json.loads((out/'inputs/manifest.json').read_text())['rows'][row['index']]
            bundle=out/'inputs'/('case-%02d'%row['index'])
            group=out/'projects'/('%02d'%row['unit'])
            purpose='upstream-'+sha(out/'freeze.json')[:10]+'-'+str(row['sequence'])
            package=out/'inputs/grader/featurebench-package.json'
            with TaskResource(upstream=upstream,source_root=ROOT,out=case/'resource',
                row_path=bundle/'controller-full-row.json',row_sha256=item['controller_row_sha256'],
                expected_featurebench_package=package,package_manifest_sha256=sha(package),
                image_id=item['image_id'],kind=item['kind'],purpose=purpose) as resource:
                baseline=resource.prepared['baseline_commit'];tree=resource.initial['candidate_tree'];prior=None
                if row['dependent']:
                    earlier=previous[row['unit']]
                    transferred=import_tree(resource.environment,earlier['pack'],case/'carry',
                        reader_python='/opt/miniconda3/envs/testbed/bin/python')
                    baseline=transferred['baseline_commit'];tree=transferred['retained_tree']
                    old=earlier['result'];feedback=old.get('actual_AEE_feedback') or {}
                    prior=dict(previous_instance_id=earlier['instance_id'],previous_status=old['status'],
                        previous_feature_documents=old['draft_documents'],retained_source_tree=tree,
                        unresolved_findings=feedback.get('findings',[]),
                        prior_feedback_summary=feedback.get('summary'),prior_next_action=feedback.get('next_action'),
                        independent_grades='unavailable during generation',accepted_delivery='unknown')
                row['status']='running';state('scoring')
                result=run_task(upstream=upstream,transport=transport,environment=resource.environment,
                    source_root=ROOT,out=case/'execution',arm=row['arm'],
                    public_task=(bundle/'public-task.txt').read_bytes().decode('utf-8'),
                    baseline_commit=baseline,literal_baseline_tree=tree,deadline=time.monotonic()+14400,
                    continuity_root=group,prior_context=prior,instance_id=row['instance_id'],study_id=out.name)
                row.update(status=result['status'],native_request_attempts=result['native_request_attempts'],
                    known_native_tokens=result['known_native_tokens_lower_bound'],usage_unknown=result['usage_unknown'],
                    completion_declaration='submitted_proxy_not_human_acceptance',ended_at=stamp())
                previous[row['unit']]=dict(instance_id=row['instance_id'],result=result,
                    pack=case/'execution/checkpoints/final/literal-tree-pack')
            state('scoring')
        state('generation_complete_pending_independent_grades')
    except BaseException as exc:
        failure=repr(exc)
        # Recover actual counters/source receipts for the failed endpoint only;
        # never turn an unattempted endpoint into another inference attempt.
        row['status']='stopped_first_failure';row['ended_at']=stamp()
        result_path=case/'execution/task-result.json'
        if result_path.is_file():
            result=json.loads(result_path.read_text());row.update(
                native_request_attempts=result['native_request_attempts'],
                known_native_tokens=result['known_native_tokens_lower_bound'],usage_unknown=result['usage_unknown'])
        state('stopped_first_failure_pending_offline_grades')
        raise
    finally:
        write_exclusive(out/'generation-ended.json',dict(at=stamp(),failure=failure,rows=rows,
            source_still_matches=(source_files()==value['source_files']),mission_complete=False,
            boundary='Generation terminal only; independent grades, complete cost/integrity audits and publication still required.'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    action=p.add_mutually_exclusive_group(required=True)
    action.add_argument('--freeze',action='store_true');action.add_argument('--score',action='store_true')
    p.add_argument('--study-root',type=Path,required=True)
    p.add_argument('--inputs',type=Path);p.add_argument('--binding',type=Path)
    a=p.parse_args()
    if a.freeze:
        if a.inputs is None or a.binding is None:p.error('--freeze requires --inputs and --binding')
        freeze(a.inputs.resolve(),a.study_root.resolve(),a.binding.resolve())
    else:score(a.study_root.resolve())


if __name__=='__main__':main()
