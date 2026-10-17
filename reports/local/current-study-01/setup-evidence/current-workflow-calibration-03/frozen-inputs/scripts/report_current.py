"""Export current measured lifecycle evidence with explicit completion-claim stats."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmark_runner.lifecycle import summarize, markdown
from benchmark_runner.store import write_json
from report_repeated import export, summarize_study, manifest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_ids(grade):
    counts={}
    result=[]
    for case in grade["cases"]:
        stem=f"{case.get('file','')}::{case['name']}"
        counts[stem]=counts.get(stem,0)+1
        result.append(f"{stem}::{counts[stem]}")
    return result


def build(raw, dest):
    freeze=json.loads((raw/"freeze.json").read_text())
    rows=json.loads((raw/"results.json").read_text())
    schedule=[dict(project=p,seed=s,arm=a,stage=stage) for p,s,a in freeze["schedule"] for stage in (1,2,3)]
    if len(rows)!=len(schedule) or len({(r['project'],r['seed'],r['arm'],r['stage']) for r in rows})!=len(schedule):
        raise ValueError("not every scheduled milestone has a unique final record")
    projects=len({s['project'] for s in schedule});seeds=len({s['seed'] for s in schedule})
    doc=dict(schema="lifecycle-v1",campaign_id=raw.name,scope=f"{projects} convenience-selected projects × {seeds} seeds × three arms; {len(schedule)} dependent checkpoints. Not a production lifetime or causal superiority claim.",schedule=schedule,milestones=[])
    opportunities={arm:dict(positive=0,negative=0,unknown=0,false_completion=0,ungraded_positive=0) for arm in ("baseline","spec_kit","spec_kit_aee")}
    for row in rows:
        grade=row["hidden_final"]
        source=raw/row["final_snapshot"]
        if grade.get("source_sha256")!=sha(source):
            raise ValueError("independent grade belongs to another source snapshot")
        project,seed,arm,stage=(row[k] for k in ("project","seed","arm","stage"))
        reference=freeze["calibration"]["projects"][project]["reference"][f"{stage}-hidden"]
        expected_ids=case_ids(reference)
        ids=case_ids(grade)
        complete=(set(ids)==set(expected_ids) and len(ids)==len(expected_ids)
                  and grade["exit_code"] in (0,1) and not any(f["kind"]=="skipped" for c in grade["cases"] for f in c.get("failures",[])))
        if grade["grader_source_sha256"]!=reference["grader_source_sha256"]:
            raise ValueError("independent grading source differs from calibration")
        if complete and grade["passed"] != (grade["exit_code"]==0 and all(c["passed"] for c in grade["cases"])):
            raise ValueError("independent grading verdict disagrees with case results")
        grade_ref=None
        if complete:
            name=f"lifecycle-grades/{project}-{seed}-{arm}-{stage}.json"
            bound=dict(grader_completed=True,exit_code=grade["exit_code"],source_sha256=sha(source),
                       cases=[dict(id=cid,passed=c["passed"]) for cid,c in zip(ids,grade["cases"])])
            write_json(dest/name,bound)
            grade_ref=dict(path=name,sha256=sha(dest/name))
        declaration=row.get("completion_asserted")
        key="positive" if declaration is True else "negative" if declaration is False else "unknown"
        opportunities[arm][key]+=1
        claims=[]
        if declaration is True:
            claims=[dict(id="FINAL-COMPLETION",kind="completion",flagged=None)]
            if complete:
                opportunities[arm]["false_completion"]+=int(not grade["passed"])
            else:
                opportunities[arm]["ungraded_positive"]+=1
        calls=[]
        folder=raw/f"{project}-{seed}-{arm}"
        for path in sorted(folder.glob("call-*.json")):
            record=json.loads(path.read_text(encoding="utf-8-sig"))
            if record["stage"]!=stage:continue
            usage=record.get("usage") or {}
            if usage and usage.get("total_tokens") is not None and usage["total_tokens"]!=usage["prompt_tokens"]+usage["completion_tokens"]:
                raise ValueError("native token total disagrees with input plus output")
            cached=(usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            reasoning=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            calls.append(dict(call_id=path.relative_to(raw).as_posix(),phase=record["phase"],
                input_tokens=usage.get("prompt_tokens"),output_tokens=usage.get("completion_tokens"),
                cached_input_tokens=cached,reasoning_tokens=reasoning,
                unknown_reason="native usage detail unavailable" if not usage or cached is None or reasoning is None else None,
                api_cost_usd="0",error=record.get("error")))
        doc["milestones"].append(dict(project=project,seed=seed,arm=arm,stage=stage,
            source_sha256=sha(source),expected_case_ids=expected_ids,grade=grade_ref,calls=calls,
            source_changing_repairs=sum(r["source_changed"] for r in row["repairs"]),claims=claims))
    write_json(dest/"lifecycle-evidence.json",doc)
    report=summarize(doc,dest)
    report["completion_opportunities"]=opportunities
    for value in opportunities.values():
        denominator=value["positive"]-value["ungraded_positive"]
        value["false_completion_rate"]=value["false_completion"]/denominator if denominator else None
    write_json(dest/"lifecycle-report.json",report)
    (dest/"lifecycle-report.md").write_text(markdown(report),encoding="utf-8")
    text="\n## Explicit completion claims and hallucination proxy\n\n| Arm | Positive / negative / unknown declarations | False completion / graded positive declarations | Rate |\n|---|---:|---:|---:|\n"
    for arm,value in opportunities.items():
        n=value['positive']-value['ungraded_positive']
        rate=f"{100*value['false_completion_rate']:.1f}%" if n else "undefined"
        text+=f"| {arm} | {value['positive']} / {value['negative']} / {value['unknown']} | {value['false_completion']}/{n} | {rate} |\n"
    text+="\nThis is a preregistered false-completion proxy, not a comprehensive hallucination rate. Unknown/missing declarations are not confident assertions. AEE findings are not independent truth labels; matching detector decisions were not collected for these final claims, so detector precision/recall remains unmeasured. See lifecycle-report.json for bound grading, unknowns and denominators.\n"
    with (dest/"README.md").open("a",encoding="utf-8") as handle:handle.write(text)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw",type=Path);parser.add_argument("dest",type=Path)
    args=parser.parse_args()
    export(args.raw,args.dest)
    summarize_study(args.raw,args.dest)
    build(args.raw,args.dest)
    manifest(args.dest)


if __name__=="__main__":
    main()
