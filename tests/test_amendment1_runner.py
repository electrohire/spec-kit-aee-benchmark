"""Amendment 1 (2026-10-21) acceptance tests for the runner core:
setup by construction (R-A1), the phase guard and its exhaustion
semantics (R-A3/R-A4), construction-failure admission (R-A4), and
the worker-availability probe (R-A6). Runner-level replays in the
style of tests/test_needle_stop_policy.py: the Stage 1 shapes are
rebuilt from scripted providers and every claim is read back from
the run store."""
import base64
import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path

import pytest

from benchmark_runner import runner
from benchmark_runner.provider import ProviderError
from benchmark_runner.store import Store

ROOT = Path(__file__).resolve().parents[1]

CONSTITUTION = b"# Constitution\nfixture principles\n"
CONSTITUTION_SHA = sha256(CONSTITUTION).hexdigest()


def workflow_tar():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo("workflow/.specify/memory/constitution.md")
        info.size = len(CONSTITUTION)
        tar.addfile(info, io.BytesIO(CONSTITUTION))
    return buffer.getvalue()


class RecordingProvider:
    """A provider that records every call in the store (as the real
    providers do) and answers from a per-phase script. A script step
    is ("shell", input_tokens, output_tokens), ("done", in, out), or
    ("raise",). The last step repeats."""

    def __init__(self, store, identity, script):
        self.store, self.identity, self.script = store, identity, script
        self.counts = {}
        self.queried = []

    def query(self, messages, phase, timeout):
        self.queried.append(phase)
        idx = self.counts.get(phase, 0)
        self.counts[phase] = idx + 1
        steps = self.script[phase]
        step = steps[min(idx, len(steps) - 1)]
        if step[0] == "raise":
            self.store.append("calls", {**self.identity, "phase": phase,
                                        "call_id": f"{self.identity['attempt_id']}-{phase}-{idx}",
                                        "input_tokens": None, "output_tokens": None,
                                        "usage_status": "unknown"})
            raise ProviderError("URLError")
        _, tin, tout = step
        self.store.append("calls", {**self.identity, "phase": phase,
                                    "call_id": f"{self.identity['attempt_id']}-{phase}-{idx}",
                                    "input_tokens": tin, "output_tokens": tout,
                                    "usage_status": "reported"})
        if step[0] == "done":
            return json.dumps({"action": "done", "summary": "fixture",
                               "claims": {"schema_version": "1.0", "claims": []}})
        return json.dumps({"action": "shell", "command": "true"})


class FakeSandbox:
    BASE_BY_IMAGE = {}

    def __init__(self, image=None):
        self.image = image
        self.details = {}
        self.commands = []
        self.staged = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def stage_workflow(self, root):
        self.staged = True

    def execute(self, command, timeout=60):
        self.commands.append(command)
        if "git rev-parse HEAD" in command:
            return {"exit_code": 0, "stdout": self.BASE_BY_IMAGE[self.image], "stderr": ""}
        if "tar -cf -" in command:
            return {"exit_code": 0,
                    "stdout": base64.b64encode(workflow_tar()).decode(), "stderr": ""}
        if "sha256sum" in command:
            return {"exit_code": 0, "stdout": CONSTITUTION_SHA + "\n", "stderr": ""}
        if "git diff" in command:
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}


BASE_CFG = {"timeout_seconds": 600, "max_input_tokens": 24576, "max_output_tokens": 8192,
            "token_cap": 1500000, "max_calls": 120, "max_recovery_rounds": 2,
            "global_cap_usd": 100, "attempt_cap_usd": 25, "purpose": "scored_comparison"}


def done_script(phases, tin=100, tout=50):
    return {phase: [("done", tin, tout)] for phase in phases}


# ---------------- execute_attempt level: the phase guard ----------------

def run_attempt(tmp_path, arm, script, cfg_extra=None):
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": arm, "repeat": 1}
    provider = RecordingProvider(store, identity, script)
    cfg = {**BASE_CFG, **(cfg_extra or {})}
    result = runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                    arm, provider, FakeSandbox(), store, identity, cfg)
    return store, provider, result


