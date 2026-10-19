"""Independent read-only receipt/label audit and public export of corrected diagnostic11."""
from pathlib import Path
import json,hashlib,sys,datetime,copy
BASE=Path(__file__).resolve().parent
ROOT=BASE/'work/spec-kit-aee-benchmark'
DEST=BASE/'work/benchmark-results-publication/reports/local/labelled-factbooks-11-20261019'
sys.path.insert(0,str(ROOT/'scripts'))
from report_current import setup_inventory
from report_repeated import manifest
from labelled_hallucinations import metrics

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
raw=ROOT/'artifacts/current-hallucination-11'
state=load(raw/'result.json');assert state['complete'] is True and state['passed'] is True and state['physical_calls']==12
before={p.relative_to(raw).as_posix():sha(p) for p in raw.rglob('*') if p.is_file()}
freeze=load(raw/'freeze.json');plan=load(raw/'diagnostic-plan.json')
assert plan['corpus_version']==2 and plan['max_output']==256 and plan['max_calls']==12 and plan['context']==32768 and plan['timeout']==600 and plan['seed']==20261018
for name,digest in freeze['hashes'].items():assert sha(raw/'frozen-inputs'/name)==digest,name
corpus=raw/'frozen-inputs/benchmarks/current_local/hallucination-cases-v2.json'
assert sha(corpus)==plan['corpus_sha256'] and load(corpus)['cases']==plan['cases']
rows=[];known=0;cache=0;ids=set();mapping=[]
for i,case in enumerate(plan['cases']):
 p=raw/'calls'/f'call-{i:04}.json';native=load(p);req=native['request'];response=native['response'];usage=native['usage']
 assert not native.get('error') and native.get('ended_at') and usage
 assert req['model']==response['model']=='qwen3.8-27b' and req['max_tokens']==256 and req['seed']==20261018
 assert req['chat_template_kwargs']=={'enable_thinking':False} and req['cache_prompt'] is False
 assert req['temperature']==.6 and req['top_p']==.95 and req['top_k']==20
 assert len(req['messages'])==2 and json.loads(req['messages'][1]['content'])==case and 'gold' not in case
 assert response['id'] not in ids;ids.add(response['id'])
 assert usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens']
 known+=usage['total_tokens'];cache+=(usage.get('prompt_tokens_details') or {}).get('cached_tokens',0)
 choice=response['choices'][0];parsed=json.loads(choice['message']['content'])
 prediction=parsed.get('verdict') if choice['finish_reason']=='stop' and isinstance(parsed.get('reason'),str) else None
 row=state['rows'][i]
 assert row['id']==case['id'] and row['gold']==plan['gold'][case['id']] and row['prediction']==prediction and row['call_sha256']==sha(p)
 rows.append(copy.deepcopy(row))
assert metrics(rows)==state['metrics']
assert len(list((raw/'calls').glob('call-*.json')))==12
assert freeze['config']['url']=='http://127.0.0.1:50467' and freeze['worker_binding']['pid']==50912
DEST.mkdir(parents=True,exist_ok=False)
inv=setup_inventory([raw],DEST)
assert inv['physical_calls']==12 and inv['by_model']['qwen3.8-27b']['known_tokens_lower_bound']==known and not inv['by_model']['qwen3.8-27b']['unknown_token_calls']
for i in range(12):
 source=raw/'calls'/f'call-{i:04}.json';target=DEST/'setup-evidence/current-hallucination-11/calls'/source.name
 exported=load(target);assert 'request' not in exported
 for choice in exported['response']['choices']:
  assert not {'reasoning','reasoning_content'}.intersection(choice.get('message',{}))
 mapping.append(dict(source=source.relative_to(raw).as_posix(),original_sha256=sha(source),published=target.relative_to(DEST).as_posix(),published_sha256=sha(target)))
