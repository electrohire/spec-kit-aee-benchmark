"""Tool-backed staged TinyDB study. All inference is explicit localhost HTTP."""
import argparse
import io
import json
import os
import random
import subprocess
import tarfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from benchmark_runner.store import Store, canonical, utc, write_json
from benchmark_runner.workflow import assess, grounded_claims
from benchmark_runner.runner import MiniModel, MiniEnvironment
from gpu_experiment import local_json, digest, source_hashes

ROOT=Path(__file__).resolve().parents[1]
TASK=ROOT/'benchmarks/long_horizon'
ARMS=['baseline','spec_kit','spec_kit_aee']
COMMON='''You are a capable software engineering agent working in a real TinyDB repository.
Inspect files, plan as useful, edit code, add your own tests and run existing tests.
Preserve earlier active requirements as new milestones arrive. You may keep notes.
No internet or human assistance. All shell commands run inside /testbed in an isolated
container. Use exactly one JSON action: {"action":"shell","command":"..."} or
{"action":"done","summary":"what you implemented and actually verified"}.
Commands may use cd explicitly. Do not claim tests ran without command evidence.
Upstream tests are visible; public milestone tests are acceptance_public.py. Hidden
tests are unavailable and will not be supplied as feedback. The newest task text
is authoritative. Source implementation belongs in /testbed/tinydb. Do not modify
upstream tests to make them pass. Workflow artifacts are outside the submitted code.
'''
CLAIMS='''At phase completion, include a claims object in your done JSON. Extract actual
active requirements, not a generic assertion. Example shape (replace example values):
"claims":{"schema_version":"1.0","claims":[{"id":"R01","text":"bounded claim",
"kind":"requirement","status":"unsupported","boundary":["this milestone"],
"depends_on":[],"conflicts_with":[],"falsification_tests":["specific counterexample"],
"source_ref":"milestone requirement R01","uncertainty":"high","evidence":[]}]}
Keep each requirement claim's kind="requirement" (claim kind is never "observed").
Inside its evidence array, for actual shell evidence use kind="observed", source_quality="test" or "primary",
ref=<evidence_ref returned by shell>, source_id=<source_id returned by shell>,
direction="supports" and a scoped description. A test you authored is an observed
test result, not independent validation. Unverified prose remains asserted/model.
'''


def archive_files(files):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for name,data in files.items():
            info=tarfile.TarInfo(name)
            info.size=len(data);info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    return buffer.getvalue()


