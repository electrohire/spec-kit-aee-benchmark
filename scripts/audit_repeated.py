"""Read-only audit of raw model accounting, frozen inputs and independent grades."""
import argparse
import hashlib
import json
from pathlib import Path

from report_long_horizon import source_digest
from report_repeated import accounting

ROOT = Path(__file__).resolve().parents[1]


def audit(raw, kind):
    freeze = json.loads((raw / 'freeze.json').read_text())
    for name, expected in freeze['hashes'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    records = []
    for path in sorted(raw.rglob('call-*.json')):
        record = json.loads(path.read_text())
        request = record['request']
        assert request['model'] == 'long-coder' and request['max_tokens'] == 4096, path
        assert request['temperature'] == .6 and request['top_p'] == .95 and request['top_k'] == 20, path
        assert record['preflight_input_tokens'] + request['max_tokens'] <= 32768, path
        usage = record.get('usage')
        if usage is not None:
            assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'], path
            assert 0 <= usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) <= usage['prompt_tokens'], path
            assert usage['completion_tokens'] <= request['max_tokens'], path
            assert record['budget_debit'] == usage['total_tokens'], path
        else:
            assert record.get('unknown_reason'), path
            assert record['budget_debit'] == record['preflight_input_tokens'] + request['max_tokens'], path
        records.append(record)
    rows = json.loads((raw / 'results.json').read_text())
    assert len(rows) == (36 if kind == 'study' else 32)
    assert len({(r['project'], r['seed'], r['arm'], r['stage'] if kind == 'study' else r['variant']) for r in rows}) == len(rows)
    for row in rows:
        stage = row['stage'] if kind == 'study' else 3
        expected = {'tinydb': {1:228, 2:233, 3:239}, 'cachetools': {1:221, 2:226, 3:232}}[row['project']][stage]
        grades = [row['hidden_final']]
        grades += [row['hidden_primary']] if kind == 'study' else [r['hidden'] for r in row['repairs']]
        for grade in grades:
            if grade['passed']:
                assert grade['test_count'] == expected and all(c['passed'] for c in grade['cases']), row
        for phase in row.get('phases', []):
            if 'source_before' in phase:
                assert phase['source_changed'] == (source_digest(raw / phase['source_before']) != source_digest(raw / phase['source_after']))
        assert (raw / row['final_snapshot']).is_file()
    return dict(passed=True, rows=len(rows), economics=accounting(records),
                note='Accounting, source hashes and grade consistency audited; this is not external replication or semantic source review.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['study', 'repair'])
    parser.add_argument('raw', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.raw, args.kind), indent=2))
