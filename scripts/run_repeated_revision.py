"""Wait for the paired experiment, then run the corrected fresh study sequentially."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
os.chdir(root)
assets=root/'artifacts/repeated-assets'
status={'state':'waiting_for_matched_repair','restored':False}
def save():
    (assets/'revision-status.json').write_text(json.dumps(status,indent=2))
save()
while True:
    if (assets/'CANCEL_SUITE').exists():
        status['state']='cancelled_before_start';save();raise SystemExit(1)
    try:
        previous=json.loads((assets/'suite-status.json').read_text())
        if previous.get('restored') and len(previous.get('runs',[]))==2:
            assert previous['runs'][1]['exit_code']==0, 'Matched repair must complete before next study'
            break
    except (FileNotFoundError,json.JSONDecodeError):
        pass
    time.sleep(2)
print('Matched repair finished and original service restored; starting fresh study02.',flush=True)
try:
    status['state']='starting_benchmark_server';save()
    subprocess.run(['powershell','-NoProfile','-File',str(assets/'start-revision-server.ps1')],check=True)
    status['state']='running_study02';save()
    result=subprocess.run([sys.executable,'scripts/repeated_local.py','run','artifacts/repeated-study-02',
                           '--preflight','artifacts/repeated-calibration-01','--timeout','180'],check=False)
    status['exit_code']=result.returncode
finally:
    restored=subprocess.run(['powershell','-NoProfile','-File',str(assets/'restore-service.ps1')],capture_output=True,text=True,check=False)
    status.update(restored=restored.returncode==0,restoration_stdout=restored.stdout,restoration_stderr=restored.stderr,state='finished')
    save()
if status.get('exit_code')!=0 or not status['restored']:
    raise SystemExit(1)
