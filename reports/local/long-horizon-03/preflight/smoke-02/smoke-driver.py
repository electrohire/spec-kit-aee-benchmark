from pathlib import Path
import sys,os,time
sys.path.insert(0,str(Path('scripts').resolve()))
from long_horizon import Provider,Sandbox,run_phase,MiniModel,MiniEnvironment,Store,write_json,skill,PHASE_GOALS
out=Path('artifacts/long-smoke-02');out.mkdir()
os.environ['MSWEA_GLOBAL_CONFIG_DIR']=str(out/'mini-config');os.environ['MSWEA_SILENT_STARTUP']='1'
from minisweagent.agents.default import DefaultAgent
p=Provider(out,'Unscored development task unrelated to TinyDB features: create /testbed/smoke.py defining add(a,b), create a test, run it with python, and finish. Do not edit TinyDB. The workflow artifacts apply to this small arithmetic utility.')
image=Path('artifacts/long-assets/image-id.txt').read_text().strip()
with Sandbox(image,Path('artifacts/tinydb-upstream')) as sandbox:
 sandbox.stage_workflow();deadline=time.monotonic()+500
 m=MiniModel(p,deadline);env=MiniEnvironment(sandbox,deadline,Store(out/'evidence'),{'attempt_id':'smoke'})
 a=DefaultAgent(m,env,system_template='',instance_template='',cost_limit=0)
 adapter=Path('prompts/adapter.md').read_text()
 constitution=run_phase(a,m,p,'constitution',adapter+'\n'+skill('constitution')+'\nCURRENT PHASE DELIVERABLE: '+PHASE_GOALS['constitution'],deadline,25,0)
 done=run_phase(a,m,p,'solve','Now implement and test the unrelated arithmetic utility. Use shell actions, then done.',deadline,25,0)
 verification=sandbox.execute("python -c 'from smoke import add; assert add(17,25)==42; assert add(-2,2)==0'")
 document=sandbox.execute('cat /workflow/.specify/memory/constitution.md')
 passed=verification['exit_code']==0 and '[PROJECT_NAME]' not in document['stdout'] and len(document['stdout'])>200
 write_json(out/'result.json',dict(constitution=constitution,done=done,verification=verification,document=document,calls=len(p.calls),tool_calls=env.tool_calls,passed=passed))
 assert passed
