import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('external_hallucinations', SCRIPTS / 'external_hallucinations.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def test_question_pairs_selected_without_label_leakage():
    rows = [dict(knowledge=f'evidence{i}', question=f'question{i}', right_answer='true', hallucinated_answer='false') for i in range(8)]
    cases = h.select_halueval(rows, 3)
    assert len(cases) == 6
    assert len({r['cluster'] for r in cases}) == 3
    assert sorted(r['gold'] for r in cases) == ['grounded'] * 3 + ['hallucinated'] * 3
    assert all(set(r['payload']) == {'source', 'question', 'response'} for r in cases)
    assert h.select_halueval(rows, 3) == cases
    assert h.select_halueval(rows + [rows[0]], 3) == cases


def rag_fixture():
    sources, rows = [], []
    for task in ('QA', 'Summary', 'Data2txt'):
        for label in (False, True):
            for i in range(3):
                sid = f'{task}:{label}:{i}'
                sources.append(dict(source_id=sid, task_type=task, source_info='context', prompt='instruction'))
                rows.append(dict(id=sid, source_id=sid, split='test', quality='good', response='answer',
                    labels=[dict(implicit_true=not label)]))
    return rows, sources


def test_ragtruth_test_only_unique_sources_and_author_gold_convention():
    rows, sources = rag_fixture()
    rows += [dict(rows[0], id='excluded-train', split='train'), dict(rows[0], id='excluded-quality', quality='truncated')]
    cases = h.select_ragtruth(rows, sources, 2)
    assert len(cases) == len({r['cluster'] for r in cases}) == 12
    assert not {'excluded-train', 'excluded-quality'} & {r['id'] for r in cases}
    assert set(h.Counter((r['task'], r['gold']) for r in cases).values()) == {2}
    assert all('labels' not in r['payload'] for r in cases)
    with pytest.raises(ValueError, match='duplicate'):
        h.select_ragtruth(rows + [rows[0]], sources, 1)
    with pytest.raises(ValueError, match='insufficient'):
        h.select_ragtruth(rows, sources, 4)


def test_upstream_bad_flags_and_missing_fields_refused():
    rows, sources = rag_fixture()
    rows[0]['labels'][0]['implicit_true'] = 'False'
    with pytest.raises(ValueError, match='boolean'):
        h.select_ragtruth(rows, sources, 1)
    with pytest.raises(ValueError, match='malformed'):
        h.select_halueval([{}], 1)


def test_metrics_abstention_not_hidden_or_counted_as_true_negative():
    pairs = [('hallucinated', 'hallucinated'), ('hallucinated', 'grounded'),
             ('hallucinated', 'abstain'), ('grounded', 'hallucinated'),
             ('grounded', 'grounded'), ('grounded', 'abstain')]
    result = h.metrics([dict(gold=g, prediction=p, cluster=str(i // 2)) for i, (g, p) in enumerate(pairs)])
    assert (result['tp'], result['fp'], result['fn'], result['tn']) == (1, 1, 1, 1)
    assert result['abstentions'] == 2
    assert result['accuracy_all'] == result['recall_all_positives'] == 1 / 3
    assert result['dependent_question_clusters'] == 3
    assert h.metrics([])['precision'] is None


@pytest.mark.parametrize('value,finish', [({'verdict': 'yes'}, 'stop'), ({'verdict': 'grounded', 'gold': 'grounded'}, 'stop'),
    ({'verdict': 'grounded'}, 'length'), ([], 'stop')])
def test_invalid_native_responses_stop(value, finish):
    with pytest.raises(ValueError):
        h.parse_verdict(dict(choices=[dict(finish_reason=finish, message=dict(content=json.dumps(value)))]))


@pytest.mark.parametrize('stage', ['latency', 'pipeline', 'scored-study'])
def test_no_inference_before_successful_coding_supervisor(tmp_path, stage):
    p = tmp_path / 'coding.json'
    p.write_text(json.dumps(dict(stage=stage)))
    with pytest.raises(RuntimeError, match='supervisor'):
        h.assert_coding_complete(p)


def test_first_transport_failure_retained_with_unknown_usage_and_no_retry(tmp_path, monkeypatch):
    case = dict(dataset='fixture', id='1', cluster='1', gold='grounded', task='QA',
                payload=dict(source='source', response='response'))
    monkeypatch.setattr(h, 'verify', lambda out: [case, case])
    monkeypatch.setattr(h, 'assert_coding_complete', lambda p: None)
    monkeypatch.setattr(h, 'source_hashes', lambda: {})
    monkeypatch.setattr(h.subprocess, 'check_output', lambda args, **kw: b'' if 'status' in args else b'fixture-head')
    monkeypatch.setattr(h.current, 'configure_worker_binding', lambda p: None)
    monkeypatch.setattr(h.current, 'setup', lambda: None)
    weights = tmp_path / 'fixture.gguf'
    weights.write_bytes(b'explicit synthetic model bytes')
    monkeypatch.setattr(h.current, 'WEIGHTS', weights)
    binding = tmp_path / 'binding.json'
    binding.write_text('{}')
    (tmp_path / 'input-hashes.json').write_text('{}')
    (tmp_path / 'coding.json').write_text('{}')
    generations = []

    def http(route, payload=None, timeout=120):
        if route == '/slots':
            return [dict(is_processing=False)]
        if route in ('/v1/models', '/props'):
            return {}
        if route == '/apply-template':
            assert 'gold' not in payload['messages'][1]['content']
            return dict(prompt='prompt')
        if route == '/tokenize':
            return dict(tokens=[1, 2])
        generations.append(payload)
        raise OSError('fixture connection loss')

    monkeypatch.setattr(h.current, 'http', http)
    with pytest.raises(OSError, match='connection loss'):
        h.run(tmp_path, tmp_path / 'coding.json', binding)
    assert len(generations) == 1
    result = json.loads((tmp_path / 'result.json').read_text())
    assert not result['complete'] and result['physical_calls'] == 1 and result['rows'] == []
    call = json.loads((tmp_path / 'calls/call-0000.json').read_text())
    assert call['usage'] is None and call['unknown_reason'] == 'failed_request_usage_unknown'
    with pytest.raises(FileExistsError):
        h.run(tmp_path, tmp_path / 'coding.json', binding)
    assert len(generations) == 1


def test_native_schema_accepts_three_decisions():
    for verdict in h.LABELS:
        assert h.parse_verdict(dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps({'verdict': verdict})))])) == verdict


def test_retained_coding_stop_allows_distinct_experiment_not_resume(tmp_path):
    path = tmp_path / 'coding.json'
    path.write_text(json.dumps(dict(stage='halted', error='original coding failure retained')))
    h.assert_coding_complete(path)
    path.write_text(json.dumps(dict(stage='halted')))
    with pytest.raises(RuntimeError, match='reason'):
        h.assert_coding_complete(path)


def test_prepare_rejects_tampered_download_before_output(tmp_path, monkeypatch):
    registration = tmp_path / 'registration.json'
    registration.write_text(json.dumps({'fixture': {'files': {'input': {'sha256': '0' * 64}}}}))
    monkeypatch.setattr(h, 'REGISTRATION', registration)
    (tmp_path / 'fixture').mkdir()
    (tmp_path / 'fixture/input').write_text('changed')
    with pytest.raises(ValueError, match='upstream hash'):
        h.prepare(tmp_path, tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def audit_fixture(tmp_path, monkeypatch):
    case = dict(dataset='halueval_qa', id='fixture', cluster='cluster', gold='hallucinated', task='QA',
                payload=dict(source='truth', response='false'))
    monkeypatch.setattr(h, 'verify', lambda out: [case])
    (tmp_path / 'calls').mkdir()
    (tmp_path / 'input-hashes.json').write_text('{}')
    (tmp_path / 'run-started.json').write_text(json.dumps(dict(
        input_hashes_sha256=h.digest(b'{}'), source_hashes={})))
    response = dict(model=h.current.MODEL, choices=[dict(finish_reason='stop',
        message=dict(content=json.dumps({'verdict': 'grounded'})))])
    call = dict(request=h.request_for(case), response=response, case_index=0,
                usage=dict(total_tokens=42))
    path = tmp_path / 'calls/call-0000.json'
    path.write_text(json.dumps(call))
    row = {k: case[k] for k in ('dataset', 'id', 'cluster', 'gold', 'task')} | dict(
        prediction='grounded', call='calls/call-0000.json', call_sha256=h.digest(path.read_bytes()))
    state = dict(complete=False, physical_calls=1, rows=[row])
    (tmp_path / 'result.json').write_text(json.dumps(state))
    return case, call, path, row, state


def test_independent_audit_scores_wrong_predictions_without_relabelling(tmp_path, monkeypatch):
    audit_fixture(tmp_path, monkeypatch)
    result = h.score(tmp_path)
    assert result['graded'] == result['physical_calls'] == 1
    assert result['known_native_tokens'] == 42 and result['usage_unknown'] == 0
    assert result['metrics']['halueval_qa']['false_acceptances'] == 1
    assert result['AEE_efficacy_measured'] is False and not result['complete']
    assert 'INCOMPLETE' in (tmp_path / 'README.md').read_text()


@pytest.mark.parametrize('mutation', ['hash', 'gold', 'prompt', 'settings', 'prediction', 'duplicate', 'complete', 'schedule'])
def test_audit_refuses_evidence_or_grade_tampering(tmp_path, monkeypatch, mutation):
    case, call, path, row, state = audit_fixture(tmp_path, monkeypatch)
    if mutation == 'hash':
        path.write_text(path.read_text() + ' ')
    elif mutation == 'gold':
        row['gold'] = 'grounded'
    elif mutation == 'prediction':
        row['prediction'] = 'hallucinated'
    elif mutation == 'duplicate':
        state['rows'].append(row)
    elif mutation == 'complete':
        state['complete'] = True
    elif mutation == 'schedule':
        row['call'] = '../outside.json'
    else:
        if mutation == 'prompt':
            call['request']['messages'][1]['content'] += ' label: hallucinated'
        else:
            call['request']['max_tokens'] += 1
        path.write_text(json.dumps(call))
        row['call_sha256'] = h.digest(path.read_bytes())
    (tmp_path / 'result.json').write_text(json.dumps(state))
    with pytest.raises(ValueError):
        h.score(tmp_path)
