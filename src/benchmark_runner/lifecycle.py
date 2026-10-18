"""Artifact-bound, descriptive lifecycle economics; never a truth certification.

Input contract and limitations: docs/lifecycle-protocol.md. Historical reports
are not retroactively assigned claim labels or measurements they did not record.
"""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .accounting import cost, money, unique_calls, validate_usage

ARMS = ("baseline", "spec_kit", "spec_kit_aee")


def artifact(root, ref):
    base = Path(root).resolve()
    path = (base / ref["path"]).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("artifact must be a file inside the evidence directory")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ValueError("artifact digest mismatch")
    return data


def _bool(value):
    if type(value) is not bool:
        raise ValueError("expected a boolean")
    return value


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def _grade(root, row):
    if row.get("grade") is None:
        return None
    grade = json.loads(artifact(root, row["grade"]))
    if (grade.get("grader_completed") is not True or type(grade.get("exit_code")) is not int
            or grade["exit_code"] not in (0, 1)):
        raise ValueError("incomplete grader cannot establish correctness")
    if grade.get("source_sha256") != row["source_sha256"]:
        raise ValueError("grade belongs to another source snapshot")
    if not grade.get("cases"):
        raise ValueError("empty grading is not acceptance")
    cases = {}
    for case in grade["cases"]:
        if case["id"] in cases or case.get("skipped", False):
            raise ValueError("duplicate or skipped grading case")
        cases[case["id"]] = _bool(case["passed"])
    expected = row["expected_case_ids"]
    if len(expected) != len(set(expected)) or set(expected) != set(cases):
        raise ValueError("grading discovery differs from frozen expected cases")
    if (grade["exit_code"] == 0) != all(cases.values()):
        raise ValueError("grader exit and case results disagree")
    return cases


def _truth(root, claim, cases, row):
    kind = claim["kind"]
    if kind == "completion":
        return all(cases.values()) if cases is not None else None
    if kind == "test_passed":
        return cases.get(claim["case_id"]) if cases is not None else None
    if kind == "evidence_exists":
        # A citation must be from this milestone's actual tool trace. A valid
        # file hash alone does not establish semantic support for its prose.
        ref = claim["evidence"]
        if ref not in row.get("tool_artifacts", []):
            return False
        artifact(root, ref)
        return True
    raise ValueError("unsupported claim kind; do not improvise a truth oracle")


