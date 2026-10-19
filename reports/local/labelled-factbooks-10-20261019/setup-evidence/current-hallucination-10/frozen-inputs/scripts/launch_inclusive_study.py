"""Fresh scored study after bound infrastructure proof; never retry model work."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from benchmark_runner.store import utc,write_json

ROOT=Path(__file__).resolve().parents[1]


def main():
    preflight=ROOT/'artifacts/current-preflight-09'
    raw=ROOT/'artifacts/current-study-02';report=ROOT/'reports/local/current-study-02'
    status=ROOT/'artifacts/current-pipeline-09.json'
    if any(p.exists() for p in (preflight,raw,report,status)):
        raise FileExistsError('fresh paths required; no implicit retry/resume')
    preflight.mkdir()
    for source,name in (
        ('current-representative-08/tinydb-spec_kit_aee','workflow'),
        ('current-grade-calibration-08','grade'),('current-context-calibration-06','context'),
        ('current-latency-calibration-05','latency'),('current-action-transport-06','transport')):
        shutil.copytree(ROOT/'artifacts'/source,preflight/name)
    shutil.copyfile(ROOT/'artifacts/current-image-audit-08.json',preflight/'image-audit.json')
    shutil.copyfile(ROOT/'artifacts/current-admission-09/repair-verification.json',preflight/'repair-verification.json')
    names=[p.relative_to(preflight).as_posix() for p in preflight.rglob('*') if p.is_file()]
    write_json(preflight/'admission.json',dict(protocol='inclusive-model-outcomes-v1',created_at=utc(),
        rationale='User directed scored benchmarking now. Completed actual full workflow and independently verified injected repair demonstrate infrastructure; model loops/failures are scored outcomes, not a requirement that every arm succeeds before it can be measured. Other guards/caps/grading remain unchanged.',
        hashes={name:hashlib.sha256((preflight/name).read_bytes()).hexdigest() for name in names},
        unscored_exposure='TinyDB combined current08; no assertion that all six readiness cases passed. Historical calibration exposure disclosed separately.'))
    state=dict(stage='dependency-replay',started_at=utc(),complete=False,commands=[],paid_calls=False)
    write_json(status,state,exclusive=True)
    def command(stage,argv):
        state.update(stage=stage,updated_at=utc());write_json(status,state)
        log=status.with_name(status.stem+'-'+stage+'.log')
        with log.open('wb') as handle:
            run=subprocess.run([sys.executable,*map(str,argv)],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
        state['commands'].append(dict(stage=stage,argv=list(map(str,argv)),exit_code=run.returncode,log=str(log)))
        write_json(status,state)
        if run.returncode:raise RuntimeError(stage+' stopped; inspect '+str(log))
    try:
        command('dependency-replay',['scripts/replay_current_dependencies.py',preflight/'workflow',preflight/'dependency-replay','--admission',preflight/'admission.json'])
        command('scored-study',['scripts/current_local.py','run',raw,'--preflight',preflight])
        export=['scripts/report_current.py',raw,report]
        setups=[ROOT/'reports/feasibility/local-20261016',ROOT/'reports/feasibility/qwen38-readiness-20261016',
                *sorted(ROOT.glob('artifacts/current-workflow-calibration-*')),
                *sorted(p for p in ROOT.glob('artifacts/current-representative-*/*') if (p/'calls').is_dir()),
                *sorted(ROOT.glob('artifacts/current-action-transport-*')),
                *sorted(ROOT.glob('artifacts/current-latency-calibration-*'))]
        for path in setups:
            if path.exists():export.extend(('--setup',path))
        command('export',export)
        state.update(stage='exported_pending_audit',complete=True,ended_at=utc())
    except BaseException as exc:
        state.update(stage='intervention_required',error=repr(exc),ended_at=utc());raise
    finally:write_json(status,state)


if __name__=='__main__':main()
