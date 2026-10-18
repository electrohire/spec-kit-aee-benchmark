"""Current-version free local calibration and staged study, with no service changes.

The historical runners and published freezes remain immutable. This adapter uses
their same task/phase/independent-grader protocol with an explicit router model.
"""
import argparse
import ast
import hashlib
import inspect
import importlib.metadata
import json
import random
import math
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import repeated_local as runner
from benchmark_runner.store import Store, canonical, utc, write_json
from benchmark_runner.workflow import assess, grounded_claims
from local_feasibility import NoRedirect
from long_horizon import PHASE_GOALS, skill
from context_window import select_context
from benchmark_runner.project_assessment import assess_project

_grade_impl = runner.grade

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.8-27b"
WEIGHTS = Path("C:/Models/qwen3.8-27b.gguf")
URL = "http://127.0.0.1:8081"
SEEDS = [20261016, 20261017]
CONFIG = {**runner.CONFIG, "seeds": SEEDS, "model": MODEL, "url": URL,
          "paid_calls_permitted": False, "physical_call_timeout": 180,
          "stage_seconds": 2400, "primary_calls": 160, "context": 32768,
          "max_output": 4096, "token_cap": 18000000,
          "claim_rubric": "Final explicit all-requirements completion declarations only; missing/ambiguous = unknown. Independently grade exact submitted snapshot. AEE findings are not truth labels.",
          "scenario_prices_per_million":{"input":"1","cached_input":"0.10","output":"4"},
          "scenario_note":"Illustrative USD/million token sensitivity calculation, not a provider quote, bill, GPU/energy/human cost or a claim that hosted inference has the same behavior."}
COMPLETION = ('In your final done JSON include completion_asserted: true only if you claim every active task requirement is implemented; false if you know work remains; null if uncertain. This is your declaration, not a claim that hidden acceptance was run. Never claim tests were run when they were not. Include this field even if your summary is short.')


def http(route, payload=None, timeout=120):
    if payload is not None:
        payload["model"] = MODEL
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = URL+route
    if payload is None:
        url += "?"+urllib.parse.urlencode({"model":MODEL})
    request = urllib.request.Request(url, canonical(payload) if payload is not None else None,
                                     {"Content-Type":"application/json"})
    with opener.open(request, timeout=timeout) as handle:
        return json.loads(handle.read())


class Provider(runner.Provider):
    def query(self, messages, phase, stage, deadline):
        text = super().query(messages, phase, stage, deadline)
        record = self.calls[-1]
        if record["response"].get("model") != MODEL:
            record["error"] = "ModelIdentityMismatch"
            write_json(self.folder/f"call-{len(self.calls)-1:04}.json", record)
            raise RuntimeError("ModelIdentityMismatch")
        return text


def setup():
    runner.local_json = http
    runner.CONFIG = CONFIG
    runner.SEEDS = SEEDS
    runner.Provider = Provider
    runner.grade = bound_grade
    for project, meta in runner.PROJECTS.items():
        directory = ROOT/meta["upstream"]
        actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
        if actual != meta["revision"]:
            raise ValueError("upstream revision mismatch: "+project)
    actual = subprocess.check_output(["docker", "image", "inspect", runner.IMAGE, "--format", "{{.Id}}"], text=True).strip()
    if actual != runner.IMAGE:
        raise ValueError("sandbox image mismatch")


def bound_grade(project,snapshot,stage,public,expected=None):
    value=_grade_impl(project,snapshot,stage,public,expected)
    value["source_sha256"]=hashlib.sha256(Path(snapshot).read_bytes()).hexdigest() if snapshot else None
    value["grader_source_sha256"]=hashlib.sha256(runner.tests_for(project,stage,public)).hexdigest()
    value["grader_mode"]="public" if public else "hidden"
    value["grader_function_sha256"]=hashlib.sha256(ast.dump(ast.parse(inspect.getsource(_grade_impl)),include_attributes=False).encode()).hexdigest()
    return value


