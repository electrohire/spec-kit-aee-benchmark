"""Export current measured lifecycle evidence with explicit completion-claim stats."""
from benchmark_runner.markdown_presentation import format_markdown, write_markdown
import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from benchmark_runner.lifecycle import summarize, markdown
from benchmark_runner.store import write_json
from report_repeated import export, summarize_study, manifest, workflow_completed


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root,name):
    path=(root/name.replace('\\','/')).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("snapshot must remain inside the evidence directory")
    return path


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
    doc["scenario_prices_per_million"]=freeze["config"]["scenario_prices_per_million"]
    opportunities={arm:dict(positive=0,negative=0,unknown=0,false_completion=0,ungraded_positive=0) for arm in ("baseline","spec_kit","spec_kit_aee")}
    recovery={arm:dict(primary_false_completion=0,code_recovered=0,positive_withdrawn_but_code_fails=0,
                       final_declaration_unknown=0,ungraded_final=0,persisting_false_completion=0) for arm in opportunities}
    for row in rows:
        grade=row["hidden_final"]
        source=inside(raw,row["final_snapshot"])
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
        primary=row["hidden_primary"]
        primary_source=inside(raw,row["primary_snapshot"])
        if primary.get("source_sha256")!=sha(primary_source) or primary["grader_source_sha256"]!=reference["grader_source_sha256"]:
            raise ValueError("primary grade source binding differs")
        primary_ids=case_ids(primary)
        primary_complete=(set(primary_ids)==set(expected_ids) and len(primary_ids)==len(expected_ids)
                          and primary["exit_code"] in (0,1) and not any(f["kind"]=="skipped" for c in primary["cases"] for f in c.get("failures",[])))
        if primary_complete and primary["passed"] != (primary["exit_code"]==0 and all(c["passed"] for c in primary["cases"])):
            raise ValueError("primary grading verdict disagrees with case results")
        if row.get("primary_completion_asserted") is True and primary_complete and not primary["passed"]:
            value=recovery[arm];value["primary_false_completion"]+=1
            if not complete:value["ungraded_final"]+=1
            elif grade["passed"]:value["code_recovered"]+=1
            elif declaration is False:value["positive_withdrawn_but_code_fails"]+=1
            elif declaration is None:value["final_declaration_unknown"]+=1
            else:value["persisting_false_completion"]+=1
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
    if freeze.get("intervention_policy")=="model-outcomes-v1":
        for milestone,row in zip(doc["milestones"],rows):
            milestone["workflow_completed"]=workflow_completed(row)
            milestone["execution_status"]=row.get("status","completed")
    write_json(dest/"lifecycle-evidence.json",doc)
    report=summarize(doc,dest)
    report["completion_opportunities"]=opportunities
    report["completion_recovery"]=recovery
    report["aee_process"]={}
    for arm in opportunities:
        selected=[r for r in rows if r["arm"]==arm]
        assessments=[a for r in selected for a in r.get("assessments",[])]
        valid=[a for a in assessments if "error" not in a]
        findings=[f for a in valid for f in a["evaluation"].get("findings",[])]
        report["aee_process"][arm]=dict(
            assessment_invocations=len(assessments),assessment_errors=len(assessments)-len(valid),
            verdicts=dict(Counter(a["evaluation"]["outcome"] for a in valid)),
            findings_by_severity=dict(Counter(f.get("severity","unspecified") for f in findings)),
            evidence_rework_rounds=sum(p["phase"]=="evidence_rework" for r in selected for p in r.get("phases",[])),
            note="Process observations, not independently adjudicated hallucinations or code defects. No finding-to-final-claim detector join was measured.")
    report["scenario_note"]=freeze["config"]["scenario_note"]
    report["delivered_projects"]={}
    for arm,value in report["arms"].items():
        final_rows=[r for r in rows if r["arm"]==arm and r["stage"]==3]
        delivered=sum(r["hidden_final"]["passed"] and (workflow_completed(r) if freeze.get("intervention_policy")=="model-outcomes-v1" else True) for r in final_rows)
        report["delivered_projects"][arm]=dict(project_trajectories=len(final_rows),final_stage_accepted=delivered,
            all_call_tokens_per_delivered_project=value["total_tokens"]/delivered if delivered and value["total_tokens"] is not None else None,
            scenario_cost_per_delivered_project=str(Decimal(value["scenario_cost_usd"])/delivered) if delivered and value["scenario_cost_usd"] is not None else None,
            blocked_milestones=sum(bool(r.get("blocked_phase")) for r in rows if r["arm"]==arm))
    for value in opportunities.values():
        denominator=value["positive"]-value["ungraded_positive"]
        value["false_completion_rate"]=value["false_completion"]/denominator if denominator else None
    write_json(dest/"lifecycle-report.json",report)
    write_markdown(dest/"lifecycle-report.md", markdown(report))
    text="\n## Explicit completion claims and hallucination proxy\n\n| Arm | Positive / negative / unknown declarations | False completion / graded positive declarations | Rate |\n|---|---:|---:|---:|\n"
    for arm,value in opportunities.items():
        n=value['positive']-value['ungraded_positive']
        rate=f"{100*value['false_completion_rate']:.1f}%" if n else "undefined"
        text+=f"| {arm} | {value['positive']} / {value['negative']} / {value['unknown']} | {value['false_completion']}/{n} | {rate} |\n"
    text+="\nThis is a preregistered false-completion proxy, not a comprehensive hallucination rate. Unknown/missing declarations are not confident assertions. AEE findings are not independent truth labels; matching detector decisions were not collected for these final claims, so detector precision/recall remains unmeasured. See lifecycle-report.json for bound grading, unknowns and denominators.\n"
    text+="\nPrimary-to-final recovery counts distinguish independently repaired code from explicit withdrawal of a positive declaration while code still fails. Missing declarations are unknown, not evidence of self-correction. Public-feedback repairs are shared across arms; these counts do not isolate an AEE mechanism.\n"
    text+="\n## Recorded AEE management activity\n\n| Arm | Assessment invocations / errors | Verdict counts | Findings by severity | Evidence rework rounds |\n|---|---:|---|---|---:|\n"
    for arm,value in report["aee_process"].items():
        text+=f"| {arm} | {value['assessment_invocations']} / {value['assessment_errors']} | {value['verdicts']} | {value['findings_by_severity']} | {value['evidence_rework_rounds']} |\n"
    text+="\nThese are recorded management actions, not verified hallucination detections. Claim structure, evidence quality and human-acceptance findings must remain separate from independently graded behavioral defects.\n"
    text+="\nFinal-stage project delivery is separate from uninterrupted success at every checkpoint. Per-delivered-project costs include all scored calls on both delivered and failed trajectories. "+report["scenario_note"]+" Rates are recorded in lifecycle-evidence.json; no actual financial-saving conclusion follows from illustrative rates or unpriced labor/energy. Failing cases are not automatically unique bugs.\n"
    text+="\n## Delivery and token economics\n\n| Arm | Final-stage projects delivered | All scored tokens per delivered project | Illustrative USD per delivered project | Blocked milestones |\n|---|---:|---:|---:|---:|\n"
    for arm,value in report["delivered_projects"].items():
        tokens=value["all_call_tokens_per_delivered_project"]
        cost=value["scenario_cost_per_delivered_project"]
        text+=f"| {arm} | {value['final_stage_accepted']}/{value['project_trajectories']} | {tokens if tokens is not None else 'undefined/unknown'} | {cost if cost is not None else 'undefined/unknown'} | {value['blocked_milestones']} |\n"
    text+="\nZero delivered projects makes cost per delivery undefined, rather than zero. Compare quality and complete accounting before interpreting token differences; cumulative stages and repeated seeds are not independent production projects. No electricity, hardware depreciation or human rework cost was priced.\n"
    with (dest/"README.md").open("a",encoding="utf-8") as handle:handle.write(format_markdown(text))
    return report