def test_phase_guard_runaway_constitution_ends_at_the_guard(tmp_path):
    # The Stage 1 failure shape: a constitution phase that never
    # completes, charged 40,000 tokens per call.
    script = {"constitution": [("shell", 40000, 0)]}
    store, provider, result = run_attempt(tmp_path, "spec_kit", script)
    calls = [c for c in store.events("calls") if c["phase"] == "constitution"]
    charged = sum(c["input_tokens"] + c["output_tokens"] for c in calls)
    assert result["phase_exhausted"] == "constitution"
    assert 900000 <= charged < 900000 + 40000
    assert len(calls) <= 40
    assert result["patch"]  # graded as it stands (here: empty patch object)


def test_phase_guard_completion_pattern_completes_untouched(tmp_path):
    # The one healthy Stage 1 setup shape: 26 calls, 695,742 charged
    # tokens, completes. 25 shell calls + the done call at 26,752
    # charged tokens each = 695,552, inside both guard bounds.
    script = {"constitution": [("shell", 26000, 752)] * 25 + [("done", 26000, 752)]}
    for phase in ("specify", "plan", "tasks", "implement", "converge"):
        script[phase] = [("done", 100, 50)]
    store, provider, result = run_attempt(tmp_path, "spec_kit", script)
    assert "phase_exhausted" not in result
    constitution_calls = [c for c in store.events("calls") if c["phase"] == "constitution"]
    assert len(constitution_calls) == 26
    assert any(p["phase"] == "constitution" and not p.get("setup_reused")
               for p in store.events("phases"))


def test_phase_guard_implement_is_token_exempt_but_call_capped(tmp_path):
    script = done_script(("constitution", "specify", "plan", "tasks", "converge"))
    # 25 delivery calls at 50,000 charged tokens: 1,250,000 phase
    # tokens, above the token guard — exempt; below the call cap.
    script["implement"] = [("shell", 50000, 0)] * 24 + [("done", 50000, 0)]
    store, provider, result = run_attempt(
        tmp_path, "spec_kit", script, {"token_cap": 3000000})
    assert "phase_exhausted" not in result
    implement = [c for c in store.events("calls") if c["phase"] == "implement"]
    assert sum(c["input_tokens"] for c in implement) == 1250000


def test_phase_guard_call_cap_trips_even_when_tokens_are_small(tmp_path):
    script = done_script(("specify", "plan", "tasks", "implement", "converge"))
    script["constitution"] = [("shell", 10, 0)]  # never done, tiny tokens
    store, provider, result = run_attempt(tmp_path, "spec_kit", script)
    calls = [c for c in store.events("calls") if c["phase"] == "constitution"]
    assert result["phase_exhausted"] == "constitution"
    assert len(calls) == 40


def test_phase_guard_baseline_loop_is_unguarded(tmp_path):
    # 45 shell calls and 1,350,000 charged tokens: past BOTH phase
    # guard bounds (40 calls / 900,000 tokens), inside the attempt
    # cap, which continues to apply to the baseline arm unchanged.
    script = {"solve": [("shell", 30000, 0)] * 45 + [("done", 100, 50)]}
    store, provider, result = run_attempt(tmp_path, "baseline", script)
    assert "phase_exhausted" not in result
    assert len([c for c in store.events("calls") if c["phase"] == "solve"]) == 46


# ---------------- execute_attempt level: construction reuse ----------------

def test_reuse_places_the_frozen_workspace_and_issues_zero_calls(tmp_path):
    store = Store(tmp_path)
    workspace = store.artifact(workflow_tar())
    completion = store.artifact(b"{}")
    store.append("campaign_setups", {
        "attempt_id": "TASK--campaign-setup", "task_id": "TASK",
        "setup_key": "TASK", "artifact": completion,
        "record": {"action": "done", "summary": "frozen"},
        "workspace_artifact": workspace,
        "constitution_file": {"path": ".specify/memory/constitution.md",
                              "sha256": CONSTITUTION_SHA}})
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit", "repeat": 1}
    script = done_script(("specify", "plan", "tasks", "implement", "converge"))
    script["constitution"] = [("done", 1, 1)]  # must never be queried
    provider = RecordingProvider(store, identity, script)
    sandbox = FakeSandbox()
    result = runner.execute_attempt(ROOT, {"problem_statement": "fixture"}, "spec_kit",
                                    provider, sandbox, store, identity,
                                    {**BASE_CFG, "share_campaign_setup": True})
    assert "constitution" not in provider.queried
    record = [p for p in store.events("phases") if p["phase"] == "constitution"][0]
    assert record["setup_reused"] is True
    assert record["setup_workspace"] == "placed"
    assert record["setup_artifact_sha256"] == workspace["sha256"]
    assert record["constitution_sha256"] == CONSTITUTION_SHA
    assert any("tar -xf" in c for c in sandbox.commands)


