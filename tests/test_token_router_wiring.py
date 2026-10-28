"""Window 4 Phase 1: token-router wiring (freeze-gated, fail-closed).
Window 5 Phase 1: the double now reproduces the real tool's
status/exit contract, and real-tool pins cover the unplanted leg.

The router is exercised through a test DOUBLE: a small script the
tests write to tmp that mimics the pinned token-router v2.8.1 CLI
(error_log mode, literal-search selection emitting the recorded
packet shape, a report JSON with model_called, --version printing
the pinned version string). The double returns the REAL tool's
documented exit code for the status it reports (0 for
auto_candidates, 2 for needs_targeted_read, 1 for error, ...):
Window 4's double returned 0 for every status, which — together
with a battery that planted the search terms into every output —
hid the wiring's exit-code defect until the live smoke. Knobs
ride in environment variables so one double serves every variant
(model_called true, forced status, forced exit, wrong version,
forced empty selection). The double's SHA-256 is computed by the
tests and passed in the freeze config, exactly as the Phase 2
freeze will pin the real script's digest.

E-1 wired drills reuse the shapes of the tournament filters run
(scripts/run_filters.py): workflow.grounded_claims downgrades a
routed-packet citation while a real store-artifact citation stays
observed; lifecycle.artifact refuses outside-root and
digest-mismatched refs; grading.grade refuses a routed packet
path as a repo input.
"""
import hashlib
import json
import os
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
    forced = os.environ.get("TR_DOUBLE_FORCE_STATUS")
    if forced:
        status = forced
        if forced == "auto_full":
            packet = text
        elif forced != "auto_candidates":
            packet = ""
    report = {"status": status, "schema_version": 1,
              "model_called":
                  os.environ.get("TR_DOUBLE_MODEL_CALLED") == "1"}
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    sys.stdout.write(packet)
    if os.environ.get("TR_DOUBLE_EXIT"):
        return int(os.environ["TR_DOUBLE_EXIT"])
    # The real tool's documented status/exit contract (its README
    # status table) — the double reproduces it per status.
    return {"auto_full": 0, "auto_candidates": 0, "fallback": 0,
            "needs_targeted_read": 2, "bypass": 2,
            "usage_error": 2, "error": 1}[status]

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


def test_router_exit_outside_contract_raises(tmp_path, double,
                                             monkeypatch):
    # Exit 3 documents no status: the report in hand is a valid
    # auto_candidates, so the status/exit cross-check is what
    # raises — not a blanket non-zero rule (exit 2 is documented
    # and routine; see the targeted-read tests, which now run
    # against a double that returns it).
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_EXIT="3")
    with pytest.raises(TokenRouterFreezeError, match="status/exit"):
        env.execute({"command": "run tests"})


def test_router_status_exit_mismatch_raises(tmp_path, double,
                                            monkeypatch):
    # needs_targeted_read documents exit 2; exit 0 for it is a
    # mismatch and raises.
    monkeypatch.setenv("TR_DOUBLE_EXIT", "0")
    result = {"exit_code": 0, "stdout": QUIET_TEXT, "stderr": ""}
    env, _store = make_env(tmp_path, result, router_cfg(double),
                           phase="solve")
    with pytest.raises(TokenRouterFreezeError, match="status/exit"):
        env.execute({"command": "cat file"})
    # The mirror: auto_candidates documents exit 0; exit 2 for it
    # is equally a mismatch.
    monkeypatch.setenv("TR_DOUBLE_EXIT", "2")
    result = {"exit_code": 0, "stdout": SELECTION_TEXT, "stderr": ""}
    env, _store = make_env(tmp_path, result, router_cfg(double),
                           phase="solve")
    with pytest.raises(TokenRouterFreezeError, match="status/exit"):
        env.execute({"command": "run tests"})


def test_router_error_status_raises_on_its_status(tmp_path, double,
                                                  monkeypatch):
    # status error / exit 1 is contract-consistent, so the
    # cross-check passes and the raise is on the status itself.
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_FORCE_STATUS="error")
    with pytest.raises(TokenRouterFreezeError, match="reported error"):
        env.execute({"command": "run tests"})


def test_router_usage_error_raises_despite_documented_exit(
        tmp_path, double, monkeypatch):
    # usage_error shares exit 2 with needs_targeted_read: dispatch
    # is on the report's status, so this raises on a code that —
    # read as a bare exit code — is routine.
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_FORCE_STATUS="usage_error")
    with pytest.raises(TokenRouterFreezeError,
                       match="reported usage_error"):
        env.execute({"command": "run tests"})


def test_router_fallback_status_raises(tmp_path, double, monkeypatch):
    # fallback belongs to the tool's optional model-selector path,
    # never enabled here; it fails closed.
    env, _store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                              TR_DOUBLE_FORCE_STATUS="fallback")
    with pytest.raises(TokenRouterFreezeError, match="fallback"):
        env.execute({"command": "run tests"})


