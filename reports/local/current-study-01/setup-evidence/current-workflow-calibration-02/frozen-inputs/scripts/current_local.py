"""Current-version free local calibration and staged study, with no service changes.

The historical runners and published freezes remain immutable. This adapter uses
their same task/phase/independent-grader protocol with an explicit router model.
"""
import argparse
import ast
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-oss-20b-Q5_K_M"
URL = "http://127.0.0.1:8081"
SEEDS = [20261016, 20261017]
CONFIG = {**runner.CONFIG, "seeds": SEEDS, "model": MODEL, "url": URL,
          "paid_calls_permitted": False, "physical_call_timeout": 180,
          "stage_seconds": 2400, "primary_calls": 160, "context": 32768,
          "max_output": 4096, "token_cap": 18000000,
          "claim_rubric": "Final explicit all-requirements completion declarations only; missing/ambiguous = unknown. Independently grade exact submitted snapshot. AEE findings are not truth labels."}
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
    for project, meta in runner.PROJECTS.items():
        directory = ROOT/meta["upstream"]
        actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
        if actual != meta["revision"]:
            raise ValueError("upstream revision mismatch: "+project)
    actual = subprocess.check_output(["docker", "image", "inspect", runner.IMAGE, "--format", "{{.Id}}"], text=True).strip()
    if actual != runner.IMAGE:
        raise ValueError("sandbox image mismatch")


def freeze(out, purpose):
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for folder in ("src/benchmark_runner", "scripts", "benchmarks/repeated_local", "prompts", ".specify"):
        for path in (ROOT/folder).rglob("*"):
            if path.is_file() and not {"__pycache__", ".runtime", "assessments", "ledger", "results"}.intersection(path.parts):
                hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("uv.lock", "manifests/versions.json"):
        hashes[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    weights = Path("C:/Models/gpt-oss-20b-Q5_K_M.gguf")
    with weights.open("rb") as handle:
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


def calibrate(out):
    freeze(out, "unscored full-workflow and repair calibration")
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
    write_json(out/"result.json",dict(passed=True,cases=rows,inference_calls=0,
        selector_sha256=hashlib.sha256((ROOT/"scripts/context_window.py").read_bytes()).hexdigest()))


def latency(out):
    out.mkdir(parents=True, exist_ok=False)
    filler = "Neutral calibration alpha beta gamma delta 0123456789.\n"*2500
    while len(http("/tokenize",dict(content=filler,add_special=False))["tokens"]) > 26000:
        filler = filler[:int(len(filler)*.94)]
    calls = []
    for i in range(2):
        request = dict(model=MODEL,messages=[dict(role="user",content=filler+"\nReturn a JSON list containing integers 1 through 10000; continue to the output limit.")],
                       max_tokens=4096,temperature=.6,seed=SEEDS[0],cache_prompt=False)
        start=time.monotonic()
        response=http("/v1/chat/completions",request,600)
        row=dict(seconds=time.monotonic()-start,request=request,response=response,usage=response.get("usage"))
        calls.append(row);write_json(out/f"call-{i:04}.json",row)
        if response.get("model") != MODEL or row["usage"] is None:
            raise ValueError("latency calibration identity/usage unavailable")
    timeout=max(180,min(600,math.ceil(2*max(r["seconds"] for r in calls)/30)*30))
    write_json(out/"calibration.json",dict(passed=True,timeout=timeout,samples=2))


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


def run(out, preflight):
    workflow=preflight/"workflow/result.json"
    if not json.loads(workflow.read_text())["passed"]:
        raise ValueError("full workflow calibration has not passed")
    frozen=preflight/"workflow/frozen-inputs"
    # Launcher/report additions do not invalidate measured core calibration;
    # compare the exact ASTs of every shared treatment/provider component.
    for filename,names in {
        "scripts/current_local.py":{"http","Provider","calibrate"},
        "scripts/repeated_local.py":{"Provider","Session","do_assessment","tests_for","grade","ProjectSandbox"},
        "scripts/long_horizon.py":{"Sandbox","skill"},
        "src/benchmark_runner/workflow.py":{"assess","grounded_claims"},
    }.items():
        if _definitions((frozen/filename).read_text(encoding="utf-8"),names)!=_definitions((ROOT/filename).read_text(encoding="utf-8"),names):
            raise ValueError("calibrated treatment changed: "+filename)
    assets=preflight/"assets";assets.mkdir(exist_ok=False)
    calibration=json.loads((preflight/"workflow/freeze.json").read_text())
    write_json(assets/"hardware.json",dict(gpus=calibration["hardware"]))
    write_json(assets/"server-launch.json",dict(model=MODEL,url=URL,weights_sha256=calibration["weights_sha256"],server_props=calibration["server_props"],shared_service_modified=False))
    import importlib.metadata
    write_json(assets/"package-versions.json",{n:importlib.metadata.version(n) for n in ("applied-epistemic-engineering","specify-cli","mini-swe-agent","jsonschema")})
    timeout=json.loads((preflight/"latency/calibration.json").read_text())["timeout"]
    CONFIG["physical_call_timeout"]=timeout
    CONFIG["completion_contract"]=COMPLETION
    runner.campaign(out,preflight/"grade",timeout,
        workflow_preflight=workflow,latency_preflight=preflight/"latency/calibration.json",
        context_preflight=preflight/"context/result.json",assets=assets,
        extra_sources=(Path(__file__).resolve(),ROOT/"scripts/local_feasibility.py"),
        completion_contract=COMPLETION,freeze_hook=archive_inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("grade-calibration", "workflow-calibration", "context-calibration", "latency", "run"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--preflight",type=Path)
    args = parser.parse_args()
    setup()
    if args.command == "grade-calibration":
        runner.calibrate(args.output)
    elif args.command == "workflow-calibration":
        calibrate(args.output)
    elif args.command == "context-calibration":
        context_calibration(args.output)
    elif args.command == "latency":
        latency(args.output)
    else:
        run(args.output,args.preflight)


if __name__ == "__main__":
    main()
