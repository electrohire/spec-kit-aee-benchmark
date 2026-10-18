"""Unscored native JSON action checks. All model calls and failures are retained."""
import argparse
import json
import time

import current_local as current
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
        ('done','Return done with completion_asserted null and summary containing a newline and literal backslash.'),
        ('draft','Return draft with claims containing schema_version 1.0 and a nonempty claims array with an object having id R01 and text a bounded draft.'),
    ]
    try:
        for action,prompt in fixtures:
            if any(s.get('is_processing') for s in current.http('/slots')):
                raise RuntimeError('shared inference is busy; no overlapping request permitted')
            text=provider.query([dict(role='system',content='Return exactly one action conforming to the native schema, without prose or tool tags.'),dict(role='user',content=prompt)],'transport_probe',0,time.monotonic()+630)
            value=json.loads(text)
            if value['action']!=action:raise ValueError('wrong fixture action')
            if action=='shell' and not isinstance(value.get('command'),str):raise ValueError('missing command')
            if action=='done' and ('completion_asserted' not in value or value['completion_asserted'] is not None):raise ValueError('missing explicit unknown')
            if action=='draft' and not value.get('claims',{}).get('claims'):raise ValueError('empty draft')
            result['checks'].append(dict(action=action,valid_json=True,native_usage=provider.calls[-1]['usage']))
        result['passed']=True
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        result['physical_calls']=len(provider.calls)
        write_json(args.output/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
