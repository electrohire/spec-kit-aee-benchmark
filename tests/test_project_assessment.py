"""Real extension/evaluator checks with persistent per-trajectory provenance."""
from pathlib import Path

import pytest
from aee.ledger import HashChainLedger

from benchmark_runner.project_assessment import assess_project
from benchmark_runner.store import Store,read_json,canonical
from benchmark_runner.workflow import assess

ROOT=Path(__file__).resolve().parents[1]


def test_real_project_keeps_ledger_and_composes_only_current_phase(tmp_path):
    claims=read_json(ROOT/".specify/extensions/aee/templates/aee-claims.json")
    store=Store(tmp_path/"trajectory/evidence")
    first=assess_project(ROOT,claims,"plan",store,"trajectory-one")
    second=assess_project(ROOT,claims,"implement",store,"trajectory-one")
    assert first["metadata"]["evaluator_count"]==second["metadata"]["evaluator_count"]==1
    events=store.events("assessments")
    assert [event["ledger_entries"] for event in events]==[1,2]
    ledger=tmp_path/"trajectory/aee-project/.specify/extensions/aee/ledger/epistemic-ledger.jsonl"
    assert HashChainLedger(ledger).verify(require_anchor=True).valid
    import sys
    sys.path.insert(0,str(ROOT/"scripts"))
    from replay_current_dependencies import semantic
    old=assess(ROOT,claims,"plan",Store(tmp_path/"stateless"),"old-adapter")
    assert semantic(first)==semantic(old)


def test_project_refuses_observations_from_another_attempt(tmp_path):
    claims=read_json(ROOT/".specify/extensions/aee/templates/aee-claims.json")
    store=Store(tmp_path/"trajectory/evidence")
    ref=store.artifact(canonical(dict(stdout="test passed")))
    store.append("tools",dict(attempt_id="other",artifact=ref))
    claims["claims"][0]["evidence"]=[dict(ref=ref["path"],source_id=ref["sha256"],kind="observed",source_quality="test")]
    with pytest.raises(ValueError,match="same-attempt"):
        assess_project(ROOT,claims,"plan",store,"this-attempt")


def test_full_dependency_replay_retains_tools_and_all_four_ledgers(tmp_path,monkeypatch):
    import hashlib
    import sys
    sys.path.insert(0,str(ROOT/"scripts"))
    import replay_current_dependencies as replay
    from benchmark_runner.store import write_json
    workflow=tmp_path/"workflow"
    store=Store(workflow/"evidence")
    ref=store.artifact(canonical(dict(stdout="fixture tool output",exit_code=0)))
    store.append("tools",dict(attempt_id="current-calibration",artifact=ref))
    claims=read_json(ROOT/".specify/extensions/aee/templates/aee-claims.json")
    rows=[]
    for phase in ("specify","plan","tasks","implement"):
        evaluation=assess_project(ROOT,claims,phase,store,"current-calibration")
        rows.append(dict(phase=phase,claims=claims,evaluation=evaluation))
    write_json(workflow/"result.json",dict(passed=True,assessments=rows))
    write_json(workflow/"freeze.json",dict(hashes={"uv.lock":hashlib.sha256((ROOT/"uv.lock").read_bytes()).hexdigest()}))
    output=tmp_path/"replay"
    monkeypatch.setattr(sys,"argv",["replay",str(workflow),str(output)])
    replay.main()
    result=read_json(output/"result.json")
    assert result["passed"] and result["inference_calls"]==0
    assert result["persistent_ledger_entries"]==[1,2,3,4]
    assert all(row["semantic_match"] for row in result["checkpoints"])
    assert len(Store(output/"evidence").events("tools"))==1
