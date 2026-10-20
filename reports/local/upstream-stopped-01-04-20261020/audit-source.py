"""Independent offline audit of stopped upstream episodes01..04; zero inference."""
from pathlib import Path
import json,hashlib,datetime,collections,re,subprocess
R=Path(__file__).resolve().parent.parent;OUT=R/'validation/upstream-stopped-01-04-audit-01';OUT.mkdir(exist_ok=False)
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();records=[]
for episode in range(1,5):
 study=R/'work/spec-kit-aee-benchmark/artifacts'/('upstream-coding-%02d'%episode)
 freeze=json.loads((study/'freeze.json').read_text());ended=json.loads((study/'generation-ended.json').read_text())
 assert len(freeze['rows'])==12 and ended['failure'] and ended['source_still_matches']
 for name,digest in freeze['input_files'].items():assert H(study/'inputs'/name)==digest
 assert H(study/'source.tar')==freeze['source_archive_sha256'] and H(study/'declared-source.tar')==freeze['declared_source_archive_sha256']
 source=Path(freeze['source_root']);assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==freeze['source_head']
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=source,text=True).strip()
 for name,digest in freeze['source_files'].items():assert H(source/name)==digest
 for name,digest in freeze['runtime_files'].items():assert H(Path(name))==digest
 native=study/'native-admission';manifest=json.loads((native/'manifest.json').read_text());assert len(manifest['calls'])==4
 for name,digest in manifest['files'].items():assert H(native/name)==digest
 grouped={};all_paths=[('setup',p) for p in sorted((native/'model').glob('call-*.json'))]+[('scored',p) for p in sorted((study/'trajectories').glob('*/execution/calls/call-*.json'))]
 for cohort,p in all_paths:
  d=json.loads(p.read_text());u=d['response']['usage'];assert d['usage_validated'] and not d.get('error') and d['usage']==u
  assert u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and d['ended_at']>=d['started_at']
  assert d['request']['seed']==20261019 and d['request']['chat_template_kwargs']==dict(enable_thinking=False)
  assert d['response']['model']=='qwen3.8-27b' and d['response']['choices'][0]['finish_reason']=='tool_calls'
  assert d['preflight_input_tokens']+d['request']['max_tokens']<=32768
  v=grouped.setdefault(cohort,dict(calls=0,prompt_tokens=0,completion_tokens=0,known_native_tokens=0,usage_unknown=0,cache_tokens=0))
  v['calls']+=1;v['prompt_tokens']+=u['prompt_tokens'];v['completion_tokens']+=u['completion_tokens'];v['known_native_tokens']+=u['total_tokens'];v['cache_tokens']+=u.get('prompt_tokens_details',{}).get('cached_tokens',0)
 task=json.loads((study/'trajectories/00/execution/task-result.json').read_text());assert task['status']=='stopped_first_failure' and task['actual_AEE_feedback'] is None
 assert task['native_request_attempts']==grouped['scored']['calls'] and task['known_native_tokens_lower_bound']==grouped['scored']['known_native_tokens'] and task['usage_unknown']==0
 assert ended['rows'][0]['status']=='stopped_first_failure' and all(row['status']=='unattempted' and row['native_request_attempts']==0 for row in ended['rows'][1:])
 assert json.loads((study/'trajectories/00/resource/owned-cleanup.json').read_text())['observed_absent']
 grades=R/'validation'/('upstream-coding-independent-grades-%02d'%episode)
 assert json.loads((grades/'ended.json').read_text())['error'] is None
 case=grades/'00/grades/initial';row=json.loads((case/'input.json').read_text());result=json.loads((case/'results/result.json').read_text());report=json.loads(next((case/'results/logs').rglob('report.json')).read_text())[row['instance_id']]
 assert result['grade_execution_complete'] and report['resolved'] is False
 log=next((case/'results/logs').rglob('test_output.txt'));observed={}
 for line in log.read_text(errors='replace').splitlines():
  m=re.match(r'^(\S.*?::.*?)\s+(PASSED|FAILED|SKIPPED|XFAIL|XPASS|ERROR)(?:\s|$)',line)
  if m:observed[m[1]]=m[2]
 joined={}
 for field in ['FAIL_TO_PASS','PASS_TO_PASS']:
  ids=json.loads(row[field]) if isinstance(row[field],str) else row[field]
  for node in ids:
   matches=[k for k in observed if k==node or k.split(' ')[0]==node];assert len(matches)<=1
   joined[node]=observed[matches[0]] if matches else None
 assert joined==result['observed_required_statuses']
 projection=grades/'00/projections/stopped/conversion.json';conversion=json.loads(projection.read_text());assert conversion['patch_bytes']==0
 summary=dict(episode=episode,source_head=freeze['source_head'],freeze_sha256=H(study/'freeze.json'),setup=grouped['setup'],scored=grouped['scored'],attempted=1,unattempted=11,actual_scored_AEE=0,completion_declarations=0,final_delivery_grade='ungraded: no submitted proposal',retained_source_required_status_counts=collections.Counter(str(v) for v in joined.values()),retained_source_resolved=False,independent_projection_application_delta_bytes=0,source_archive_verified=True,all_declared_local_source_runtime_bytes_unchanged=True,files={p.relative_to(study).as_posix():H(p) for p in study.rglob('*') if p.is_file()})
 records.append(summary);print(json.dumps({k:v for k,v in summary.items() if k!='files'}),flush=True)
value=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_requests=0,episodes=records,total_generation_requests=sum(v[c]['calls'] for v in records for c in ['setup','scored']),known_native_tokens=sum(v[c]['known_native_tokens'] for v in records for c in ['setup','scored']),usage_unknown=0,scope='Bounded four stopped upstream preparations, same controller independent log/hash/accounting reconciliation; NOT independent human replication, completed matched comparison, spontaneous hallucination labels, AEE effect or token savings. All original episodes unchanged. APIspend0 excludes hardware/energy/labor.')
(OUT/'audit.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k!='episodes'}))
