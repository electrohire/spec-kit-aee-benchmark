"""Export repair evidence, retaining failures and omitting raw exercise prompts."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from benchmark_runner.store import canonical, write_json
from export_gpu_results import digest, read


def export(source, target, primary):
    frozen, rows, summary = (read(source/name) for name in ('freeze.json','results.json','summary.json'))
    assert len(rows)==18
    assert frozen['primary_results_sha256']==digest(primary/'results.json')
    for path, expected in frozen['hashes'].items():
        assert digest(path)==expected
    for row in rows:
        assert len(row['rounds'])<=2
        assert not row['original_passed'] or len(row['rounds'])==0
        for event in row['rounds']:
            raw=read(source/row['path']/f'repair-{event["round"]}.json')
            assert raw['usage']==event['usage']
        if row['final_passed'] and not row['original_passed']:
            assert row['rounds'][-1]['grade']['passed']
    primary_summary=read(primary/'coding-summary.json')
    for item in summary:
        selected=[r for r in rows if r['arm']==item['arm']]
        events=[e for r in selected for e in r['rounds']]
        assert len(selected)==item['attempts']==6
        assert len(events)==item['repair_calls']
        assert item['final_passed']==sum(r['final_passed'] for r in selected)
        assert item['cases_repaired']==sum(r['final_passed'] and not r['original_passed'] for r in selected)
        assert all(e['usage'] for e in events), 'Unknown usage requires an explicitly nullable audit'
        inp=sum(e['usage']['prompt_tokens'] for e in events)
        out=sum(e['usage']['completion_tokens'] for e in events)
        assert inp==item['repair_input_tokens'] and out==item['repair_output_tokens']
        before=next(x for x in primary_summary if x['arm']==item['arm'])
        cumulative=before['input_tokens']+before['output_tokens']+inp+out
        assert cumulative==item['cumulative_total_tokens']
        assert item['cumulative_tokens_per_correct_answer']==cumulative/item['final_passed']
    target.mkdir(parents=True,exist_ok=False)
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        dest=target/path.relative_to(source)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if path.suffix=='.json':
            data=read(path)
            if isinstance(data,dict) and 'request' in data:
                request=data.pop('request')
                data['request_sha256']=hashlib.sha256(canonical(request)).hexdigest()
                data['original_record_sha256']=digest(path)
                data['request_omission']='Exercise facts omitted; repair instruction and prior feedback are reproducible from frozen sources.'
            write_json(dest,data)
        else:
            shutil.copy2(path,dest)
    write_json(target/'audit.json',dict(primary_results_unchanged=True,attempts=18,
        repair_calls=sum(x['repair_calls'] for x in summary),usage_recomputed=True,
        cumulative_ratios_verified=True,grading_feedback_exposed=True,
        independent_held_out_evaluation=False,original_freeze_sha256=digest(source/'freeze.json')))
    write_json(target/'files-sha256.json',{p.relative_to(target).as_posix():digest(p) for p in sorted(target.rglob('*')) if p.is_file()})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('--primary',type=Path,required=True)
    args=parser.parse_args()
    export(args.source,args.target,args.primary)