class Sandbox:
    def __init__(self,image,upstream):
        self.name='aee-long-'+uuid.uuid4().hex
        self.image,self.upstream=image,upstream
    def __enter__(self):
        subprocess.run(['docker','run','-d','--name',self.name,'--network','none','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2',
            '--user','1000:1000',self.image],check=True,capture_output=True,timeout=60)
        info=json.loads(subprocess.check_output(['docker','inspect',self.name]))[0]
        assert not info['Mounts'] and info['HostConfig']['NetworkMode']=='none'
        data=subprocess.check_output(['git','-c','safe.directory='+self.upstream.resolve().as_posix(),'-C',str(self.upstream),'archive','HEAD'],timeout=30)
        self.put_archive(data,'/testbed')
        self.execute('git init -q && git add . && git -c user.name=Benchmark -c user.email=benchmark@example.invalid commit -qm base')
        return self
    def put_archive(self,data,target):
        subprocess.run(['docker','exec','-i',self.name,'tar','--no-same-owner','-xf','-','-C',target],
                       input=data,check=True,capture_output=True,timeout=30)
    def put(self,files,target='/testbed'):
        self.put_archive(archive_files(files),target)
    def execute(self,command,timeout=60):
        # Linux timeout terminates commands inside container, not only the Docker client.
        limit=max(1,int(timeout))
        result=subprocess.run(['docker','exec',self.name,'timeout','-k','2',str(limit),
            'bash','-lc',command],capture_output=True,timeout=limit+10)
        return dict(exit_code=result.returncode,stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace'))
    def stage_workflow(self):
        files={}
        for part in ('scripts/python','templates'):
            for p in (ROOT/'.specify'/part).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:
                    files['.specify/'+part+'/'+p.relative_to(ROOT/'.specify'/part).as_posix()]=p.read_bytes()
        files['.specify/memory/constitution.md']=(ROOT/'.specify/templates/constitution-template.md').read_bytes()
        self.put(files,'/testbed')
        self.execute('mkdir -p /testbed/specs/001-transactions')
    def snapshot(self,path):
        # Only source modules cross into grading. No solver tests/config/hooks.
        command="import io,tarfile,pathlib,sys; b=io.BytesIO(); t=tarfile.open(fileobj=b,mode='w'); files=sorted(pathlib.Path('tinydb').rglob('*.py')); assert all(not p.is_symlink() for p in files); [t.add(p,arcname=str(p)) for p in files]; t.close(); sys.stdout.buffer.write(b.getvalue())"
        data=subprocess.check_output(['docker','exec',self.name,'python','-c',command],timeout=30)
        path.write_bytes(data)
    def __exit__(self,*args):
        subprocess.run(['docker','rm','-f',self.name],capture_output=True,timeout=30)


def acceptance(stage,kind):
    paths=[TASK/f'{kind}_base.py']
    paths += [TASK/f'{kind}_stage1.py'] if stage==1 else [TASK/f'{kind}_stage2.py']
    if stage==3:paths.append(TASK/f'{kind}_stage3.py')
    return b'\n\n'.join(p.read_bytes() for p in paths)


def grade(snapshot,stage,kind,image,upstream):
    with Sandbox(image,upstream) as sandbox:
        sandbox.execute('rm -rf /testbed/tinydb')
        sandbox.put_archive(snapshot.read_bytes(),'/testbed')
        sandbox.put({'test_acceptance.py':acceptance(stage,kind)},'/grade')
        result=sandbox.execute('PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null -q tests /grade/test_acceptance.py --junitxml=/tmp/grade.xml',120)
        xml=sandbox.execute('cat /tmp/grade.xml')
        try:
            root=ET.fromstring(xml['stdout'])
            cases=[dict(name=n.attrib.get('name'),file=n.attrib.get('classname'),passed=not any(n.find(t) is not None for t in ('failure','error','skipped')),
                        failures=[dict(kind=c.tag,message=c.attrib.get('message'),text=c.text) for c in n if c.tag in ('failure','error','skipped')]) for n in root.iter('testcase')]
        except ET.ParseError:
            cases=[]
        expected={'public':{1:227,2:228,3:231},'holdout':{1:229,2:231,3:247}}[kind][stage]
        return dict(passed=result['exit_code']==0 and len(cases)==expected and all(c['passed'] for c in cases),
                    expected_test_count=expected,
                    exit_code=result['exit_code'],cases=cases,test_count=len(cases),
                    passed_count=sum(c['passed'] for c in cases),output=result['stdout']+result['stderr'])


class Provider:
    def __init__(self,folder,stage_spec):
        self.folder=folder;self.calls=[];self.stage_spec=stage_spec;self.instructions='';self.stage=0
    def query(self,messages,phase,timeout):
        # Preserve the actual conversation and native reasoning returned by this model.
        history=[dict(role=m['role'],content=(m['content'].split('\n',1)[0]+' Begin this new phase now; follow its current system instructions.' if m['content'].startswith('CONTROL_PHASE:') else m['content'])) for m in messages if m['role']!='system']
        cursor=0
        for message in history:
            if message['role']!='assistant':continue
            for index in range(cursor,len(self.calls)):
                response=self.calls[index].get('response',{}).get('choices',[{}])[0].get('message',{})
                if response.get('content')==message['content']:
                    if response.get('reasoning_content'):message['reasoning_content']=response['reasoning_content']
                    cursor=index+1;break
        prefix=[dict(role='system',content=COMMON+'\nCURRENT PHASE: '+phase+'\n'+self.instructions+
            '\nFinish this phase with done when its artifacts are ready. You have 120 primary calls per stage and up to 20 calls per public repair round.'),
            dict(role='user',content=self.stage_spec)]
        removed=0
        while True:
            chosen=prefix+history
            rendered=local_json('/apply-template',dict(messages=chosen,chat_template_kwargs={'enable_thinking':True,'preserve_thinking':True}))['prompt']
            token_count=len(local_json('/tokenize',dict(content=rendered,add_special=False))['tokens'])
            if token_count+6144<=131072:break
            if not history:raise RuntimeError('Instructions exceed context')
            history=history[2:];removed+=2
        if len(self.calls)>=480 or sum((c.get('usage') or {}).get('total_tokens',0) for c in self.calls)+token_count+6144>60000000:
            raise RuntimeError('whole_project_token_or_call_limit')
        if any(c.get('usage') is None for c in self.calls):raise RuntimeError('unknown_usage_stop')
        payload=dict(model='long-coder',messages=chosen,temperature=0.6,top_p=0.95,top_k=20,min_p=0.0,presence_penalty=0.0,repeat_penalty=1.0,seed=20260917,max_tokens=6144,
                     cache_prompt=bool(self.calls),response_format={'type':'json_object'},reasoning_effort='medium',
                     chat_template_kwargs={'enable_thinking':True,'preserve_thinking':True})
        path=self.folder/f'call-{len(self.calls):03}.json'
        record=dict(stage=self.stage,phase=phase,started_at=utc(),request=payload,usage=None,
                    unknown_reason='pending',removed_history_messages=removed,preflight_input_tokens=token_count)
        self.calls.append(record);write_json(path,record,exclusive=True)
        start=time.monotonic()
        try:
            response=local_json('/v1/chat/completions',payload,min(timeout,180))
            record.update(response=response,usage=response.get('usage'),unknown_reason=None)
            choice=response['choices'][0]
            if choice['finish_reason']!='stop':raise RuntimeError('response_limit:'+choice['finish_reason'])
            return choice['message']['content']
        except BaseException as exc:
            record['error']=type(exc).__name__+': '+str(exc)
            if record['usage'] is None:record['unknown_reason']='failed_or_interrupted_call'
            raise
        finally:
            record.update(seconds=time.monotonic()-start,ended_at=utc());write_json(path,record)
            print(f'{self.folder.name} stage={self.stage} phase={phase} call={len(self.calls)} seconds={record["seconds"]:.1f}',flush=True)


def skill(phase):
    part='implement' if phase in ('final_implement','repair') else phase
    return (ROOT/f'prompts/skills/speckit-{part}.md').read_text(encoding='utf-8')

PHASE_GOALS={
    'constitution':'Write /testbed/.specify/memory/constitution.md using these supplied principles: preserve existing public API behavior; attach testable acceptance criteria to requirements; distinguish observed evidence from unverified assertions; prefer simple scoped implementations; document unresolved assumptions and regressions. Choose the project name from the task. These principles are approved inputs for this autonomous benchmark. Defer application implementation to later phases. Inspect only what is needed, write the document, then return done.',
    'specify':'Create or update spec.md in /testbed/specs/001-transactions for the current requirements, retaining active earlier requirements. Finish this specification phase with done.',
    'plan':'Create or update plan.md and needed supporting design artifacts for the current milestone, then return done.',
    'tasks':'Create or update tasks.md with executable tasks for this milestone, then return done.',
    'implement':'Implement the tasks in /testbed/tinydb, run tests, and update tasks.md with honest completion status, then return done.',
    'converge':'Review current artifacts, implementation and test evidence; document unresolved gaps and any follow-up tasks, then return done.',
    'final_implement':'Complete outstanding convergence tasks, rerun relevant checks, and report unresolved gaps, then return done.'}


def run_phase(agent,model,provider,phase,instructions,deadline,max_stage_calls,stage_start_count):
    instructions=instructions.replace('$ARGUMENTS', PHASE_GOALS.get(phase,'Complete the current milestone.')+'\n'+provider.stage_spec)
    provider.instructions=instructions;model.phase=phase;model.deadline=deadline
    agent.add_messages(dict(role='user',content='CONTROL_PHASE: '+phase+'\n'+instructions))
    artifact_retries=0
    claim_retries=0
    while True:
        if (provider.folder.parent/'CANCEL').exists():raise KeyboardInterrupt('campaign_cancelled')
        if time.monotonic()>=deadline:raise TimeoutError('stage_time_limit')
        if len(provider.calls)-stage_start_count>=max_stage_calls:raise RuntimeError('stage_call_limit')
        agent.step()
        if model.last['action']=='done':
            if CLAIMS in instructions:
                try:
                    from aee.model import Claim
                    bundle=model.last.get('claims')
                    if not isinstance(bundle,dict) or not isinstance(bundle.get('claims'),list) or not bundle['claims']:
                        raise ValueError('Required nonempty claims object/list is missing')
                    for claim in bundle['claims']:Claim.from_dict(claim)
                except (ValueError,TypeError,KeyError,AttributeError) as exc:
                    if claim_retries>=2:raise RuntimeError('phase_claims_invalid:'+phase+': '+str(exc))
                    claim_retries+=1
                    agent.add_messages(dict(role='user',content='Phase completion rejected by claims schema check: '+str(exc)[:1000]+'. Correct the structure without inventing evidence. '+CLAIMS))
                    continue
            required={'constitution':'.specify/memory/constitution.md','specify':'specs/001-transactions/spec.md',
                'plan':'specs/001-transactions/plan.md','tasks':'specs/001-transactions/tasks.md'}.get(phase)
            if required:
                command="python -c \"from pathlib import Path; p=Path('"+required+"'); s=p.read_text() if p.is_file() else ''; assert len(s)>100 and '[PROJECT_NAME]' not in s, 'Required phase artifact is absent or an unchanged scaffold'\""
                checked=agent.env.execute({'action':'shell','command':command})
                if checked['exit_code']:
                    if artifact_retries>=2:raise RuntimeError('phase_artifact_missing:'+phase)
                    artifact_retries+=1
                    agent.add_messages(dict(role='user',content='Phase completion rejected by mechanical artifact check. Write the required artifact before done. '+json.dumps(checked)))
                    continue
            return model.last


def campaign(output,upstream,image,metadata):
    meta=json.loads(metadata.read_text(encoding='utf-8-sig'))
    assert meta['smoke']['passed'] and meta['calibration']['passed']
    for path,sha in meta['verified_files'].items():
        assert digest(path)==sha, 'changed preflight file: '+path
    output.mkdir(parents=True,exist_ok=False)
    hashes=source_hashes()
    hashes.update({str(p.resolve()):digest(p) for p in TASK.rglob('*') if p.is_file()})
    for base in (ROOT/'.specify/scripts/python',ROOT/'.specify/templates'):
        hashes.update({str(p.resolve()):digest(p) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
    hashes[str((ROOT/'prompts/adapter.md').resolve())]=digest(ROOT/'prompts/adapter.md')
    hashes[str(Path(__file__).resolve())]=digest(__file__)
    schedule=ARMS.copy();random.Random(20260917).shuffle(schedule)
    freeze=dict(timestamp=utc(),hashes=hashes,upstream_revision=subprocess.check_output(['git','-c','safe.directory='+upstream.resolve().as_posix(),'-C',str(upstream),'rev-parse','HEAD'],text=True).strip(),
        image=image,metadata=meta,server_props=local_json('/props'),schedule=schedule,
        stage_seconds=3000,primary_seconds=2400,stage_max_calls=160,primary_max_calls=120,repair_round_max_calls=20,project_max_calls=480,project_token_cap=60000000,
        context=131072,max_output=6144,temperature=0.6,top_p=0.95,top_k=20,min_p=0.0,presence_penalty=0.0,seed=20260917,reasoning='enabled_server_budget_2048',public_repair_rounds=2,
        cache_policy='disabled first call per arm, enabled thereafter',history_policy='full conversation with native model reasoning; drop oldest pairs only at context boundary')
    write_json(output/'freeze.json',freeze,exclusive=True)
    os.environ['MSWEA_GLOBAL_CONFIG_DIR']=str(output/'mini-config')
    os.environ['MSWEA_SILENT_STARTUP']='1'
    from minisweagent.agents.default import DefaultAgent
    rows=[]
    for arm in schedule:
        folder=output/arm;folder.mkdir();store=Store(folder/'evidence')
        provider=Provider(folder,'');identity=dict(attempt_id=arm)
        with Sandbox(image,upstream) as sandbox:
            if arm!='baseline':sandbox.stage_workflow()
            model=MiniModel(provider,time.monotonic()+2400)
            environment=MiniEnvironment(sandbox,model.deadline,store,identity)
            agent=DefaultAgent(model,environment,system_template='',instance_template='',cost_limit=0)
            agent.add_messages(dict(role='system',content=COMMON))
            for stage in (1,2,3):
                begin=time.monotonic();deadline=begin+2400;environment.deadline=deadline
                provider.stage=stage
                provider.stage_spec='\n\n'.join((TASK/f'stage{s}.md').read_text() for s in range(1,stage+1))
                sandbox.put({'acceptance_public.py':acceptance(stage,'public'),f'TASK_STAGE_{stage}.md':provider.stage_spec.encode()})
                row=dict(arm=arm,stage=stage,started_at=utc(),phases=[],assessments=[],repairs=[],error=None)
                rows.append(row);start_count=len(provider.calls);start_tools=environment.tool_calls
                phases=['solve'] if arm=='baseline' else (['constitution'] if stage==1 else [])+['specify','plan','tasks','implement','converge','final_implement']
                try:
                    for phase in phases:
                        instructions='Implement this milestone, using any planning and repository tests you find useful. Finish only when ready for acceptance.' if arm=='baseline' else (
                            (ROOT/'prompts/adapter.md').read_text().replace('/workflow','/testbed')+f'\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions when running setup scripts.\n'+skill(phase))
                        if phase=='final_implement':instructions+='\nImplement outstanding convergence tasks and rerun tests. Finish with done; do not repeat planning.'
                        if arm!='baseline':instructions+='\nCURRENT PHASE DELIVERABLE: '+PHASE_GOALS[phase]
                        if arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement'):instructions+='\n'+CLAIMS
                        done=run_phase(agent,model,provider,phase,instructions,deadline,120,start_count)
                        row['phases'].append(dict(phase=phase,done=done));write_json(output/'attempts.json',rows)
                        if arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement'):
                            try:
                                claims=grounded_claims(done.get('claims') or {},store,arm)
                                evaluation=assess(ROOT,claims,phase,store)
                                row['assessments'].append(dict(phase=phase,outcome=evaluation['outcome'],claims=claims,evaluation=evaluation))
                                agent.add_messages(dict(role='user',content='AEE/Evaluator evidence gaps (not hidden-test grades): '+json.dumps(evaluation)))
                                if phase=='implement' and evaluation['outcome'] not in ('pass','warn'):
                                    done=run_phase(agent,model,provider,'evidence_rework','Gather available repository evidence and address the implementation gaps, preserving unresolved uncertainty. '+CLAIMS,deadline,120,start_count)
                                    claims=grounded_claims(done.get('claims') or {},store,arm)
                                    again=assess(ROOT,claims,'implement',store)
                                    row['assessments'].append(dict(phase='implement_rework',outcome=again['outcome'],claims=claims,evaluation=again))
                            except Exception as exc:
                                row['assessments'].append(dict(phase=phase,error=type(exc).__name__+': '+str(exc)))
                except Exception as exc:
                    row['error']=type(exc).__name__+': '+str(exc)
                snapshot=folder/f'stage{stage}-primary.tar';sandbox.snapshot(snapshot)
                row['primary_snapshot']=snapshot.relative_to(output).as_posix()
                row['public_primary']=grade(snapshot,stage,'public',image,upstream)
                current=row['public_primary']
                deadline=begin+3000;environment.deadline=deadline
                for repair_round in (1,2):
                    if current['passed'] or time.monotonic()+30>=deadline or len(provider.calls)-start_count>=160:break
                    repair=dict(round=repair_round,error=None)
                    row['repairs'].append(repair)
                    try:
                        instructions='Repair the current implementation using public acceptance/regression feedback. Preserve all active requirements. Use shell edits/tests; do not change upstream/public tests.\n'+current['output'][-20000:]
                        repair['done']=run_phase(agent,model,provider,'repair',instructions,deadline,20,len(provider.calls))
                    except Exception as exc:repair['error']=type(exc).__name__+': '+str(exc)
                    snapshot=folder/f'stage{stage}-repair{repair_round}.tar';sandbox.snapshot(snapshot)
                    current=grade(snapshot,stage,'public',image,upstream)
                    repair.update(snapshot=snapshot.relative_to(output).as_posix(),grade=current)
                final=folder/f'stage{stage}-final.tar';sandbox.snapshot(final)
                row.update(final_snapshot=final.relative_to(output).as_posix(),public_final=current,
                    seconds=time.monotonic()-begin,calls=len(provider.calls)-start_count,
                    tool_calls=environment.tool_calls-start_tools,ended_at=utc())
                if arm!='baseline':
                    workflow=subprocess.check_output(['docker','exec',sandbox.name,'tar','--exclude=.git','-cf','-','-C','/testbed','.specify','specs'],timeout=30)
                    (folder/f'stage{stage}-workflow.tar').write_bytes(workflow)
                patch=sandbox.execute('git diff --stat; git status --short')
                row['changes']=patch
                write_json(output/'attempts.json',rows)
                print(f'CHECKPOINT {arm} stage {stage}: public={current["passed"]} calls={row["calls"]} error={row["error"]}',flush=True)
    # Hidden cases never reach solver containers or feedback. Grade only now.
    for row in rows:
        row['hidden_primary']=grade(output/row['primary_snapshot'],row['stage'],'holdout',image,upstream)
        row['hidden_final']=grade(output/row['final_snapshot'],row['stage'],'holdout',image,upstream)
        write_json(output/'results.json',rows)
    print('All long-horizon stages and hidden grading complete',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    args=parser.parse_args()
    campaign(args.output,args.upstream,args.image,args.metadata)
