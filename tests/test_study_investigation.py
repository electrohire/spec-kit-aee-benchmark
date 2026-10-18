"""Regression checks for a functional calibration mistaken for budget fitness."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from current_local import validate_workflow_budget
from investigate_current_study import investigate


def test_recorded_study_never_exercised_structured_implementation():
    value = investigate(ROOT/'reports/local/current-study-01')
    assert not value['calibration']['fits_scored_budget']
    assert value['calibration']['controller_allowed_seconds'] == 7200
    for arm in ('spec_kit', 'spec_kit_aee'):
        assert value['arms'][arm]['phases']['implement']['calls'] == 0
        assert value['arms'][arm]['phases']['final_implement']['calls'] == 0
        assert value['arms'][arm]['repair_calls'] == 0


def test_historical_functional_success_is_rejected_as_budget_calibration():
    with pytest.raises(ValueError, match='exceeds scored stage budget'):
        validate_workflow_budget(ROOT/'reports/local/current-study-01/setup-evidence/current-workflow-calibration-04', 2400)


def test_budget_gate_requires_explicit_matching_cap_and_exercised_repair(tmp_path):
    (tmp_path/'calls').mkdir()
    (tmp_path/'calls/call-0000.json').write_text(json.dumps(dict(
        started_at='2026-10-18T00:00:00+00:00', ended_at='2026-10-18T00:01:00+00:00')))
    def result(**kwargs):
        (tmp_path/'result.json').write_text(json.dumps(dict(passed=True, **kwargs)))
    result(allowed_seconds=7200, repair=dict(calls=1))
    with pytest.raises(ValueError, match='matching explicit'): validate_workflow_budget(tmp_path, 2400)
    result(allowed_seconds=2400, repair=dict(calls=0))
    with pytest.raises(ValueError, match='exercised repair'): validate_workflow_budget(tmp_path, 2400)
    result(allowed_seconds=2400, repair=dict(calls=1))
    assert validate_workflow_budget(tmp_path, 2400) == 60
