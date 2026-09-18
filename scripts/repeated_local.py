"""Repeated local campaigns; isolated graders, reserved unknown usage, real AEE."""
import argparse
import ast
import hashlib
import json
import math
import os
import random
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from benchmark_runner.store import Store, canonical, utc, write_json
from benchmark_runner.workflow import assess, grounded_claims
from gpu_experiment import local_json, digest
from long_horizon import Sandbox, CLAIMS, skill, PHASE_GOALS
from report_long_horizon import source_digest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / 'benchmarks/repeated_local'
IMAGE = 'sha256:adc751293f079d2ed0a459cbeb36e2b746ef8382e23d0b04c1fa282b8cb2a120'
PROJECTS = {
    'tinydb': {'upstream':'artifacts/tinydb-upstream', 'package':'tinydb', 'module':'tinydb/journal.py', 'revision':'19066e03139e904c24410e23901e4b069d715a2e'},
    'cachetools': {'upstream':'artifacts/cachetools-upstream', 'package':'src/cachetools', 'module':'src/cachetools/tagged.py', 'revision':'c403f9f4185e58090b904c1915345b9ba46d5a08'},
}
SEEDS = [20260918, 20260919]
ARMS = ['baseline', 'spec_kit', 'spec_kit_aee']
COMMON = '''You are a capable software engineering agent in an isolated real repository.
Return exactly one JSON action: {"action":"shell","command":"..."} or
{"action":"done","summary":"implemented and actually verified work"}.
Use shell to inspect/edit source and run tests. No internet or human assistance.
Do not modify upstream tests or acceptance_public.py. You may add your own tests.
Preserve previous active requirements. The latest requirement text overrides older
asserted design notes. You may keep persistent HANDOFF.md and any other notes.
All shell commands run in /testbed. Use PYTHONPATH=src:. for repository imports.
Do not fabricate test evidence. Hidden acceptance is unavailable. Inspect concise
outputs; full tool outputs are retained as evidence. Source and notes persist at
the stage-three handoff but conversation history is cleared for every arm.
'''
CONFIG = dict(context=32768, max_output=4096, primary_calls=160, repair_calls=8,
              repair_rounds=2, stage_seconds=2400, token_cap=18000000,
              seeds=SEEDS, temperature=0.6, top_p=0.95, top_k=20,
              history='drop oldest complete pairs at context boundary; explicit stage3 reset',
              unknown_policy='retain null native usage; reserve input+max_output; wait for idle slot; continue within cap')


def reservation(call):
    usage = call.get('usage')
    return usage['total_tokens'] if usage is not None else call['preflight_input_tokens'] + call['max_output']


def compact_assessment(value):
    # Preserve semantic fields without nested raw copies. Full JSON stays in evidence.
    return {key:value.get(key) for key in ('outcome','findings','next_action','confidence','uncertainty') if key in value}


def tests_for(project, stage, public):
    source=(TASK/project/'tests.py').read_text()
    parts=source.split('# STAGE2')
    first=parts[0]; second,third=parts[1].split('# STAGE3')
    chosen=first+(second if stage>=2 else '')+(third if stage>=3 else '')
    if not public:
        return chosen.encode()
    tree=ast.parse(chosen)
    keep=[node for node in tree.body if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
          or not node.name.startswith('test_') or node.name.startswith('test_public_')]
    tree.body=keep
    return ast.unparse(tree).encode()


class ProjectSandbox(Sandbox):
    def __init__(self, project):
        self.project=project
        super().__init__(IMAGE,ROOT/PROJECTS[project]['upstream'])
    def snapshot(self,path):
        package=PROJECTS[self.project]['package']
        command=("import io,tarfile,pathlib,sys; b=io.BytesIO(); t=tarfile.open(fileobj=b,mode='w'); "
                 f"files=sorted(pathlib.Path({package!r}).rglob('*.py')); "
                 "assert files and all(not p.is_symlink() for p in files); "
                 "[t.add(p,arcname=str(p)) for p in files]; t.close(); sys.stdout.buffer.write(b.getvalue())")
        path.write_bytes(subprocess.check_output(['docker','exec',self.name,'python','-c',command],timeout=30))


