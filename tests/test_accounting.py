from decimal import Decimal

import pytest

from benchmark_runner.accounting import Budget, BudgetExceeded, cost, cumulative_delta, native_usage, unique_calls, validate_usage
from benchmark_runner.store import Store


def usage(i=100, c=20, o=30, r=10):
    return dict(input_tokens=i, cached_input_tokens=c, output_tokens=o, reasoning_tokens=r, unknown_reason=None)


def test_cache_and_reasoning_not_double_counted():
    assert cost(usage(), dict(input=2, cached_input=1, output=4)) == Decimal("0.0003")


@pytest.mark.parametrize("u", [usage(-1), usage(c=101), usage(r=31), usage(i=1.5), usage(i=True)])
def test_invalid_usage(u):
    with pytest.raises(ValueError):
        validate_usage(u)


def test_unknown_not_zero():
    u = native_usage({})
    assert u["input_tokens"] is None and u["unknown_reason"]
    assert cost(u, dict(input=1, cached_input=1, output=1)) is None


def test_cumulative_delta():
    assert cumulative_delta(usage(200, 40, 60, 20), usage()) == usage()
    with pytest.raises(ValueError):
        cumulative_delta(usage(), usage(200, 40, 60, 20))


def test_dedup_and_billable_retries():
    first = dict(call_id="a", request_id="r1", cost="1")
    retry = dict(call_id="b", request_id="r2", cost="1")
    assert unique_calls([first, first, retry]) == [first, retry]
    with pytest.raises(ValueError):
        unique_calls([first, {**first, "cost": "2"}])


def test_reservation_resume_unknown_retry_and_caps(tmp_path):
    store = Store(tmp_path)
    budget = Budget(store, 3, 2)
    budget.reserve("call1", "attempt1", 1)
    budget.settle("call1", None)
    Budget(store, 3, 2).reserve("retry", "attempt1", 1)
    with pytest.raises(BudgetExceeded):
        budget.reserve("call3", "attempt1", .01)
    budget.settle("retry", Decimal("0.25"))
    budget.reserve("call4", "attempt2", 1.5)
    with pytest.raises(BudgetExceeded):
        budget.reserve("call5", "attempt3", 1)
    with pytest.raises(ValueError):
        budget.reserve("call1", "attempt1", 1)


def test_bound_violation_persists_actual_charge(tmp_path):
    budget = Budget(Store(tmp_path), 10, 10)
    budget.reserve("a", "t", 1)
    with pytest.raises(RuntimeError):
        budget.settle("a", 2)
    assert budget.charges()["a"]["amount"] == "2"


def test_long_context_pricing_and_reservation():
    from benchmark_runner.accounting import request_prices
    cfg = dict(prices=dict(input=2, cached_input=1, output=4), long_context_threshold=100,
               long_context_prices=dict(input=4, cached_input=2, output=6))
    assert request_prices(cfg, usage())["input"] == 2
    assert request_prices(cfg, usage(101))["input"] == 4
    assert request_prices(cfg)["output"] == 6
