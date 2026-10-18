"""Synthetic accounting/oracle fixtures, never empirical benchmark results."""
import copy
import hashlib
import json

import pytest

from benchmark_runner.lifecycle import ARMS, summarize
from benchmark_runner.cli import main


def put(root, name, data):
    raw = json.dumps(data).encode()
    (root/name).write_bytes(raw)
    return dict(path=name, sha256=hashlib.sha256(raw).hexdigest())


def campaign(root):
    rows = []
    for arm in ARMS:
        for stage in (1, 2):
            grade = put(root, f"{arm}-{stage}.json", dict(grader_completed=True,
                exit_code=0 if stage == 1 else 1, source_sha256="snapshot",
                cases=[dict(id="retained", passed=stage == 1)]))
            rows.append(dict(project="p", seed=1, arm=arm, stage=stage,
                source_sha256="snapshot", grade=grade, expected_case_ids=["retained"], source_changing_repairs=1,
                calls=[dict(call_id=f"{arm}-{stage}", phase="repair", input_tokens=100,
                    cached_input_tokens=50, output_tokens=20, reasoning_tokens=10,
                    api_cost_usd="0")], claims=[dict(id="done", kind="completion", flagged=False)]))
    return dict(schema="lifecycle-v1", campaign_id="synthetic-test", scope="synthetic fixtures",
        schedule=[{k:r[k] for k in ("project", "seed", "arm", "stage")} for r in rows],
        milestones=rows, scenario_prices_per_million=dict(input="2", cached_input="1", output="4"))


def test_all_calls_regressions_and_false_completion(tmp_path):
    report = summarize(campaign(tmp_path), tmp_path)
    for arm in ARMS:
        value = report["arms"][arm]
        assert value["total_tokens"] == 240  # no cached/reasoning double count
        assert value["scenario_cost_usd"] == "0.00046"
        assert value["api_cost_usd"] == "0"
        assert value["false_completion_claims"] == 1
        assert value["detector"] == dict(tp=0, fp=0, fn=1, tn=1, precision=None, recall=0)
        assert len(value["regressions"]) == 1
        assert value["tokens_per_accepted_milestone"] == 240
    assert report["paired_trajectories"][0]["arms"] == dict.fromkeys(ARMS, False)


def test_failed_and_unknown_calls_not_free_or_complete(tmp_path):
    doc = campaign(tmp_path)
    call = doc["milestones"][0]["calls"][0]
    call.update(input_tokens=None, output_tokens=None, cached_input_tokens=None,
                reasoning_tokens=None, api_cost_usd=None, unknown_reason="timeout", error="timeout")
    v = summarize(doc, tmp_path)["arms"]["baseline"]
    assert v["failed_calls"] == v["unknown_token_calls"] == 1
    assert v["total_tokens"] is v["api_cost_usd"] is v["scenario_cost_usd"] is None
    assert v["known_tokens_lower_bound"] == 120


def test_unobserved_schedule_not_silently_dropped(tmp_path):
    doc = campaign(tmp_path)
    doc["milestones"].pop(0)
    report = summarize(doc, tmp_path)
    assert report["arms"]["baseline"]["unobserved_milestones"] == 1
    assert report["arms"]["baseline"]["total_tokens"] is None
    assert report["paired_trajectories"][0]["arms"]["baseline"] is None


def test_ungraded_claim_truth_and_unscored_detector(tmp_path):
    doc = campaign(tmp_path)
    doc["milestones"][0]["grade"] = None
    doc["milestones"][1]["claims"][0]["flagged"] = None
    v = summarize(doc, tmp_path)["arms"]["baseline"]
    assert v["unknown_truth_claims"] == 1
    assert v["detector_scored_claims"] == 0
    assert v["detector"]["recall"] is None


def test_fabricated_citation_and_wrong_attempt(tmp_path):
    doc = campaign(tmp_path)
    ref = put(tmp_path, "tool.json", {"stdout":"test passed"})
    row = doc["milestones"][0]
    row["claims"] = [dict(id="fake", kind="evidence_exists", evidence=ref, flagged=True)]
    assert summarize(doc, tmp_path)["arms"]["baseline"]["contradicted_claims"] == 2
    row["tool_artifacts"] = [ref]
    assert summarize(doc, tmp_path)["arms"]["baseline"]["contradicted_claims"] == 1


@pytest.mark.parametrize("mutation", ["tamper", "traversal", "snapshot", "skipped", "empty", "duplicate", "call", "negative", "discovery"])
def test_rejects_invalid_evidence(tmp_path, mutation):
    doc = campaign(tmp_path)
    row = doc["milestones"][0]
    ref = row["grade"]
    if mutation == "tamper":
        (tmp_path/ref["path"]).write_text("{}")
    elif mutation == "traversal":
        ref["path"] = "../outside.json"
    elif mutation == "snapshot":
        row["source_sha256"] = "other"
    elif mutation in ("skipped", "empty"):
        grade = json.loads((tmp_path/ref["path"]).read_text())
        if mutation == "skipped": grade["cases"][0]["skipped"] = True
        else: grade["cases"] = []
        row["grade"] = put(tmp_path, ref["path"], grade)
    elif mutation == "duplicate":
        doc["milestones"].append(copy.deepcopy(row))
    elif mutation == "call":
        doc["milestones"][1]["calls"] = copy.deepcopy(row["calls"])
    elif mutation == "discovery":
        row["expected_case_ids"].append("omitted-failing-case")
    else:
        row["calls"][0]["output_tokens"] = -1
    with pytest.raises(ValueError):
        summarize(doc, tmp_path)


def test_cli_writes_report_without_replacing_evidence(tmp_path):
    doc = campaign(tmp_path)
    source = tmp_path/"campaign.json"
    source.write_text(json.dumps(doc))
    assert main(["lifecycle-report", str(source), str(tmp_path/"report.json")]) == 0
    assert "synthetic fixtures" in (tmp_path/"report.md").read_text()
    assert json.loads(source.read_text()) == doc
    assert main(["lifecycle-report", str(source), str(tmp_path/"report.json")]) == 2


def test_unmatched_schedule_rejected(tmp_path):
    doc = campaign(tmp_path)
    doc["schedule"].pop()
    with pytest.raises(ValueError, match="same milestones"):
        summarize(doc, tmp_path)


def test_cli_cannot_overwrite_markdown_or_input(tmp_path):
    source = tmp_path/"campaign.json"
    source.write_text(json.dumps(campaign(tmp_path)))
    (tmp_path/"report.md").write_text("existing evidence")
    assert main(["lifecycle-report", str(source), str(tmp_path/"report.json")]) == 2
    assert not (tmp_path/"report.json").exists()
    assert (tmp_path/"report.md").read_text() == "existing evidence"
