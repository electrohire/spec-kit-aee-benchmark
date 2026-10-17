"""Read-only audit of complete current-study grades, calls and AEE provenance."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

from aee.ledger import HashChainLedger
from benchmark_runner.lifecycle import summarize
from report_current import case_ids,inside


def read(path):return json.loads(path.read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(folder):
    freeze=read(folder/"freeze.json"); rows=read(folder/"results.json")
    expected={(p,s,a,n) for p,s,a in freeze["schedule"] for n in (1,2,3)}
    actual=[(r["project"],r["seed"],r["arm"],r["stage"]) for r in rows]
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError("incomplete or duplicated schedule")
    for name,record in read(folder/"frozen-input-map.json").items():
        if sha(inside(folder,record["file"]))!=freeze["hashes"][name]:raise ValueError("frozen input changed")
    grades=0;complete_grades=0;collection_failures=[]
    for row in rows:
        for kind in ("primary","final"):
            snapshot=inside(folder,row[kind+"_snapshot"]);source=sha(snapshot)
            module=freeze["projects"][row["project"]]["module"]
            with tarfile.open(snapshot) as archive:
                missing=module not in {m.name.removeprefix("./") for m in archive.getmembers() if m.isfile()}
            for mode in ("public","hidden"):
                value=row[mode+"_"+kind]
                gold=freeze["calibration"]["projects"][row["project"]]["reference"][f"{row['stage']}-{mode}"]
                ids=case_ids(value); expected_ids=case_ids(gold)
                if (value["source_sha256"]!=source or value["grader_source_sha256"]!=gold["grader_source_sha256"]
                    or value["grader_function_sha256"]!=gold["grader_function_sha256"]):
                    raise ValueError("grade/snapshot/inventory binding failed")
                complete=(len(ids)==len(expected_ids) and set(ids)==set(expected_ids) and value["exit_code"] in (0,1)
                    and not any(f["kind"]=="skipped" for c in value["cases"] for f in c.get("failures",[])))
                if complete:
                    if value["passed"]!=(value["exit_code"]==0 and all(c["passed"] for c in value["cases"])):
                        raise ValueError("grading verdict disagrees with cases")
                    complete_grades+=1
                elif (value["exit_code"]==2 and not value["passed"] and value["cases"]
                      and all(c.get("failures") and all(f["kind"]=="error" and f["message"]=="collection failure" for f in c["failures"]) for c in value["cases"])):
                    collection_failures.append(dict(project=row["project"],seed=row["seed"],arm=row["arm"],stage=row["stage"],
                        snapshot=kind,grader=mode,required_module=module,module_absent=missing,source_sha256=source,
                        error=value["cases"][0]["failures"][0]["text"],status="ungraded; pytest collection failed"))
                else:raise ValueError("unexplained incomplete grading; do not relabel it as completed")
                grades+=1
    document=read(folder/"lifecycle-evidence.json"); recorded=read(folder/"lifecycle-report.json")
    recomputed=summarize(document,folder)
    if any(recorded[key]!=value for key,value in recomputed.items()):raise ValueError("derived lifecycle totals differ")
    allocated={c["call_id"] for m in document["milestones"] for c in m["calls"]}
    paths=list(folder.glob("*/call-*.json"))
    if allocated!={p.relative_to(folder).as_posix() for p in paths}:raise ValueError("unallocated or invented native call")
    for milestone in document["milestones"]:
        for call in milestone["calls"]:
            native=read(inside(folder,call["call_id"]));usage=native.get("usage") or {}
            if (call["input_tokens"]!=usage.get("prompt_tokens") or call["output_tokens"]!=usage.get("completion_tokens")
                or call["cached_input_tokens"]!=(usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                or call["reasoning_tokens"]!=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                or call["error"]!=native.get("error") or call["phase"]!=native["phase"] or milestone["stage"]!=native["stage"]):
                raise ValueError("native usage/phase allocation differs")
            if "request" in native:raise ValueError("raw prompt exported")
            for choice in (native.get("response") or {}).get("choices",[]):
                if any(k in choice.get("message",{}) for k in ("reasoning_content","reasoning")):
                    raise ValueError("private native reasoning exported")
    ledgers=[]
    for path in folder.glob("*/aee-project/.specify/extensions/aee/ledger/epistemic-ledger.jsonl"):
        verification=HashChainLedger(path).verify(require_anchor=True)
        if not verification.valid:raise ValueError("AEE anchor/ledger verification failed")
        ledgers.append(dict(trajectory=path.relative_to(folder).parts[0],entries=verification.entries))
    composition=list(folder.glob("*/aee-project/composition/*/composed.json"))
    if any(read(p)["metadata"]["evaluator_count"]!=1 for p in composition):raise ValueError("composition did not consume one result")
    assessments=sum(len(r["assessments"]) for r in rows)
    if assessments!=sum(v["entries"] for v in ledgers) or assessments!=len(composition):raise ValueError("assessment provenance count differs")
    summary=read(folder/"summary.json")
    exposure={}
    for arm in recomputed["arms"]:
        selected=[r for r in rows if r["arm"]==arm]; repairs=[p for r in selected for p in r["repairs"]]
        exposure[arm]=dict(completed_workflows=summary["arms"][arm]["completed_milestone_workflows"],
            assessments=sum(len(r["assessments"]) for r in selected),
            assessment_phases=sorted({a["phase"] for r in selected for a in r["assessments"]}),
            repair_records=len(repairs),repair_model_calls=sum(p["calls"] for p in repairs),
            repairs_without_inference=sum(p["calls"]==0 for p in repairs))
    return dict(schedule_records=len(rows),bound_primary_final_grade_records=grades,complete_grade_inventories=complete_grades,
        collection_failures=collection_failures,physical_scored_calls=len(paths),
        frozen_input_files=len(freeze["hashes"]),aee_assessments=assessments,verified_ledgers=ledgers,
        single_result_compositions=len(composition),workflow_exposure=exposure,
        note="Post-run read-only audit; no inference, grader changes or relabeling. Test outcomes and AEE judgments remain separate.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("folder",type=Path)
    print(json.dumps(audit(parser.parse_args().folder),indent=2))
