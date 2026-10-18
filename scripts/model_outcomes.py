"""Prospective model-failure containment; infrastructure faults still stop."""
import hashlib
import json
import time
from collections import Counter
from datetime import datetime

from benchmark_runner.store import utc


def model_failure(alert):
    if alert.get('snapshot_error'):
        return False
    if alert.get('reason') in {
        'repeated identical action without changed observation',
        'phase did not complete; downstream execution withheld',
        'insufficient capacity before phase',
        'primary call budget exhausted before phase',
    }:
        return True
    return (alert.get('reason') == 'consecutive action/transport failures'
            and alert.get('error','').startswith(('ValueError(', 'JSONDecodeError(')))


def finish_stopped_stage(box, row, folder, out, grade, expected, calls, begin, alert, dependent=False):
    """Retain exact source and independent grades; never retry model work."""
    stage=row['stage']
    primary=folder/f'stage{stage}-primary.tar'
    if 'primary_snapshot' not in row:
        box.snapshot(primary)
        row.update(primary_snapshot=primary.relative_to(out).as_posix(),
                   public_primary=grade(row['project'],primary,stage,True,expected),
                   primary_completion_asserted=None)
    final=folder/f'stage{stage}-final.tar';box.snapshot(final)
    row.update(final_snapshot=final.relative_to(out).as_posix(),
               public_final=grade(row['project'],final,stage,True,expected),
               calls=calls,seconds=time.monotonic()-begin,ended_at=utc(),
               completion_asserted=None,completion_declaration_source='unavailable_after_intervention',
               status='not_attempted_dependent' if dependent else 'runtime_interrupted',
               blocked_phase=alert.get('phase','prior_stage'),
               blocked_reason='Prior stage intervention' if dependent else alert['reason'],
               runtime_intervention=alert,notes_index={'stdout':'','stderr':'','exit_code':0})


def validate_admission(workflow, path, config):
    """Validate genuine completed workflow/repair exposure, not all-arm success.

    Original interrupted result remains unchanged. A separately bound independent
    grade proves the repaired snapshot; no solver success is fabricated.
    """
    data=json.loads(path.read_text())
    if workflow.resolve()!=(path.parent/'workflow').resolve():
        raise ValueError('admission workflow path differs')
    if data.get('protocol')!='inclusive-model-outcomes-v1':
        raise ValueError('unknown scored admission protocol')
    for name,digest in data['hashes'].items():
        source=(path.parent/name).resolve()
        if not source.is_relative_to(path.parent.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise ValueError('admission evidence hash/path mismatch')
    required={'workflow/result.json','workflow/freeze.json','workflow/runtime-stopped.tar',
              'workflow/runtime-alert.json','repair-verification.json','grade/calibration.json'}
    if not required.issubset(data['hashes']):
        raise ValueError('admission evidence incomplete')
    value=json.loads((workflow/'result.json').read_text())
    if not model_failure(json.loads((workflow/'runtime-alert.json').read_text())):
        raise ValueError('unresolved infrastructure intervention cannot admit scoring')
    phases={r['phase']:r for r in value['phases']}
    if not all(phases.get(p,{}).get('completed') and phases[p]['calls']>0 for p in
               ('constitution','specify','plan','tasks','implement','converge','final_implement')):
        raise ValueError('actual full workflow exposure missing')
    if {r['phase'] for r in value['assessments']}!={'specify','plan','tasks','implement'} or len(value['assessments'])!=4:
        raise ValueError('four actual AEE checkpoints required')
    if not value['before_repair']['passed'] or value['injected_failure']['passed']:
        raise ValueError('actual pre-repair/injected controls missing')
    calls=[json.loads(p.read_text()) for p in (workflow/'calls').glob('call-*.json')]
    if any(p.relative_to(path.parent).as_posix() not in data['hashes'] for p in (workflow/'calls').glob('call-*.json')):
        raise ValueError('unbound calibration call')
    if not calls or any(not r.get('ended_at') or not r.get('usage') for r in calls):
        raise ValueError('incomplete calibration calls/usage')
    elapsed=(max(datetime.fromisoformat(r['ended_at']) for r in calls)
             -min(datetime.fromisoformat(r['started_at']) for r in calls)).total_seconds()
    if value['allowed_seconds']!=config['stage_seconds'] or not 0<=elapsed<=config['stage_seconds'] or not any(r['phase']=='repair' for r in calls):
        raise ValueError('workflow/repair exposure exceeds prospective capacity')
    proof=json.loads((path.parent/'repair-verification.json').read_text())
    gold=json.loads((path.parent/'grade/calibration.json').read_text())['projects'][value['project']]['reference']['1-public']
    if (not proof.get('passed') or proof['exit_code']!=0 or not proof.get('cases')
        or not all(c['passed'] for c in proof['cases'])
        or proof['test_count']!=gold['test_count']
        or len(proof['cases'])!=proof['test_count']
        or Counter((r.get('file'),r['name']) for r in proof['cases'])!=Counter((r.get('file'),r['name']) for r in gold['cases'])
        or proof['grader_source_sha256']!=gold['grader_source_sha256']
        or proof['grader_function_sha256']!=gold['grader_function_sha256']
        or proof['source_sha256']!=data['hashes']['workflow/runtime-stopped.tar']):
        raise ValueError('independent repaired snapshot verification failed')
    return data
