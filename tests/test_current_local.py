"""Offline guards for current-version local campaigns; no inference requests."""
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
from aee.model import Claim

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import long_horizon
import local_experiment
import repeated_local
import current_local


def test_completion_pipeline_stops_before_generation_when_calibration_failed(tmp_path,monkeypatch):
    import complete_current_study as pipeline
    workflow=tmp_path/"workflow";workflow.mkdir()
    (workflow/"result.json").write_text(json.dumps(dict(passed=False,error="fixture failure")))
    monkeypatch.setattr(pipeline,"ROOT",tmp_path)
    monkeypatch.setattr(pipeline.subprocess,"run",lambda *a,**k:pytest.fail("must not start any child command"))
    argv=["complete"]
    for name in ("workflow","grade","context","latency","image-audit","preflight","raw","report","status"):
        argv.extend(("--"+name,str(tmp_path/name)))
    monkeypatch.setattr(sys,"argv",argv)
    with pytest.raises(RuntimeError,match="fixture failure"):pipeline.main()
    status=json.loads((tmp_path/"status").read_text())
    assert status["stage"]=="stopped" and not status["complete"]
    assert status["commands"]==[] and not (tmp_path/"raw").exists()


def test_failed_latency_request_retains_unknown_usage(tmp_path,monkeypatch):
    monkeypatch.setattr(current_local,"freeze",lambda *args: tmp_path.mkdir(exist_ok=True))
    def failed(route,payload=None,timeout=120):
        if route=="/tokenize":return {"tokens":[1]}
        raise TimeoutError("fixture")
    monkeypatch.setattr(current_local,"http",failed)
    with pytest.raises(TimeoutError):current_local.latency(tmp_path)
    record=json.loads((tmp_path/"call-0000.json").read_text())
    assert record["usage"] is None
    assert record["error"]=="TimeoutError"
    assert record["unknown_reason"]=="failed_request_not_imputed"
    assert record["seconds"]>=0 and record["started_at"] and record["ended_at"]
    assert not (tmp_path/"calibration.json").exists()


def test_every_active_local_claim_example_loads_strict_current_engine():
    start=long_horizon.CLAIMS.index('"claims":')+len('"claims":')
    bundle,_=json.JSONDecoder().raw_decode(long_horizon.CLAIMS[start:])
    for source in (bundle,local_experiment.claims(2)):
        for claim in source["claims"]:
            parsed=Claim.from_dict(claim)
            assert parsed.stage.value=="created"
            assert parsed.status.value=="draft"


def test_ast_calibration_comparison_ignores_only_unrelated_launcher_changes():
    one='def calibrated():\n return 1\ndef launcher():\n return 2\n'
    two='def calibrated():\n return 1\ndef launcher():\n return 3\n'
    assert current_local._definitions(one,{"calibrated"})==current_local._definitions(two,{"calibrated"})
    assert current_local._definitions(one,{"launcher"})!=current_local._definitions(two,{"launcher"})
    assert current_local._bindings('MODEL="a"',{"MODEL"})!=current_local._bindings('MODEL="b"',{"MODEL"})


def test_frozen_inputs_reject_change_and_preserve_bytes(tmp_path,monkeypatch):
    (tmp_path/"source.py").write_bytes(b"x=1\n")
    monkeypatch.setattr(current_local,"ROOT",tmp_path)
    import hashlib
    manifest={"hashes":{"source.py":hashlib.sha256(b"x=1\n").hexdigest()}}
    current_local.archive_inputs(tmp_path/"run",manifest)
    assert (tmp_path/"run/frozen-inputs/source.py").read_bytes()==b"x=1\n"
    (tmp_path/"source.py").write_bytes(b"x=2\n")
    with pytest.raises(ValueError,match="changed during freeze"):
        current_local.archive_inputs(tmp_path/"other",manifest)


def test_current_provider_keeps_usage_when_wrong_response_identity(tmp_path,monkeypatch):
    def local(route,payload=None,timeout=120):
        if route=="/apply-template":return {"prompt":"x"}
        if route=="/tokenize":return {"tokens":[1,2,3]}
        assert route=="/v1/chat/completions"
        return {"model":"wrong","usage":{"prompt_tokens":3,"completion_tokens":4,"total_tokens":7},
                "choices":[{"finish_reason":"stop","message":{"content":'{"action":"done"}'}}]}
    monkeypatch.setattr(repeated_local,"local_json",local)
    provider=current_local.Provider(tmp_path/"calls",20261016,5)
    with pytest.raises(RuntimeError,match="ModelIdentityMismatch"):
        provider.query([{"role":"user","content":"fixture"}],"solve",1,time.monotonic()+100)
    assert provider.calls[0]["usage"]["total_tokens"]==7
    assert json.loads((tmp_path/"calls/call-0000.json").read_text())["error"]=="ModelIdentityMismatch"


def test_real_aee_assessment_is_bound_to_session_identity(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(repeated_local,"assess",lambda *args: calls.append(args) or {"outcome":"iterate"})
    session=type("Session",(),dict(store=repeated_local.Store(tmp_path),identity="exact-attempt",history=[]))()
    row={"assessments":[]}
    done={"claims":local_experiment.claims(1)}
    repeated_local.do_assessment(session,row,"plan",done)
    assert calls[0][-1]=="exact-attempt"
    assert row["assessments"][0]["outcome"]=="iterate"
