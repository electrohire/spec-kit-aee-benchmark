"""Inventory measured local benchmark-model work without pooling success rates."""
import json
from pathlib import Path
base=Path('reports/local'); study=base/'long-horizon-03'; small=base/'gpu-20260917'
read=lambda p:json.loads(p.read_text())
summary=read(study/'summary.json');setup=read(study/'setup-accounting.json')
primary=[c for r in read(small/'coding/results.json') for c in r['calls']]
repairs=read(small/'repair/summary.json');smoke=read(small/'coding/development-smoke/hello-call.json')
rows=[]
def add(scope,calls,tokens,unknown,source):rows.append(dict(scope=scope,calls=calls,known_tokens=tokens,unknown_calls=unknown,source=source))
add('Small-task development smoke',1,smoke['usage']['total_tokens'],0,'gpu-20260917/coding/development-smoke/hello-call.json')
add('Small-task primary comparison',len(primary),sum(c['usage']['total_tokens'] for c in primary),0,'gpu-20260917/coding/results.json')
add('Small-task supplemental repairs',sum(r['repair_calls'] for r in repairs),sum(r['repair_total_tokens'] for r in repairs),sum(r['unknown_usage_calls'] for r in repairs),'gpu-20260917/repair/summary.json')
add('Long-study development smokes',sum(r['calls'] for r in setup['smokes']),sum(r['total_tokens'] for r in setup['smokes']),sum(r['unknown_calls'] for r in setup['smokes']),'long-horizon-03/setup-accounting.json')
for n in (1,2):
 source=f'long-horizon-{n:02}-interrupted/summary.json';u=read(base/source)['usage'];add(f'Interrupted long pilot {n}',u['calls'],u['total_tokens'],u['unknown_calls'],source)
u=summary['total'];add('Frozen long comparison including failures',u['calls'],u['known_total_tokens'],u['unknown_calls'],'long-horizon-03/summary.json')
known=sum(r['known_tokens'] for r in rows);extra=sum(a['total_token_reservation_upper_bound']-a['known_total_tokens'] for a in summary['arms'].values())
ledger=dict(rows=rows,calls=sum(r['calls'] for r in rows),known_tokens=known,unknown_calls=sum(r['unknown_calls'] for r in rows),complete_native_token_total=None,configured_reservation_upper_bound=known+extra,api_expenditure_usd=0,note='Development and scored benchmark-model work across different models and task scopes. This inventory is not a pooled treatment-efficiency estimate. Hardware, energy and controller work are unpriced; reasoning and cached input are not counted twice.')
(base/'token-ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
text='# Local measurement index\n\nBoth GPUs were verified: RTX 4070 SUPER 12282 MiB and RTX 5060 Ti 16311 MiB.\nAll benchmark inference used localhost, with $0 API expenditure. Hardware, energy\nand controller work are unpriced. The original SWE-bench pilot remains unrun.\n\n- [CPU application/AEE runtime and six-task study](gpu-20260917/README.md), including actual supplemental repairs.\n- [Staged TinyDB study](long-horizon-03/README.md): nine dependent checkpoints, no complete hidden milestone passes, all three arms timed out.\n- [Interrupted pilot 1](long-horizon-01-interrupted/README.md) and [pilot 2](long-horizon-02-interrupted/README.md), retained as development overhead.\n\n## Complete benchmark-model work inventory\n\nThis combines work counts, not success rates or treatment estimates across models.\n\n| Scope | Calls | Known tokens | Calls with unknown usage |\n|---|---:|---:|---:|\n'
for r in rows:text+=f"| [{r['scope']}]({r['source']}) | {r['calls']:,} | {r['known_tokens']:,} | {r['unknown_calls']} |\n"
text+=f"\nTotal: **{ledger['calls']:,} calls; at least {known:,} tokens; {ledger['unknown_calls']} unknown usages**.\nThe configured reservation bound is {known+extra:,} tokens; this is not an imputed\nmeasured total. See [the ledger](token-ledger.json). Failed work and development\nsmokes are retained separately from the scored arm denominators.\n"
(base/'README.md').write_text(text)
print(json.dumps({k:v for k,v in ledger.items() if k!='rows'},indent=2))