def grade(project,snapshot,stage,public,expected=None):
    with ProjectSandbox(project) as box:
        if snapshot:
            # The fixed known package path is inside the isolated container only.
            box.execute('rm -rf /testbed/'+PROJECTS[project]['package'])
            box.put_archive(Path(snapshot).read_bytes(),'/testbed')
        box.put({'test_acceptance.py':tests_for(project,stage,public)},'/grade')
        result=box.execute('PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null -q tests /grade/test_acceptance.py --junitxml=/tmp/grade.xml',120)
        xml=box.execute('cat /tmp/grade.xml')['stdout']
        try:
            cases=[dict(name=n.attrib.get('name'),file=n.attrib.get('classname'),passed=not any(n.find(k) is not None for k in ('failure','error','skipped')),
                        failures=[dict(kind=c.tag,message=c.attrib.get('message'),text=c.text) for c in n if c.tag in ('failure','error','skipped')])
                   for n in ET.fromstring(xml).iter('testcase')]
        except ET.ParseError: cases=[]
        return dict(passed=result['exit_code']==0 and bool(cases) and (expected is None or len(cases)==expected) and all(c['passed'] for c in cases),
                    test_count=len(cases),cases=cases,output=result['stdout']+result['stderr'],expected=expected)


class Provider:
    def __init__(self,folder,seed,timeout):
        self.folder=folder; self.seed=seed; self.timeout=timeout; self.calls=[]
        self.folder.mkdir(parents=True,exist_ok=True)
    def query(self,messages,phase,stage,deadline):
        if (self.folder.parent/'CANCEL').exists(): raise KeyboardInterrupt('cancelled')
        chosen=[dict(m) for m in messages]; removed=0
        while True:
            prompt=local_json('/apply-template',dict(messages=chosen,chat_template_kwargs={'enable_thinking':True}))['prompt']
            count=len(local_json('/tokenize',dict(content=prompt,add_special=False))['tokens'])
            if count+CONFIG['max_output']<=CONFIG['context']: break
            if len(chosen)<=3: raise RuntimeError('fixed_instructions_exceed_context')
            # Keep system/current requirements; drop the oldest exchange only.
            del chosen[2:4]; removed+=2
        if sum(reservation(c) for c in self.calls)+count+CONFIG['max_output']>CONFIG['token_cap']:
            raise RuntimeError('reserved_token_cap')
        remaining=deadline-time.monotonic()
        if remaining<self.timeout: raise TimeoutError('insufficient_request_time_reservation')
        request=dict(model='long-coder',messages=chosen,temperature=0.6,top_p=0.95,top_k=20,min_p=0.0,
                     presence_penalty=0.0,repeat_penalty=1.0,seed=self.seed,max_tokens=CONFIG['max_output'],
                     cache_prompt=bool(self.calls),response_format={'type':'json_object'},
                     chat_template_kwargs={'enable_thinking':True})
        record=dict(stage=stage,phase=phase,started_at=utc(),request=request,usage=None,unknown_reason='pending',
                    preflight_input_tokens=count,max_output=CONFIG['max_output'],removed_history_messages=removed)
        path=self.folder/f'call-{len(self.calls):04}.json';self.calls.append(record);write_json(path,record,exclusive=True)
        begin=time.monotonic()
        try:
            response=local_json('/v1/chat/completions',request,self.timeout)
            record.update(response=response,usage=response.get('usage'),unknown_reason=None if response.get('usage') else 'native_usage_missing')
            choice=response['choices'][0]
            if choice['finish_reason']!='stop':raise RuntimeError('output_limit:'+str(choice['finish_reason']))
            return choice['message']['content']
        except Exception as exc:
            record['request_seconds']=time.monotonic()-begin
            record['error']=type(exc).__name__+': '+str(exc)
            if record['usage'] is None:
                record['unknown_reason']='failed_request_reserved_not_imputed'
                # Do not start overlapping work after a disconnected request.
                wait=time.monotonic()+self.timeout
                while time.monotonic()<wait:
                    try:
                        slots=local_json('/slots',timeout=10)
                        if all(not s.get('is_processing') for s in slots): break
                    except Exception: pass
                    time.sleep(2)
                else:raise RuntimeError('server_not_idle_after_failure') from exc
            raise
        finally:
            record.setdefault('request_seconds',time.monotonic()-begin)
            record.update(seconds=time.monotonic()-begin,ended_at=utc(),budget_debit=reservation(record))
            write_json(path,record)
            print(f'CALL {self.folder.name} stage={stage} phase={phase} n={len(self.calls)} seconds={record["seconds"]:.1f}',flush=True)


