from pathlib import Path
import json,hashlib,copy,datetime,shutil,csv
root=Path.cwd();src=root/'artifacts/study02-postmortem-01';out=root/'reports/local/current-study-02-stopped-postmortem';out.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
original=json.loads((src/'run.json').read_bytes());assert original['complete'] and original['stopped_artifacts_unchanged'];d=copy.deepcopy(original)
freeze_path=root/'artifacts/current-study-02/freeze.json';f=json.loads(freeze_path.read_bytes());cal=json.loads((root/'artifacts/current-preflight-09/grade/calibration.json').read_bytes());assert cal==f['calibration']
shutil.copyfile(freeze_path,out/'freeze.json');shutil.copyfile(src/'run.json',out/'initial-export-run.json');shutil.copyfile(src/'stopped-input-sha256.json',out/'stopped-input-sha256.json');shutil.copyfile(root.parent.parent/'audit-stopped-study-postmortem.py',out/'controller.py')
assert sha(out/'controller.py')==d['controller_sha256'] and sha(out/'freeze.json')==d['freeze_sha256']
for g in d['grades']:shutil.copyfile(src/g['path'],out/g['path']);assert sha(out/g['path'])==g['sha256']
for row in d['rows']:
 row['grade_invocations_available']=row.get('grade_status')=='exact_retained_snapshot_graded';row['complete_test_inventory']=False;row['proxy_eligible']=False
 if row['grade_invocations_available']:
  complete=True
  for mode,g in row['grades'].items():
   expected=f['calibration']['projects'][row['project']]['reference'][f"{row['stage']}-{mode}"]['test_count'];grade=json.loads((out/g['path']).read_bytes());g['expected_test_count']=expected;g['complete_test_inventory']=grade['test_count']==expected and not any(any(x['kind'] in ('error','skipped') for x in c['failures']) for c in grade['cases']);complete &= g['complete_test_inventory']
  row['complete_test_inventory']=complete;row['proxy_eligible']=complete;row['grade_status']='complete_test_inventory' if complete else 'incomplete_test_inventory'
eligible=[r for r in d['rows'] if r['proxy_eligible']];assert len(eligible)==1 and eligible[0]['project']=='tinydb'
d['declaration_denominators']=dict(positive=0,negative=0,unknown_graded=1,ungraded=35)
d['source_snapshots_with_grade_invocations']=2;d['checkpoints_with_complete_inventory']=1;d['attempted_checkpoints']=3;d['unattempted_checkpoints']=33
d['normalization']=dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),reason='Initial exporter counted any grade invocation as proxy-eligible. Apply the existing complete-test-inventory requirement: cachetools collected1error versus218public/221hidden expected, so it remains proxy-ungraded. No grade or raw source changed; no extra model or grader call.',initial_export_sha256=sha(out/'initial-export-run.json'))
write('summary.json',d);write('checkpoint-rows.json',d['rows'])
with (out/'checkpoint-rows.csv').open('w',newline='',encoding='utf-8') as handle:
 keys=['project','seed','arm','stage','status','generation_calls','grade_status','complete_test_inventory','completion_asserted','accepted_project_delivery'];w=csv.DictWriter(handle,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(d['rows'])
shutil.copyfile(root/'artifacts/study02-retained-cost-audit-03/summary.json',out/'bounded-cost-inventory.json')
(out/'REVIEW.md').write_text('Initial exporter01 confused grade availability with complete inventory eligibility. Its original bytes are retained in initial-export-run.json. Cachetools has a bound failed collection, not a completed test inventory. The final disjoint proxy denominators are positive0, negative0, unknown1, ungraded35. This follows the existing inventory rule; no scored snapshot, test, grader, threshold or raw campaign artifact changed.\n',encoding='utf-8')
print(json.dumps(dict(rows=len(d['rows']),grade_invocations=len(d['grades']),complete_inventory=1,denominators=d['declaration_denominators'],raw_unchanged=d['stopped_artifacts_unchanged'])))
