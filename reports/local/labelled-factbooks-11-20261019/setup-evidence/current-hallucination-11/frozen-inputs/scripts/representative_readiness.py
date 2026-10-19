"""Unscored project-sized execution/repair readiness, isolated from scored solvers."""
import argparse
import json
import time

import current_local as current
import repeated_local as runner
from benchmark_runner.project_assessment import assess_project
from benchmark_runner.store import Store,write_json,utc
from runtime_checks import RuntimeWatchdog,validate_capacity


def one_case(folder,project,arm,timeout):
    phases=runner.phase_plan(arm,1)
    validate_capacity(current.CONFIG['stage_seconds'],timeout,phases,2)
    current.freeze(folder,'unscored representative stage1 plus independently checked injected repair: '+project+'/'+arm)
    identity='current-calibration' if (project,arm)==('tinydb','spec_kit_aee') else 'readiness-'+project+'-'+arm
    provider=current.Provider(folder/'calls',current.SEEDS[0],timeout)
    result=dict(passed=False,calibration_only=True,project=project,arm=arm,identity=identity,
                phases=[],assessments=[],additional_assessments=[],allowed_seconds=current.CONFIG['stage_seconds'],
                workload='representative_project_stage1',started_at=utc())
    try:
        with runner.ProjectSandbox(project) as box:
            if arm!='baseline':box.stage_workflow()
            store=Store(folder/'evidence')
            session=runner.Session(box,provider,store,identity)
            session.watchdog=RuntimeWatchdog(folder,capture=lambda:box.snapshot(folder/'runtime-stopped.tar'))
            spec=(runner.TASK/project/'stage1.md').read_text()
            box.put({'acceptance_public.py':runner.tests_for(project,1,True),'TASK_STAGE_1.md':spec.encode()})
            start=time.monotonic();deadline=start+current.CONFIG['stage_seconds']
            for index,phase in enumerate(phases):
                end=deadline-(len(phases)-index-1+2)*timeout
                session.watchdog.deadline(end,timeout,phase,1)
                left=current.CONFIG['primary_calls']-len(provider.calls)
                row=session.phase(phase,runner.phase_instructions(project,arm,phase,spec,current.COMPLETION),spec,1,
                                  min(left,runner.PHASE_LIMITS.get(phase,left)),end,
                                  arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement'))
                result['phases'].append(row);write_json(folder/'result.json',result)
                session.watchdog.completed(row,1)
                if arm=='spec_kit_aee' and phase in ('specify','plan','tasks','implement'):
                    verdict=runner.do_assessment(session,result,phase,row['done'])
                    if verdict['outcome']=='block':session.watchdog.stop('AEE blocked readiness',phase=phase,stage=1)
                    if phase=='implement' and verdict['outcome'] not in ('pass','warn'):
                        rework=session.phase('evidence_rework','Address actual evidence gaps with repository inspection/tests and scoped changes. Keep unsupported claims explicit; return revised claims.',
                                             spec,1,min(16,max(0,current.CONFIG['primary_calls']-len(provider.calls))),end,True)
                        result['phases'].append(rework);session.watchdog.completed(rework,1)
                        again=runner.do_assessment(session,result,'implement',rework['done'])
                        result['additional_assessments'].append(result['assessments'].pop())
                        if again['outcome']=='block':session.watchdog.stop('AEE blocked readiness rework',phase=phase,stage=1)
            before=folder/'before-repair.tar';box.snapshot(before)
            result['before_repair']=runner.grade(project,before,1,True)
            if not result['before_repair']['passed']:
                raise RuntimeError('representative workflow did not pass public verification; no scored generation')
            module=runner.PROJECTS[project]['module']
            # Controller injection is clearly unscored and the original source is
            # retained. The agent receives ordinary actual public-test feedback.
            injected=box.execute("printf '\\nraise RuntimeError(\"calibration injected regression\")\\n' >> "+module)
            if injected['exit_code']:raise RuntimeError('injection command failed')
            broken=folder/'injected.tar';box.snapshot(broken)
            result['injected_failure']=runner.grade(project,broken,1,True)
            if result['injected_failure']['passed']:raise RuntimeError('injected regression was not detected')
            session.watchdog.deadline(deadline,timeout,'repair',1)
            result['repair']=session.phase('repair','Repair using public test feedback. Preserve active requirements.\n'+
                result['injected_failure']['output'][-12000:]+'\n'+current.COMPLETION,spec,1,current.CONFIG['repair_calls'],deadline)
            session.watchdog.completed(result['repair'],1)
            final=folder/'after-repair.tar';box.snapshot(final)
            result['after_repair']=runner.grade(project,final,1,True)
            result['elapsed_seconds']=time.monotonic()-start
            if not result['after_repair']['passed'] or result['repair']['calls']<1:
                raise RuntimeError('representative injected repair did not pass')
            if result['elapsed_seconds']>result['allowed_seconds']:raise RuntimeError('representative full execution exceeded budget')
            if arm=='spec_kit_aee' and len(result['assessments'])!=4:raise RuntimeError('four actual AEE checkpoints required')
            result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result.update(ended_at=utc(),physical_calls=len(provider.calls))
        write_json(folder/'result.json',result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=current.Path);parser.add_argument('--latency',type=current.Path,required=True)
    args=parser.parse_args();current.setup();runner.assess=assess_project
    latency=json.loads(args.latency.read_text())
    if not latency.get('passed') or any(latency.get(k)!=current.CONFIG[k] for k in ('model','context','max_output')):
        raise ValueError('matching successful latency required')
    current.CONFIG['physical_call_timeout']=latency['timeout']
    args.output.mkdir(parents=True,exist_ok=False)
    result=dict(passed=False,cases=[],unscored=True,started_at=utc())
    try:
        for arm in ('spec_kit_aee','spec_kit','baseline'):
            for project in runner.PROJECTS:
                name=project+'-'+arm
                write_json(args.output/'progress.json',dict(project=project,arm=arm,stage='representative_readiness',at=utc()))
                value=one_case(args.output/name,project,arm,latency['timeout'])
                import hashlib
                result['cases'].append(dict(project=project,arm=arm,folder=name,passed=value['passed'],
                    result_sha256=hashlib.sha256((args.output/name/'result.json').read_bytes()).hexdigest()))
                write_json(args.output/'result.json',result)
        result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result['ended_at']=utc();write_json(args.output/'result.json',result)


if __name__=='__main__':main()