class Session:
    def __init__(self,box,provider,store,identity):
        self.box=box; self.provider=provider; self.store=store; self.identity=identity
        self.history=[];self.tools=0
    def phase(self,phase,instructions,spec,stage,limit,deadline,claims=False):
        messages=[dict(role='system',content=COMMON+'\nCURRENT PHASE: '+phase+'\n'+instructions+('\n'+CLAIMS if claims else '')),
                  dict(role='user',content=spec)] + list(self.history)
        messages.append(dict(role='user',content=f'Begin the current {phase} phase now. You have at most {limit} actions in this phase, including done. Complete its requested deliverable, then return done.'))
        done=None;errors=[];start=len(self.provider.calls)
        for step in range(limit):
            if step==limit-1:
                messages.append(dict(role='user',content='This is the last allocated action for this phase. Return done now with an honest summary of completed and unresolved work'+(' and the required claims object.' if claims else '. Do not perform another shell action.')))
            if step==limit-2:
                messages.append(dict(role='user',content='Two actions remain in this phase. Finish the requested artifact/check now and use done to report its actual state; preserve unresolved issues.'))
            try:
                text=self.provider.query(messages,phase,stage,deadline)
                action=json.loads(text)
                if not isinstance(action,dict):raise ValueError('Action must be an object')
                messages.append(dict(role='assistant',content=text))
                if action.get('action')=='done':
                    if claims:
                        from aee.model import Claim
                        bundle=action.get('claims')
                        if not isinstance(bundle,dict) or not bundle.get('claims'):raise ValueError('Nonempty claims required')
                        for c in bundle['claims']:Claim.from_dict(c)
                    required={'constitution':'.specify/memory/constitution.md','specify':'specs/001-transactions/spec.md','plan':'specs/001-transactions/plan.md','tasks':'specs/001-transactions/tasks.md'}.get(phase)
                    if required:
                        check=self.box.execute("python -c \"from pathlib import Path;p=Path('"+required+"');assert p.is_file() and len(p.read_text())>100 and '[PROJECT_NAME]' not in p.read_text()\"")
                        if check['exit_code']:raise ValueError('Required phase artifact missing or scaffold: '+required)
                    done=action;break
                if action.get('action')!='shell' or not isinstance(action.get('command'),str):raise ValueError('Expected shell command or done')
                result=self.box.execute(action['command'],60);self.tools+=1
                ref=self.store.artifact(canonical(dict(command=action['command'],**result)))
                self.store.append('tools',dict(attempt_id=self.identity,timestamp=utc(),artifact=ref,exit_code=result['exit_code']))
                observation=dict(exit_code=result['exit_code'],stdout=result['stdout'][-6000:],stderr=result['stderr'][-2000:],evidence_ref=ref['path'],source_id=ref['sha256'])
                messages.append(dict(role='user',content=json.dumps(observation)))
            except Exception as exc:
                errors.append(type(exc).__name__+': '+str(exc))
                if 'server_not_idle' in str(exc) or isinstance(exc,TimeoutError) or 'token_cap' in str(exc):break
                messages.append(dict(role='user',content='Last action/request failed: '+errors[-1]+'. Correct the action; do not invent evidence.'))
        self.history=messages[2:]
        # Bound history promptly as well as by measured tokenization on next call.
        self.store.append('history',dict(phase=phase,stage=stage,messages=len(self.history)))
        return dict(phase=phase,done=done,completed=done is not None,errors=errors,calls=len(self.provider.calls)-start)


