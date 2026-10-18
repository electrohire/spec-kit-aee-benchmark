"""No inference: prove the runner intervenes and preserves a diagnostic."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import repeated_local as runner
from runtime_checks import RuntimeIntervention, RuntimeWatchdog, validate_capacity


def test_original_budget_cannot_admit_structured_campaign(tmp_path):
    with pytest.raises(ValueError, match='infeasible workflow budget'):
        runner.campaign(tmp_path/'run', tmp_path/'missing-preflight', 480)
    assert not (tmp_path/'run').exists()


def test_valid_capacity_reserves_every_phase_and_repairs():
    validate_capacity(4320, 480, list(range(7)), 2)
    with pytest.raises(ValueError): validate_capacity(4319, 480, list(range(7)), 2)


def test_expired_query_does_not_even_start_context_http_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.time, 'monotonic', lambda:100)
    monkeypatch.setattr(runner, 'local_json', lambda *a, **k:pytest.fail('no HTTP allowed'))
    provider=runner.Provider(tmp_path/'calls', 1, 480)
    with pytest.raises(TimeoutError, match='before_preflight'):
        provider.query([], 'implement', 1, 579)
    assert not provider.calls and not provider.preflights


def test_bad_actions_intervene_before_more_generation_and_preserve_source(tmp_path):
    class FakeProvider:
        calls = []
        def query(self, *args):
            self.calls.append({})
            return 'not a JSON action'
    provider = FakeProvider()
    session = runner.Session(None, provider, runner.Store(tmp_path/'store'), 'fixture')
    saved = []
    session.watchdog = RuntimeWatchdog(tmp_path/'run', capture=lambda:saved.append('snapshot'))
    with pytest.raises(RuntimeIntervention, match='consecutive'):
        session.phase('specify', 'fixture', 'requirements', 1, 20, 100)
    assert len(provider.calls) == 3 and saved == ['snapshot']
    alert = json.loads((tmp_path/'run/runtime-alert.json').read_text())
    assert alert['status'] == 'intervention_required' and alert['stage'] == 1


def test_deadline_stops_instead_of_recording_zero_call_repair(tmp_path, monkeypatch):
    import runtime_checks
    monkeypatch.setattr(runtime_checks.time, 'monotonic', lambda:100)
    guard = RuntimeWatchdog(tmp_path)
    with pytest.raises(RuntimeIntervention, match='capacity before phase'):
        guard.deadline(579, 480, 'repair', 2)


def test_repeated_tools_stop_even_when_exit_zero(tmp_path):
    guard = RuntimeWatchdog(tmp_path)
    for _ in range(2): guard.tool('ls', {'exit_code':0, 'stdout':'same'}, 'plan', 1)
    with pytest.raises(RuntimeIntervention, match='identical action'):
        guard.tool('ls', {'exit_code':0, 'stdout':'same'}, 'plan', 1)


def test_rolling_bad_action_rate_stops_even_without_three_consecutive_errors(tmp_path):
    guard = RuntimeWatchdog(tmp_path)
    for good in (False,False,True,False,False,True,False,True,False):
        guard.success() if good else guard.error(ValueError('fixture'), 'plan', 1)
    with pytest.raises(RuntimeIntervention, match='50 percent'):
        guard.error(ValueError('fixture'), 'plan', 1)


@pytest.mark.parametrize('error', [TimeoutError('fixture'), RuntimeError('ModelIdentityMismatch'),
                                   RuntimeError('server_not_idle'), RuntimeError('reserved_token_cap')])
def test_safety_errors_stop_immediately(tmp_path, error):
    with pytest.raises(RuntimeIntervention, match='safety/budget'):
        RuntimeWatchdog(tmp_path).error(error, 'implement', 3)


def test_coerced_completion_is_not_successful_runtime_handoff(tmp_path):
    with pytest.raises(RuntimeIntervention, match='phase did not complete'):
        RuntimeWatchdog(tmp_path).completed(dict(phase='specify', calls=32, completed=True,
            errors=['TerminalActionCoerced: fixture']), 1)


def test_snapshot_failure_does_not_suppress_alert(tmp_path):
    def broken(): raise OSError('fixture')
    with pytest.raises(RuntimeIntervention): RuntimeWatchdog(tmp_path, capture=broken).stop('fixture')
    assert 'snapshot_error' in json.loads((tmp_path/'runtime-alert.json').read_text())