# ---------------- run() level: construction gate, probe, taxonomy ----------

TASKS = [{"instance_id": "TASK_A", "image": "imgA", "base_commit": "baseA",
          "problem_statement": "fixture A"},
         {"instance_id": "TASK_B", "image": "imgB", "base_commit": "baseB",
          "problem_statement": "fixture B"}]
FakeSandbox.BASE_BY_IMAGE = {"imgA": "baseA", "imgB": "baseB"}


def entry(task, arm, repeat=1):
    return {"task_id": task, "arm": arm, "repeat": repeat, "seed": 20261021,
            "attempt_id": f"{task}--{arm}--r{repeat}"}


def run_campaign(tmp_path, monkeypatch, schedule, scripts, cfg_extra=None,
                 probe=None):
    cfg = {**BASE_CFG, "share_campaign_setup": True, **(cfg_extra or {})}
    manifest = {"freeze_id": "f" * 64, "config": cfg,
                "tasks": {"tasks": TASKS}, "schedule": schedule}
    monkeypatch.setattr(runner, "verify_freeze", lambda root, m: m["freeze_id"])
    monkeypatch.setattr(runner, "validate_live", lambda m, smoke=False: None)
    monkeypatch.setattr(runner, "DockerSandbox", FakeSandbox)
    if probe is not None:
        monkeypatch.setattr(runner, "probe_worker", probe)

    def factory(cfg_, store, budget, identity):
        return RecordingProvider(store, identity, scripts[identity["attempt_id"]])

    monkeypatch.setattr(runner, "make_provider", factory)
    out = tmp_path / "store"
    runner.run(ROOT, manifest, out)
    return Store(out)


def construction_script(calls=3):
    return {"constitution": [("shell", 1000, 500)] * (calls - 1) + [("done", 1000, 500)]}


def attempt_script():
    return done_script(("constitution", "specify", "plan", "tasks", "implement",
                        "converge", "solve"))


def test_construction_runs_once_and_both_attempts_reuse_it(tmp_path, monkeypatch):
    scripts = {"TASK_A--campaign-setup": construction_script(),
               "TASK_A--spec_kit--r1": attempt_script(),
               "TASK_A--spec_kit--r2": attempt_script()}
    store = run_campaign(tmp_path, monkeypatch,
                         [entry("TASK_A", "spec_kit", 1), entry("TASK_A", "spec_kit", 2)],
                         scripts)
    setups = store.events("campaign_setups")
    assert len(setups) == 1
    assert setups[0]["attempt_id"] == "TASK_A--campaign-setup"
    assert setups[0]["workspace_artifact"]["sha256"]
    assert setups[0]["constitution_file"]["sha256"] == CONSTITUTION_SHA
    construction_calls = [c for c in store.events("calls")
                          if c.get("purpose") == "campaign_setup"]
    assert len(construction_calls) == 3
    assert all(c["phase"] == "constitution" for c in construction_calls)
    reuse = [p for p in store.events("phases") if p.get("setup_reused")]
    assert len(reuse) == 2
    assert all(p["setup_workspace"] == "placed" for p in reuse)
    attempt_constitution_calls = [c for c in store.events("calls")
                                  if c.get("purpose") != "campaign_setup"
                                  and c["phase"] == "constitution"]
    assert attempt_constitution_calls == []
    terminal = [a for a in store.events("attempts") if a["status"] != "started"]
    assert {a["status"] for a in terminal} == {"completed"}


