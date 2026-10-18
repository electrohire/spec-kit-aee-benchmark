"""One guarded fresh pipeline: six representative cases, replay, scoring, export.

No implicit retries/resume, no paid calls and no overlap with preparatory inference.
The user authorized merges/rerun on 2026-10-18; publication outside git stays separate.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from benchmark_runner.store import write_json,utc
from readiness_gate import validate_representative
import current_local as current

ROOT=Path(__file__).resolve().parents[1]


def execute(status,latency,context,transport):
    state=dict(stage='waiting_for_preparatory_inference',complete=False,started_at=utc(),commands=[],paid_calls=False)
    representative=ROOT/'artifacts/current-representative-01'
    preflight=ROOT/'artifacts/current-preflight-02'
    raw=ROOT/'artifacts/current-study-02'
    report=ROOT/'reports/local/current-study-02'
    if any(p.exists() for p in (representative,preflight,raw,report)):raise FileExistsError('new study paths required; no retry/resume')
    status.parent.mkdir(parents=True,exist_ok=True);write_json(status,state,exclusive=True)
    def command(stage,argv,timeout):
        state.update(stage=stage,updated_at=utc());write_json(status,state)
        log=status.parent/(status.stem+'-'+stage+'.log')
        with log.open('wb') as handle:
            run=subprocess.run([sys.executable,*map(str,argv)],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout)
        state['commands'].append(dict(stage=stage,argv=list(map(str,argv)),exit_code=run.returncode,log=str(log)))
        write_json(status,state)
        if run.returncode:raise RuntimeError(stage+' stopped; inspect '+str(log))
    try:
        until=time.monotonic()+1800
        while not (latency/'calibration.json').exists():
            if time.monotonic()>until:raise TimeoutError('latency preparation did not finish')
            if any(json.loads(p.read_text()).get('error') for p in latency.glob('call-*.json')):
                raise RuntimeError('latency preparation failed')
            time.sleep(5)
        for path in (latency/'calibration.json',context/'result.json',transport/'result.json'):
            if not json.loads(path.read_text()).get('passed'):raise ValueError('preparation failed: '+str(path))
        command('independent-grade-controls',['scripts/current_local.py','grade-calibration',ROOT/'artifacts/current-grade-calibration-02'],1800)
        command('image-isolation',['scripts/audit_current_image.py',ROOT/'artifacts/current-image-audit-02.json'],120)
        command('representative-readiness',['scripts/representative_readiness.py',representative,'--latency',latency/'calibration.json'],6*current.CONFIG['stage_seconds']+1800)
        validate_representative(representative,current.CONFIG,current.runner.PROJECTS,current.runner.ARMS)
        preflight.mkdir()
        for source,name in ((representative,'representative'),(representative/'tinydb-spec_kit_aee','workflow'),
                            (ROOT/'artifacts/current-grade-calibration-02','grade'),(latency,'latency'),(context,'context'),(transport,'transport')):
            shutil.copytree(source,preflight/name)
        shutil.copyfile(ROOT/'artifacts/current-image-audit-02.json',preflight/'image-audit.json')
        command('dependency-replay',['scripts/replay_current_dependencies.py',preflight/'workflow',preflight/'dependency-replay'],300)
        command('scored-study',['scripts/current_local.py','run',raw,'--preflight',preflight],12*3*current.CONFIG['stage_seconds']+3600)
        export=['scripts/report_current.py',raw,report]
        # Earlier preparations remain setup costs. The exporter deduplicates each
        # physical call by original hash, including duplicated replay/copy folders.
        setups=[transport,latency,*sorted(p for p in representative.iterdir() if p.is_dir()),
                ROOT/'reports/feasibility/local-20261016',ROOT/'reports/feasibility/qwen38-readiness-20261016',
                *sorted(ROOT.glob('artifacts/current-workflow-calibration-*')),
                *sorted(ROOT.glob('artifacts/current-action-transport-*')),
                *sorted(ROOT.glob('artifacts/current-latency-calibration-*'))]
        for path in setups:
            if path.exists():export.extend(('--setup',path))
        command('export',export,1800)
        state.update(stage='exported_pending_audit',complete=True,ended_at=utc())
    except Exception as exc:
        state.update(stage='intervention_required',error=repr(exc),ended_at=utc())
        raise
    finally:write_json(status,state)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--status',type=Path,required=True)
    args=parser.parse_args()
    execute(args.status,ROOT/'artifacts/current-latency-calibration-02',ROOT/'artifacts/current-context-calibration-03',ROOT/'artifacts/current-action-transport-01')


if __name__=='__main__':main()