(DEST/'call-export-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
limits=['Twelve synthetic closed-world factbooks, four cases per truth category; a convenience diagnostic, not spontaneous workflow hallucination prevalence.', 'Two factbooks were corrected after observing original v1 responses: case09 removed the finished=false presupposition conflict; case11 removed an explicitly wrong known reference from an incomplete inventory. Original labels, claims, other10 cases and oracle remain unchanged; original v1 results stay published.', 'This corrective rerun is not an independent replication or a causal AEE benefit estimate. AEE was not the factbook verdict detector. No AEE precision/recall, whole-workflow hallucination rate or universal zero-hallucination claim follows.', 'Only the benchmark client route changed to the same existing worker with process/port/model/path guards. Historical underlying router socket failure remains unresolved.', 'API spend0 excludes hardware, energy and labor; tokens are not bills. Diagnostic output256 differs from main study output8192 and is reported separately.']
audit=dict(complete=True,audited_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Independent read-only input/call/response/label/accounting/export audit; zero generation',freeze_sha256=sha(raw/'freeze.json'),result_sha256=sha(raw/'result.json'),frozen_input_files=len(freeze['hashes']),physical_calls=12,known_native_tokens=known,usage_unknown=0,cached_tokens_reported=cache,metrics=state['metrics'],limits=limits,source_unchanged=before=={p.relative_to(raw).as_posix():sha(p) for p in raw.rglob('*') if p.is_file()},controller_sha256=sha(Path(__file__)))
assert audit['source_unchanged']
(DEST/'integrity-and-label-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
(DEST/'diagnostic-plan.json').write_bytes((raw/'diagnostic-plan.json').read_bytes())
(DEST/'result.json').write_bytes((raw/'result.json').read_bytes())
text=f'''# Corrected labelled factbooks: twelve real local-model judgments\n\nThe corrective corpus2 diagnostic completed12/12 calls. **{state['metrics']['correct']}/12 judgments match the frozen labels; {state['metrics']['invalid_decisions']} invalid responses.** Supported4/4, contradicted4/4, unknown4/4. The four known-false controls were flagged and all four incomplete-evidence controls abstained. No contradicted or unknown control was accepted.\n\n| Denominator / result | Count |\n|---|---:|\n| Supported gold / predicted supported |4 /4|\n| Contradicted gold / predicted contradicted |4 /4|\n| Unknown gold / predicted unknown |4 /4|\n| Known-truth TP / FP / FN / TN |4 /0 /0 /4|\n| Invalid decisions |0|\n| Physical generation calls |12|\n| Known native input+output tokens |{known:,}|\n| Generation usage unknowns |0|\n\nThe known-truth judgment confusion matrix has eight eligible controls; unknown gold is excluded from that binary denominator and separately reported. Its point precision and recall are1.0 in this tiny constructed set. They are **not AEE detector performance estimates**.\n\n## Correction history and limits\n\n'''
text+='\n\n'.join(limits)+'\n\n[Original corpus1:10/12 original-label agreement with two challenged fixtures](../labelled-factbooks-10-20261019/README.md). Both original disagreements were defensible given explicit counterevidence/presuppositions; they were not established model hallucinations. Corrected controls were prospectively frozen before these new real model calls. Do not pool the two versions as independent samples or call the change an efficacy gain.\n\nThe separately frozen study04/pipeline11 continues through the full12 trajectories /36 dependent checkpoints, independent grading, accounting/integrity audit and publication. This diagnostic alone does not complete that mission.\n\nSee diagnostic-plan.json, result.json, integrity-and-label-audit.json, call-export-map.json, setup-inventory.json, byte-exact frozen inputs and sanitized native receipts. Raw prompts/private reasoning remain local with hashes. All evidence file hashes are in files-sha256.json.\n'
(DEST/'README.md').write_text(text,encoding='utf-8')
manifest(DEST)
(BASE/'work/spec-kit-aee-benchmark/artifacts/current-hallucination-audit-11.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps({k:audit[k] for k in ('complete','frozen_input_files','physical_calls','known_native_tokens','usage_unknown','source_unchanged')}))
