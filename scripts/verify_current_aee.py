"""Real latest-engine evidence verification; report machine/human lanes separately."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from benchmark_runner.store import write_json, utc

ROOT=Path(__file__).resolve().parents[1]
FILES=("test_lifecycle.py","test_local_provider.py","test_assessment_contract.py",
       "test_current_local.py","test_report_current.py","test_project_assessment.py",
       "test_current_report_audit.py")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT):raise ValueError("evidence must be inside this project")
    out.mkdir(parents=True,exist_ok=False)
    (out/"tests").mkdir();(out/"evaluator-results").mkdir()
    env={**os.environ,"PYTHONUTF8":"1","PATH":str(Path(sys.executable).parent)+os.pathsep+os.environ.get("PATH","")}
    command=[sys.executable,"-m","pytest","-v",*["tests/"+name for name in FILES],"--junitxml="+str(out/"tests/junit.xml")]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,env=env,timeout=90)
    (out/"tests/execution.log").write_bytes(result.stdout+result.stderr)
    cases=list(ET.parse(out/"tests/junit.xml").getroot().iter("testcase"))
    if result.returncode or not cases or any(c.find(tag) is not None for c in cases for tag in ("failure","error","skipped")):
        raise RuntimeError("machine contract tests did not all pass")
    log=out/"tests/execution.log";digest=hashlib.sha256(log.read_bytes()).hexdigest()
    claims=[]
    for i,name in enumerate(FILES,1):
        count=sum(name.removesuffix(".py") in c.attrib.get("classname","") for c in cases)
        if count==0:raise RuntimeError("expected test file was not collected")
        claims.append(dict(id=f"OBS-CURRENT-{i:03}",kind="observation",stage="checked",status="partially_supported",
            text=f"All {count} collected cases in {name} passed in this recorded local execution.",
            boundary=["Only this recorded local Python3.12.6 execution; not general correctness or workflow efficacy"],
            depends_on=[],conflicts_with=[],source_ref="tests/"+name,uncertainty="low",
            falsification_tests=["A case in the recorded JUnit file has a failure, error or skip; the process exit is nonzero."],
            stage_events=[dict(kind="checked",author="Codex automated test runner",date=utc(),basis=f"Actual pytest process exited0; execution artifact SHA256{digest}; no human acceptance asserted")],
            evidence=[dict(ref=log.relative_to(ROOT).as_posix(),kind="observed",direction="supports",
                source_quality="test",source_id="recorded-pytest-execution",content_hash=digest,observed_at=utc(),
                description="Actual process output; accompanying JUnit confirms all collected cases passed without skips.")]))
    write_json(out/"claims.json",dict(schema_version="1.0",claims=claims))
    command=[sys.executable,"-m","aee","assess","--input",str(out/"claims.json"),"--project-root",str(ROOT),
        "--project","benchmark-current-validation","--phase","after_implement","--verify-evidence",
        "--output",str(out/"assessment.json"),"--evaluator-output",str(out/"evaluator-results/aee-after_implement-current.json"),
        "--ledger",str(out/"ledger.jsonl"),"--actor","Codex automated test runner"]
    assessed=subprocess.run(command,cwd=ROOT,capture_output=True,env=env,timeout=60)
    (out/"assessment-command.log").write_bytes(assessed.stdout+assessed.stderr)
    if assessed.returncode not in (0,1):raise RuntimeError("actual AEE assessment failed")
    value=json.loads((out/"assessment.json").read_text())
    composer=ROOT/".specify/extensions/evaluator/scripts/python/compose_results.py"
    composed=subprocess.run([sys.executable,str(composer),"--results-dir",str(out/"evaluator-results"),
        "--phase","after_implement","--strategy","strict","--output",str(out/"composed.json")],
        cwd=ROOT,capture_output=True,env=env,timeout=60)
    if composed.returncode not in (0,1,2) or not (out/"composed.json").is_file():
        raise RuntimeError("actual evaluator composition failed")
    composition=json.loads((out/"composed.json").read_text())
    if composition["metadata"]["evaluator_count"]!=1 or composition["metadata"].get("no_results"):
        raise RuntimeError("evaluator did not consume the actual AEE result")
    lanes=value["lanes"]
    lane=lanes["lane_1"]
    evidence=value["metadata"]["evidence_verification"]
    summary=dict(tests=len(cases),test_exit=0,aee_exit=assessed.returncode,
        evaluator_count=composition["metadata"]["evaluator_count"],composition_exit=composed.returncode,
        machine_claims=len(claims),machine_claims_above_threshold=lane["claims_at_or_above_threshold"],
        machine_claims_below_threshold=lane["claims_below_threshold"],evidence_verification=evidence,
        human_acceptance=lanes["lane_2"],outcome=value["outcome"],
        limitation="Machine verification coverage, not100% confidence or human acceptance. No inference/effectiveness claim is established by these tests.")
    write_json(out/"summary.json",summary)
    if summary["machine_claims_below_threshold"] or evidence["findings"] or evidence["unresolvable_offline"]:
        raise RuntimeError("machine evidence validation is incomplete; inspect recorded findings")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