def freeze(out, purpose):
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for folder in ("src/benchmark_runner", "scripts", "benchmarks/repeated_local", "prompts", ".specify"):
        for path in (ROOT/folder).rglob("*"):
            if path.is_file() and not {"__pycache__", ".runtime", "assessments", "ledger", "results"}.intersection(path.parts):
                hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("uv.lock", "manifests/versions.json"):
        hashes[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    with WEIGHTS.open("rb") as handle:
        weight_sha = hashlib.file_digest(handle, "sha256").hexdigest()
    manifest = dict(schema="current-local-v1", created_at=utc(), purpose=purpose,
                    config=CONFIG, hashes=hashes, image=runner.IMAGE,
                    weights_sha256=weight_sha, projects=runner.PROJECTS,
                    models=http("/v1/models"), server_props=http("/props"),
                    hardware=subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], text=True))
    write_json(out/"freeze.json", manifest, exclusive=True)
    # Archive the exact treatment/controller source before any generation.
    archive_inputs(out,manifest)
    return manifest


def calibrate(out,latency_preflight):
    if latency_preflight is None:raise ValueError("run latency calibration first and provide --latency")
    measured=json.loads(latency_preflight.read_text())
    if measured.get("passed") is not True or measured.get("model")!=MODEL:
        raise ValueError("successful latency calibration for selected model required")
    CONFIG["physical_call_timeout"]=measured["timeout"]
    runner.assess=assess_project
    freeze(out, "unscored full-workflow and repair calibration")
    write_json(out/"latency-prerequisite.json",measured,exclusive=True)
    result = dict(passed=False, phases=[], assessments=[], calibration_only=True)
    provider = Provider(out/"calls", SEEDS[0], CONFIG["physical_call_timeout"])
    store = Store(out/"evidence")
    spec = "Unscored calibration. R01: create smoke.py with add(a,b) returning a+b. R02: support negative integers, zero and floats. R03: add and run tests. Do not modify TinyDB. Keep workflow artifacts concise under specs/001-transactions. No service or deployment is involved."
    try:
        with runner.ProjectSandbox("tinydb") as box:
            box.stage_workflow()
            session = runner.Session(box, provider, store, "current-calibration")
            deadline = time.monotonic()+7200
            for phase in ("constitution", "specify", "plan", "tasks", "implement", "converge", "final_implement"):
                goal = PHASE_GOALS[phase]
                instructions = (ROOT/"prompts/adapter.md").read_text().replace("/workflow", "/testbed")
                instructions += "\n"+skill(phase).replace("$ARGUMENTS",spec)+"\n"+goal
                instructions += "\nUse SPECIFY_FEATURE_DIRECTORY=/testbed/specs/001-transactions. Avoid unnecessary architecture for this arithmetic utility."
                need = phase in ("specify", "plan", "tasks", "implement")
                row = session.phase(phase, instructions, spec, 1, 32, deadline, need)
                result["phases"].append(row)
                write_json(out/"result.json", result)
                if not row["completed"]:
                    raise RuntimeError("incomplete_calibration_phase:"+phase)
                if need:
                    runner.do_assessment(session, result, phase, row["done"])
            before = box.execute("python -c 'from smoke import add; assert add(-2,3)==1; assert add(0,0)==0; assert add(1.5,2.5)==4.0'")
            result["before_repair"] = before
            if before["exit_code"]:
                raise RuntimeError("calibration implementation failed")
            box.put({"smoke.py":b"def add(a,b):\n    return a-b\n", "acceptance_public.py":b"from smoke import add\ndef test_sum():\n    assert add(2,3)==5\n"})
            feedback = box.execute("python -m pytest -q acceptance_public.py")
            if feedback["exit_code"] == 0:
                raise RuntimeError("injected defect was not detected")
            result["repair"] = session.phase("repair", "Repair the injected calibration regression using actual feedback: "+feedback["stdout"], spec, 1, 8, deadline)
            result["after_repair"] = box.execute("python -c 'from smoke import add; assert add(-2,3)==1; assert add(0,0)==0; assert add(1.5,2.5)==4.0'")
            result["passed"] = result["repair"]["completed"] and result["after_repair"]["exit_code"] == 0 and len(result["assessments"]) == 4
    except Exception as exc:
        result["error"] = type(exc).__name__+": "+str(exc)
    finally:
        result["physical_calls"] = len(provider.calls)
        write_json(out/"result.json", result)
    if not result["passed"]:
        raise RuntimeError("full workflow calibration did not pass; scored generation is blocked")


