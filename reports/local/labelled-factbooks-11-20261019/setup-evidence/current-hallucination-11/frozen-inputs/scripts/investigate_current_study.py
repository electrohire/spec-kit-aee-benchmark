"""Recompute harness exposure and calibration mismatch from immutable public data."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def investigate(folder):
    rows = read(folder/'attempts.json')
    freeze = read(folder/'freeze.json')
    arms = {}
    for arm in ('baseline', 'spec_kit', 'spec_kit_aee'):
        phases = defaultdict(lambda: dict(records=0, calls=0, completed=0, zero_call_records=0, errors=Counter()))
        selected = [r for r in rows if r['arm'] == arm]
        for row in selected:
            for phase in row['phases']:
                target = phases[phase['phase']]
                target['records'] += 1
                target['calls'] += phase['calls']
                target['completed'] += bool(phase['done'])
                target['zero_call_records'] += phase['calls'] == 0
                target['errors'].update(e.split(':', 1)[0] for e in phase['errors'])
        repair = [r for row in selected for r in row['repairs']]
        actions = Counter()
        for path in sorted(folder.glob('*-'+arm+'/call-*.json')):
            call = read(path)
            choices = (call.get('response') or {}).get('choices') or []
            if not choices:
                actions['no_response'] += 1
            elif choices[0].get('finish_reason') == 'length':
                actions['output_limit'] += 1
            else:
                try:
                    value = json.loads(choices[0]['message'].get('content') or '')
                    actions['json_'+value.get('action', 'other')] += 1
                except (ValueError, TypeError, AttributeError):
                    actions['invalid_action_json'] += 1
        arms[arm] = dict(phases=dict(phases), repair_records=len(repair),
                         repair_calls=sum(r['calls'] for r in repair), response_categories=dict(actions))
    calibration = folder/'setup-evidence/current-workflow-calibration-04'
    calls = [read(p) for p in sorted((calibration/'calls').glob('call-*.json'))]
    elapsed = (max(datetime.fromisoformat(c['ended_at']) for c in calls)
               - min(datetime.fromisoformat(c['started_at']) for c in calls)).total_seconds()
    frozen_source = (folder/'frozen-inputs/scripts/current_local.py').read_text(encoding='utf-8')
    inputs = ['attempts.json', 'freeze.json', 'setup-evidence/current-workflow-calibration-04/result.json',
              'frozen-inputs/scripts/current_local.py', 'frozen-inputs/scripts/repeated_local.py']
    return dict(arms=arms, calibration=dict(functional_passed=read(calibration/'result.json')['passed'],
        elapsed_seconds=elapsed, summed_call_seconds=sum(c['seconds'] for c in calls),
        controller_allowed_seconds=7200 if 'deadline = time.monotonic()+7200' in frozen_source else None,
        scored_stage_seconds=freeze['config']['stage_seconds'], request_reservation_seconds=freeze['config']['timeout'],
        fits_scored_budget=elapsed <= freeze['config']['stage_seconds']),
        source_hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in inputs})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = investigate(ROOT/'reports/local/current-study-01')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
