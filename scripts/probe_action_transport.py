"""Unscored native JSON action checks. All model calls and failures are retained."""
import argparse
import json
import time
import hashlib

import current_local as current
from aee.model import Claim
from benchmark_runner.store import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=current.Path)
    parser.add_argument('--worker-binding',type=current.Path)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():raise FileExistsError('fresh native probe path required')
    try:
        current.configure_worker_binding(args.worker_binding)
        current.setup()
        current.freeze(args.output,'unscored native action transport; at most five local calls; literal argv and write checked in isolated sandbox')
    except Exception as exc:
        try:
            args.output.mkdir(parents=True,exist_ok=True)
            write_json(args.output/'bootstrap-failure.json',dict(error=repr(exc),infrastructure_evidence=getattr(exc,'evidence',None),generation_requests=0),exclusive=True)
        except OSError:
            pass
        raise
    result=dict(passed=False,checks=[],paid_calls=False)
    provider=current.Provider(args.output/'calls',current.SEEDS[0],600)
    fixtures=[
        ('shell','Return a shell action whose command prints hello. Do not execute it.'),
        ('exec','Return exec with argv exactly ["python","-c","import json,sys;print(json.dumps(sys.argv[1:]))","quoted phrase","$(touch NEVER)","\\\"literal\\\""] . Do not run a shell.'),
        ('write_file','Return write_file with path transport-literal.txt and content exactly equal to this JSON string: '+json.dumps('**Input**: User description: "quoted"\nit\'s literal; $(touch NEVER) `no`\nUnicode: λ\n')),
        ('done','Return done with completion_asserted null and a complete claim bundle. Use the claim below unchanged; no tests have run.'),
        ('draft','Return draft with a complete claim bundle. Use the claim below unchanged; no tests have run.'),
    ]
    try:
        for action,prompt in fixtures:
            provider.requires_claims=action in ('done','draft')
            if provider.requires_claims:
                prompt+='\n'+json.dumps(dict(schema_version='1.0',claims=[dict(id='R01',text='An unverified bounded requirement',kind='requirement',status='draft',stage='created',boundary=['transport fixture only'],depends_on=[],conflicts_with=[],falsification_tests=['actual implementation violates the requirement'],source_ref='transport fixture R01',uncertainty='insufficient_evidence',evidence=[])]))
            if any(s.get('is_processing') for s in current.http('/slots')):
                raise RuntimeError('shared inference is busy; no overlapping request permitted')
            text=provider.query([dict(role='system',content='Return exactly one action conforming to the native schema, without prose or tool tags.'),dict(role='user',content=prompt)],'transport_probe',0,time.monotonic()+630)
            value=json.loads(text)
            if value['action']!=action:raise ValueError('wrong fixture action')
            if action=='shell' and not isinstance(value.get('command'),str):raise ValueError('missing command')
            if action=='exec':
                from action_protocol import action_command
                expected=['python','-c','import json,sys;print(json.dumps(sys.argv[1:]))','quoted phrase','$(touch NEVER)','"literal"']
                if value.get('argv')!=expected:raise ValueError('literal argv fixture differs')
                with current.runner.ProjectSandbox('tinydb') as box:
                    observed=box.execute(action_command(value))
                    if observed['exit_code'] or json.loads(observed['stdout'])!=expected[3:]:
                        raise ValueError('literal sandbox argv did not roundtrip')
                    write_json(args.output/'literal-argv.json',dict(execution=observed,expected_argv=expected))
            if action=='write_file':
                from action_protocol import action_command
                expected='**Input**: User description: "quoted"\nit\'s literal; $(touch NEVER) `no`\nUnicode: λ\n'
                if value.get('path')!='transport-literal.txt' or value.get('content')!=expected:
                    raise ValueError('literal file fixture differs')
                with current.runner.ProjectSandbox('tinydb') as box:
                    result_write=box.execute(action_command(value))
                    observed=box.execute('cat transport-literal.txt')
                    if result_write['exit_code'] or observed['exit_code'] or observed['stdout']!=expected:
                        raise ValueError('literal sandbox write did not roundtrip')
                    write_json(args.output/'literal-write.json',dict(write=result_write,readback=observed,
                        expected_sha256=hashlib.sha256(expected.encode()).hexdigest()))
            if action=='done' and ('completion_asserted' not in value or value['completion_asserted'] is not None):raise ValueError('missing explicit unknown')
            if provider.requires_claims:
                if not value.get('claims',{}).get('claims'):raise ValueError('empty claims')
                for item in value['claims']['claims']:
                    claim=Claim.from_dict(item)
                    if claim.status.value!='draft' or claim.stage.value!='created' or claim.evidence:
                        raise ValueError('transport fixture promoted unverified claims')
            check=dict(action=action,valid_json=True,strict_claims_loaded=provider.requires_claims,native_usage=provider.calls[-1]['usage'])
            if action=='write_file':
                check.update(literal_write_verified=True,literal_write_sha256=hashlib.sha256((args.output/'literal-write.json').read_bytes()).hexdigest())
            if action=='exec':
                check.update(literal_argv_verified=True,literal_argv_sha256=hashlib.sha256((args.output/'literal-argv.json').read_bytes()).hexdigest())
            result['checks'].append(check)
        result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result['physical_calls']=len(provider.calls)
        write_json(args.output/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
