"""Economic reporting must preserve failed work and unknown native usage."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('long_report', Path(__file__).parents[1]/'scripts/report_long_horizon.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_failed_known_call_still_counts():
    calls = [dict(usage=dict(prompt_tokens=20,completion_tokens=4,total_tokens=24),seconds=2,error='response_limit')]
    result = module.usage(calls)
    assert result['total_tokens'] == 24
    assert result['calls'] == 1 and result['http_seconds'] == 2

def test_unknown_call_prevents_complete_cost_claim():
    calls = [dict(usage=dict(prompt_tokens=20,completion_tokens=4,total_tokens=24),seconds=2),dict(usage=None,seconds=5)]
    result = module.usage(calls)
    assert result['total_tokens'] is None and result['input_tokens'] is None
    assert result['unknown_calls'] == 1 and result['calls'] == 2
    assert result['http_seconds'] == 7
