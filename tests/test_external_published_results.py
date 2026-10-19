"""Audit the measured public export without inference or source-corpus downloads."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/hallucinations/external-01-20261019'


def read(name):
    return json.loads((REPORT / name).read_text(encoding='utf-8'))


def test_published_detector_files_and_registered_inputs_are_bound():
    manifest = read('files-sha256.json')
    assert set(manifest) == {p.name for p in REPORT.iterdir() if p.is_file() and p.name != 'files-sha256.json'}
    for name, expected in manifest.items():
        assert hashlib.sha256((REPORT / name).read_bytes()).hexdigest() == expected, name
    assert read('upstream-sources.json') == json.loads((ROOT / 'benchmarks/hallucinations/upstream-sources-v1.json').read_text())
    identity = read('run-identity.json')
    assert identity['source_head'] == 'f6634d279f63de13da12dee493b449c9f6109170'
    assert identity['model'] == 'qwen3.8-27b'
    assert identity['input_hashes_sha256'] == read('result.json')['input_hashes_sha256']


def test_all_public_calls_join_author_gold_and_recompute_real_metrics():
    selection = json.loads((ROOT / 'benchmarks/hallucinations/selection-v1.json').read_text())
    receipts = read('call-receipts.json')
    result = read('result.json')
    assert len(receipts) == len(selection) == 240
    assert result['complete'] and result['graded'] == result['physical_calls'] == 240
    assert result['ungraded'] == result['usage_unknown'] == 0
    assert not result['pooled_with_coding'] and not result['AEE_efficacy_measured']
    tables, native = {}, Counter()
    for index, (call, chosen, row) in enumerate(zip(receipts, selection, result['scheduled_rows'], strict=True)):
        assert call['index'] == index and call['model'] == 'qwen3.8-27b' and call['finish_reason'] == 'stop'
        assert call['unknown_reason'] is None
        for key in ('dataset', 'id', 'cluster', 'gold', 'task'):
            assert call[key] == chosen[key] == row[key]
        assert call['prediction'] == row['prediction'] and row['status'] == 'graded'
        assert call['prediction'] in ('hallucinated', 'grounded', 'abstain')
        tables.setdefault(call['dataset'], Counter())[call['gold'], call['prediction']] += 1
        usage = call['usage']
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        for key in ('total_tokens', 'prompt_tokens', 'completion_tokens'):
            native[key] += usage[key]
        native['cached_tokens'] += usage['prompt_tokens_details']['cached_tokens']
    assert native['total_tokens'] == result['known_native_tokens'] == 213457
    assert native['prompt_tokens'] == 209990 and native['completion_tokens'] == 3467 and native['cached_tokens'] == 0
    for name, table in tables.items():
        tp, fp = table['hallucinated', 'hallucinated'], table['grounded', 'hallucinated']
        fn, tn = table['hallucinated', 'grounded'], table['grounded', 'grounded']
        abstain = table['hallucinated', 'abstain'] + table['grounded', 'abstain']
        metrics = result['metrics'][name]
        assert (metrics['tp'], metrics['fp'], metrics['fn'], metrics['tn']) == (tp, fp, fn, tn)
        assert metrics['accuracy_all'] == (tp + tn) / 120
        assert metrics['abstentions'] == abstain == 0
        assert metrics['precision'] == tp / (tp + fp)
        assert metrics['recall_all_positives'] == tp / (tp + fn)
        assert {key: metrics[key] for key in ('tp', 'fp', 'fn', 'tn')} == {key: read('upstream-regrade.json')['metrics'][name][key] for key in ('tp', 'fp', 'fn', 'tn')}