def context_calibration(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for n in (20, 40, 80):
        messages = [dict(role="system",content="Context selector calibration; no generation."),
                    dict(role="user",content="Preserve the fixed prefix.")]
        messages += [dict(role="user" if i%2==0 else "assistant", content="Neutral calibration words alpha beta gamma delta. "*128) for i in range(n)]
        def measure(items):
            prompt = http("/apply-template", dict(messages=items))["prompt"]
            return len(http("/tokenize",dict(content=prompt,add_special=False))["tokens"])
        linear = list(messages)
        counts = []
        while True:
            count = measure(linear)
            counts.append(count)
            if count+CONFIG["max_output"] <= CONFIG["context"]:
                break
            if len(linear) <= 3:
                raise ValueError("context prefix does not fit")
            del linear[2:4]
        if any(a < b for a,b in zip(counts,counts[1:])):
            raise ValueError("template is not monotone on calibration")
        chosen, tokens, removed = select_context(messages,measure,CONFIG["context"],CONFIG["max_output"])
        if chosen != linear or tokens != count:
            raise ValueError("binary and linear selectors differ")
        rows.append(dict(messages=len(messages),removed=removed,input_tokens=tokens,
                         fixture_sha256=hashlib.sha256(canonical(messages)).hexdigest(),identical_selection=True,
                         observed_monotone_counts=counts))
        write_json(out/"result.json",dict(passed=False,cases=rows))
    write_json(out/"result.json",dict(passed=True,model=MODEL,context=CONFIG["context"],max_output=CONFIG["max_output"],cases=rows,inference_calls=0,
        selector_sha256=hashlib.sha256((ROOT/"scripts/context_window.py").read_bytes()).hexdigest()))


def latency(out):
    freeze(out,"unscored near-context latency: at most2calls,4096output tokens/call,600seconds/call,zero paid inference")
    filler = "Neutral calibration alpha beta gamma delta 0123456789.\n"*2500
    while len(http("/tokenize",dict(content=filler,add_special=False))["tokens"]) > 26000:
        filler = filler[:int(len(filler)*.94)]
    calls = []
    for i in range(2):
        request = dict(model=MODEL,messages=[dict(role="user",content=filler+"\nReturn a JSON list containing integers 1 through 10000; continue to the output limit.")],
                       max_tokens=4096,temperature=.6,seed=SEEDS[0],cache_prompt=False)
        start=time.monotonic()
        row=dict(started_at=utc(),request=request,usage=None,unknown_reason="pending")
        path=out/f"call-{i:04}.json";write_json(path,row,exclusive=True)
        try:
            response=http("/v1/chat/completions",request,600)
            row.update(response=response,usage=response.get("usage"),unknown_reason=None if response.get("usage") else "native_usage_missing")
        except Exception as exc:
            row.update(error=type(exc).__name__,unknown_reason="failed_request_not_imputed")
            raise
        finally:
            row.update(seconds=time.monotonic()-start,ended_at=utc())
            write_json(path,row)
        calls.append(row)
        if response.get("model") != MODEL or row["usage"] is None:
            raise ValueError("latency calibration identity/usage unavailable")
    timeout=max(180,min(600,math.ceil(2*max(r["seconds"] for r in calls)/30)*30))
    write_json(out/"calibration.json",dict(passed=True,model=MODEL,context=CONFIG["context"],max_output=CONFIG["max_output"],timeout=timeout,samples=2,
        records=[dict(seconds=r["seconds"],usage=r["usage"],response_model=r["response"]["model"],original_sha256=hashlib.sha256((out/f"call-{i:04}.json").read_bytes()).hexdigest()) for i,r in enumerate(calls)]))


def archive_inputs(out, manifest):
    for name,digest in manifest["hashes"].items():
        data=(ROOT/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError("source changed during freeze: "+name)
        target=out/"frozen-inputs"/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)


def _definitions(source, names):
    tree=ast.parse(source)
    return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names}


