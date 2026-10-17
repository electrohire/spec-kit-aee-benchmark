"""Audit real exported provenance and reject a falsely rebound grade."""
import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import audit_current_results as checker


def test_actual_report_keeps_collection_failures_ungraded():
    result=checker.audit(ROOT/"reports/local/current-study-01")
    assert result["schedule_records"]==36
    assert result["complete_grade_inventories"]==48
    assert len(result["collection_failures"])==96
    assert result["aee_assessments"]==result["single_result_compositions"]==6
    assert result["workflow_exposure"]["spec_kit_aee"]["assessment_phases"]==["specify"]
    assert all(v["repair_model_calls"]==0 for v in result["workflow_exposure"].values())


def test_audit_rejects_grade_bound_to_another_snapshot(monkeypatch):
    folder=ROOT/"reports/local/current-study-01"
    original=checker.read
    modified=copy.deepcopy(original(folder/"results.json"))
    modified[0]["hidden_final"]["source_sha256"]="0"*64
    monkeypatch.setattr(checker,"read",lambda p:modified if p==folder/"results.json" else original(p))
    with pytest.raises(ValueError,match="binding failed"):checker.audit(folder)
