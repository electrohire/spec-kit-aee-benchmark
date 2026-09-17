"""Describe observed workflow artifacts and tool activity without inferring fixes."""
import argparse
import collections
import json
import tarfile
from pathlib import Path

from benchmark_runner.store import write_json

parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path)
args=parser.parse_args();root=args.campaign
rows=json.loads((root/'results.json').read_text());audit=[]
for arm in ('baseline','spec_kit','spec_kit_aee'):
    events=[json.loads(line) for line in (root/arm/'evidence/tools.jsonl').read_text().splitlines()]
    tools=[json.loads((root/arm/'evidence'/e['artifact']['path']).read_text()) for e in events]
    counts=collections.Counter(t['command'] for t in tools)
    stages=[]
    for row in [r for r in rows if r['arm']==arm]:
        stage=row['stage'];path=root/arm/f'stage{stage}-workflow.tar'
        documents=[]
        if path.exists():
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if member.isfile() and member.name.endswith('.md') and '/templates/' not in member.name:
                        data=archive.extractfile(member).read()
                        documents.append(dict(path=member.name,bytes=len(data),unchanged_project_placeholder=b'[PROJECT_NAME]' in data))
        stages.append(dict(stage=stage,completed_phases=[p['phase'] for p in row['phases']],
            workflow_error=row['error'],documents=documents,
            assessments=[dict(phase=a['phase'],outcome=a.get('outcome'),error=a.get('error')) for a in row['assessments']]))
    audit.append(dict(arm=arm,stages=stages,total_shell_calls=len(tools),nonzero_shell_exits=sum(t['exit_code']!=0 for t in tools),
        repeated_commands=[dict(command=c,count=n) for c,n in counts.most_common() if n>1],
        script_commands=[dict(command=t['command'],exit_code=t['exit_code']) for t in tools if '.specify/scripts/' in t['command']],
        note='Repeated commands may be legitimate retests. Script mentions require manual execution review. Document presence does not certify content. Nonzero exits include negative tests and environment errors.'))
write_json(root/'workflow-audit.json',audit)
print(json.dumps([dict(arm=a['arm'],shell_calls=a['total_shell_calls'],nonzero_exits=a['nonzero_shell_exits'],stages=[dict(stage=s['stage'],phases=s['completed_phases'],documents=len(s['documents']),error=s['workflow_error']) for s in a['stages']]) for a in audit],indent=2))