def _bindings(source,names):
    result={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in names:
                    result[target.id]=ast.dump(node.value,include_attributes=False)
    return result


def run(out, preflight):
    if preflight is None:raise ValueError("explicit preflight directory required")
    out=out.resolve()
    preflight=preflight.resolve()
    workflow=preflight/"workflow/result.json"
    if not json.loads(workflow.read_text())["passed"]:
        raise ValueError("full workflow calibration has not passed")
    workflow_freeze=json.loads((preflight/"workflow/freeze.json").read_text())
    calibrated=workflow_freeze["config"]
    for key in ("model","url","context","max_output","temperature","top_p","top_k"):
        if calibrated[key]!=CONFIG[key]:raise ValueError("model/config differs from successful workflow calibration")
    for path in (preflight/"context/result.json",preflight/"latency/calibration.json"):
        value=json.loads(path.read_text())
        if not value["passed"] or any(value.get(k)!=CONFIG[k] for k in ("model","context","max_output")):
            raise ValueError("context/latency calibration differs from selected model/config")
    old_lock=workflow_freeze["hashes"]["uv.lock"]
    new_lock=hashlib.sha256((ROOT/"uv.lock").read_bytes()).hexdigest()
    replay_file=preflight/"dependency-replay/result.json"
    # The scored adapter retains one actual project ledger per trajectory.
    # A deterministic replay also validates this adapter change when dependency
    # versions happen to be identical.
    replay=json.loads(replay_file.read_text())
    packages={d.metadata["Name"]:d.version for d in importlib.metadata.distributions()}
    expected_phases={"specify","plan","tasks","implement"}
    if (replay.get("passed") is not True or replay.get("old_lock_sha256")!=old_lock
            or replay.get("new_lock_sha256")!=new_lock or replay.get("packages")!=packages
            or replay.get("workflow_freeze_sha256")!=hashlib.sha256((preflight/"workflow/freeze.json").read_bytes()).hexdigest()
            or len(replay.get("checkpoints",[]))!=4
            or {r["phase"] for r in replay["checkpoints"]}!=expected_phases
            or not all(r["semantic_match"] for r in replay["checkpoints"])
            or replay.get("persistent_ledger_entries")!=[1,2,3,4]):
        raise ValueError("updated dependencies/project adapter lack a matching successful deterministic replay")
    image_audit=preflight/"image-audit.json"
    image=json.loads(image_audit.read_text())
    if image.get("passed") is not True or image["image"]!=runner.IMAGE or any(image["paths"].values()) or image["forbidden_env_names"]:
        raise ValueError("immutable base image isolation audit failed")
    frozen=preflight/"workflow/frozen-inputs"
    # Launcher/report additions do not invalidate measured core calibration;
    # compare the exact ASTs of every shared treatment/provider component.
    for filename,names in {
        "scripts/current_local.py":{"http","Provider","calibrate"},
        "scripts/repeated_local.py":{"Provider","Session","do_assessment","compact_assessment","tests_for","ProjectSandbox"},
        "scripts/long_horizon.py":{"Sandbox","skill"},
        "scripts/local_feasibility.py":{"NoRedirect"},
        "src/benchmark_runner/workflow.py":{"assess","grounded_claims"},
        "src/benchmark_runner/project_assessment.py":{"assess_project"},
    }.items():
        before=_definitions((frozen/filename).read_text(encoding="utf-8"),names)
        after=_definitions((ROOT/filename).read_text(encoding="utf-8"),names)
        if set(before)!=names or before!=after:
            raise ValueError("calibrated treatment changed: "+filename)
    for filename,names in {
        "scripts/current_local.py":{"MODEL","WEIGHTS","URL","SEEDS","CONFIG"},
        "scripts/long_horizon.py":{"CLAIMS","PHASE_GOALS"},
        "scripts/repeated_local.py":{"COMMON"},
    }.items():
        before=_bindings((frozen/filename).read_text(encoding="utf-8"),names)
        if set(before)!=names or before!=_bindings((ROOT/filename).read_text(encoding="utf-8"),names):
            raise ValueError("calibrated model/treatment constants changed: "+filename)
    gold=json.loads((preflight/"grade/calibration.json").read_text())
    if gold.get("passed") is not True or set(gold["projects"])!=set(runner.PROJECTS):
        raise ValueError("independent grader inventory differs from scheduled projects")
    grader_hash=hashlib.sha256(ast.dump(ast.parse(inspect.getsource(_grade_impl)),include_attributes=False).encode()).hexdigest()
    for project,value in gold["projects"].items():
        expected_keys={f"{stage}-{mode}" for stage in (1,2,3) for mode in ("public","hidden")}
        if set(value["reference"])!=expected_keys or value["untouched"]["passed"] is not False:
            raise ValueError("independent grader controls incomplete")
        for key,grade in value["reference"].items():
            stage,mode=key.split("-")
            if grade.get("passed") is not True or not grade["cases"] or grade.get("grader_function_sha256") != grader_hash or grade["grader_source_sha256"] != hashlib.sha256(runner.tests_for(project,int(stage),mode=="public")).hexdigest():
                raise ValueError("calibrated independent grader changed")
    assets=preflight/"assets";assets.mkdir(exist_ok=False)
    calibration=json.loads((preflight/"workflow/freeze.json").read_text())
    write_json(assets/"hardware.json",dict(gpus=calibration["hardware"]))
    write_json(assets/"server-launch.json",dict(model=MODEL,url=URL,weights_sha256=calibration["weights_sha256"],server_props=calibration["server_props"],shared_service_modified=False))
    write_json(assets/"package-versions.json",{n:importlib.metadata.version(n) for n in ("applied-epistemic-engineering","specify-cli","mini-swe-agent","jsonschema")})
    timeout=json.loads((preflight/"latency/calibration.json").read_text())["timeout"]
    CONFIG["physical_call_timeout"]=timeout
    CONFIG["completion_contract"]=COMPLETION
    CONFIG["persistent_project_ledger"]=True
    CONFIG["block_on_assessment"]=True
    runner.assess=assess_project
    extras=[Path(__file__).resolve(),ROOT/"scripts/local_feasibility.py",ROOT/"scripts/report_current.py",ROOT/"scripts/report_repeated.py",ROOT/"scripts/complete_current_study.py",ROOT/"benchmarks/current_local/PROTOCOL.md"]
    extras.extend((replay_file,ROOT/"scripts/replay_current_dependencies.py"))
    extras.extend((image_audit,ROOT/"scripts/audit_current_image.py"))
    runner.campaign(out,preflight/"grade",timeout,
        workflow_preflight=workflow,latency_preflight=preflight/"latency/calibration.json",
        context_preflight=preflight/"context/result.json",assets=assets,
        extra_sources=tuple(extras),
        completion_contract=COMPLETION,freeze_hook=archive_inputs,block_on_assessment=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("grade-calibration", "workflow-calibration", "context-calibration", "latency", "run"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--preflight",type=Path)
    parser.add_argument("--latency",type=Path)
    args = parser.parse_args()
    setup()
    if args.command == "grade-calibration":
        runner.calibrate(args.output)
    elif args.command == "workflow-calibration":
        calibrate(args.output,args.latency)
    elif args.command == "context-calibration":
        context_calibration(args.output)
    elif args.command == "latency":
        latency(args.output)
    else:
        run(args.output,args.preflight)


if __name__ == "__main__":
    main()