def test_construction_failure_skips_the_task_and_the_run_continues(tmp_path, monkeypatch):
    scripts = {"TASK_A--campaign-setup": {"constitution": [("raise",)]},
               "TASK_B--campaign-setup": construction_script(),
               "TASK_B--spec_kit--r1": attempt_script()}
    store = run_campaign(tmp_path, monkeypatch,
                         [entry("TASK_A", "baseline"), entry("TASK_A", "spec_kit"),
                          entry("TASK_B", "spec_kit")], scripts)
    attempts = store.events("attempts")
    a_terminal = [a for a in attempts if a["task_id"] == "TASK_A" and a["status"] != "started"]
    assert len(a_terminal) == 2
    assert all(a["status"] == "skipped" and "task_setup_failed" in a["reason"]
               for a in a_terminal)
    kinds = [e["halt_kind"] for e in store.events("tripwires")]
    assert kinds.count("task_setup_failed") == 3  # construction + two admissions
    b_terminal = [a for a in attempts if a["task_id"] == "TASK_B" and a["status"] != "started"]
    assert [a["status"] for a in b_terminal] == ["completed"]


def test_runaway_constitution_scores_as_phase_budget_exhausted(tmp_path, monkeypatch):
    scripts = {"TASK_A--campaign-setup": construction_script(),
               "TASK_A--spec_kit--r1": {**attempt_script(),
                                        "specify": [("shell", 40000, 0)]},
               "TASK_A--baseline--r1": attempt_script()}
    store = run_campaign(tmp_path, monkeypatch,
                         [entry("TASK_A", "spec_kit"), entry("TASK_A", "baseline")],
                         scripts)
    terminal = {a["attempt_id"]: a for a in store.events("attempts")
                if a["status"] != "started"}
    runaway = terminal["TASK_A--spec_kit--r1"]
    assert runaway["status"] == "limit"
    assert runaway["reason"] == "phase_budget_exhausted:specify"
    event = [e for e in store.events("tripwires")
             if e["attempt_id"] == "TASK_A--spec_kit--r1"][0]
    assert event["halt_class"] == "model_outcome"
    assert event["halt_kind"] == "phase_budget_exhausted"
    assert event["behavior"] == "score_and_continue"
    # score-and-continue proven at run level: the next entry still ran.
    assert terminal["TASK_A--baseline--r1"]["status"] == "completed"


@pytest.mark.parametrize("probe", [
    {"busy": True, "model_ok": True, "error": None, "probed_at": "t"},
    {"busy": None, "model_ok": False, "error": "URLError", "probed_at": "t"},
])
def test_busy_or_unprovable_worker_blocks_attempts_and_halts_at_three(
        tmp_path, monkeypatch, probe):
    scripts = {f"TASK_A--spec_kit--r{i}": attempt_script() for i in (1, 2)}
    scripts["TASK_A--campaign-setup"] = construction_script()
    store = run_campaign(tmp_path, monkeypatch,
                         [entry("TASK_A", "spec_kit", 1), entry("TASK_A", "spec_kit", 2),
                          entry("TASK_A", "baseline", 1), entry("TASK_A", "baseline", 2)],
                         scripts, cfg_extra={"provider_backend": "local",
                                             "worker_availability_probe": True},
                         probe=lambda policy=None: probe)
    assert [a for a in store.events("attempts") if a["status"] == "started"] == []
    kinds = [e["kind"] for e in store.events("worker_probes")]
    assert kinds == ["worker_busy_block"] * 3 + ["worker_busy_stage_halt"]


def test_free_worker_probe_is_recorded_on_the_attempt(tmp_path, monkeypatch):
    probe = {"busy": False, "model_ok": True, "error": None, "probed_at": "t"}
    scripts = {"TASK_A--campaign-setup": construction_script(),
               "TASK_A--baseline--r1": attempt_script()}
    store = run_campaign(tmp_path, monkeypatch, [entry("TASK_A", "baseline")],
                         scripts, cfg_extra={"provider_backend": "local",
                                             "worker_availability_probe": True},
                         probe=lambda policy=None: probe)
    started = [a for a in store.events("attempts") if a["status"] == "started"]
    assert started and started[0]["worker_probe"]["busy"] is False
