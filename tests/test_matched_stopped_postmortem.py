import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/hallucinations/matched-01-stopped-20261019'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_stopped_matched_manifest_and_complete_schedule_preserve_unknown_rows():
    for name, expected in read(REPORT / 'files-sha256.json').items():
        assert hashlib.sha256((REPORT / name).read_bytes()).hexdigest() == expected
    rows = read(REPORT / 'scheduled-rows.json')
    selection = read(ROOT / 'benchmarks/hallucinations/selection-v1.json')
    assert len(rows) == 720
    assert {(r['index'], r['arm']) for r in rows} == {(i, arm) for i in range(240) for arm in ('baseline', 'spec_kit', 'spec_kit_aee')}
    assert Counter(r['status'] for r in rows) == {'graded':72, 'attempted_ungraded':1, 'unattempted':647}
    for row in rows:
        assert all(row[k] == selection[row['index']][k] for k in ('id', 'gold', 'dataset', 'cluster', 'task'))
        if row['status'] == 'unattempted':
            assert row['new_calls'] == 0 and row['prediction'] is None


def test_failure_receipt_known_usage_and_all_retained_aee_counts_agree():
    calls = read(REPORT / 'call-receipts.json')
    assert len(calls) == 185 and all(c['usage'] for c in calls)
    assert sum(c['usage']['total_tokens'] for c in calls) == 712919
    failures = [c for c in calls if c['error']]
    assert len(failures) == 1
    assert failures[0]['path'] == 'calls/call-0184.json'
    assert failures[0]['response_model'] == 'qwen3.8-27b'
    assert failures[0]['finish_reason'] == 'length'
    assert failures[0]['usage']['completion_tokens'] == failures[0]['max_tokens'] == 1024
    assert sum(p['entries'] for p in read(REPORT / 'aee-ledger-commitments.json')) == 54
    assert read(REPORT / 'summary.json')['complete'] is False
