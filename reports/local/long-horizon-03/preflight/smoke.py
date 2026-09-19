from pathlib import Path
import sys, os, time
sys.path.insert(0, str(Path('scripts').resolve()))
from long_horizon import Provider, Sandbox, run_phase, MiniModel, MiniEnvironment, Store, write_json
out = Path('artifacts/long-smoke-01')
out.mkdir()
os.environ['MSWEA_GLOBAL_CONFIG_DIR'] = str(out/'mini-config')
os.environ['MSWEA_SILENT_STARTUP'] = '1'
from minisweagent.agents.default import DefaultAgent
p = Provider(out, 'Unscored development task unrelated to TinyDB. Create /testbed/smoke.py defining add(a,b), create a test, run it with python, and finish. Do not edit TinyDB.')
image = Path('artifacts/long-assets/image-id.txt').read_text().strip()
with Sandbox(image, Path('artifacts/tinydb-upstream')) as sandbox:
    deadline = time.monotonic()+300
    m = MiniModel(p, deadline)
    env = MiniEnvironment(sandbox, deadline, Store(out/'evidence'), {'attempt_id':'smoke'})
    a = DefaultAgent(m, env, system_template='', instance_template='', cost_limit=0)
    done = run_phase(a,m,p,'solve','Use shell actions to implement and test the unscored development task.',deadline,10,0)
    verification = sandbox.execute("python -c 'from smoke import add; assert add(17,25)==42; assert add(-2,2)==0'")
    write_json(out/'result.json',dict(done=done,verification=verification,calls=len(p.calls),tool_calls=env.tool_calls,passed=verification['exit_code']==0))
    assert verification['exit_code']==0 and env.tool_calls>0