def setup_names(folders):
    """Archive names only; never merge different runs that share a basename."""
    folders = list(dict.fromkeys(Path(p).resolve() for p in folders))
    counts = Counter(p.name for p in folders)
    labels = {p: p.name if counts[p.name] == 1 else p.parent.name+'--'+p.name for p in folders}
    collisions = Counter(labels.values())
    for p in folders:
        if collisions[labels[p]] > 1:
            labels[p] += '--'+hashlib.sha256(p.as_posix().encode()).hexdigest()[:12]
    if len(set(labels.values())) != len(labels):
        raise ValueError('setup archive names remain ambiguous')
    return list(labels.items())


def setup_inventory(folders,dest):
    """Count every retained unscored physical generation, once per actual call."""
    import copy
    seen={};models={};sources=[]
    for folder,label in setup_names(folders):
        if (folder/"freeze.json").is_file() and (folder/"frozen-inputs").is_dir():
            export(folder,dest/"setup-evidence"/label)
        paths=list(folder.rglob("call-*.json"))
        result=folder/"result.json"
        if result.is_file():
            record=json.loads(result.read_text())
            if record.get("physical_calls")==1 and "usage" in record:paths.append(result)
        frozen=json.loads((folder/"freeze.json").read_text()) if (folder/"freeze.json").exists() else {}
        fallback=frozen.get("model",frozen.get("config",{}).get("model","unidentified"))
        for path in sorted(paths):
            original=path.read_bytes();record=json.loads(original)
            response=record.get("response") or {}
            model=response.get("model") or (record.get("request")or{}).get("model") or record.get("response_model") or fallback
            identity=response.get("id") or hashlib.sha256(original).hexdigest()
            if identity in seen:
                if seen[identity]!=hashlib.sha256(original).hexdigest():raise ValueError("conflicting copies of a physical call")
                continue
            seen[identity]=hashlib.sha256(original).hexdigest()
            value=models.setdefault(model,dict(calls=0,known_input_tokens=0,known_output_tokens=0,
                known_tokens_lower_bound=0,unknown_token_calls=0,errors=0,api_spend_usd="0"))
            value["calls"]+=1;value["errors"]+=bool(record.get("error"))
            usage=record.get("usage") or {}
            i,o=usage.get("prompt_tokens"),usage.get("completion_tokens")
            if type(i) is int and type(o) is int and i>=0 and o>=0:
                if usage.get("total_tokens",i+o)!=i+o:raise ValueError("native setup token total disagrees")
                value["known_input_tokens"]+=i;value["known_output_tokens"]+=o;value["known_tokens_lower_bound"]+=i+o
            else:value["unknown_token_calls"]+=1
            public=copy.deepcopy(record)
            request=public.pop("request",None)
            if request is not None:public["request_sha256"]=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            for choice in public.get("response",{}).get("choices",[]):
                message=choice.get("message",{})
                for key in ("reasoning_content","reasoning"):
                    reasoning=message.pop(key,None)
                    if reasoning:message[key+"_sha256"]=hashlib.sha256(str(reasoning).encode()).hexdigest()
            public["original_sha256"]=hashlib.sha256(original).hexdigest()
            public["source"]=label+"/"+path.relative_to(folder).as_posix()
            target=dest/"setup-calls"/(public["original_sha256"]+".json")
            write_json(target,public)
        sources.append(label)
    for value in models.values():
        value["total_tokens"]=value["known_tokens_lower_bound"] if not value["unknown_token_calls"] else None
    summary=dict(scope="All retained unscored readiness, failed/successful workflow and latency calibration generation; not scored treatment denominators",sources=sources,by_model=models,
        physical_calls=len(seen),api_spend_usd="0",note="Hardware, power and human labor unpriced. Tokenizers/models differ; this physical inventory is not a pooled performance estimate. CPU tokenizer/template helper requests are separate from generation.")
    write_json(dest/"setup-inventory.json",summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw",type=Path);parser.add_argument("dest",type=Path)
    parser.add_argument("--setup",type=Path,action="append",default=[])
    args=parser.parse_args()
    export(args.raw,args.dest)
    summarize_study(args.raw,args.dest)
    build(args.raw,args.dest)
    inventory=setup_inventory(args.setup,args.dest)
    with (args.dest/"README.md").open("a",encoding="utf-8") as handle:
        handle.write(f"\n## Retained setup work\n\n{inventory['physical_calls']} unscored physical generation calls are retained in setup-inventory.json, grouped by actual model, with unknown usage explicit. They are not silently assigned to scored treatment denominators or discarded. API spend $0; hardware, energy and human work unpriced.\n")
    manifest(args.dest)


if __name__=="__main__":
    main()
