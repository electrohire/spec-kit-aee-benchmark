"""Revalidate deterministic AEE/evaluator behavior after compatible lock upgrades.

No model generation. The calibrated local agent/transport uses stdlib; its exact
ASTs/configuration are checked separately before scoring. Engine/extension releases
remain unchanged. Replays must preserve scores, findings, routing and lane states.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from benchmark_runner.store import Store, write_json, utc
from benchmark_runner.workflow import assess, grounded_claims
from benchmark_runner.project_assessment import assess_project

ROOT=Path(__file__).resolve().parents[1]


def semantic(value):
    raw=value["state"]["aee"]["aee"]
    return {**{k:value.get(k) for k in ("schema_version","phase","outcome","findings","next_action")},
            "scores":raw["scores"],"recoveries":raw["recoveries"],
            "lane_states":value["metadata"].get("lane_states")}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args()
    source=json.loads((args.workflow/"result.json").read_text())
    if not source["passed"] or len(source["assessments"])!=4:
        raise ValueError("successful full workflow calibration required")
    if {r['phase'] for r in source['assessments']}!={'specify','plan','tasks','implement'}:
        raise ValueError("required actual assessment checkpoints missing")
    args.output.mkdir(parents=True,exist_ok=False)
    frozen=json.loads((args.workflow/"freeze.json").read_text())
    rows=[]
    replay_store=Store(args.output/"evidence")
    original_store=Store(args.workflow/"evidence")
    if not original_store.verify_stream("tools")["chain_verified"]:
        raise ValueError("original tool trace hash chain failed")
    for event in original_store.events("tools"):
        artifact_path=args.workflow/"evidence"/event["artifact"]["path"]
        ref=replay_store.artifact(artifact_path.read_bytes())
        if ref!=event["artifact"]:raise ValueError("original tool artifact hash mismatch")
        replay_store.append("tools",dict(event,attempt_id="dependency-replay",replay_of="current-calibration"))
    for i,row in enumerate(source["assessments"]):
        original=row["claims"]
        checked=grounded_claims(original,Store(args.workflow/"evidence"),"current-calibration")
        for old_claim,new_claim in zip(original["claims"],checked["claims"]):
            for old,new in zip(old_claim.get("evidence",[]),new_claim.get("evidence",[])):
                if (old.get("kind")=="observed" or old.get("source_quality")!="model") and old!=new:
                    raise ValueError("calibration evidence can no longer be grounded")
        # Already downgraded model assertions stay byte-for-byte the original
        # assessment input; grounding them again would prepend the warning twice.
        claims=original
        result=assess_project(ROOT,claims,row["phase"],replay_store,"dependency-replay")
        write_json(args.output/f"checkpoint-{i}/composed.json",result)
        equal=semantic(result)==semantic(row["evaluation"])
        rows.append(dict(phase=row["phase"],semantic_match=equal,outcome=result["outcome"]))
        if not equal:
            write_json(args.output/"mismatch.json",dict(before=semantic(row["evaluation"]),after=semantic(result)))
            raise RuntimeError("dependency replay changed deterministic assessment semantics")
    value=dict(passed=True,created_at=utc(),checkpoints=rows,
        old_lock_sha256=frozen["hashes"]["uv.lock"],
        new_lock_sha256=hashlib.sha256((ROOT/"uv.lock").read_bytes()).hexdigest(),
        workflow_freeze_sha256=hashlib.sha256((args.workflow/"freeze.json").read_bytes()).hexdigest(),
        packages={d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},
        persistent_ledger_entries=[e["ledger_entries"] for e in replay_store.events("assessments")],
        inference_calls=0,note="Same engine/extension releases; native model interaction stays unchanged. All4 actual AEE/evaluator checkpoints replayed under the updated dependency environment and persistent project adapter with identical scores, findings, routing and machine/human lane states. Original tools are hash-verified replay inputs, not newly executed observations.")
    write_json(args.output/"result.json",value)
    print(json.dumps(dict(passed=True,checkpoints=rows,inference_calls=0)))


if __name__=="__main__":main()