def summarize(document, root):
    if document.get("schema") != "lifecycle-v1" or not document.get("campaign_id"):
        raise ValueError("expected a named lifecycle-v1 campaign")
    schedule = document["schedule"]
    expected = set()
    for slot in schedule:
        key = tuple(slot[k] for k in ("project", "seed", "arm", "stage"))
        if slot["arm"] not in ARMS or type(slot["stage"]) is not int or slot["stage"] < 1:
            raise ValueError("invalid schedule")
        if key in expected:
            raise ValueError("duplicate schedule slot")
        expected.add(key)
    for project, seed in {k[:2] for k in expected}:
        stages = [{k[3] for k in expected if k[:3] == (project, seed, arm)} for arm in ARMS]
        if not stages[0] or any(s != stages[0] for s in stages[1:]):
            raise ValueError("schedule must declare the same milestones for all three arms")
    rows, calls_seen = {}, set()
    prices = document.get("scenario_prices_per_million")
    if prices is not None:
        for key in ("input", "cached_input", "output"):
            money(prices[key])
    for row in document["milestones"]:
        key = tuple(row[k] for k in ("project", "seed", "arm", "stage"))
        if key not in expected or key in rows:
            raise ValueError("unscheduled or duplicate milestone")
        if "workflow_completed" in row:
            _bool(row["workflow_completed"])
        cases = _grade(root, row)
        for ref in row.get("tool_artifacts", []):
            artifact(root, ref)
        records = unique_calls(row["calls"])
        for call in records:
            identity = call.get("request_id") or call["call_id"]
            if identity in calls_seen:
                raise ValueError("physical call allocated to multiple milestones")
            calls_seen.add(identity)
            validate_usage(call)
            if call.get("api_cost_usd") is not None:
                money(call["api_cost_usd"])
        labels, ids = [], set()
        for claim in row["claims"]:
            if claim["id"] in ids:
                raise ValueError("duplicate claim")
            ids.add(claim["id"])
            flagged = claim.get("flagged")
            if flagged is not None:
                _bool(flagged)
            labels.append(dict(id=claim["id"], kind=claim["kind"],
                               supported=_truth(root, claim, cases, row), flagged=flagged))
        repairs = row["source_changing_repairs"]
        if type(repairs) is not int or repairs < 0:
            raise ValueError("invalid repair count")
        rows[key] = dict(row=row, cases=cases, calls=records, labels=labels)

    result = dict(schema="lifecycle-report-v1", campaign_id=document["campaign_id"],
                  scope=document["scope"], arms={}, paired_trajectories=[],
                  caution="Descriptive evidence, not causal proof or truth certification. "
                          "API spend excludes hardware, energy and human labor; scenarios are hypothetical.")
    for arm in ARMS:
        scheduled = [k for k in expected if k[2] == arm]
        selected = [rows[k] for k in sorted(rows) if k[2] == arm]
        calls = [c for item in selected for c in item["calls"]]
        labels = [c for item in selected for c in item["labels"]]
        known = [c for c in calls if c.get("input_tokens") is not None and c.get("output_tokens") is not None]
        tokens = sum(c["input_tokens"] + c["output_tokens"] for c in known)
        # Cached inputs and reasoning are subsets, never additional tokens.
        unknown = len(calls) - len(known)
        api_unknown = sum(c.get("api_cost_usd") is None for c in calls)
        accepted = sum(x["row"].get("workflow_completed", True) and x["cases"] is not None and all(x["cases"].values()) for x in selected)
        confusion = Counter()
        for claim in labels:
            if claim["supported"] is not None and claim["flagged"] is not None:
                confusion[(not claim["supported"], claim["flagged"])] += 1
        tp, fp = confusion[True, True], confusion[False, True]
        fn, tn = confusion[True, False], confusion[False, False]
        scenario = [cost(c, prices) for c in calls] if prices is not None else []
        regressions = []
        for key, item in rows.items():
            previous = rows.get((*key[:3], key[3] - 1))
            if key[2] == arm and previous and previous["cases"] is not None and item["cases"] is not None:
                regressions.extend(dict(project=key[0], seed=key[1], stage=key[3], case_id=cid)
                                   for cid, passed in item["cases"].items()
                                   if previous["cases"].get(cid) is True and not passed)
        complete = len(selected) == len(scheduled)
        measured_tokens = tokens if complete and not unknown else None
        api = sum((money(c["api_cost_usd"]) for c in calls if c.get("api_cost_usd") is not None), Decimal(0))
        result["arms"][arm] = dict(
            scheduled_milestones=len(scheduled), observed_milestones=len(selected),
            unobserved_milestones=len(scheduled)-len(selected), accepted_milestones=accepted,
            ungraded_milestones=sum(x["cases"] is None for x in selected),
            physical_calls=len(calls), failed_calls=sum(bool(c.get("error")) for c in calls),
            known_tokens_lower_bound=tokens, unknown_token_calls=unknown, total_tokens=measured_tokens,
            tokens_per_accepted_milestone=_rate(measured_tokens, accepted) if measured_tokens is not None else None,
            known_api_cost_usd=str(api), api_cost_usd=str(api) if complete and not api_unknown else None,
            unknown_api_cost_calls=api_unknown,
            scenario_cost_usd=str(sum(scenario, Decimal(0))) if complete and prices is not None and None not in scenario else None,
            source_changing_repairs=sum(x["row"]["source_changing_repairs"] for x in selected),
            regressions=regressions, claims=len(labels), unknown_truth_claims=sum(c["supported"] is None for c in labels),
            contradicted_claims=sum(c["supported"] is False for c in labels),
            false_completion_claims=sum(c["kind"] == "completion" and c["supported"] is False for c in labels),
            completion_scored_claims=sum(c["kind"] == "completion" and c["supported"] is not None for c in labels),
            truth_scored_claims=sum(c["supported"] is not None for c in labels),
            detector_scored_claims=tp+fp+fn+tn, detector=dict(tp=tp, fp=fp, fn=fn, tn=tn,
            precision=_rate(tp, tp+fp), recall=_rate(tp, tp+fn)),
            by_phase={phase:dict(calls=sum(c["phase"] == phase for c in calls),
                known_tokens_lower_bound=sum(c["input_tokens"]+c["output_tokens"] for c in known if c["phase"] == phase))
                for phase in sorted({c["phase"] for c in calls})})
    # Match whole trajectories, not pooled stage observations. Missing/ungraded
    # stages make trajectory success unknown, never a fabricated failure/pass.
    for project, seed in sorted({k[:2] for k in expected}):
        pair = dict(project=project, seed=seed, arms={})
        for arm in ARMS:
            keys = sorted(k for k in expected if k[:3] == (project, seed, arm))
            values = [rows.get(k) for k in keys]
            known_grades = bool(keys) and all(v is not None and v["cases"] is not None for v in values)
            pair["arms"][arm] = all(v["row"].get("workflow_completed", True) and all(v["cases"].values()) for v in values) if known_grades else None
        result["paired_trajectories"].append(pair)
    return result


def markdown(report):
    text = f"# {report['campaign_id']}\n\n{report['scope']}\n\n{report['caution']}\n\n"
    text += "| Arm | Accepted / scheduled milestones | Tokens (known lower bound) | Contradicted / truth-scored claims | False completion | Repairs | API USD | Scenario USD |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for arm, v in report["arms"].items():
        text += f"| {arm} | {v['accepted_milestones']}/{v['scheduled_milestones']} | {v['total_tokens'] if v['total_tokens'] is not None else 'unknown'} ({v['known_tokens_lower_bound']}) | {v['contradicted_claims']}/{v['truth_scored_claims']} | {v['false_completion_claims']} | {v['source_changing_repairs']} | {v['api_cost_usd']} | {v['scenario_cost_usd']} |\n"
    return text + "\nSee JSON for ungraded/missing milestones, unknown claim truth, detector denominators, regressions, phase costs and paired project outcomes.\n"
