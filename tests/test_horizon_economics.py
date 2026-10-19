import pytest

from benchmark_runner.horizon_economics import compare, trajectory


def point(index, tokens, passed=None, unsafe=0):
    return dict(index=index, required_ids=['R1'], passed_ids=['R1'] if passed is None else passed,
        grade_complete=True, unsafe_claim_count=unsafe,
        new_calls=[dict(receipt_id=str(index), category='setup' if index == 1 else 'implementation',
            usage=dict(prompt_tokens=tokens-1, completion_tokens=1, total_tokens=tokens,
                       prompt_tokens_details=dict(cached_tokens=0)))])


def test_fixed_setup_tax_can_pay_back_but_only_at_observed_quality_matched_prefix():
    control = [point(i, 100) for i in range(1, 5)]
    treatment = [point(1, 180), point(2, 20), point(3, 20), point(4, 20)]
    result = compare(control, treatment)
    assert result['first_observed_break_even'] == result['sustained_observed_break_even'] == 2
    assert [r['extra_tokens'] for r in result['checkpoints']] == [80, 0, -80, -160]
    assert result['extrapolated_break_even'] is None


def test_cheap_failure_or_more_false_claims_is_not_payback():
    control = [point(1, 100), point(2, 100)]
    assert compare(control, [point(1, 20, passed=[]), point(2, 20, passed=[])])['first_observed_break_even'] is None
    assert compare(control, [point(1, 20, unsafe=1), point(2, 20, unsafe=1)])['first_observed_break_even'] is None
    assert trajectory([point(1, 20, passed=[])])[0]['tokens_per_verified_requirement'] is None


def test_unknown_usage_is_a_lower_bound_not_a_saving():
    control = [point(1, 100), point(2, 100)]
    treatment = [point(1, 20), point(2, 20)]
    treatment[0]['new_calls'][0].update(usage=None, unknown_reason='cancelled native call')
    result = compare(control, treatment)
    assert result['first_observed_break_even'] is None
    assert all(r['pays_back'] is None for r in result['checkpoints'])
    assert result['checkpoints'][-1]['treatment']['known_tokens'] == 20


def test_native_cached_tokens_are_not_added_twice():
    record = point(1, 100)
    record['new_calls'][0]['usage']['prompt_tokens_details']['cached_tokens'] = 80
    values = trajectory([record])[0]
    assert values['known_tokens'] == 100 and values['cached_tokens'] == 80


def test_crossover_can_reverse_and_last_point_does_not_establish_sustained_payoff():
    control = [point(i, 100) for i in range(1, 5)]
    treatment = [point(1, 80), point(2, 10), point(3, 400), point(4, 1)]
    result = compare(control, treatment)
    assert result['first_observed_break_even'] == 1
    assert result['sustained_observed_break_even'] is None


def test_missing_quality_adjudication_blocks_payoff_claim():
    result = compare([point(1, 100, unsafe=None)], [point(1, 10)])
    assert result['checkpoints'][0]['pays_back'] is None


@pytest.mark.parametrize('problem', ['drop', 'duplicate', 'cache', 'total', 'unknown'])
def test_accounting_and_requirement_integrity_refuse_invalid_inputs(problem):
    data = [point(1, 100), point(2, 100)]
    if problem == 'drop':
        data[1].update(required_ids=[], passed_ids=[])
    elif problem == 'duplicate':
        data[1]['new_calls'][0]['receipt_id'] = '1'
    elif problem == 'cache':
        data[0]['new_calls'][0]['usage']['prompt_tokens_details']['cached_tokens'] = 1000
    elif problem == 'total':
        data[0]['new_calls'][0]['usage']['total_tokens'] = 999
    else:
        data[0]['new_calls'][0]['usage'] = None
    with pytest.raises(ValueError):
        trajectory(data)
