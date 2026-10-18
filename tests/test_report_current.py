"""Synthetic measured-trace shape tests; never empirical results."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from report_current import build,setup_inventory


def fixture(tmp_path):
    raw=tmp_path/"synthetic-fixture";raw.mkdir()
    dest=tmp_path/"report";dest.mkdir()
    (dest/"README.md").write_text("SYNTHETIC ONLY\n")
    arms=("baseline","spec_kit","spec_kit_aee")
    case=dict(file="suite",name="test_known",passed=True,failures=[])
    reference=dict(cases=[case],grader_source_sha256="grader")
    freeze=dict(config=dict(scenario_prices_per_million=dict(input="1",cached_input="0.1",output="4"),scenario_note="SYNTHETIC hypothetical rates"),schedule=[["p",1,a] for a in arms],calibration=dict(projects=dict(p=dict(reference={f"{stage}-hidden":reference for stage in (1,2,3)}))))
    (raw/"freeze.json").write_text(json.dumps(freeze))
    rows=[]
    for arm in arms:
        folder=raw/f"p-1-{arm}";folder.mkdir()
        for stage in (1,2,3):
            snap=folder/f"{stage}.tar";snap.write_bytes(b"SYNTHETIC SOURCE")
            grade=dict(cases=[dict(case,passed=stage==1)],source_sha256=hashlib.sha256(snap.read_bytes()).hexdigest(),
                       passed=stage==1,exit_code=0 if stage==1 else 1,grader_source_sha256="grader")
            rows.append(dict(project="p",seed=1,arm=arm,stage=stage,hidden_final=grade,
                hidden_primary=grade.copy(),primary_snapshot=snap.relative_to(raw).as_posix(),primary_completion_asserted=True,
                final_snapshot=snap.relative_to(raw).as_posix(),repairs=[],completion_asserted=True if stage!=3 else None))
            record=dict(stage=stage,phase="implement",usage=dict(prompt_tokens=100,completion_tokens=20,
                        total_tokens=120,prompt_tokens_details=dict(cached_tokens=0)))
            (folder/f"call-{stage:04}.json").write_text(json.dumps(record))
    (raw/"results.json").write_text(json.dumps(rows))
    return raw,dest,rows


def test_completion_denominators_and_measured_costs(tmp_path):
    raw,dest,_=fixture(tmp_path)
    result=build(raw,dest)
    for arm,value in result["completion_opportunities"].items():
        assert value==dict(positive=2,negative=0,unknown=1,false_completion=1,
                          ungraded_positive=0,false_completion_rate=.5)
        assert result["arms"][arm]["total_tokens"]==360
        assert result["arms"][arm]["detector_scored_claims"]==0
        assert result["completion_recovery"][arm]["primary_false_completion"]==2
        assert result["completion_recovery"][arm]["persisting_false_completion"]==1
        assert result["completion_recovery"][arm]["final_declaration_unknown"]==1
    assert "SYNTHETIC ONLY" in (dest/"README.md").read_text()
    assert "Delivery and token economics" in (dest/"README.md").read_text()
    assert result["aee_process"]["baseline"]["assessment_invocations"]==0
    for value in result["delivered_projects"].values():
        assert value["final_stage_accepted"]==0
        assert value["all_call_tokens_per_delivered_project"] is None
        assert value["scenario_cost_per_delivered_project"] is None
    from readme_results import current_table
    rendered=current_table(result)
    assert "0/1" in rendered and "1/2" in rendered
    assert "undefined/unknown" in rendered
    assert "cannot establish general hallucination reduction" in rendered


@pytest.mark.parametrize("kind",["missing-row","wrong-source","wrong-grader","wrong-verdict","wrong-primary-verdict"])
def test_incomplete_or_misattributed_evidence_rejected(tmp_path,kind):
    raw,dest,rows=fixture(tmp_path)
    if kind=="missing-row":rows.pop()
    elif kind=="wrong-source":rows[0]["hidden_final"]["source_sha256"]="other"
    elif kind=="wrong-grader":rows[0]["hidden_final"]["grader_source_sha256"]="other"
    elif kind=="wrong-verdict":rows[0]["hidden_final"]["passed"]=False
    else:rows[0]["hidden_primary"]["passed"]=False
    (raw/"results.json").write_text(json.dumps(rows))
    with pytest.raises(ValueError):build(raw,dest)


def test_setup_retains_unknown_failures_without_double_counting_copies(tmp_path):
    first=tmp_path/"first";first.mkdir();second=tmp_path/"second";second.mkdir()
    record=dict(response=dict(id="physical1",model="local"),usage=dict(prompt_tokens=15,completion_tokens=5,total_tokens=20))
    for folder in (first,second):(folder/"call-0000.json").write_text(json.dumps(record))
    (first/"freeze.json").write_text(json.dumps(dict(model="local")))
    (first/"result.json").write_text(json.dumps(dict(physical_calls=1,usage=None,error="TimeoutError")))
    report=setup_inventory([first,second],tmp_path/"out")
    assert report["physical_calls"]==2
    assert report["by_model"]["local"]["unknown_token_calls"]==1
    assert report["by_model"]["local"]["known_tokens_lower_bound"]==20
    assert report["by_model"]["local"]["total_tokens"] is None
