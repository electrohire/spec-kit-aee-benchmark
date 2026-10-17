"""Finish one preregistered free-local study after its calibration passes.

Never retries failed calibration, resumes a partial scored campaign, merges a PR,
or publishes a release. Durable status and command logs support long local runs.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from benchmark_runner.store import utc,write_json

ROOT=Path(__file__).resolve().parents[1]


def wait_workflow(path,seconds):
    deadline=time.monotonic()+seconds
    while True:
        result=path/"result.json"
        if result.exists():
            value=json.loads(result.read_text())
            if value.get("passed") is True:return
            if value.get("error"):raise RuntimeError("workflow calibration failed: "+value["error"])
        if time.monotonic()>=deadline:raise TimeoutError("workflow calibration did not finish within the wait limit")
        time.sleep(min(30,max(0,deadline-time.monotonic())))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("workflow","grade","context","latency","image_audit","preflight","raw","report","status"):
        parser.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    parser.add_argument("--setup",type=Path,action="append",default=[])
    parser.add_argument("--wait-seconds",type=int,default=10800)
    args=parser.parse_args()
    for name,value in vars(args).items():
        if isinstance(value,Path):
            value=value.resolve()
            if not value.is_relative_to(ROOT):raise ValueError("paths must remain inside the benchmark checkout")
            setattr(args,name,value)
    if any(p.exists() for p in (args.preflight,args.raw,args.report,args.status)):
        raise FileExistsError("new preflight, run, report and status paths required; no implicit retry/resume")
    state=dict(started_at=utc(),stage="waiting_for_workflow",complete=False,paid_inference=False,
               workflow=str(args.workflow),raw=str(args.raw),report=str(args.report),commands=[])
    write_json(args.status,state,exclusive=True)
    def command(stage,argv):
        state.update(stage=stage,updated_at=utc());write_json(args.status,state)
        log=args.status.parent/(args.status.stem+"-"+stage+".log")
        with log.open("wb") as handle:
            code=subprocess.run([sys.executable,*map(str,argv)],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT).returncode
        state["commands"].append(dict(stage=stage,argv=list(map(str,argv)),exit_code=code,log=str(log)))
        write_json(args.status,state)
        if code:raise RuntimeError(stage+" failed; see "+str(log))
    try:
        wait_workflow(args.workflow,args.wait_seconds)
        args.preflight.mkdir()
        for name in ("workflow","grade","context","latency"):
            shutil.copytree(getattr(args,name),args.preflight/name)
        shutil.copyfile(args.image_audit,args.preflight/"image-audit.json")
        command("dependency-replay",["scripts/replay_current_dependencies.py",args.preflight/"workflow",args.preflight/"dependency-replay"])
        command("scored-study",["scripts/current_local.py","run",args.raw,"--preflight",args.preflight])
        export=["scripts/report_current.py",args.raw,args.report]
        for path in args.setup:export.extend(("--setup",path))
        command("export",export)
        state.update(stage="evidence_exported_pending_review",complete=True,ended_at=utc())
    except Exception as exc:
        state.update(stage="stopped",error=type(exc).__name__+": "+str(exc),ended_at=utc())
        raise
    finally:write_json(args.status,state)


if __name__=="__main__":main()
