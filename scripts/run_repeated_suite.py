"""Run frozen experiments sequentially and restore the user's original local model."""
import json
import os
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
os.chdir(root)
assets=root/'artifacts/repeated-assets'
status={'runs':[],'restored':False}
try:
    gate=json.loads((root/'artifacts/repeated-workflow-04/result.json').read_text())
    assert gate['passed'], 'Full workflow calibration required'
    timeout=json.loads((root/'artifacts/repeated-latency-01/calibration.json').read_text())['timeout']
    commands=[
        ['scripts/repeated_local.py','run','artifacts/repeated-study-01','--preflight','artifacts/repeated-calibration-01','--timeout',str(timeout)],
        ['scripts/matched_repair.py','run','artifacts/matched-repair-01','--preflight','artifacts/matched-calibration-01','--timeout',str(timeout)],
    ]
    for args in commands:
        done=subprocess.run([sys.executable,*args],check=False)
        status['runs'].append({'args':args,'exit_code':done.returncode})
        (assets/'suite-status.json').write_text(json.dumps(status,indent=2))
finally:
    restored=subprocess.run(['powershell','-NoProfile','-File',str(assets/'restore-service.ps1')],capture_output=True,text=True,check=False)
    status['restored']=restored.returncode==0
    status['restoration_stdout']=restored.stdout
    status['restoration_stderr']=restored.stderr
    (assets/'suite-status.json').write_text(json.dumps(status,indent=2))
if not status['restored'] or any(r['exit_code'] for r in status['runs']):
    raise SystemExit(1)
