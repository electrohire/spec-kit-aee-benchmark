from pathlib import Path
import sys,os,time
sys.path.insert(0,str(Path('scripts').resolve()))
from long_horizon import Provider,Sandbox,run_phase,MiniModel,MiniEnvironment,Store,write_json,skill,PHASE_GOALS,CLAIMS,assess,grounded_claims,ROOT
out=Path('artifacts/long-smoke-09');out.mkdir()
os.environ['MSWEA_GLOBAL_CONFIG_DIR']=str(out/'mini-config');os.environ['MSWEA_SILENT_STARTUP']='1'
from minisweagent.agents.default import DefaultAgent
p=Provider(out,'Unscored arithmetic utility, unrelated to the scored TinyDB features. R01: create /testbed/smoke.py with add(a,b) returning a+b. R02: support integers and floats without changing TinyDB source. R03: add and run tests, including negative values and zero. Build the small utility through every requested workflow phase. Workflow files use /testbed/specs/001-transactions, a fixed benchmark directory name; this task is arithmetic, not database transactions.')
image=Path('artifacts/long-assets/image-id.txt').read_text().strip();store=Store(out/'evidence');result={'passed':False,'phases':[],'assessments':[]}
try:
 with Sandbox(image,Path('artifacts/tinydb-upstream')) as sandbox:
  sandbox.stage_workflow();deadline=time.monotonic()+1800
  m=MiniModel(p,deadline);env=MiniEnvironment(sandbox,deadline,store,{'attempt_id':'smoke'})
  a=DefaultAgent(m,env,system_template='',instance_template='',cost_limit=0)
  adapter=Path('prompts/adapter.md').read_text().replace('/workflow','/testbed')
  for phase in ('constitution','specify','plan','tasks','implement','converge','final_implement'):
   instructions=adapter+'\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions for setup scripts.\n'+skill(phase)+'\nCURRENT PHASE DELIVERABLE: '+PHASE_GOALS[phase]
   if phase in ('specify','plan','tasks','implement'):instructions+='\n'+CLAIMS
   done=run_phase(a,m,p,phase,instructions,deadline,80,0);result['phases'].append({'phase':phase,'done':done})
   if phase in ('specify','plan','tasks','implement'):
    claims=grounded_claims(done.get('claims') or {},store,'smoke');evaluation=assess(ROOT,claims,phase,store);result['assessments'].append({'phase':phase,'evaluation':evaluation})
    a.add_messages({'role':'user','content':'AEE/Evaluator evidence result (not an independent test grade): '+__import__('json').dumps(evaluation)})
   write_json(out/'result.json',result)
  verification=sandbox.execute("python -c 'from smoke import add; assert add(17,25)==42; assert add(-2,2)==0; assert add(1.5,2.5)==4.0'")
  document=sandbox.execute('cat /testbed/.specify/memory/constitution.md')
  result.update(verification=verification,calls=len(p.calls),tool_calls=env.tool_calls,passed=verification['exit_code']==0 and len(result['phases'])==7 and len(result['assessments'])==4)
except BaseException as exc:
 result['error']=type(exc).__name__+': '+str(exc)
 raise
finally:write_json(out/'result.json',result)
assert result['passed']
