"""Synthetic transport fixtures; real local Spec Kit/AEE tests make no model calls."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import matched_hallucinations as m
import matched_hallucinations_audit as a
from benchmark_runner.store import canonical, write_json


class FixtureProvider:
    def __init__(self, out):
        self.out, self.plan = out, m.load(m.REGISTRATION)
        self.inputs = []

    def call(self, messages, schema, output, metadata):
        self.inputs.append((messages, metadata))
        value = ({'document': 'Draft method:\nCompare candidate with source; preserve uncertainty.\n'}
                 if schema == m.DOC_SCHEMA else dict(verdict='abstain', rationale='Uncertain synthetic case.', source_quotes=[], uncertainties=['Not adjudicated.']))
        path = self.out / 'calls' / f'call-{len(self.inputs)-1:04}.json'
        native = dict(prompt_tokens=20, completion_tokens=10, total_tokens=30,
                      prompt_tokens_details=dict(cached_tokens=0))
        request = dict(model=self.plan['model'], seed=self.plan['seed'], max_tokens=output,
            messages=messages, cache_prompt=False, chat_template_kwargs={'enable_thinking': False},
            temperature=.6, top_p=.95, top_k=20, min_p=0., presence_penalty=0., repeat_penalty=1.,
            grammar=m.schema_grammar(schema))
        write_json(path, dict(metadata=metadata, request=request, validation_schema=schema, usage=native,
            preflight_input_tokens=20, response=dict(model=self.plan['model'], usage=native,
            choices=[dict(finish_reason='stop', message=dict(content=json.dumps(value)))])))
        return value, path


def test_schedule_is_matched_and_seeded_without_duplicate_or_missing_arms():
    rows = m.schedule([{}, {}, {}], 77)
    assert {(r['index'], r['arm']) for r in rows} == {(i, arm) for i in range(3) for arm in m.ARMS}
    assert len(rows) == 9 and rows == m.schedule([{}, {}, {}], 77)
    assert rows != m.schedule([{}, {}, {}], 78)


def test_real_speckit_helpers_and_templates_persist_draft_policy_without_labels(tmp_path):
    provider = FixtureProvider(tmp_path)
    folder = tmp_path / 'spec-policy'
    documents = m.build_policy(provider, folder, 'spec_kit', 'test')
    assert list(documents) == list(m.PHASES)
    assert len(provider.inputs) == 4
    for messages, metadata in provider.inputs:
        user = json.loads(messages[1]['content'])
        assert 'speckit_template' in user and 'speckit_command' in user
        assert not {'gold', 'input', 'actual_AEE_feedback'} & set(user)
    for tag in ('git-init', 'create-feature', 'setup-plan', 'check-prerequisites'):
        assert m.load(folder / 'host-commands' / (tag + '.json'))['exit_code'] == 0
    assert m.load(folder / 'policy.json')['human_acceptance'] == 'unrecorded'


def baseline_prefix(tmp_path):
    provider = FixtureProvider(tmp_path)
    policy = m.build_policy(provider, tmp_path / 'policies/test/baseline', 'baseline', 'test')
    case = dict(dataset='test', id='secret-case-id', gold='hallucinated', cluster='test-1', task='QA',
                payload=dict(source='Only cobalt exists.', question='What exists?', response='Amber exists.'))
    row = m.judge(provider, tmp_path / 'judgments/case-0000-baseline', 'baseline', 'test', case, policy, 'scored', 0)
    row.update(index=0, schedule_order=0)
    write_json(tmp_path / 'schedule.json', [dict(index=0, arm='baseline')])
    write_json(tmp_path / 'input-hashes.json', {'fixture': 'synthetic'})
    write_json(tmp_path / 'run-started.json', dict(source_hashes={}, input_hashes_sha256=a.digest((tmp_path / 'input-hashes.json').read_bytes())))
    write_json(tmp_path / 'result.json', dict(complete=False, physical_calls=3, rows=[row]))
    plan = {**provider.plan, 'datasets': ['test']}
    return provider, case, row, plan


def test_baseline_brief_is_one_real_cost_not_four_padded_calls_and_gold_is_absent(tmp_path):
    provider, case, row, plan = baseline_prefix(tmp_path)
    assert len(provider.inputs) == 3
    assert row['prediction'] == row['gate_prediction'] == 'abstain'
    for messages, _ in provider.inputs:
        assert case['id'] not in json.dumps(messages)
        assert '"gold"' not in json.dumps(messages)
    result = a.audit(tmp_path, plan, [case])
    assert result['accounting']['setup']['known_native_tokens'] == 30
    assert result['accounting']['scored/baseline']['known_native_tokens'] == 60
    assert result['scored_receipts_joined'] == 2
    assert result['scored_AEE_outcomes'] == {}


@pytest.mark.parametrize('change', ['hash', 'payload', 'draft', 'usage', 'arm', 'policy', 'gate', 'acceptance', 'schedule', 'escape'])
def test_offline_audit_rejects_changed_receipts_sources_costs_or_promotions(tmp_path, change):
    _, case, row, plan = baseline_prefix(tmp_path)
    state = m.load(tmp_path / 'result.json')
    path = tmp_path / row['final_call']
    call = m.load(path)
    user = json.loads(call['request']['messages'][1]['content'])
    if change == 'hash':
        call['preflight_input_tokens'] = 21
    elif change == 'payload':
        user['input']['source'] = 'Replacement source'
    elif change == 'draft':
        user['draft']['verdict'] = 'grounded'
    elif change == 'usage':
        call['usage']['total_tokens'] += 1
    elif change == 'arm':
        call['metadata']['arm'] = 'spec_kit'
    elif change == 'policy':
        user['policy'] = {'constitution': 'Other policy'}
    elif change == 'gate':
        state['rows'][0]['gate_prediction'] = 'grounded'
    elif change == 'acceptance':
        state['rows'][0]['human_acceptance'] = 'accepted'
    elif change == 'schedule':
        write_json(tmp_path / 'schedule.json', [dict(index=0, arm='spec_kit')])
    else:
        state['rows'][0]['final_call'] = '../outside.json'
    call['request']['messages'][1]['content'] = json.dumps(user, ensure_ascii=False)
    write_json(path, call)
    if change != 'hash':
        state['rows'][0]['final_call_sha256'] = m.sha(path.read_bytes())
    write_json(tmp_path / 'result.json', state)
    with pytest.raises((ValueError, KeyError)):
        a.audit(tmp_path, plan, [case])


def test_real_aee_composition_and_anchor_are_audited_without_human_promotion(tmp_path):
    project = tmp_path / 'actual-aee'
    project.mkdir()
    result = m.assessment(project, 'implement', 'Draft proposal only: cobalt is registered.', {'source': 'Cobalt is registered.'})
    assert a.audit_aee(project, ['implement']) == [result['outcome']]
    assert a.actual_feedback(project, 0) == m.feedback(result)
    event = m.Store(project / 'store').events('assessments')[0]
    artifact = project / 'store' / event['artifacts'][0]['path']
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        a.audit_aee(project, ['implement'])


def test_redacted_context_does_not_claim_original_evidence_bytes(tmp_path):
    with pytest.raises(ValueError, match='redaction changed'):
        m.assessment(tmp_path, 'implement', 'Draft', {'source': 'Bearer syntheticFixtureValue'})


def test_transport_failure_is_one_retained_unknown_call_without_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'verify', lambda out: None)
    monkeypatch.setattr(m, 'source_hashes', lambda: {})
    requests = []
    def transport(endpoint, body=None, **kwargs):
        if endpoint == '/slots':
            return []
        if endpoint == '/apply-template':
            return {'prompt': 'fixture'}
        if endpoint == '/tokenize':
            return {'tokens': [1, 2]}
        requests.append(endpoint)
        raise RuntimeError('synthetic transport failure')
    monkeypatch.setattr(m.current, 'http', transport)
    provider = m.Provider(tmp_path, m.load(m.REGISTRATION))
    with pytest.raises(RuntimeError, match='transport failure'):
        provider.call([], m.DECISION_SCHEMA, 1024, dict(cohort='scored', arm='baseline'))
    receipts = list((tmp_path / 'calls').glob('*.json'))
    assert len(receipts) == provider.count == len(requests) == 1
    assert m.load(receipts[0])['unknown_reason'] == 'failed_request_usage_unknown'


def test_template_failure_is_retained_without_a_generation_call(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'verify', lambda out: None)
    monkeypatch.setattr(m, 'source_hashes', lambda: {})
    requests = []
    def transport(endpoint, body=None, **kwargs):
        requests.append(endpoint)
        if endpoint == '/slots':
            return []
        raise RuntimeError('synthetic template failure')
    monkeypatch.setattr(m.current, 'http', transport)
    provider = m.Provider(tmp_path, m.load(m.REGISTRATION))
    with pytest.raises(RuntimeError, match='template failure'):
        provider.call([], m.DECISION_SCHEMA, 1024, dict(cohort='scored', arm='baseline'))
    assert provider.count == 0 and requests == ['/slots', '/apply-template']
    assert m.load(tmp_path / 'preflight-errors/before-call-0000.json')['generation_calls_started'] == 0


def test_aee_hard_block_prevents_review_call(tmp_path, monkeypatch):
    provider = FixtureProvider(tmp_path)
    monkeypatch.setattr(m, 'assessment', lambda *args: dict(outcome='block'))
    with pytest.raises(RuntimeError, match='hard block'):
        m.judge(provider, tmp_path / 'case', 'spec_kit_aee', 'test', dict(payload={'source': 'fixture'}), {}, 'setup', 0)
    assert len(provider.inputs) == 1


def test_all_three_workflows_join_real_helpers_aee_feedback_and_accounting(tmp_path):
    provider = FixtureProvider(tmp_path)
    case = dict(dataset='test', id='withheld', gold='hallucinated', cluster='one', task='QA',
                payload=dict(source='Only cobalt exists.', question='What exists?', response='Amber exists.'))
    rows = []
    for order, arm in enumerate(m.ARMS):
        policy = m.build_policy(provider, tmp_path / 'policies/test' / arm, arm, 'test')
        row = m.judge(provider, tmp_path / 'judgments' / f'case-0000-{arm}', arm, 'test', case, policy, 'scored', 0)
        row.update(index=0, schedule_order=order)
        rows.append(row)
    write_json(tmp_path / 'schedule.json', [dict(index=0, arm=arm) for arm in m.ARMS])
    write_json(tmp_path / 'input-hashes.json', {'fixture': 'synthetic'})
    write_json(tmp_path / 'run-started.json', dict(source_hashes={}, input_hashes_sha256=a.digest((tmp_path / 'input-hashes.json').read_bytes())))
    write_json(tmp_path / 'result.json', dict(complete=False, physical_calls=15, rows=rows))
    result = a.audit(tmp_path, {**provider.plan, 'datasets': ['test']}, [case])
    assert result['scored_receipts_joined'] == 6
    assert sum(result['scored_AEE_outcomes'].values()) == 2
    assert result['accounting']['setup/baseline']['calls'] == 1
    assert result['accounting']['setup/spec_kit']['calls'] == result['accounting']['setup/spec_kit_aee']['calls'] == 4
    assert all(result['accounting']['scored/' + arm]['calls'] == 2 for arm in m.ARMS)
    assert all(row['human_acceptance'] == 'unrecorded' for row in rows)


@pytest.mark.parametrize('field,limit', [('rationale', 320), ('source_quotes', 120), ('uncertainties', 80)])
def test_native_decision_schema_refuses_unbounded_review_strings(field, limit):
    import jsonschema
    value = dict(verdict='abstain', rationale='Unknown.', source_quotes=[], uncertainties=[])
    value[field] = 'x' * (limit + 1) if field == 'rationale' else ['x' * (limit + 1)]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, m.DECISION_SCHEMA)


def test_native_policy_schema_refuses_unbounded_document():
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({'document': 'x' * 3001}, m.DOC_SCHEMA)


def test_v2_only_adds_bounds_and_prospective_explanation_without_budget_or_gold_changes():
    old = m.load(m.REGISTRATIONS['matched-source-grounding-v1'])
    new = m.load(m.REGISTRATIONS['matched-source-grounding-v2'])
    changed = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
    assert changed == {'version', 'schema_bounds', 'prospective_amendment'}


@pytest.mark.parametrize('fail', [False, True])
def test_native_probe_is_three_separate_setup_calls_and_first_fault_stops(tmp_path, monkeypatch, fail):
    import probe_matched_output_bounds as probe
    calls = []
    class Fake(FixtureProvider):
        def __init__(self, out, plan):
            super().__init__(out)
            self.plan = plan
        def call(self, *args):
            calls.append(args)
            if fail:
                raise RuntimeError('synthetic native failure')
            from matched_grammar import native_probe_contracts
            value = ({'document': 'x' * 3000} if len(calls) == 1 else
                     {'document': native_probe_contracts()[2]['schema']['properties']['document']['const']} if len(calls) == 3 else
                     dict(verdict='abstain', rationale='Synthetic.', source_quotes=[], uncertainties=[]))
            path = self.out / 'calls' / f'call-{len(calls)-1:04}.json'
            write_json(path, {'usage': {'total_tokens': 30}})
            return value, path
    def prepare(out, original):
        out.mkdir()
        return m.load(m.REGISTRATION)
    monkeypatch.setattr(m, 'prepare', prepare)
    monkeypatch.setattr(m, 'Provider', Fake)
    monkeypatch.setattr(m, 'source_hashes', lambda: {})
    monkeypatch.setattr(m.current, 'configure_worker_binding', lambda path: None)
    monkeypatch.setattr(m.current, 'http', lambda *args, **kwargs: [])
    monkeypatch.setattr(m.subprocess, 'check_output', lambda argv, **kwargs: b'' if 'status' in argv else b'fixture-head')
    binding = tmp_path / 'binding.json'
    binding.write_text('{}')
    out = tmp_path / 'probe'
    if fail:
        with pytest.raises(RuntimeError, match='synthetic native failure'):
            probe.probe(out, tmp_path / 'original', binding)
        assert len(calls) == 1 and not (out / 'probe-result.json').exists()
    else:
        result = probe.probe(out, tmp_path / 'original', binding)
        assert len(calls) == result['physical_calls'] == 3
        assert result['known_native_tokens'] == 90
        assert all(args[-1]['cohort'] == 'setup' for args in calls)
