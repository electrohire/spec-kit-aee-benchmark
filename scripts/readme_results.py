"""Render the prominent historical table from committed measured artifacts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- historical-results:start -->"
END = "<!-- historical-results:end -->"
CURRENT_START="<!-- current-results:start -->"
CURRENT_END="<!-- current-results:end -->"


def current_table(report,audit=None):
    text="\n\n### Current-version staged comparison\n\n"
    text+="| Metric | Agent alone | Spec Kit (adapted) | Spec Kit + AEE (adapted) |\n|---|---:|---:|---:|\n"
    arms=("baseline","spec_kit","spec_kit_aee")
    values=[report["arms"][a] for a in arms]
    delivery=[report["delivered_projects"][a] for a in arms]
    claims=[report["completion_opportunities"][a] for a in arms]
    text+="| Final-stage projects delivered | "+" | ".join(f"{v['final_stage_accepted']}/{v['project_trajectories']}" for v in delivery)+" |\n"
    text+="| Hidden checkpoints accepted | "+" | ".join(f"{v['accepted_milestones']}/{v['scheduled_milestones']}" for v in values)+" |\n"
    text+="| Checkpoints without complete test inventory | "+" | ".join(str(v['ungraded_milestones']) for v in values)+" |\n"
    if audit:
        text+="| Completed milestone workflows | "+" | ".join(f"{audit['workflow_exposure'][a]['completed_workflows']}/12" for a in arms)+" |\n"
        text+="| Actual AEE assessments / planned | n/a | n/a | "+str(audit['aee_assessments'])+"/48 |\n"
    text+="| All scored tokens | "+" | ".join(f"{v['total_tokens']:,}" if v['total_tokens'] is not None else f"≥{v['known_tokens_lower_bound']:,} (incomplete)" for v in values)+" |\n"
    text+="| Unknown token calls | "+" | ".join(str(v['unknown_token_calls']) for v in values)+" |\n"
    text+="| Tokens per delivered project | "+" | ".join(f"{v['all_call_tokens_per_delivered_project']:,.0f}" if v['all_call_tokens_per_delivered_project'] is not None else "undefined/unknown" for v in delivery)+" |\n"
    text+="| False completion / graded positive declarations | "+" | ".join(f"{v['false_completion']}/{v['positive']-v['ungraded_positive']}" for v in claims)+" |\n"
    text+="| Unknown completion declarations | "+" | ".join(str(v['unknown']) for v in claims)+" |\n"
    text+="| Source-changing public repair rounds | "+" | ".join(str(v['source_changing_repairs']) for v in values)+" |\n\n"
    if audit:
        text+="**Treatment exposure:** neither structured arm completed a milestone workflow within the fixed 40-minute budgets. AEE was reached at only 6/48 planned checkpoints, all after specification. All 24 structured checkpoints failed test collection: 22 snapshots lack the implementation module; two contain a module that raises `NameError` during import. They remain **ungraded**, not completed failing test inventories. The small successful arithmetic calibration did not establish that full project workflows fit the milestone budget. All 52 public-repair records made zero model calls after their budgets ran out; there is no observed repair efficacy here. These are outcomes of attempted policies under these constraints, not a completed AEE workflow efficacy comparison. A false-completion rate of 0/0 is undefined, not zero hallucinations.\n\n"
    combined=report["delivered_projects"]["spec_kit_aee"]["final_stage_accepted"]
    baseline=report["delivered_projects"]["baseline"]["final_stage_accepted"]
    structured=report["delivered_projects"]["spec_kit"]["final_stage_accepted"]
    text+=f"**Insight:** the combined workflow delivered {combined} final-stage projects, versus {baseline} with the agent alone and {structured} with Spec Kit. Read this together with all-call tokens and false-completion denominators, rather than treating fewer tokens on failing work as savings.\n\n"
    text+="Two projects × two seeds × three arms, with three dependent milestones each; these are not 36 independent tasks or months of production history. False completion means an explicit positive completion declaration contradicted by independent grading of the exact snapshot. Missing declarations are unknown; a failed test alone is not a hallucination. AEE process findings are not independently labeled detections.\n\n"
    text+="**What it means:** this tests a narrow simulated maintenance/handoff workload and the measured overhead/quality tradeoff. It cannot establish general hallucination reduction, production lifetime savings or an AEE-only causal effect. All API bills were $0; hardware, energy and human work were unpriced. Hypothetical token prices are sensitivity scenarios, not actual savings.\n\n"
    text+="[Full results and paired outcomes](reports/local/current-study-01/README.md) · [Bound grades, completion recovery and cost details](reports/local/current-study-01/lifecycle-report.json) · [Every retained setup call](reports/local/current-study-01/setup-inventory.json) · [Frozen protocol](benchmarks/current_local/PROTOCOL.md)\n\n"
    return text


def table():
    rows = json.loads((ROOT/"reports/local/gpu-20260917/repair/summary.json").read_text())
    long = json.loads((ROOT/"reports/local/long-horizon-03/summary.json").read_text())
    text = "\n\n| Historical local run | Agent alone | Spec Kit (adapted) | Spec Kit + AEE (adapted) |\n|---|---:|---:|---:|\n"
    text += "| Six-task primary passes | " + " | ".join(f"{v['original_passed']}/{v['attempts']}" for v in rows) + " |\n"
    text += "| After same-test repairs | " + " | ".join(f"{v['final_passed']}/{v['attempts']}" for v in rows) + " |\n"
    text += "| Tokens including repairs | " + " | ".join(f"{v['cumulative_total_tokens']:,}" for v in rows) + " |\n"
    text += "| Tokens per repaired-suite pass | " + " | ".join(f"{v['cumulative_tokens_per_correct_answer']:,.2f}" for v in rows) + " |\n"
    arms = [long["arms"][a] for a in ("baseline", "spec_kit", "spec_kit_aee")]
    text += "| TinyDB hidden milestones accepted | " + " | ".join(f"{v['hidden_final_passes']}/3" for v in arms) + " |\n"
    text += "| TinyDB tokens, lower bound | " + " | ".join(f"≥{v['known_total_tokens']:,}" for v in arms) + " |\n"
    text += "| TinyDB unknown token calls | " + " | ".join(str(v['unknown_calls']) for v in arms) + " |\n\n"
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    path = ROOT/"README.md"
    text = path.read_text(encoding="utf-8")
    before, rest = text.split(START)
    _, after = rest.split(END)
    updated = before + START + table() + END + after
    before,rest=updated.split(CURRENT_START)
    _,after=rest.split(CURRENT_END)
    report=ROOT/"reports/local/current-study-01/lifecycle-report.json"
    audit=ROOT/"reports/local/current-study-01/post-run-audit.json"
    current=current_table(json.loads(report.read_text()),json.loads(audit.read_text()) if audit.exists() else None) if report.exists() else "\n\nFresh current-version comparative evidence is pending successful workflow calibration and the complete scored study. Focused machine validation is recorded separately; it is not an efficacy result.\n\n"
    updated=before+CURRENT_START+current+CURRENT_END+after
    if args.check:
        if updated != text:
            raise SystemExit("README results differ from measured artifacts")
        print("README results match committed measurements")
    else:
        path.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
