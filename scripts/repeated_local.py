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
from context_window import select_context
from infrastructure_errors import InfrastructureFailure
from runtime_checks import RuntimeWatchdog, RuntimeIntervention, validate_capacity
from action_protocol import action_response_format, action_command

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
Return exactly one JSON action: {"action":"exec","argv":["program","argument one","argument two"]} or
{"action":"write_file","path":"relative/file.py","content":"literal complete file content"} or
{"action":"done","summary":"what this phase actually completed and what remains"}.
Use write_file for creating/replacing files; its content is literal UTF-8,
not shell/Python source to quote again. Use exec to inspect source and run tests.
Every argument is literal: do not add shell quote characters around arguments.
Command strings, pipelines, shell actions and bash/sh -c wrappers are unavailable.
Issue separate actions for separate programs. Use write_file for helper scripts
then exec the script; executing existing bash script files is supported.
For example search with ["grep","-n","search text","relative/file.txt"]:
the pattern is one complete argv item, not a partially quoted command string.
Include every required operand. No model content is repaired. In fail-fast campaigns every nonzero tool
exit halts the campaign, including search no-match exits; use a program that
reports absent matches as data with exit zero when absence is an expected query
result. Never suppress execution/test errors. Reserve actions for phase deliverables.
Phase-control notices and controller diagnostics are not verification evidence.
No internet or human assistance.
Do not modify upstream tests or acceptance_public.py. You may add your own tests.
Preserve previous active requirements. The latest requirement text overrides older
asserted design notes. You may keep persistent HANDOFF.md and any other notes.
Programs run in /testbed. For repository imports use exec ["env","PYTHONPATH=src:.","python",...].
Do not fabricate test evidence. Hidden acceptance is unavailable. Inspect concise
outputs; full tool outputs are retained as evidence. Source and notes persist at
the stage-three handoff but conversation history is cleared for every arm.
'''
CONFIG = dict(context=32768, max_output=4096, primary_calls=160, repair_calls=8,
              repair_rounds=2, stage_seconds=2400, token_cap=18000000,
              seeds=SEEDS, temperature=0.6, top_p=0.95, top_k=20,
              history='first-fitting oldest two-message cutoff by calibrated binary search; explicit stage3 reset',
              unknown_policy='retain null native usage; reserve input+max_output; wait for idle slot; continue within cap')

PHASE_LIMITS={'constitution':32,'specify':32,'plan':32,'tasks':32,'implement':32,'converge':16,'final_implement':16}
PHASE_ARTIFACTS={'constitution':'.specify/memory/constitution.md','specify':'specs/001-transactions/spec.md','plan':'specs/001-transactions/plan.md','tasks':'specs/001-transactions/tasks.md'}
PHASE_CONTROL_PREFIX='[BENCHMARK_PHASE_CONTROL:'


def phase_control(phase,stage,text):
    return dict(role='user',content=f'{PHASE_CONTROL_PREFIX}{stage}:{phase}]\n'+text)


def is_phase_control(message):
    return message['role']=='user' and message['content'].startswith(PHASE_CONTROL_PREFIX)


def phase_artifact_check(path):
    return "python -c \"from pathlib import Path;p=Path('"+path+"');assert p.is_file() and len(p.read_text())>100 and '[PROJECT_NAME]' not in p.read_text()\""


def phase_plan(arm,stage):
    return ['solve'] if arm=='baseline' else (['constitution'] if stage==1 else [])+['specify','plan','tasks','implement','converge','final_implement']


def phase_instructions(project,arm,phase,spec,completion_contract):
    goal=('Implement the active milestone; plan and keep notes as useful; run public and upstream tests. Finish with done.'
          if arm=='baseline' else PHASE_GOALS[phase].replace('/testbed/tinydb','/testbed/'+PROJECTS[project]['package']))
    text=goal
    if arm!='baseline':
        text=(ROOT/'prompts/adapter.md').read_text().replace('/workflow','/testbed')+'\n'+skill(phase).replace('$ARGUMENTS',goal+'\n'+spec)+'\n'+goal+'\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions. Keep documents concise and evidence explicit.'
    if phase in ('solve','final_implement'):text+='\n'+completion_contract
    return text


def reservation(call):
    usage = call.get('usage')
    return usage['total_tokens'] if usage is not None else call['preflight_input_tokens'] + call['max_output']


def compact_assessment(value):
    # Preserve semantic fields without nested raw copies. Full JSON stays in evidence.
    result={key:value.get(key) for key in ('outcome','findings','next_action','confidence','uncertainty') if key in value}
    metadata=value.get('metadata') or {}
    display={key:metadata[key] for key in ('lane_states','reported_statuses','evaluator_count') if key in metadata}
    if display:result['metadata']=display
    return result


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
                    exit_code=result['exit_code'],test_count=len(cases),cases=cases,output=result['stdout']+result['stderr'],expected=expected)


class Provider:
    def __init__(self,folder,seed,timeout):
        self.folder=folder; self.seed=seed; self.timeout=timeout; self.calls=[]
        self.preflights=[]
        self.folder.mkdir(parents=True,exist_ok=True)
    def query(self,messages,phase,stage,deadline):
        if (self.folder.parent/'CANCEL').exists(): raise KeyboardInterrupt('cancelled')
        if deadline-time.monotonic()<self.timeout:
            raise TimeoutError('insufficient_request_time_reservation_before_preflight')
        preflight=dict(stage=stage,phase=phase,started_at=utc(),http_requests=0)
        self.preflights.append(preflight);preflight_begin=time.monotonic()
        def measure(selected):
            remaining=deadline-time.monotonic()-self.timeout
            if remaining<=0:raise TimeoutError('context_preflight_exhausted_phase_budget')
            probe_timeout=min(30,remaining)
            preflight['http_requests']+=1
            prompt=local_json('/apply-template',dict(messages=selected,chat_template_kwargs={'enable_thinking':CONFIG.get('enable_thinking',True)}),timeout=probe_timeout)['prompt']
            remaining=deadline-time.monotonic()-self.timeout
            if remaining<=0:raise TimeoutError('context_preflight_exhausted_phase_budget')
            preflight['http_requests']+=1
            return len(local_json('/tokenize',dict(content=prompt,add_special=False),timeout=min(30,remaining))['tokens'])
        try:
            chosen,count,removed=select_context(messages,measure,CONFIG['context'],CONFIG['max_output'])
            preflight.update(input_tokens=count,removed_history_messages=removed)
        except Exception as exc:
            preflight['error']=repr(exc)
            preflight['infrastructure_evidence']=getattr(exc,'evidence',None)
            if isinstance(exc,OSError):raise
            raise InfrastructureFailure('context preflight infrastructure failure',
                dict(original_error=repr(exc),preflight=preflight)) from exc
        finally:
            preflight.update(seconds=time.monotonic()-preflight_begin,ended_at=utc())
            try:
                write_json(self.folder/f'preflight-{len(self.preflights)-1:04}.json',preflight)
            except OSError as exc:
                raise InfrastructureFailure('context preflight evidence write failed',
                    dict(write_error=repr(exc),preflight=preflight)) from exc
        if sum(reservation(c) for c in self.calls)+count+CONFIG['max_output']>CONFIG['token_cap']:
            raise RuntimeError('reserved_token_cap')
        remaining=deadline-time.monotonic()
        if remaining<self.timeout: raise TimeoutError('insufficient_request_time_reservation')
        request=dict(model='long-coder',messages=chosen,temperature=0.6,top_p=0.95,top_k=20,min_p=0.0,
                     presence_penalty=0.0,repeat_penalty=1.0,seed=self.seed,max_tokens=CONFIG['max_output'],
                     cache_prompt=bool(self.calls),response_format=action_response_format(getattr(self,'requires_claims',False),structured=getattr(self,'structured_actions',False)),
                     chat_template_kwargs={'enable_thinking':CONFIG.get('enable_thinking',True)})
        record=dict(stage=stage,phase=phase,started_at=utc(),request=request,usage=None,unknown_reason='pending',
                    preflight_input_tokens=count,max_output=CONFIG['max_output'],removed_history_messages=removed,
                    preflight_http_requests=preflight['http_requests'],preflight_seconds=preflight['seconds'])
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
            if hasattr(exc,'evidence'):record['infrastructure_evidence']=exc.evidence
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
        self.watchdog=None
    def phase(self,phase,instructions,spec,stage,limit,deadline,claims=False):
        self.provider.requires_claims=claims
        messages=[dict(role='system',content=COMMON+'\nCURRENT PHASE: '+phase+'\n'+instructions+('\n'+CLAIMS if claims else '')),
                  dict(role='user',content=spec)] + list(self.history)
        messages.append(phase_control(phase,stage,f'Begin the current {phase} phase now. You have at most {limit} actions in this phase, including done. Complete its requested deliverable, then return done.'))
        done=None;errors=[];start=len(self.provider.calls)
        # Structural termination and staged deliverables apply to claim-bearing
        # phases only. Measured diagnostics show models ignore final-call nudges
        # and never emit done, so the final step is done-only (a non-done final
        # action is not executed; an honest terminal done is recorded instead)
        # and a mid-phase draft claims object is required. Non-claim phases keep
        # the previous nudge behavior.
        draft_step=limit//2 if (claims and limit>=6) else None
        draft_claims=None
        for step in range(limit):
            if step in (limit//2, 3*limit//4):
                required=PHASE_ARTIFACTS.get(phase)
                status=''
                if required:
                    check=self.box.execute(phase_artifact_check(required))
                    state='present_basic_check_only' if not check['exit_code'] else 'missing_or_scaffold'
                    data=dict(phase=phase,stage=stage,step=step,artifact=required,state=state,**check)
                    ref=self.store.artifact(canonical(data))
                    self.store.append('phase_progress',dict(**data,observation_ref=ref))
                    messages.append(dict(role='user',content=json.dumps(dict(
                        observation_type='phase_artifact_observation',phase=phase,stage=stage,
                        artifact=required,state=state,semantic_validation=False,
                        diagnostic_ref=ref,evidence_eligibility='controller diagnostic only'))))
                    status=f' Host artifact observation: {required}={state}; this is not semantic validation.'
                messages.append(phase_control(phase,stage,(
                    f'PHASE PROGRESS: {phase}; {limit-step} actions remain, including done. '
                    'Exploration alone does not complete this phase. Write the required '
                    'deliverables with write_file, inspect their actual contents, and report '
                    'unresolved work honestly. No extra actions will be granted.'+status)))
            if step==limit-1 and claims:
                messages.append(phase_control(phase,stage,'FINAL STEP: this is the last allocated action for this phase. Only a done action is accepted now. Return {"action":"done","summary":"...","claims":{"schema_version":"1.0","claims":[...]}} with your best current claims object'+(' (finalize your recorded mid-phase draft)' if draft_claims else '')+'. Shell actions are no longer available: any other action ends the phase and the harness records an honest terminal done.'))
            elif step==limit-1:
                messages.append(phase_control(phase,stage,'This is the last allocated action for this phase. Return done now with an honest summary of completed and unresolved work. Do not perform another shell action.'))
            elif draft_step is not None and step==draft_step:
                messages.append(phase_control(phase,stage,'MID-PHASE CHECKPOINT (action %d of %d). Return a draft claims object now: {"action":"draft","claims":{"schema_version":"1.0","claims":[...]}} with your current best hypothesis claims; they may be refined later, and you may also return done if finished. Shell exploration may continue afterwards, but this step does not accept shell actions.' % (step+1,limit)))
            elif step==limit-2:
                messages.append(phase_control(phase,stage,'Two actions remain in this phase. Finish the requested artifact/check now and use done to report its actual state; preserve unresolved issues.'))
            try:
                expected=f'{PHASE_CONTROL_PREFIX}{stage}:{phase}]\n'
                stale=[hashlib.sha256(m['content'].encode()).hexdigest() for m in messages
                       if is_phase_control(m) and not m['content'].startswith(expected)]
                if stale:
                    if self.watchdog:
                        self.watchdog.stop('stale phase control in active request',phase=phase,stage=stage,
                                           stale_control_sha256=stale)
                    raise RuntimeIntervention('stale phase control in active request')
                text=self.provider.query(messages,phase,stage,deadline)
                action=json.loads(text)
                if not isinstance(action,dict):raise ValueError('Action must be an object')
                messages.append(dict(role='assistant',content=text))
                if claims and step==limit-1 and action.get('action')!='done':
                    # Structural termination: the final-call nudge was ignored in
                    # 15/16 measured diagnostics, so a non-done final action is
                    # not executed. A draft returned on the final step is adopted
                    # as the terminal claims; otherwise an honest terminal done
                    # is synthesized (never inventing grounded claims).
                    if action.get('action')=='draft':
                        bundle=action.get('claims')
                        if isinstance(bundle,dict) and bundle.get('claims'):
                            from aee.model import Claim
                            for c in bundle['claims']:Claim.from_dict(c)
                            draft_claims=bundle
                    done=self._terminal_done(phase,limit,draft_claims)
                    errors.append('TerminalActionCoerced: non-done action on the final step was not executed; recorded honest terminal done')
                    break
                if draft_step is not None and step==draft_step and action.get('action') not in ('draft','done'):
                    raise ValueError('Mid-phase draft claims required on this step: return {"action":"draft","claims":{...}} or done')
                if claims and action.get('action')=='draft':
                    from aee.model import Claim
                    bundle=action.get('claims')
                    if not isinstance(bundle,dict) or not bundle.get('claims'):raise ValueError('Nonempty draft claims required')
                    for c in bundle['claims']:Claim.from_dict(c)
                    draft_claims=bundle
                    if self.watchdog:self.watchdog.success()
                    messages.append(dict(role='user',content=json.dumps(dict(
                        observation_type='draft_claim_receipt',phase=phase,stage=stage,
                        claims=len(bundle['claims']),truth_status='unassessed'))))
                    messages.append(phase_control(phase,stage,'Continue exploration or refinement; your final done must still include the complete claims object.'))
                    continue
                if action.get('action')=='done':
                    if claims:
                        from aee.model import Claim
                        bundle=action.get('claims')
                        if not isinstance(bundle,dict) or not bundle.get('claims'):raise ValueError('Nonempty claims required')
                        for c in bundle['claims']:Claim.from_dict(c)
                    required=PHASE_ARTIFACTS.get(phase)
                    if required:
                        check=self.box.execute(phase_artifact_check(required))
                        if check['exit_code']:raise ValueError('Required phase artifact missing or scaffold: '+required)
                    done=action
                    if self.watchdog:self.watchdog.success()
                    break
                command=action_command(action,allow_shell=not getattr(self.provider,'structured_actions',False))
                result=self.box.execute(command,60);self.tools+=1
                ref=self.store.artifact(canonical(dict(action=action,command=command,**result)))
                self.store.append('tools',dict(attempt_id=self.identity,timestamp=utc(),artifact=ref,exit_code=result['exit_code']))
                if self.watchdog:
                    self.watchdog.tool(command,result,phase,stage)
                    self.watchdog.success()
                observation=dict(exit_code=result['exit_code'],stdout=result['stdout'][-6000:],stderr=result['stderr'][-2000:],evidence_ref=ref['path'],source_id=ref['sha256'])
                messages.append(dict(role='user',content=json.dumps(observation)))
            except Exception as exc:
                if isinstance(exc,RuntimeIntervention):raise
                errors.append(type(exc).__name__+': '+str(exc))
                if self.watchdog:self.watchdog.error(exc,phase,stage)
                if 'server_not_idle' in str(exc) or isinstance(exc,TimeoutError) or 'token_cap' in str(exc):break
                data=dict(observation_type='action_error',phase=phase,stage=stage,error=errors[-1])
                ref=self.store.artifact(canonical(data))
                self.store.append('action_errors',dict(**data,observation_ref=ref))
                messages.append(dict(role='user',content=json.dumps(dict(**data,
                    diagnostic_ref=ref,evidence_eligibility='controller diagnostic only'))))
                messages.append(phase_control(phase,stage,'Correct the action; do not invent evidence.'))
        retired=[m for m in messages[2:] if is_phase_control(m)]
        self.history=[m for m in messages[2:] if not is_phase_control(m)]
        # Bound history promptly as well as by measured tokenization on next call.
        self.store.append('history',dict(phase=phase,stage=stage,messages=len(self.history),
            retired_controls=len(retired),retired_control_sha256=[hashlib.sha256(m['content'].encode()).hexdigest() for m in retired]))
        return dict(phase=phase,done=done,completed=done is not None,errors=errors,calls=len(self.provider.calls)-start)

    @staticmethod
    def _terminal_done(phase,limit,draft_claims):
        """Honest terminal done for a claim-bearing phase that exhausts its
        action budget without the model returning done. Never invents grounded
        claims: it either finalizes the recorded mid-phase draft as unrefined,
        or records a single explicitly unsupported non-termination claim."""
        from aee.model import Claim
        if draft_claims is not None:
            bundle=draft_claims
            summary=('Phase %s ended without an explicit done: the model did not terminate within its %d allocated actions. '
                     'The recorded mid-phase draft claims are reported as the terminal claims; treat them as unrefined.' % (phase,limit))
        else:
            bundle={"schema_version":"1.0","claims":[{
                "id":"DIAG-NONTERMINATION-01",
                "text":("The %s phase exhausted its %d allocated actions without the model returning done. "
                        "No grounded defect claims were established; every defect claim remains unsupported." % (phase,limit)),
                "kind":"hypothesis","status":"unsupported","stage":"created","boundary":[phase],
                "depends_on":[],"conflicts_with":[],
                "falsification_tests":["Re-run the phase and observe whether done is returned within the action budget"],
                "source_ref":"phase transcript","uncertainty":"high","evidence":[]}]}
            summary=('Phase %s exhausted its %d allocated actions without the model returning done. '
                     'No grounded claims were produced; the terminal claim records this non-termination honestly.' % (phase,limit))
        for c in bundle['claims']:Claim.from_dict(c)
        return {"action":"done","summary":summary,"claims":bundle,"terminal_synthesized":True}


def do_assessment(session,row,phase,done):
    claims=grounded_claims(done['claims'],session.store,session.identity)
    started=time.monotonic()
    evaluation=assess(ROOT,claims,phase,session.store,session.identity)
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


def campaign(out,preflight,timeout,*,workflow_preflight=None,latency_preflight=None,
             context_preflight=None,assets=None,extra_sources=(),completion_contract='',freeze_hook=None,block_on_assessment=False,admission=None,contain_model_failures=False,fail_fast=False):
    # Stop before any scored call if later phases/repairs cannot be reserved.
    validate_capacity(CONFIG['stage_seconds'],timeout,
                      ['constitution','specify','plan','tasks','implement','converge','final_implement'],
                      CONFIG['repair_rounds'])
    # No outcome-dependent changes and no rerun/resume of partial trajectories.
    out.mkdir(parents=True,exist_ok=False)
    cal=json.loads((preflight/'calibration.json').read_text());assert cal['passed']
    workflow_preflight=workflow_preflight or ROOT/'artifacts/repeated-workflow-04/result.json'
    latency_preflight=latency_preflight or ROOT/'artifacts/repeated-latency-01/calibration.json'
    context_preflight=context_preflight or ROOT/'artifacts/context-selection-01/result.json'
    assets=assets or ROOT/'artifacts/repeated-assets'
    gate=json.loads(workflow_preflight.read_text())
    if admission is None:assert gate['passed']
    else:
        from model_outcomes import validate_admission
        validate_admission(workflow_preflight.parent,admission,CONFIG)
    latency_result=json.loads(latency_preflight.read_text());assert latency_result['passed'] and timeout==latency_result['timeout']
    context_calibration=json.loads(context_preflight.read_text())
    assert context_calibration['passed'] and context_calibration['selector_sha256']==digest(ROOT/'scripts/context_window.py')
    for project,meta in PROJECTS.items():
        actual=subprocess.check_output(['git','-c','safe.directory='+str((ROOT/meta['upstream']).resolve()).replace('\\','/'),'-C',str(ROOT/meta['upstream']),'rev-parse','HEAD'],text=True).strip()
        assert actual==meta['revision']
    schedule=[(p,s,a) for p in PROJECTS for s in SEEDS for a in ARMS]
    random.Random(SEEDS[0]).shuffle(schedule)
    hashes={str(p.relative_to(ROOT)):digest(p) for folder in (TASK,ROOT/'prompts',ROOT/'src/benchmark_runner',ROOT/'.specify/extensions',ROOT/'.specify/templates',ROOT/'.specify/scripts/python') for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for item in (assets/'installed-aee').rglob('*.py'):
        hashes[str(item.relative_to(ROOT))]=digest(item)
    for name in ('hardware.json','server-launch.json','package-versions.json'):
        item=assets/name;hashes[str(item.relative_to(ROOT))]=digest(item)
    hashes['scripts/calibrate_repeated_workflow.py']=digest(ROOT/'scripts/calibrate_repeated_workflow.py')
    hashes['scripts/context_window.py']=digest(ROOT/'scripts/context_window.py')
    hashes['scripts/runtime_checks.py']=digest(ROOT/'scripts/runtime_checks.py')
    hashes['scripts/action_protocol.py']=digest(ROOT/'scripts/action_protocol.py')
    hashes['scripts/calibrate_context_selection.py']=digest(ROOT/'scripts/calibrate_context_selection.py')
    hashes[str(context_preflight.relative_to(ROOT))]=digest(context_preflight)
    for item in (*extra_sources,workflow_preflight,latency_preflight):
        hashes[str(item.relative_to(ROOT))]=digest(item)
    hashes['scripts/gpu_experiment.py']=digest(ROOT/'scripts/gpu_experiment.py')
    hashes['scripts/report_long_horizon.py']=digest(ROOT/'scripts/report_long_horizon.py')
    hashes['uv.lock']=digest(ROOT/'uv.lock')
    hashes['.specify/memory/constitution.md']=digest(ROOT/'.specify/memory/constitution.md')
    hashes['scripts/repeated_local.py']=digest(__file__);hashes['scripts/long_horizon.py']=digest(ROOT/'scripts/long_horizon.py')
    hashes={name.replace('\\','/'):value for name,value in hashes.items()}
    freeze=dict(created_at=utc(),config={**CONFIG,'timeout':timeout},schedule=schedule,hashes=hashes,projects=PROJECTS,image=IMAGE,server_props=local_json('/props'),calibration=cal,workflow_calibration=gate,latency_calibration=latency_result,context_selection_calibration=context_calibration)
    freeze['intervention_policy']='fail-fast-v1' if fail_fast else ('model-outcomes-v1' if contain_model_failures else 'stop-campaign')
    write_json(out/'freeze.json',freeze,exclusive=True)
    if freeze_hook is not None:
        freeze_hook(out,freeze)
    rows=[]
    for project,seed,arm in schedule:
        identity=f'{project}-{seed}-{arm}';folder=out/identity;folder.mkdir()
        provider=Provider(folder,seed,timeout);store=Store(folder/'evidence')
        with ProjectSandbox(project) as box:
            if arm!='baseline':box.stage_workflow()
            session=Session(box,provider,store,identity)
            session.watchdog=RuntimeWatchdog(folder,capture=lambda:box.snapshot(folder/'runtime-stopped.tar'),fail_fast=fail_fast)
            stopped=None
            for stage in (1,2,3):
                begin=time.monotonic();deadline=begin+CONFIG['stage_seconds'];start=len(provider.calls)
                spec='\n\n'.join((TASK/project/f'stage{i}.md').read_text() for i in range(1,stage+1))
                box.put({'acceptance_public.py':tests_for(project,stage,True),f'TASK_STAGE_{stage}.md':spec.encode()})
                row=dict(project=project,seed=seed,arm=arm,stage=stage,phases=[],assessments=[],repairs=[],started_at=utc(),handoff=stage==3)
                rows.append(row)
                if stopped is not None:
                    from model_outcomes import finish_stopped_stage
                    expected=cal['projects'][project]['reference'][f'{stage}-public']['test_count']
                    finish_stopped_stage(box,row,folder,out,grade,expected,0,begin,stopped,dependent=True)
                    write_json(out/'attempts.json',rows)
                    continue
                try:
                    if stage==3:
                        handoff=box.execute('git status --short; test ! -f HANDOFF.md || cat HANDOFF.md')
                        row['handoff_record']=handoff
                        subprocess.run(['docker','restart',box.name],check=True,capture_output=True,timeout=30)
                        session.history=[]
                    phases=phase_plan(arm,stage)
                    for phase_index,phase in enumerate(phases):
                        # Keep at least one physical-call reservation for every later
                        # phase and each public repair round. These limits are frozen.
                        phase_deadline=deadline-(len(phases)-phase_index-1+CONFIG['repair_rounds'])*timeout
                        session.watchdog.deadline(phase_deadline,timeout,phase,stage)
                        left=CONFIG['primary_calls']-(len(provider.calls)-start)
                        if left<=0:session.watchdog.stop('primary call budget exhausted before phase',phase=phase,stage=stage)
                        instructions=phase_instructions(project,arm,phase,spec,completion_contract)
                        need_claims=arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement')
                        phase_before=folder/f'stage{stage}-{phase}-before.tar';box.snapshot(phase_before)
                        phase_row=session.phase(phase,instructions,spec,stage,min(left,PHASE_LIMITS.get(phase,left)),phase_deadline,need_claims)
                        phase_after=folder/f'stage{stage}-{phase}-after.tar';box.snapshot(phase_after)
                        phase_row.update(source_changed=source_digest(phase_before)!=source_digest(phase_after),source_before=phase_before.relative_to(out).as_posix(),source_after=phase_after.relative_to(out).as_posix())
                        row['phases'].append(phase_row)
                        write_json(out/'attempts.json',rows)
                        session.watchdog.completed(phase_row,stage)
                        if need_claims and phase_row['done']:
                            try:
                                evaluation=do_assessment(session,row,phase,phase_row['done'])
                                if block_on_assessment and evaluation['outcome']=='block':
                                    row['blocked_phase']=phase;row['blocked_reason']='AEE block verdict'
                                elif phase=='implement' and evaluation['outcome'] not in ('pass','warn'):
                                    rework=session.phase('evidence_rework','Address actual evidence gaps with repository inspection/tests and scoped changes. Keep unsupported claims explicit; return revised claims.',spec,stage,min(16,max(0,CONFIG['primary_calls']-(len(provider.calls)-start))),phase_deadline,True)
                                    row['phases'].append(rework)
                                    session.watchdog.completed(rework,stage)
                                    if rework['done']:
                                        checked=do_assessment(session,row,'implement',rework['done'])
                                        if block_on_assessment and checked['outcome']=='block':
                                            row['blocked_phase']=phase;row['blocked_reason']='AEE block after evidence rework'
                            except Exception as exc:
                                if isinstance(exc,RuntimeIntervention):raise
                                row['assessments'].append(dict(phase=phase,error=repr(exc)))
                                if block_on_assessment:
                                    row['blocked_phase']=phase;row['blocked_reason']='AEE execution error'
                        write_json(out/'attempts.json',rows)
                        if row.get('blocked_phase'):
                            if fail_fast:session.watchdog.stop(row['blocked_reason'],phase=phase,stage=stage)
                            break
                    primary=folder/f'stage{stage}-primary.tar';box.snapshot(primary)
                    primary_terminal=(row['phases'][-1].get('done') or {}) if row['phases'] else {}
                    primary_declaration=primary_terminal.get('completion_asserted')
                    row['primary_completion_asserted']=primary_declaration if type(primary_declaration) is bool else None
                    expected=cal['projects'][project]['reference'][f'{stage}-public']['test_count']
                    row['primary_snapshot']=primary.relative_to(out).as_posix();row['public_primary']=grade(project,primary,stage,True,expected)
                    current=row['public_primary']
                    if fail_fast and not current['passed']:
                        write_json(out/'attempts.json',rows)
                        session.watchdog.stop('public verification failed; campaign halted',stage=stage,phase='public-grade')
                    for iteration in (1,2):
                        if current['passed'] or row.get('blocked_phase'):break
                        before=source_digest(primary if iteration==1 else folder/f'stage{stage}-repair1.tar')
                        repair_deadline=deadline-(CONFIG['repair_rounds']-iteration)*timeout
                        session.watchdog.deadline(repair_deadline,timeout,'repair',stage)
                        repair=session.phase('repair','Repair using public test feedback. Preserve active requirements.\n'+current['output'][-12000:]+'\n'+completion_contract,spec,stage,CONFIG['repair_calls'],repair_deadline)
                        session.watchdog.completed(repair,stage)
                        snap=folder/f'stage{stage}-repair{iteration}.tar';box.snapshot(snap)
                        current=grade(project,snap,stage,True,expected)
                        repair.update(round=iteration,grade=current,source_changed=source_digest(snap)!=before,snapshot=snap.relative_to(out).as_posix())
                        row['repairs'].append(repair)
                    final=folder/f'stage{stage}-final.tar';box.snapshot(final)
                    row.update(final_snapshot=final.relative_to(out).as_posix(),public_final=current,seconds=time.monotonic()-begin,calls=len(provider.calls)-start,ended_at=utc())
                    terminal=(row['repairs'] or row['phases'])[-1].get('done') or {}
                    declaration=terminal.get('completion_asserted')
                    row['completion_asserted']=declaration if type(declaration) is bool else None
                    row['completion_declaration_source']='repair' if row['repairs'] else 'primary'
                    if fail_fast:
                        expected_hidden=cal['projects'][project]['reference'][f'{stage}-hidden']['test_count']
                        for kind in ('primary','final'):
                            row['hidden_'+kind]=grade(project,out/row[kind+'_snapshot'],stage,False,expected_hidden)
                            write_json(out/'attempts.json',rows)
                            if not row['hidden_'+kind]['passed']:
                                session.watchdog.stop('independent verification failed; campaign halted',stage=stage,phase='hidden-grade')
                    notes=box.execute('find .specify specs -type f 2>/dev/null; test ! -f HANDOFF.md || cat HANDOFF.md')
                    row['notes_index']=notes
                    if arm!='baseline':
                        (folder/f'stage{stage}-workflow.tar').write_bytes(subprocess.check_output(['docker','exec',box.name,'tar','--exclude=.git','-cf','-','-C','/testbed','.specify','specs'],timeout=30))
                except RuntimeIntervention as intervention:
                    from model_outcomes import model_failure,finish_stopped_stage
                    alert=intervention.alert
                    if alert is None:alert=json.loads((folder/'runtime-alert.json').read_text())
                    if fail_fast or not contain_model_failures or not model_failure(alert):
                        row.update(status='runtime_interrupted',runtime_alert=alert,calls=len(provider.calls)-start,ended_at=utc())
                        write_json(out/'attempts.json',rows)
                        raise
                    expected=cal['projects'][project]['reference'][f'{stage}-public']['test_count']
                    finish_stopped_stage(box,row,folder,out,grade,expected,len(provider.calls)-start,begin,alert)
                    stopped=alert
                write_json(out/'attempts.json',rows)
                print('CHECKPOINT',identity,stage,row['public_final']['passed'],row['calls'],row.get('status','completed'),flush=True)
    for row in rows:
        expected=cal['projects'][row['project']]['reference'][f'{row["stage"]}-hidden']['test_count']
        for kind in ('primary','final'):
            if 'hidden_'+kind not in row:
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