def do_assessment(session,row,phase,done):
    claims=grounded_claims(done['claims'],session.store,session.identity)
    started=time.monotonic()
    evaluation=assess(ROOT,claims,phase,session.store)
    value=dict(phase=phase,claims=claims,evaluation=evaluation,outcome=evaluation['outcome'],seconds=time.monotonic()-started)
    row['assessments'].append(value)
    session.history.append(dict(role='user',content='AEE/Evaluator findings (not hidden grades). Claim atomicity/schema/evidence-quality findings are not established code defects: fix claim structure or gather scoped evidence, and leave correct code unchanged unless a concrete behavioral defect is identified. Do not repeatedly rewrite passing tests to change claim wording. '+json.dumps(compact_assessment(evaluation))))
    return evaluation


def calibrate(out):
    out.mkdir(parents=True,exist_ok=False)
    result={'passed':False,'projects':{},'created_at':utc()}
    for project in PROJECTS:
        snapshot=out/f'{project}-reference.tar'
        with ProjectSandbox(project) as box:
            box.put({PROJECTS[project]['module']:(TASK/project/'reference.py').read_bytes()})
            box.snapshot(snapshot)
        entries={}
        for stage in (1,2,3):
            for public in (True,False):
                key=f'{stage}-'+('public' if public else 'hidden')
                entry=grade(project,snapshot,stage,public)
                entries[key]=entry
                assert entry['passed'],(project,key,entry['output'])
        untouched=grade(project,None,3,False)
        assert not untouched['passed']
        result['projects'][project]=dict(reference=entries,untouched=untouched)
        write_json(out/'calibration.json',result)
    result['passed']=True;write_json(out/'calibration.json',result)
    print('REFERENCE CALIBRATION PASS',flush=True)


def latency(out):
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    # Near provider context limit; use actual tokenization, not character estimate.
    filler='Calibration neutral context only. alpha beta gamma delta 0123456789.\n'*2500
    while True:
        tokens=len(local_json('/tokenize',dict(content=filler,add_special=False))['tokens'])
        if tokens<26000:break
        filler=filler[:int(len(filler)*0.94)]
    for i in range(2):
        request=dict(model='long-coder',messages=[dict(role='user',content=filler+'\nOutput a JSON object containing the integers 1 through 10000. Do not explain. Continue until the output limit.')],max_tokens=4096,temperature=0.6,seed=SEEDS[0],cache_prompt=False,chat_template_kwargs={'enable_thinking':True})
        start=time.monotonic(); response=local_json('/v1/chat/completions',request,600)
        record=dict(seconds=time.monotonic()-start,request=request,response=response,usage=response.get('usage'))
        records.append(record);write_json(out/f'call-{i:04}.json',record)
        print('LATENCY',i,record['seconds'],flush=True)
    timeout=max(180,min(600,math.ceil(max(r['seconds'] for r in records)*2/30)*30))
    write_json(out/'calibration.json',dict(passed=True,timeout=timeout,context_tokens=tokens,samples=2,records=[f'call-{i:04}.json' for i in range(2)]))


