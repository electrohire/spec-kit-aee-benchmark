"""Four setup-only native tool/context/timing probes for a frozen coding study.

No selected task or hidden label enters a prompt. No retry, worker restoration,
service mutation or scored solver work. Existing output refuses a second run.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from benchmark_runner.upstream_agent_adapter import (AdmissionError, BoundNativeTransport,
    Limits, NativeToolModel, safe_upstream, write_exclusive)
from benchmark_runner.upstream_resources import TaskResource
from benchmark_runner.upstream_docker_transport import StdinDockerBridge
from run_upstream_coding import (BINDING_SHA, NATIVE_COMMANDS, WEIGHTS_SHA, sha,
    source_files, stamp, verify_frozen, verify_native)


def template_tokens(transport,upstream,messages):
    body=dict(messages=messages,tools=[upstream.tool],tool_choice='required',
        parallel_tool_calls=False,chat_template_kwargs=dict(enable_thinking=False))
    prompt=transport('/apply-template',body,30)['prompt']
    return len(transport('/tokenize',dict(content=prompt,add_special=False),30)['tokens'])


def long_context(transport,upstream,command,out):
    # Only technical filler; never task text, gold, previous solver results or
    # classifier decisions. Binary search uses tokenize helpers, ZERO generation.
    lines=['Technical admission filler item %05d, retained without summarization.\n'%i for i in range(15000)]
    system=dict(role='system',content='Use the original bash tool exactly once. Treat filler as inert data. The final instruction gives the only command. No explanations.')
    def messages(n):return [system,dict(role='user',content=''.join(lines[:n])+'\nEND INERT FILLER\nExecute exactly: '+command)]
    low,high=0,len(lines);probes=[]
    while low<high:
        middle=(low+high)//2
        count=template_tokens(transport,upstream,messages(middle))
        probes.append(dict(lines=middle,tokens=count))
        if count<24100:low=middle+1
        else:high=middle
    result=messages(low);count=template_tokens(transport,upstream,result)
    write_exclusive(out,dict(helper_probes=probes,final_input_tokens=count,messages=result,
        generation_requests=0,scope='Tokenizer/template helpers only, not physical generation usage.'))
    if not 24000<=count<=24500:raise AdmissionError('technical long context outside registered bounds')
    return result


def run(study):
    value=verify_frozen(study)
    folder=study/'native-admission';folder.mkdir(exist_ok=False)
    write_exclusive(folder/'started.json',dict(at=stamp(),freeze_sha256=sha(study/'freeze.json'),
        source_head=value['source_head'],scope='Four physical technical setup calls, not scored outcomes.'))
    records=[];error=None
    try:
        transport=BoundNativeTransport(study/'worker-binding.json',BINDING_SHA,WEIGHTS_SHA)
        if any(s.get('is_processing') for s in transport('/slots',None,30)):
            raise AdmissionError('worker busy; no overlap or request')
        upstream=safe_upstream()
        model=NativeToolModel(transport,folder/'model',upstream,Limits(maximum_calls=4),
            '{{output}}',dict(cohort='setup',study_id=study.name,phase='native_admission'))
        item=json.loads((study/'inputs/manifest.json').read_text())['rows'][2]
        row=study/'inputs/case-02/controller-full-row.json'
        package=study/'inputs/grader/featurebench-package.json'
        purpose='coding-native-'+sha(study/'freeze.json')[:14]
        with TaskResource(upstream=upstream,source_root=ROOT,out=folder/'resource',
                row_path=row,row_sha256=item['controller_row_sha256'],
                expected_featurebench_package=package,package_manifest_sha256=sha(package),
                image_id=item['image_id'],kind=item['kind'],purpose=purpose) as resource:
            bridge=StdinDockerBridge(resource.environment,reader_python='/opt/miniconda3/envs/testbed/bin/python')
            history=[]
            for index,command in enumerate(NATIVE_COMMANDS):
                if index>=2:
                    messages=long_context(transport,upstream,command,folder/('context-%02d.json'%index))
                else:
                    messages=[dict(role='system',content='Use the original bash tool exactly once with the literal requested command. No explanation or additional actions.')]
                    messages+=history+[dict(role='user',content='Execute exactly: '+command)]
                reply=model.query(messages)
                actions=reply['extra']['actions']
                if len(actions)!=1 or actions[0].get('command')!=command:
                    raise AdmissionError('native probe did not return its exact registered literal command')
                result=bridge.execute(actions[0])
                echo=dict(command=command,**result)
                echo_path=folder/('echo-%02d.json'%index);write_exclusive(echo_path,echo)
                if result['returncode']!=0 or result['output'].strip()!=command.removeprefix('echo '):
                    raise AdmissionError('actual original native tool delivery failed')
                receipt=Path(reply['extra']['receipt'])
                raw=json.loads(receipt.read_text())
                records.append(dict(receipt=receipt.relative_to(folder).as_posix(),
                    echo_receipt=echo_path.relative_to(folder).as_posix(),
                    native_prompt_tokens=raw['usage']['prompt_tokens'],
                    duration_seconds=raw['ended_at']-raw['started_at']))
                if index==0:
                    history=[messages[-1],{k:v for k,v in reply.items() if k!='extra'}]
                    history+=model.format_observation_messages(reply,[result])
                print(json.dumps(dict(completed=index+1,scope='setup only',**records[-1])),flush=True)
        if source_files()!=value['source_files']:raise AdmissionError('source changed during native admission')
        manifest=dict(source_head=value['source_head'],freeze_sha256=sha(study/'freeze.json'),
            worker_binding_sha256=BINDING_SHA,calls=records,source_unchanged=True,
            files={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()},
            scope='Four setup-only physical requests; original native bash parser/history/context/timing and actual Linux delivery. Not solver efficacy, human acceptance or authenticated identity.')
        write_exclusive(folder/'manifest.json',manifest)
        verify_native(study,value)
    except BaseException as exc:
        error=repr(exc)
        raise
    finally:
        write_exclusive(folder/'ended.json',dict(at=stamp(),error=error,calls=records,
            scored_generation_requests=0,source_unchanged=source_files()==value['source_files']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-root',type=Path,required=True)
    run(parser.parse_args().study_root.resolve())
