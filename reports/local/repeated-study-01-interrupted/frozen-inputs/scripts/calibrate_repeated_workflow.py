from pathlib import Path
import sys,time,json,os
sys.path.insert(0,str(Path('scripts').resolve()))
from repeated_local import *
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
lat=json.loads(Path('artifacts/repeated-latency-01/calibration.json').read_text())
p=Provider(out,SEEDS[0],lat['timeout']);store=Store(out/'evidence')
write_json(out/'source-hashes.json',{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__).resolve(),ROOT/'scripts/repeated_local.py']})
result=dict(passed=False,phases=[],assessments=[],calibration_only=True)
spec='Unscored calibration, unrelated to either scored feature. R01: create smoke.py containing add(a,b) returning a+b. R02: support negative integers, zero and floats. R03: add and run tests. Do not change TinyDB. Workflow artifacts use specs/001-transactions as a fixed directory label. Keep phase documents concise. There is no deployment, service or architecture to discover.'
try:
 with ProjectSandbox('tinydb') as box:
  box.stage_workflow();session=Session(box,p,store,'calibration');deadline=time.monotonic()+3600
  for phase in ('constitution','specify','plan','tasks','implement','converge','final_implement'):
   goal=PHASE_GOALS[phase].replace('/testbed/tinydb','/testbed/smoke.py')
   instructions=(ROOT/'prompts/adapter.md').read_text().replace('/workflow','/testbed')+'\n'+skill(phase).replace('$ARGUMENTS',spec)+'\n'+goal+'\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions. This is only an arithmetic utility; avoid unnecessary architecture.'
   need=phase in ('specify','plan','tasks','implement')
   row=session.phase(phase,instructions,spec,1,16 if phase in ('converge','final_implement') else 32,deadline,need)
   result['phases'].append(row);write_json(out/'result.json',result)
   if not row['completed']:raise RuntimeError('incomplete_calibration_phase:'+phase)
   if need:do_assessment(session,result,phase,row['done'])
   if phase=='implement':
    r=session.phase('evidence_rework','Review actual assessment gaps; run tests for negative and floating inputs and return revised grounded claims. Record unsupported boundaries honestly.',spec,1,16,deadline,True)
    result['phases'].append(r)
    if not r['completed']:raise RuntimeError('incomplete_evidence_rework')
    do_assessment(session,result,'implement',r['done'])
   write_json(out/'result.json',result)
  before=box.execute("python -c 'from smoke import add; assert add(-2,3)==1; assert add(0,0)==0; assert add(1.5,2.5)==4.0'")
  result['before_repair']=before
  if before['exit_code']:raise RuntimeError('calibration_implementation_failed')
  # Explicitly unscored injected regression exercises the identical public repair path.
  box.put({'smoke.py':b'def add(a,b):\n    return a-b\n','acceptance_public.py':b'from smoke import add\ndef test_sum():\n    assert add(2,3)==5\n'})
  feedback=box.execute('python -m pytest -q acceptance_public.py')
  result['injected_regression_feedback']=feedback
  assert feedback['exit_code']!=0
  r=session.phase('repair','Repair the injected calibration regression using this real feedback: '+feedback['stdout'],spec,1,8,deadline)
  result['repair']=r
  check=box.execute("python -c 'from smoke import add; assert add(-2,3)==1; assert add(0,0)==0; assert add(1.5,2.5)==4.0'")
  result['after_repair']=check
  result['passed']=r['completed'] and check['exit_code']==0 and len(result['assessments'])==5
  assert result['passed']
finally:
 result['calls']=len(p.calls);write_json(out/'result.json',result)
print('FULL WORKFLOW AND REPAIR CALIBRATION PASS',flush=True)