def campaign(out,preflight,timeout):
    # No outcome-dependent changes and no rerun/resume of partial trajectories.
    out.mkdir(parents=True,exist_ok=False)
    cal=json.loads((preflight/'calibration.json').read_text());assert cal['passed']
    gate=json.loads((ROOT/'artifacts/repeated-workflow-04/result.json').read_text());assert gate['passed']
    latency_result=json.loads((ROOT/'artifacts/repeated-latency-01/calibration.json').read_text());assert latency_result['passed'] and timeout==latency_result['timeout']
    for project,meta in PROJECTS.items():
        actual=subprocess.check_output(['git','-c','safe.directory='+str((ROOT/meta['upstream']).resolve()).replace('\\','/'),'-C',str(ROOT/meta['upstream']),'rev-parse','HEAD'],text=True).strip()
        assert actual==meta['revision']
    schedule=[(p,s,a) for p in PROJECTS for s in SEEDS for a in ARMS]
    random.Random(SEEDS[0]).shuffle(schedule)
    hashes={str(p.relative_to(ROOT)):digest(p) for folder in (TASK,ROOT/'prompts',ROOT/'src/benchmark_runner',ROOT/'.specify/extensions',ROOT/'.specify/templates',ROOT/'.specify/scripts/python') for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for item in (ROOT/'artifacts/repeated-assets/installed-aee').rglob('*.py'):
        hashes[str(item.relative_to(ROOT))]=digest(item)
    for name in ('hardware.json','server-launch.json','package-versions.json'):
        item=ROOT/'artifacts/repeated-assets'/name;hashes[str(item.relative_to(ROOT))]=digest(item)
    hashes['scripts/calibrate_repeated_workflow.py']=digest(ROOT/'scripts/calibrate_repeated_workflow.py')
    hashes['scripts/gpu_experiment.py']=digest(ROOT/'scripts/gpu_experiment.py')
    hashes['scripts/report_long_horizon.py']=digest(ROOT/'scripts/report_long_horizon.py')
    hashes['uv.lock']=digest(ROOT/'uv.lock')
    hashes['.specify/memory/constitution.md']=digest(ROOT/'.specify/memory/constitution.md')
    hashes['scripts/repeated_local.py']=digest(__file__);hashes['scripts/long_horizon.py']=digest(ROOT/'scripts/long_horizon.py')
    freeze=dict(created_at=utc(),config={**CONFIG,'timeout':timeout},schedule=schedule,hashes=hashes,projects=PROJECTS,image=IMAGE,server_props=local_json('/props'),calibration=cal,workflow_calibration=gate,latency_calibration=latency_result)
    write_json(out/'freeze.json',freeze,exclusive=True)
    rows=[]
    for project,seed,arm in schedule:
        identity=f'{project}-{seed}-{arm}';folder=out/identity;folder.mkdir()
        provider=Provider(folder,seed,timeout);store=Store(folder/'evidence')
        with ProjectSandbox(project) as box:
            if arm!='baseline':box.stage_workflow()
            session=Session(box,provider,store,identity)
            for stage in (1,2,3):
                begin=time.monotonic();deadline=begin+CONFIG['stage_seconds'];start=len(provider.calls)
                spec='\n\n'.join((TASK/project/f'stage{i}.md').read_text() for i in range(1,stage+1))
                box.put({'acceptance_public.py':tests_for(project,stage,True),f'TASK_STAGE_{stage}.md':spec.encode()})
                row=dict(project=project,seed=seed,arm=arm,stage=stage,phases=[],assessments=[],repairs=[],started_at=utc(),handoff=stage==3)
                rows.append(row)
                if stage==3:
                    handoff=box.execute('git status --short; test ! -f HANDOFF.md || cat HANDOFF.md')
                    row['handoff_record']=handoff
                    subprocess.run(['docker','restart',box.name],check=True,capture_output=True,timeout=30)
                    session.history=[]
                phases=['solve'] if arm=='baseline' else (['constitution'] if stage==1 else [])+['specify','plan','tasks','implement','converge','final_implement']
                for phase in phases:
                    left=CONFIG['primary_calls']-(len(provider.calls)-start)
                    if left<=0:break
                    goal='Implement the active milestone; plan and keep notes as useful; run public and upstream tests. Finish with done.' if arm=='baseline' else PHASE_GOALS[phase].replace('/testbed/tinydb','/testbed/'+PROJECTS[project]['package'])
                    instructions=goal
                    if arm!='baseline':
                        instructions=(ROOT/'prompts/adapter.md').read_text().replace('/workflow','/testbed')+'\n'+skill(phase).replace('$ARGUMENTS',goal+'\n'+spec)+'\n'+goal+'\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions. Keep documents concise and evidence explicit.'
                    limits={'constitution':32,'specify':32,'plan':32,'tasks':32,'implement':32,'converge':16,'final_implement':16}
                    need_claims=arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement')
                    phase_before=folder/f'stage{stage}-{phase}-before.tar';box.snapshot(phase_before)
                    phase_row=session.phase(phase,instructions,spec,stage,min(left,limits.get(phase,left)),deadline,need_claims)
                    phase_after=folder/f'stage{stage}-{phase}-after.tar';box.snapshot(phase_after)
                    phase_row.update(source_changed=source_digest(phase_before)!=source_digest(phase_after),source_before=str(phase_before.relative_to(out)),source_after=str(phase_after.relative_to(out)))
                    row['phases'].append(phase_row)
                    if need_claims and phase_row['done']:
                        try:
                            evaluation=do_assessment(session,row,phase,phase_row['done'])
                            if phase=='implement' and evaluation['outcome'] not in ('pass','warn'):
                                rework=session.phase('evidence_rework','Address actual evidence gaps with repository inspection/tests and scoped changes. Keep unsupported claims explicit; return revised claims.',spec,stage,min(16,max(0,CONFIG['primary_calls']-(len(provider.calls)-start))),deadline,True)
                                row['phases'].append(rework)
                                if rework['done']:do_assessment(session,row,'implement',rework['done'])
                        except Exception as exc:row['assessments'].append(dict(phase=phase,error=repr(exc)))
                    write_json(out/'attempts.json',rows)
                primary=folder/f'stage{stage}-primary.tar';box.snapshot(primary)
                expected=cal['projects'][project]['reference'][f'{stage}-public']['test_count']
                row['primary_snapshot']=str(primary.relative_to(out));row['public_primary']=grade(project,primary,stage,True,expected)
                current=row['public_primary']
                for iteration in (1,2):
                    if current['passed']:break
                    before=source_digest(primary if iteration==1 else folder/f'stage{stage}-repair1.tar')
                    repair=session.phase('repair','Repair using public test feedback. Preserve active requirements.\n'+current['output'][-12000:],spec,stage,CONFIG['repair_calls'],deadline)
                    snap=folder/f'stage{stage}-repair{iteration}.tar';box.snapshot(snap)
                    current=grade(project,snap,stage,True,expected)
                    repair.update(round=iteration,grade=current,source_changed=source_digest(snap)!=before,snapshot=str(snap.relative_to(out)))
                    row['repairs'].append(repair)
                final=folder/f'stage{stage}-final.tar';box.snapshot(final)
                row.update(final_snapshot=str(final.relative_to(out)),public_final=current,seconds=time.monotonic()-begin,calls=len(provider.calls)-start,ended_at=utc())
                notes=box.execute('find .specify specs -type f 2>/dev/null; test ! -f HANDOFF.md || cat HANDOFF.md')
                row['notes_index']=notes
                if arm!='baseline':
                    (folder/f'stage{stage}-workflow.tar').write_bytes(subprocess.check_output(['docker','exec',box.name,'tar','--exclude=.git','-cf','-','-C','/testbed','.specify','specs'],timeout=30))
                write_json(out/'attempts.json',rows)
                print('CHECKPOINT',identity,stage,current['passed'],row['calls'],flush=True)
    for row in rows:
        expected=cal['projects'][row['project']]['reference'][f'{row["stage"]}-hidden']['test_count']
        for kind in ('primary','final'):
            row['hidden_'+kind]=grade(row['project'],out/row[kind+'_snapshot'],row['stage'],False,expected)
        write_json(out/'results.json',rows)
    print('CAMPAIGN COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['calibrate','latency','run'])
    parser.add_argument('out',type=Path)
    parser.add_argument('--preflight',type=Path)
    parser.add_argument('--timeout',type=int,default=240)
    args=parser.parse_args()
    if args.mode=='calibrate':calibrate(args.out)
    elif args.mode=='latency':latency(args.out)
    else:campaign(args.out,args.preflight,args.timeout)
