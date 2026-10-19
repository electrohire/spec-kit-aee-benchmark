"""One fresh prospective campaign; serial children, no resume or implicit retry."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from benchmark_runner.store import utc, write_json

ROOT = Path(__file__).resolve().parents[1]


def paths(root, pipeline, study):
    if type(pipeline) is not int or type(study) is not int or min(pipeline, study) < 1:
        raise ValueError('positive integer campaign identifiers required')
    names = dict(image=f'artifacts/current-image-audit-{pipeline:02}.json',
        grade=f'artifacts/current-grade-calibration-{pipeline:02}',
        context=f'artifacts/current-context-calibration-{pipeline:02}',
        transport=f'artifacts/current-action-transport-{pipeline:02}',
        hallucination=f'artifacts/current-hallucination-{pipeline:02}',
        latency=f'artifacts/current-latency-calibration-{pipeline:02}',
        preflight=f'artifacts/current-preflight-{pipeline:02}',
        raw=f'artifacts/current-study-{study:02}', report=f'reports/local/current-study-{study:02}',
        status=f'artifacts/current-pipeline-{pipeline:02}.json')
    result = {key: root / name for key, name in names.items()}
    for path in result.values():
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('campaign path escapes repository')
        if path.exists() or path.is_symlink():
            raise FileExistsError(f'fresh paths required; no retry/resume: {path}')
    return result


def plan(p):
    return [
        ('image', ['scripts/audit_current_image.py', p['image']]),
        ('grade', ['scripts/current_local.py', 'grade-calibration', p['grade']]),
        ('context', ['scripts/current_local.py', 'context-calibration', p['context']]),
        ('transport', ['scripts/probe_action_transport.py', p['transport']]),
        ('hallucination', ['scripts/labelled_hallucinations.py', p['hallucination']]),
        ('latency', ['scripts/current_local.py', 'latency', p['latency']]),
    ]


def prepare(p):
    preflight = p['preflight']
    preflight.mkdir()
    shutil.copytree(ROOT / 'artifacts/current-representative-08/tinydb-spec_kit_aee', preflight / 'workflow')
    for name in ('grade', 'context', 'transport', 'latency'):
        shutil.copytree(p[name], preflight / name)
    shutil.copyfile(p['image'], preflight / 'image-audit.json')
    shutil.copyfile(ROOT / 'artifacts/current-admission-09/repair-verification.json', preflight / 'repair-verification.json')
    shutil.copyfile(ROOT / 'benchmarks/current_local/infrastructure-recovery-v1.json', preflight / 'recovery-migration.json')
    hashes = {f.relative_to(preflight).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in preflight.rglob('*') if f.is_file()}
    write_json(preflight / 'admission.json', dict(protocol='inclusive-model-outcomes-v1',
        recovery_protocol='infrastructure-recovery-v1', created_at=utc(), hashes=hashes,
        rationale='Fresh prospective study authorized by latest explicit benchmark mission. Historical HTTP500/ENOSPC cause remains unresolved. Exact infrastructure-only AST migration and fresh context/transport/latency/grader/image probes; no solver cap, task, model, guard or grading relaxation. No automatic retries.',
        unscored_exposure='Historical TinyDB combined workflow08 and injected repair proof; not fresh all-six-success readiness. Four semantic dependency replays follow. Separate synthetic-factbook hallucination diagnostic is not a treatment-effect estimate.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-id', type=int, default=10)
    parser.add_argument('--study-id', type=int, default=3)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    p = paths(ROOT, args.pipeline_id, args.study_id)
    for source in ('artifacts/current-representative-08/tinydb-spec_kit_aee/freeze.json',
                   'artifacts/current-admission-09/repair-verification.json'):
        if not (ROOT / source).is_file():
            raise FileNotFoundError(source)
    if args.dry_run:
        print(json.dumps(dict(paths={k: str(v) for k, v in p.items()},
            preparation=[(stage, list(map(str, argv))) for stage, argv in plan(p)], generation=False), indent=2))
        return
    state = dict(stage='starting', started_at=utc(), complete=False, commands=[],
                 pipeline=args.pipeline_id, study=args.study_id, paid_calls=False)
    write_json(p['status'], state, exclusive=True)

    def command(stage, argv):
        state.update(stage=stage, updated_at=utc())
        write_json(p['status'], state)
        log = p['status'].with_name(p['status'].stem + '-' + stage + '.log')
        with log.open('xb') as handle:
            run = subprocess.run([sys.executable, *map(str, argv)], cwd=ROOT,
                                 stdout=handle, stderr=subprocess.STDOUT)
        state['commands'].append(dict(stage=stage, argv=list(map(str, argv)), exit_code=run.returncode, log=str(log)))
        write_json(p['status'], state)
        if run.returncode:
            raise RuntimeError(stage + ' halted; inspect ' + str(log))

    try:
        for stage, argv in plan(p):
            command(stage, argv)
        prepare(p)
        command('dependency-replay', ['scripts/replay_current_dependencies.py', p['preflight'] / 'workflow',
            p['preflight'] / 'dependency-replay', '--admission', p['preflight'] / 'admission.json'])
        command('scored-study', ['scripts/current_local.py', 'run', p['raw'], '--preflight', p['preflight']])
        export = ['scripts/report_current.py', p['raw'], p['report']]
        setups = [ROOT / 'reports/feasibility/local-20261016', ROOT / 'reports/feasibility/qwen38-readiness-20261016',
            *sorted(ROOT.glob('artifacts/current-workflow-calibration-*')),
            *sorted(f for f in ROOT.glob('artifacts/current-representative-*/*') if (f / 'calls').is_dir()),
            *sorted(ROOT.glob('artifacts/current-action-transport-*')),
            *sorted(ROOT.glob('artifacts/current-latency-calibration-*')),
            p['hallucination']]
        for source in setups:
            if source.exists():
                export.extend(('--setup', source))
        command('export', export)
        command('audit', ['scripts/audit_current_results.py', p['report']])
        state.update(stage='exported_audited_pending_publication', complete=True, ended_at=utc())
    except BaseException as exc:
        state.update(stage='intervention_required', error=repr(exc), ended_at=utc())
        raise
    finally:
        write_json(p['status'], state)


if __name__ == '__main__':
    main()
