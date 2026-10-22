"""Stage A (2026-10-22) acceptance tests: the edit-conversion
scaffold (plan requirements H1-H3), the no-self-critique exclusion
(H4, by construction — nothing to execute), and the H5-P provider
passthrough for Pair D's registered serving.

All offline, in the established scripted-attempt style
(RecordingProvider + FakeSandbox from tests/test_amendment1_runner.py,
extended here with per-step commands and a diff-aware sandbox; the
H5-P tests reuse the stub HTTP server from
tests/test_amendment1_transport.py).

Freeze-configuration discipline, exactly as Cycle 5's drafting
reserve: every Stage A behavior is OFF unless the freeze config
carries its key, and the keys-absent pins below reproduce the
pre-change semantics.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import BASE_CFG, FakeSandbox, RecordingProvider  # noqa: E402
from test_amendment1_transport import (  # noqa: E402
    CFG as LOCAL_CFG, IDENTITY as LOCAL_IDENTITY, MODEL, stub_server)

from benchmark_runner import runner  # noqa: E402
from benchmark_runner.accounting import Budget  # noqa: E402
from benchmark_runner.local_provider import LocalProvider  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PATCH_TEXT = "diff --git a/fix.py b/fix.py\n--- a/fix.py\n+++ b/fix.py\n+fixed\n"
IDENTITY = {"attempt_id": "att-1", "task_id": "TASK", "arm": "baseline", "repeat": 1}


class StageAProvider(RecordingProvider):
    """RecordingProvider with two extensions: each query's message
    contents are captured (for system/injected-message assertions),
    and a script step may carry a 4th element, the shell command to
    return: ("shell", tin, tout, "command")."""

    def __init__(self, store, identity, script):
        super().__init__(store, identity, script)
        self.messages_seen = []  # per query: [message contents]

    def query(self, messages, phase, timeout):
        self.messages_seen.append([m.get("content", "") for m in messages])
        self.queried.append(phase)
        idx = self.counts.get(phase, 0)
        self.counts[phase] = idx + 1
        steps = self.script[phase]
        step = steps[min(idx, len(steps) - 1)]
        _, tin, tout = step[:3]
        self.store.append("calls", {**self.identity, "phase": phase,
                                    "call_id": f"{self.identity['attempt_id']}-{phase}-{idx}",
                                    "input_tokens": tin, "output_tokens": tout,
                                    "usage_status": "reported"})
        if step[0] == "done":
            return json.dumps({"action": "done", "summary": "fixture",
                               "claims": {"schema_version": "1.0", "claims": []}})
        command = step[3] if len(step) > 3 else "true"
        return json.dumps({"action": "shell", "command": command})

    def all_contents(self):
        return [content for contents in self.messages_seen for content in contents]


class StageASandbox(FakeSandbox):
    """FakeSandbox whose git diff reflects an edit the scripted
    model makes with the "make-the-edit" shell command."""

    def __init__(self, image=None):
        super().__init__(image)
        self.diff_text = ""

    def execute(self, command, timeout=60):
        if command == "make-the-edit":
            self.commands.append(command)
            self.diff_text = PATCH_TEXT
            return {"exit_code": 0, "stdout": "edited", "stderr": ""}
        if "git diff" in command:
            self.commands.append(command)
            return {"exit_code": 0, "stdout": self.diff_text, "stderr": ""}
        return super().execute(command, timeout)


def run_stagea(tmp_path, script, cfg_extra=None, sandbox=None):
    store = Store(tmp_path)
    provider = StageAProvider(store, IDENTITY, script)
    cfg = {**BASE_CFG, **(cfg_extra or {})}
    result = runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                    "baseline", provider,
                                    sandbox or StageASandbox(), store,
                                    IDENTITY, cfg)
    return store, provider, result


def patch_bytes(tmp_path, result):
    return (tmp_path / result["patch"]["path"]).read_bytes()


# ---------------- backward compatibility: keys absent ----------------

def test_keys_absent_reproduces_pre_change_behavior(tmp_path):
    # A plain baseline solve attempt with NO Stage A keys: no
    # scaffold events, the ordinary completion, the patch as the
    # sandbox reports it — the pre-change semantics, pinned.
    script = {"solve": [("shell", 100, 50), ("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script)
    assert store.events("scaffold_events") == []
    assert "phase_exhausted" not in result
    assert patch_bytes(tmp_path, result) == b""
    completed = [p for p in store.events("phases") if p["phase"] == "solve"]
    assert len(completed) == 1 and completed[0].get("artifact")


# ---------------- H1: phase-forcing ----------------

def test_h1_switch_and_nudge_fire_at_registered_fractions_by_calls(tmp_path):
    # max_calls=20: edit switch at ceil(0.40*20)=8 steps, verify
    # nudge at ceil(0.55*20)=11 steps. Tokens stay far below the
    # token thresholds (150/step vs 1.5M cap), so calls fire both.
    script = {"solve": [("shell", 100, 50)] * 14 + [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script, cfg_extra={
        "edit_switch_fraction": 0.40, "verify_nudge_fraction": 0.55,
        "max_calls": 20})
    events = store.events("scaffold_events")
    assert [e["kind"] for e in events] == ["edit_switch", "verify_nudge"]
    switch, nudge = events
    assert switch["step_index"] == 8 and switch["fired_by"] == "calls"
    assert switch["phase_charged_tokens"] == 8 * 150
    assert nudge["step_index"] == 11 and nudge["fired_by"] == "calls"
    assert nudge["phase_charged_tokens"] == 11 * 150
    # Both instructions entered the agent's history (they are in the
    # messages the provider was shown on later queries).
    final_history = provider.messages_seen[-1]
    assert runner.EDIT_SWITCH_INSTRUCTION in final_history
    assert runner.VERIFY_NUDGE_INSTRUCTION in final_history
    assert "phase_exhausted" not in result


def test_h1_token_measure_can_fire_first(tmp_path):
    # token_cap=1000 with small reservations: edit switch at
    # >= 0.40*1000 = 400 charged (3 calls x 150 = 450), verify at
    # >= 550 (4 calls = 600). The call thresholds (ceil(.4*120)=48)
    # are nowhere near, so tokens fire both.
    script = {"solve": [("shell", 100, 50)] * 5 + [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script, cfg_extra={
        "edit_switch_fraction": 0.40, "verify_nudge_fraction": 0.55,
        "token_cap": 1000, "max_input_tokens": 10, "max_output_tokens": 10})
    events = store.events("scaffold_events")
    assert [e["kind"] for e in events] == ["edit_switch", "verify_nudge"]
    assert events[0]["step_index"] == 3 and events[0]["fired_by"] == "tokens"
    assert events[0]["phase_charged_tokens"] == 450
    assert events[1]["step_index"] == 4 and events[1]["fired_by"] == "tokens"
    assert events[1]["phase_charged_tokens"] == 600


def test_h1_events_reconcile_with_the_calls_ledger(tmp_path):
    # Acceptance (5): every scaffold event carries the attempt
    # identity, and its step/charged figures equal the calls ledger
    # prefix at firing time, recomputed independently here.
    script = {"solve": [("shell", 100, 50)] * 14 + [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script, cfg_extra={
        "edit_switch_fraction": 0.40, "verify_nudge_fraction": 0.55,
        "max_calls": 20})
    calls = [c for c in store.events("calls") if c["phase"] == "solve"]
    for event in store.events("scaffold_events"):
        assert event["attempt_id"] == IDENTITY["attempt_id"]
        assert event["task_id"] == IDENTITY["task_id"]
        assert event["arm"] == IDENTITY["arm"]
        assert event["phase"] == "solve"
        assert event["timestamp"]
        prefix = calls[:event["step_index"]]
        assert len(prefix) == event["step_index"]
        assert event["phase_charged_tokens"] == sum(
            c["input_tokens"] + c["output_tokens"] for c in prefix)


# ---------------- H2: empty-patch gate ----------------

def test_h2_empty_done_is_rejected_once_and_retry_patch_is_recorded(tmp_path):
    script = {"solve": [("done", 100, 50),
                        ("shell", 100, 50, "make-the-edit"),
                        ("done", 100, 50)]}
    store, provider, result = run_stagea(
        tmp_path, script, cfg_extra={"empty_patch_gate": True})
    events = store.events("scaffold_events")
    assert [e["kind"] for e in events] == ["empty_patch_gate"]
    assert events[0]["attempt_id"] == IDENTITY["attempt_id"]
    assert events[0]["phase"] == "solve"
    # The retry instruction entered the history, the phase continued
    # (no completion was recorded for the empty done), and the one
    # recorded completion carries the follow-up edit as the patch.
    assert runner.EMPTY_PATCH_GATE_INSTRUCTION in provider.all_contents()
    completed = [p for p in store.events("phases") if p["phase"] == "solve"]
    assert len(completed) == 1
    assert patch_bytes(tmp_path, result) == PATCH_TEXT.encode()


def test_h2_second_empty_done_scores_empty_and_gate_fires_once(tmp_path):
    script = {"solve": [("done", 100, 50)]}  # repeats: done, done, ...
    store, provider, result = run_stagea(
        tmp_path, script, cfg_extra={"empty_patch_gate": True})
    events = store.events("scaffold_events")
    assert [e["kind"] for e in events] == ["empty_patch_gate"]
    assert patch_bytes(tmp_path, result) == b""
    completed = [p for p in store.events("phases") if p["phase"] == "solve"]
    assert len(completed) == 1


def test_h2_gate_absent_empty_done_completes_immediately(tmp_path):
    # Without the key, an empty done is the ordinary completion —
    # one provider query total, no gate event, no retry.
    script = {"solve": [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script)
    assert store.events("scaffold_events") == []
    assert provider.counts["solve"] == 1
    assert patch_bytes(tmp_path, result) == b""


# ---------------- H3: probe solve instruction ----------------

def test_h3_probe_instruction_is_the_frozen_sequence_text():
    text = (ROOT / "prompts" / "probe-solve.md").read_text(encoding="utf-8")
    common = (ROOT / "prompts" / "common.md").read_text(encoding="utf-8")
    # The baseline action protocol is carried verbatim.
    assert text.startswith(common.rstrip("\n"))
    # The canonical task sequence structures the instruction.
    for marker in ("Find and read the relevant code",
                   "reproduction script",
                   "Edit the source",
                   "Rerun the reproduction",
                   "relevant existing tests"):
        assert marker in text
    # Submission discipline: done is a submission and must carry a
    # non-empty repository change.
    assert "non-empty repository change" in text


def test_h3_system_message_uses_probe_instruction_when_configured(tmp_path):
    script = {"solve": [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script, cfg_extra={
        "solve_instruction_path": "prompts/probe-solve.md"})
    expected = (ROOT / "prompts" / "probe-solve.md").read_text(encoding="utf-8")
    assert provider.messages_seen[0][0] == expected


def test_h3_system_message_defaults_to_common_prompt(tmp_path):
    script = {"solve": [("done", 100, 50)]}
    store, provider, result = run_stagea(tmp_path, script)
    expected = (ROOT / "prompts" / "common.md").read_text(encoding="utf-8")
    assert provider.messages_seen[0][0] == expected


# ---------------- H5-P: provider passthrough ----------------

def _local_provider(tmp_path, monkeypatch, base_url, cfg_extra=None):
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    store = Store(tmp_path / "store")
    budget = Budget(store, Decimal("100"), Decimal("25"))
    cfg = {**LOCAL_CFG, **(cfg_extra or {})}
    return LocalProvider(cfg, store, budget, LOCAL_IDENTITY), store


def test_h5p_payload_without_keys_is_the_pre_change_payload(tmp_path, monkeypatch):
    messages = [{"role": "user", "content": "hi"}]
    with stub_server("sse") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.query(messages, "solve", 30)
    # Exact equality: the pre-change payload, nothing added.
    assert server.last_payload == {
        "model": MODEL, "messages": messages,
        "max_completion_tokens": LOCAL_CFG["max_output_tokens"],
        "stream": True, "stream_options": {"include_usage": True}}


def test_h5p_payload_carries_grammar_and_template_kwargs_verbatim(
        tmp_path, monkeypatch):
    messages = [{"role": "user", "content": "hi"}]
    grammar = 'root ::= "{" ws "\\"action\\"" ws ":" ws "\\"shell\\"" ws "}"'
    kwargs = {"preserve_thinking": True, "enable_thinking": False}
    with stub_server("sse") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url, {
            "request_grammar": grammar, "chat_template_kwargs": kwargs})
        provider.query(messages, "solve", 30)
    assert server.last_payload["grammar"] == grammar
    assert server.last_payload["chat_template_kwargs"] == kwargs
    # Nothing else in the payload changed.
    rest = {k: v for k, v in server.last_payload.items()
            if k not in ("grammar", "chat_template_kwargs")}
    assert rest == {"model": MODEL, "messages": messages,
                    "max_completion_tokens": LOCAL_CFG["max_output_tokens"],
                    "stream": True, "stream_options": {"include_usage": True}}