def test_router_bypass_status_delivers_combined_verbatim(
        tmp_path, double, monkeypatch):
    # bypass / exit 2: the tool rejected the profile and returned
    # no packet; the combined text is delivered verbatim.
    env, store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                             TR_DOUBLE_FORCE_STATUS="bypass")
    observation = env.execute({"command": "run tests"})
    assert observation["stdout"] == SELECTION_TEXT
    assert observation["stderr"] == ""
    (event,) = router_events(store)
    assert event["status"] == "bypass"
    assert event["targeted_read"] is False
    assert event["packet_bytes"] == 0
    assert event["delivered_bytes"] == len(
        SELECTION_TEXT.encode("utf-8"))


def test_router_auto_full_status_delivers_its_packet(
        tmp_path, double, monkeypatch):
    # auto_full / exit 0: the packet is the whole decoded source.
    env, store = _routed_env(tmp_path, router_cfg(double), monkeypatch,
                             TR_DOUBLE_FORCE_STATUS="auto_full")
    observation = env.execute({"command": "run tests"})
    assert observation["stdout"] == SELECTION_TEXT
    (event,) = router_events(store)
    assert event["status"] == "auto_full"
    assert event["packet_bytes"] == len(
        SELECTION_TEXT.encode("utf-8"))


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


# ---------------- real-tool pins: the unplanted leg ----------------
# Window 4's wired battery planted the search terms into every
# corpus output, so the real tool never returned
# needs_targeted_read there, and the double returned exit 0 for
# every status: the targeted-read path was never exercised
# against the real tool's exit-code contract until the live
# smoke — which halted on it. These pins run the wired path
# against the REAL pinned tool on unplanted output shapes. They
# run only where the pinned tool is present: set
# TOKEN_ROUTER_SCRIPT and TOKEN_ROUTER_SHA256 (the freeze values)
# in the environment; otherwise they skip.

REAL_ROUTER_SCRIPT = os.environ.get("TOKEN_ROUTER_SCRIPT")
REAL_ROUTER_SHA256 = os.environ.get("TOKEN_ROUTER_SHA256")


def _real_router_present():
    if not (REAL_ROUTER_SCRIPT and REAL_ROUTER_SHA256):
        return False
    path = Path(REAL_ROUTER_SCRIPT)
    return (path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest()
            == REAL_ROUTER_SHA256)


real_router = pytest.mark.skipif(
    not _real_router_present(),
    reason="pinned token-router tool not present "
           "(TOKEN_ROUTER_SCRIPT / TOKEN_ROUTER_SHA256 unset or "
           "digest mismatch)")


def _real_cfg():
    return {"token_router": True,
            "token_router_script": REAL_ROUTER_SCRIPT,
            "token_router_sha256": REAL_ROUTER_SHA256}


# A genuine read-only probe output: a find/ls listing carrying NO
# failure-vocabulary term anywhere. (The Window 4 smoke's first
# tool output had exactly this shape.)
UNPLANTED_QUIET_TEXT = (
    "/testbed/django/contrib/auth/validators.py\n"
    "/testbed/tests/auth_tests/test_validators.py\n"
    "total 8\n"
    "drwxr-xr-x 2 root root 4096 Oct 26 22:01 .\n"
    "drwxr-xr-x 1 root root 4096 Oct 26 22:01 ..\n")

# A genuine pytest failure block: the vocabulary occurs as real
# content, not planted into a recorded output for a battery.
GENUINE_FAILURE_TEXT = (
    "tests/test_widget.py::test_widget_renders FAILED\n"
    "tests/test_widget.py:42: in test_widget_renders\n"
    "    assert render(widget) == '<div>ok</div>'\n"
    "E   AssertionError: assert '<div></div>' == '<div>ok</div>'\n"
    "FAILED tests/test_widget.py::test_widget_renders"
    " - AssertionError\n")


@real_router
def test_real_router_unplanted_output_takes_targeted_read(tmp_path):
    result = {"exit_code": 0, "stdout": UNPLANTED_QUIET_TEXT,
              "stderr": ""}
    env, store = make_env(tmp_path, result, _real_cfg(),
                          phase="solve")
    observation = env.execute(
        {"command": "find /testbed -name 'validators.py'"})
    # The real tool returns needs_targeted_read (exit 2) for text
    # with no search term; the wiring's targeted read delivers
    # the raw combined text byte for byte. Against the Window 4
    # wiring this call raised a freeze violation.
    assert observation["stdout"] == UNPLANTED_QUIET_TEXT
    assert observation["stderr"] == ""
    (event,) = router_events(store)
    assert event["status"] == "needs_targeted_read"
    assert event["targeted_read"] is True
    assert event["delivered_bytes"] == len(
        UNPLANTED_QUIET_TEXT.encode("utf-8"))
    assert event["model_called"] is False


@real_router
def test_real_router_genuine_failure_text_is_selected(tmp_path):
    result = {"exit_code": 0, "stdout": GENUINE_FAILURE_TEXT,
              "stderr": ""}
    env, store = make_env(tmp_path, result, _real_cfg(),
                          phase="solve")
    observation = env.execute(
        {"command": "pytest tests/test_widget.py"})
    (event,) = router_events(store)
    assert event["status"] in ("auto_candidates", "auto_full")
    # The genuine failure lines survive in the delivered text.
    assert "AssertionError" in observation["stdout"]
    assert "FAILED tests/test_widget.py::test_widget_renders" in (
        observation["stdout"])
