"""Window 4 Phase 1: token-router wiring (freeze-gated, fail-closed).

The router is exercised through a test DOUBLE: a small script the
tests write to tmp that mimics the pinned token-router v2.8.1 CLI
(error_log mode, literal-search selection emitting the recorded
packet shape, a report JSON with model_called, --version printing
the pinned version string). Knobs ride in environment variables so
one double serves every variant (model_called true, non-zero exit,
wrong version, forced empty selection). The double's SHA-256 is
computed by the tests and passed in the freeze config, exactly as
the Phase 2 freeze will pin the real script's digest.

E-1 wired drills reuse the shapes of the tournament filters run
(scripts/run_filters.py): workflow.grounded_claims downgrades a
routed-packet citation while a real store-artifact citation stays
observed; lifecycle.artifact refuses outside-root and
digest-mismatched refs; grading.grade refuses a routed packet
path as a repo input.
"""
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from benchmark_runner import lifecycle, runner
from benchmark_runner.context import (OBSERVATION_WRITE_CAP_BYTES,
                                      cap_observation)
from benchmark_runner.grading import grade
from benchmark_runner.store import Store, canonical, sha
from benchmark_runner.token_router import (ROUTER_TERMS, ROUTER_VERSION,
                                           TokenRouterFreezeError,
                                           route_observation)
from benchmark_runner.workflow import grounded_claims

