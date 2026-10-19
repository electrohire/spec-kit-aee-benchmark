"""Actual extension execution with a persistent, isolated project per trajectory.

The older stateless adapter remains available for historical reproduction. Only
same-attempt hashed tool artifacts enter this project; grader data never does.
"""
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import jsonschema

from .store import canonical, read_json, sha, utc, write_json


def assess_project(root, claims, phase, store, attempt_id):
    if phase not in {"specify","plan","tasks","implement"}:raise ValueError("invalid assessment phase")
    if not isinstance(claims,dict) or not claims.get("claims"):
        raise ValueError("explicit nonempty claims required")
    project=store.root.parent/"aee-project"
    evaluator=project/".specify/extensions/evaluator"
    if not evaluator.exists():
        shutil.copytree(Path(root)/".specify/extensions/evaluator",evaluator,
                        ignore=shutil.ignore_patterns("__pycache__","*.pyc","results"))
    # Recompute bytes before copying. A model cannot turn an invented citation
    # into an observation or import artifacts from another trajectory.
    allowed={e["artifact"]["sha256"]:e["artifact"] for e in store.events("tools")
             if e.get("attempt_id")==attempt_id}
    for claim in claims["claims"]:
        for evidence in claim.get("evidence",[]):
            ref=allowed.get(evidence.get("source_id"))
            if not ref or evidence.get("ref")!=ref["path"]:
                if evidence.get("kind")=="observed":raise ValueError("observation lacks same-attempt tool provenance")
                continue
            source=(store.root/ref["path"]).resolve()
            if not source.is_relative_to(store.root.resolve()) or sha(source.read_bytes())!=ref["sha256"]:
                raise ValueError("tool artifact changed")
            target=project/ref["path"];target.parent.mkdir(parents=True,exist_ok=True)
            data=source.read_bytes()
            if target.exists() and target.read_bytes()!=data:raise ValueError("immutable project evidence changed")
            target.write_bytes(data)
    call=uuid.uuid4().hex
    input_path=project/"inputs"/(phase+"-"+call+".json")
    write_json(input_path,claims,exclusive=True)
    results=project/".specify/extensions/evaluator/results"
    before={p.name:sha(p.read_bytes()) for p in results.glob("*.json")}
    env={**os.environ,"PATH":str(Path(sys.executable).parent)+os.pathsep+os.environ.get("PATH",""),"PYTHONUTF8":"1"}
    command=[sys.executable,str(Path(root)/".specify/extensions/aee/scripts/python/run_aee.py"),
             "--project-root",str(project),"assess","--input",input_path.relative_to(project).as_posix(),
             "--project",attempt_id,"--phase","after_"+phase]
    run=subprocess.run(command,capture_output=True,env=env,timeout=60)
    changed=[p for p in results.glob("*.json") if before.get(p.name)!=sha(p.read_bytes())]
    candidates=[p for p in changed if read_json(p).get("evaluator",{}).get("id")=="aee"
                and read_json(p).get("phase")=="after_"+phase]
    if run.returncode not in (0,1) or len(candidates)!=1:
        ref=store.artifact(canonical(dict(phase=phase,exit_code=run.returncode,
            stdout=run.stdout.decode(errors="replace"),stderr=run.stderr.decode(errors="replace"))))
        store.append("assessment_errors",dict(attempt_id=attempt_id,phase=phase,artifact=ref,timestamp=utc()))
        raise RuntimeError("persistent AEE execution did not produce exactly one current result")
    # Compose only this invocation's result. Previous phases stay in the project
    # ledger/results but cannot be accidentally counted as additional evaluators.
    scope=project/"composition"/call;scope.mkdir(parents=True)
    shutil.copyfile(candidates[0],scope/candidates[0].name)
    output=scope/"composed.json"
    composed=subprocess.run([sys.executable,str(evaluator/"scripts/python/compose_results.py"),
        "--results-dir",str(scope),"--phase","after_"+phase,"--strategy","strict","--output",str(output)],
        capture_output=True,env=env,timeout=60)
    if composed.returncode not in (0,1,2) or not output.is_file():
        raise RuntimeError("persistent evaluator composition failed")
    value=read_json(output)
    value["metadata"]["reported_statuses"]={"aee":read_json(candidates[0]).get("metadata",{}).get("reported_statuses",{})}
    jsonschema.validate(value,read_json(evaluator/"schemas/evaluator-result.schema.json"))
    if value["metadata"]["evaluator_count"]!=1:raise RuntimeError("composition consumed wrong result count")
    ledger=project/".specify/extensions/aee/ledger/epistemic-ledger.jsonl"
    from aee.ledger import HashChainLedger
    verification=HashChainLedger(ledger).verify(require_anchor=True)
    if not verification.valid:raise RuntimeError("persistent AEE ledger/anchor failed verification")
    refs=[store.artifact(p.read_bytes()) for p in (input_path,candidates[0],output,ledger)]
    refs.append(store.artifact(canonical(value)))
    store.append("assessments",dict(attempt_id=attempt_id,phase=phase,timestamp=utc(),
        outcome=value["outcome"],aee_exit_code=run.returncode,ledger_entries=verification.entries,
        persistent_project=project.relative_to(store.root.parent).as_posix(),artifacts=refs))
    return value
