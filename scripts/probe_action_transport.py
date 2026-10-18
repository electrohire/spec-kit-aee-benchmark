"""Unscored native JSON action checks. All model calls and failures are retained."""
import argparse
import json
import time

import current_local as current
from aee.model import Claim
from benchmark_runner.store import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=current.Path)
    args=parser.parse_args()
    current.setup()
    current.freeze(args.output,'unscored native action transport; at most three local calls; no tool execution')
    result=dict(passed=False,checks=[],paid_calls=False)
    provider=current.Provider(args.output/'calls',current.SEEDS[0],600)
    fixtures=[
        ('shell','Return a shell action whose command prints hello. Do not execute it.'),
        ('done','Return done with completion_asserted null and a complete claim bundle. Use the claim below unchanged; no tests have run.'),
        ('draft','Return draft with a complete claim bundle. Use the claim below unchanged; no tests have run.'),
    ]
    try:
        for action,prompt in fixtures:
            provider.requires_claims=action!='shell'
            if provider.requires_claims:
                prompt+='\n'+json.dumps(dict(schema_version='1.0',claims=[dict(id='R01',text='An unverified bounded requirement',kind='requirement',status='draft',stage='created',boundary=['transport fixture only'],depends_on=[],conflicts_with=[],falsification_tests=['actual implementation violates the requirement'],source_ref='transport fixture R01',uncertainty='insufficient_evidence',evidence=[])]))
            if any(s.get('is_processing') for s in current.http('/slots')):
                raise RuntimeError('shared inference is busy; no overlapping request permitted')
            text=provider.query([dict(role='system',content='Return exactly one action conforming to the native schema, without prose or tool tags.'),dict(role='user',content=prompt)],'transport_probe',0,time.monotonic()+630)
            value=json.loads(text)
            if value['action']!=action:raise ValueError('wrong fixture action')
            if action=='shell' and not isinstance(value.get('command'),str):raise ValueError('missing command')
            if action=='done' and ('completion_asserted' not in value or value['completion_asserted'] is not None):raise ValueError('missing explicit unknown')
            if provider.requires_claims:
                if not value.get('claims',{}).get('claims'):raise ValueError('empty claims')
                for item in value['claims']['claims']:
                    claim=Claim.from_dict(item)
                    if claim.status.value!='draft' or claim.stage.value!='created' or claim.evidence:
                        raise ValueError('transport fixture promoted unverified claims')
            result['checks'].append(dict(action=action,valid_json=True,strict_claims_loaded=provider.requires_claims,native_usage=provider.calls[-1]['usage']))
        result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result['physical_calls']=len(provider.calls)
        write_json(args.output/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