DOUBLE_SOURCE = '''
import json, os, sys

def main(argv):
    marker = os.environ.get("TR_DOUBLE_MARKER")
    if marker:
        with open(marker, "a", encoding="utf-8") as fh:
            fh.write("invoked\\n")
    if "--version" in argv:
        sys.stdout.write(os.environ.get(
            "TR_DOUBLE_VERSION", "token-router 2.8.1") + "\\n")
        return 0
    if os.environ.get("TR_DOUBLE_EXIT"):
        return int(os.environ["TR_DOUBLE_EXIT"])
    target = argv[argv.index("error_log") + 1]
    report_path = argv[argv.index("--report-json") + 1]
    terms = [argv[i + 1] for i, a in enumerate(argv)
             if a == "--search-term"]
    text = open(target, encoding="utf-8").read()
    lines = text.split("\\n")
    matched = [i for i, line in enumerate(lines)
               if any(t in line for t in terms)]
    packet = ""
    status = "needs_targeted_read"
    if matched and os.environ.get("TR_DOUBLE_EMPTY_SELECTION") != "1":
        status = "auto_candidates"
        ranges = []
        for i in matched:
            lo, hi = max(0, i - 1), min(len(lines) - 1, i + 1)
            if ranges and lo <= ranges[-1][1] + 1:
                ranges[-1][1] = max(ranges[-1][1], hi)
            else:
                ranges.append([lo, hi])
        parts = []
        for lo, hi in ranges:
            parts.append(
                "--- [NUMBERED CONTENT FROM LINE %d TO %d] ---\\n"
                % (lo + 1, hi + 1))
            for n in range(lo, hi + 1):
                parts.append("%d: %s\\n" % (n + 1, lines[n]))
            parts.append("--- [END OF SLICE] ---\\n")
        packet = "".join(parts)
    report = {"status": status, "schema_version": 1,
              "model_called":
                  os.environ.get("TR_DOUBLE_MODEL_CALLED") == "1"}
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    sys.stdout.write(packet)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

IDENTITY = {"attempt_id": "wired-1"}


class StubSandbox:
    def __init__(self, result):
        self.result = result

    def execute(self, command, timeout=60):
        return dict(self.result)


@pytest.fixture()
def double(tmp_path):
    path = tmp_path / "router_double.py"
    path.write_text(DOUBLE_SOURCE, encoding="utf-8")
    return path


def router_cfg(double_path, **overrides):
    cfg = {"token_router": True,
           "token_router_script": str(double_path),
           "token_router_sha256": hashlib.sha256(
               double_path.read_bytes()).hexdigest()}
    cfg.update(overrides)
    return cfg


def make_env(tmp_path, result, cfg, phase=None):
    store = Store(tmp_path / "store")
    env = runner.MiniEnvironment(
        StubSandbox(result), time.monotonic() + 600, store,
        dict(IDENTITY), cfg=cfg)
    env.phase = phase
    return env, store


def direct_packet(double_path, text, tmp_path):
    """The double's own packet for a text, invoked exactly as the
    wiring invokes it — the verbatim-delivery expectation."""
    target = tmp_path / "direct.txt"
    target.write_text(text, encoding="utf-8")
    report = tmp_path / "direct.json"
    command = [sys.executable, str(double_path), "error_log",
               str(target), "--read-scope", "focused",
               "--line-numbers", "--report-json", str(report),
               "--compact-status"]
    for term in ROUTER_TERMS:
        command += ["--search-term", term]
    proc = subprocess.run(command, capture_output=True)
    assert proc.returncode == 0
    return proc.stdout.decode("utf-8")


def router_events(store):
    return store.events("router")


# ---------------- constants and combined basis ----------------

def test_router_constants_are_the_pinned_ones():
    assert ROUTER_VERSION == "token-router 2.8.1"
    assert ROUTER_TERMS == ("ERROR", "Error", "error:", "FAILED",
                            "Traceback", "AssertionError")


# ---------------- flag off: byte-identity, both branches ----------------

BIG_RESULT = {"exit_code": 0, "stdout": "x" * 30000,
              "stderr": "e" * 9000}


def test_flag_off_plain_branch_byte_identical(tmp_path):
    for cfg in ({}, {"token_router": False}):
        env, store = make_env(tmp_path, BIG_RESULT, cfg, phase="solve")
        observation = env.execute({"command": "ls"})
        artifact = store.events("tools")[-1]["artifact"]
        expected = {**BIG_RESULT,
                    "stdout": BIG_RESULT["stdout"][-24000:],
                    "stderr": BIG_RESULT["stderr"][-8000:],
                    "evidence_ref": artifact["path"],
                    "source_id": artifact["sha256"]}
        assert observation == expected
        assert not (store.root / "router.jsonl").exists()


def test_flag_off_drafting_branch_byte_identical(tmp_path):
    env, store = make_env(tmp_path, BIG_RESULT, {}, phase="specify")
    observation = env.execute({"command": "ls"})
    artifact = store.events("tools")[-1]["artifact"]
    expected = {**cap_observation(BIG_RESULT, OBSERVATION_WRITE_CAP_BYTES),
                "evidence_ref": artifact["path"],
                "source_id": artifact["sha256"]}
    assert observation == expected
    assert not (store.root / "router.jsonl").exists()


# ---------------- selection delivery ----------------

SELECTION_TEXT = ("line one is quiet\n"
                  "ERROR the widget broke\n"
                  "line three is quiet\n"
                  "another quiet line\n")


def test_selection_delivered_verbatim_with_event(tmp_path, double):
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "run tests"})
    packet = direct_packet(double, SELECTION_TEXT, tmp_path)
    assert packet.startswith("--- [NUMBERED CONTENT FROM LINE ")
    assert observation["stdout"] == packet
    assert observation["stderr"] == ""
    artifact = store.events("tools")[-1]["artifact"]
    # Evidence identity still comes from the raw artifact.
    assert observation["source_id"] == artifact["sha256"]
    assert observation["evidence_ref"] == artifact["path"]
    (event,) = router_events(store)
    assert event["attempt_id"] == "wired-1"
    assert event["artifact"] == artifact["sha256"]
    assert event["exit_code"] == 0
    assert event["status"] == "auto_candidates"
    assert event["raw_bytes"] == len(SELECTION_TEXT.encode("utf-8"))
    assert event["packet_bytes"] == len(packet.encode("utf-8"))
    assert event["delivered_bytes"] == len(packet.encode("utf-8"))
    assert event["targeted_read"] is False
    assert event["selected_lines"] == len(
        re.findall(r"(?m)^\d+:", packet))
    assert event["selected_lines"] > 0
    assert event["model_called"] is False
    assert "timestamp" in event


def test_selection_shaped_by_drafting_cap_branch(tmp_path, double):
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="specify")
    observation = env.execute({"command": "run tests"})
    packet = direct_packet(double, SELECTION_TEXT, tmp_path)
    # The cap branch shapes the delivered packet as it shapes raw
    # text: packet under the cap passes through, byte counts ride.
    assert observation["stdout"] == packet
    assert observation["stdout_bytes_total"] == len(
        packet.encode("utf-8"))
    assert observation["stdout_bytes_kept"] == len(
        packet.encode("utf-8"))


def test_router_tool_verified_once_per_environment(tmp_path, double,
                                                     monkeypatch):
    marker = tmp_path / "invocations.txt"
    monkeypatch.setenv("TR_DOUBLE_MARKER", str(marker))
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    env.execute({"command": "one"})
    env.execute({"command": "two"})
    invocations = marker.read_text(encoding="utf-8").splitlines()
    # One --version probe (first routed call) + two error_log runs.
    assert len(invocations) == 3
    assert len(router_events(store)) == 2


# ---------------- bypass and skip ----------------

def test_failure_bypasses_router_verbatim(tmp_path, double, monkeypatch):
    marker = tmp_path / "invocations.txt"
    monkeypatch.setenv("TR_DOUBLE_MARKER", str(marker))
    result = {"exit_code": 2, "stdout": "partial output\nFAILED x",
              "stderr": "boom"}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "run tests"})
    combined = "partial output\nFAILED x\nboom"
    assert observation["stdout"] == combined
    assert observation["stderr"] == ""
    assert observation["exit_code"] == 2
    assert not marker.exists()  # the router was provably not invoked
    (event,) = router_events(store)
    assert event["status"] == "bypass_failure"
    assert event["exit_code"] == 2
    assert event["raw_bytes"] == len(combined.encode("utf-8"))
    assert event["delivered_bytes"] == len(combined.encode("utf-8"))
    assert event["packet_bytes"] == 0
    assert event["targeted_read"] is False
    assert event["selected_lines"] == 0


def test_failure_bypass_needs_no_router_freeze_keys(tmp_path):
    result = {"exit_code": 1, "stdout": "died", "stderr": ""}
    env, store = make_env(tmp_path, result, {"token_router": True},
                          phase="solve")
    observation = env.execute({"command": "run tests"})
    assert observation["stdout"] == "died"
    assert router_events(store)[0]["status"] == "bypass_failure"


def test_empty_output_skips_router(tmp_path, double, monkeypatch):
    marker = tmp_path / "invocations.txt"
    monkeypatch.setenv("TR_DOUBLE_MARKER", str(marker))
    result = {"exit_code": 0, "stdout": "", "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "true"})
    assert observation["stdout"] == ""
    assert observation["stderr"] == ""
    assert not marker.exists()
    (event,) = router_events(store)
    assert event["status"] == "skipped_empty"
    assert event["raw_bytes"] == 0
    assert event["delivered_bytes"] == 0
    assert event["packet_bytes"] == 0
    assert event["targeted_read"] is False


# ---------------- targeted read ----------------

QUIET_TEXT = "all quiet here\nnothing to see\n"


def test_needs_targeted_read_delivers_raw_via_artifact(tmp_path, double):
    result = {"exit_code": 0, "stdout": QUIET_TEXT, "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "cat file"})
    assert observation["stdout"] == QUIET_TEXT
    assert observation["stderr"] == ""
    (event,) = router_events(store)
    assert event["status"] == "needs_targeted_read"
    assert event["targeted_read"] is True
    assert event["packet_bytes"] == 0
    assert event["raw_bytes"] == len(QUIET_TEXT.encode("utf-8"))
    assert event["delivered_bytes"] == len(QUIET_TEXT.encode("utf-8"))
    assert event["selected_lines"] == 0


def test_targeted_read_combines_stdout_and_stderr(tmp_path, double):
    result = {"exit_code": 0, "stdout": "out quiet",
              "stderr": "err quiet"}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "cat file"})
    assert observation["stdout"] == "out quiet\nerr quiet"
    assert router_events(store)[0]["status"] == "needs_targeted_read"


def test_targeted_read_tampered_artifact_file_raises(tmp_path, double):
    store = Store(tmp_path / "store")
    result = {"exit_code": 0, "stdout": QUIET_TEXT, "stderr": ""}
    artifact = store.artifact(canonical({"command": "cat file", **result}))
    (store.root / artifact["path"]).write_bytes(b"tampered bytes")
    with pytest.raises(TokenRouterFreezeError) as excinfo:
        route_observation(result, artifact, router_cfg(double),
                          store=store, identity=dict(IDENTITY),
                          state={"verified": False})
    assert "token_router freeze violation" in str(excinfo.value)
    assert "freeze" in str(excinfo.value)


def test_targeted_read_rebuilt_text_mismatch_raises(tmp_path, double):
    store = Store(tmp_path / "store")
    in_hand = {"exit_code": 0, "stdout": QUIET_TEXT, "stderr": ""}
    other = {"exit_code": 0, "stdout": "different quiet text",
             "stderr": ""}
    other_artifact = store.artifact(
        canonical({"command": "cat file", **other}))
    with pytest.raises(TokenRouterFreezeError) as excinfo:
        route_observation(in_hand, other_artifact, router_cfg(double),
                          store=store, identity=dict(IDENTITY),
                          state={"verified": False})
    assert "token_router freeze violation" in str(excinfo.value)


# ---------------- integrity failures (fail-closed) ----------------

def _routed_env(tmp_path, cfg, monkeypatch, **env_knobs):
    for key, value in env_knobs.items():
        monkeypatch.setenv(key, value)
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    return make_env(tmp_path, result, cfg, phase="solve")


def test_model_called_report_raises(tmp_path, double, monkeypatch):
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_MODEL_CALLED="1")
    with pytest.raises(TokenRouterFreezeError) as excinfo:
        env.execute({"command": "run tests"})
    assert "token_router freeze violation" in str(excinfo.value)
    assert "freeze" in str(excinfo.value)


def test_router_nonzero_exit_raises(tmp_path, double, monkeypatch):
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_EXIT="3")
    with pytest.raises(TokenRouterFreezeError, match="freeze"):
        env.execute({"command": "run tests"})


def test_script_sha_mismatch_raises(tmp_path, double):
    cfg = router_cfg(double, token_router_sha256="f" * 64)
    env, _store = make_env(
        tmp_path, {"exit_code": 0, "stdout": SELECTION_TEXT,
                   "stderr": ""}, cfg, phase="solve")
    with pytest.raises(TokenRouterFreezeError, match="freeze"):
        env.execute({"command": "run tests"})


def test_version_mismatch_raises(tmp_path, double, monkeypatch):
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_VERSION="token-router 0.0.0")
    with pytest.raises(TokenRouterFreezeError, match="freeze"):
        env.execute({"command": "run tests"})


def test_missing_freeze_keys_raise(tmp_path, double):
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    for cfg in ({"token_router": True},
                {"token_router": True,
                 "token_router_script": str(double)},
                {"token_router": True,
                 "token_router_sha256": "f" * 64},
                {"token_router": True,
                 "token_router_script": str(tmp_path / "absent.py"),
                 "token_router_sha256": "f" * 64}):
        env, _store = make_env(tmp_path, result, cfg, phase="solve")
        with pytest.raises(TokenRouterFreezeError, match="freeze"):
            env.execute({"command": "run tests"})


# ---------------- E-1 wired drills (run_filters shapes) ----------------

def _wired_packet(tmp_path, double):
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    env, store = make_env(tmp_path, result, router_cfg(double),
                          phase="solve")
    observation = env.execute({"command": "run tests"})
    artifact = store.events("tools")[-1]["artifact"]
    return store, observation, artifact


def _bundle(source_id, ref):
    return {"claims": [{"id": "c1", "evidence": [
        {"kind": "observed", "source_id": source_id, "ref": ref,
         "description": "drill", "source_quality": "primary"}]}]}


def test_e1_grounding_downgrades_routed_packet_citation(
        tmp_path, double):
    store, observation, artifact = _wired_packet(tmp_path, double)
    packet = observation["stdout"]
    good = grounded_claims(
        _bundle(artifact["sha256"], artifact["path"]), store, "wired-1")
    assert good["claims"][0]["evidence"][0]["kind"] == "observed"
    bad = grounded_claims(
        _bundle(sha(packet.encode("utf-8")), "router packet"),
        store, "wired-1")
    evidence = bad["claims"][0]["evidence"][0]
    assert evidence["kind"] == "asserted"
    assert evidence["source_quality"] == "model"
    # A verbatim slice alone is not a store artifact either.
    artifact_bytes = (store.root / artifact["path"]).read_bytes()
    sliced = grounded_claims(
        _bundle(sha(artifact_bytes[:50]), artifact["path"]),
        store, "wired-1")
    assert sliced["claims"][0]["evidence"][0]["kind"] == "asserted"


def test_e1_lifecycle_refuses_outside_root_and_mismatched_refs(
        tmp_path, double):
    _store, observation, _artifact = _wired_packet(tmp_path, double)
    packet = observation["stdout"]
    root = tmp_path / "evidence"
    root.mkdir()
    inside = root / "inside.txt"
    inside.write_text("verbatim source slice stored as evidence",
                      encoding="utf-8")
    inside_ref = {"path": "inside.txt",
                  "sha256": sha(inside.read_bytes())}
    assert lifecycle.artifact(root, inside_ref) == inside.read_bytes()
    packet_path = tmp_path / "packet.txt"
    packet_path.write_text(packet, encoding="utf-8")
    outside_ref = {"path": str(packet_path),
                   "sha256": sha(packet.encode("utf-8"))}
    with pytest.raises(ValueError, match="inside the evidence"):
        lifecycle.artifact(root, outside_ref)
    with pytest.raises(ValueError, match="inside the evidence"):
        lifecycle.artifact(root, {"path": "../packet.txt",
                                  "sha256": outside_ref["sha256"]})
    with pytest.raises(ValueError, match="digest mismatch"):
        lifecycle.artifact(root, {"path": "inside.txt",
                                  "sha256": sha(b"other bytes")})


def test_e1_grading_refuses_routed_packet_as_repo(tmp_path, double):
    store, observation, _artifact = _wired_packet(tmp_path, double)
    packet_path = tmp_path / "packet.txt"
    packet_path.write_text(observation["stdout"], encoding="utf-8")
    with pytest.raises((subprocess.CalledProcessError, ValueError)):
        grade(store, packet_path, packet_path, "deadbeef", "deadbeef")
