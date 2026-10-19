"""Bound postmortem integrity and conservative eligibility, not efficacy tests."""
import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_stopped_postmortem as checker
from readme_results import stopped_table

FOLDER=ROOT/'reports/local/current-study-02-stopped-postmortem'


def test_actual_stopped_export_keeps_missing_inventory_ungraded():
    result=checker.audit(FOLDER)
    assert result['schedule_rows']==36 and result['grade_invocations']==4
    assert result['complete_inventories']==1 and result['hidden_test_failures']==1
    assert result['proxy_denominators']==dict(positive=0,negative=0,unknown_graded=1,ungraded=35)
    assert result['actual_scored_AEE_assessments']==0


def test_generated_readme_keeps_unknown_rates_and_exposure_visible():
    text=stopped_table(checker.read(FOLDER/'summary.json'))
    assert 'False-completion rate is undefined' in text
    assert 'unknown with complete inventory 1, ungraded 35' in text
    assert 'Actual scored AEE assessments: **0**' in text


def test_rebound_grade_is_refused(monkeypatch):
    original=checker.read
    target=FOLDER/'grade-tinydb-20261019-spec_kit-stage1-hidden.json'
    value=copy.deepcopy(original(target));value['source_sha256']='0'*64
    monkeypatch.setattr(checker,'read',lambda p:value if p==target else original(p))
    with pytest.raises(ValueError,match='snapshot binding'):
        checker.audit(FOLDER)


def test_collection_failure_cannot_be_promoted_to_complete_inventory(monkeypatch):
    original=checker.read
    summary=copy.deepcopy(original(FOLDER/'summary.json'))
    row=next(r for r in summary['rows'] if r['grade_invocations_available'] and r['project']=='cachetools')
    row['complete_test_inventory']=row['proxy_eligible']=True
    monkeypatch.setattr(checker,'read',lambda p:summary if p.name=='summary.json' else summary['rows'] if p.name=='checkpoint-rows.json' else original(p))
    with pytest.raises(ValueError,match='proxy inventory eligibility'):
        checker.audit(FOLDER)


def test_missing_scheduled_row_is_refused(monkeypatch):
    original=checker.read
    summary=copy.deepcopy(original(FOLDER/'summary.json'));summary['rows'].pop()
    monkeypatch.setattr(checker,'read',lambda p:summary if p.name=='summary.json' else summary['rows'] if p.name=='checkpoint-rows.json' else original(p))
    with pytest.raises(ValueError,match='scheduled inventory'):
        checker.audit(FOLDER)


def test_snapshot_reference_cannot_escape_report(monkeypatch):
    original=checker.read
    summary=copy.deepcopy(original(FOLDER/'summary.json'))
    row=next(r for r in summary['rows'] if r['grade_invocations_available'])
    row['published_snapshot']=str((ROOT/'README.md').resolve())
    monkeypatch.setattr(checker,'read',lambda p:summary if p.name=='summary.json' else summary['rows'] if p.name=='checkpoint-rows.json' else original(p))
    with pytest.raises(ValueError,match='confined evidence path'):
        checker.audit(FOLDER)


def test_public_pass_cannot_hide_its_failed_hidden_grade(monkeypatch):
    original=checker.read
    summary=copy.deepcopy(original(FOLDER/'summary.json'))
    row=next(r for r in summary['rows'] if r['grade_invocations_available'] and r['project']=='tinydb')
    del row['grades']['hidden']
    monkeypatch.setattr(checker,'read',lambda p:summary if p.name=='summary.json' else summary['rows'] if p.name=='checkpoint-rows.json' else original(p))
    with pytest.raises(ValueError,match='public and hidden grades required'):
        checker.audit(FOLDER)


@pytest.mark.parametrize('field,value,message',[
    ('scored_actual_AEE_assessments',4,'actual scored AEE exposure'),
    ('known_total_tokens',4172225,'native usage sum'),
    ('false_completion_rate',0,'unmeasured performance'),
])
def test_invented_exposure_usage_or_performance_is_refused(monkeypatch,field,value,message):
    original=checker.read
    summary=copy.deepcopy(original(FOLDER/'summary.json'));summary[field]=value
    monkeypatch.setattr(checker,'read',lambda p:summary if p.name=='summary.json' else original(p))
    with pytest.raises(ValueError,match=message):
        checker.audit(FOLDER)
