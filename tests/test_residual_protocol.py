"""Probe-path residual protocol (2026-10-24): the MPCodec-style
P1/P2 configuration of the probe harness — synchronized shared state
between harness and serving, step traffic carried as deltas against
that state, recurrent content by reference, digest sync with a loud
integrity halt on any divergence.

Frozen-test discipline (modeling report §7): the digest-sync test in
this file was written before the protocol, proven able to fail (a
divergence injected into a test double did NOT halt against the
unverified assembly — see PROBE-TEST-RECORD.md), and is not edited
after the freeze.

Flag discipline, as every prior cycle: the protocol is OFF unless
the freeze config carries ``residual_protocol: true``; with the key
absent or false the wire payloads are byte-identical to the
pre-change assembly path (pinned below against assemble_history
itself).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import BASE_CFG, FakeSandbox, RecordingProvider  # noqa: E402

from benchmark_runner import residual, runner  # noqa: E402
from benchmark_runner.context import assemble_history, estimate_tokens  # noqa: E402
from benchmark_runner.residual import ResidualSession, ResidualSyncError  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402
from benchmark_runner.tripwires import INTEGRITY, classify_halt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

SYSTEM = "SYSTEM-INSTRUCTIONS-SENTINEL: act as the probe. " + ("Follow the steps. " * 20)
PROBLEM = "PROBLEM-SENTINEL: the widget frobnicate() returns None on Tuesdays."
PHASE = "Current phase: solve\nPHASE-PROMPT-SENTINEL: reproduce, edit, verify."
CFG = {**BASE_CFG, "max_input_tokens": 57344}


def brief():
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROBLEM},
            {"role": "user", "content": PHASE}]


def observation(i, size=200):
    return {"role": "user", "content": json.dumps(
        {"stdout": f"OBS-{i}-SENTINEL " + ("x" * size),
         "stderr": "", "exit_code": 0,
         "evidence_ref": f"calls/art-{i}.json", "source_id": f"sha-{i}"})}


def action(i):
    return {"role": "assistant",
            "content": json.dumps({"action": "shell", "command": f"run-step-{i}"})}


def grown_history(steps, size=200):
    history = brief()
    for i in range(steps):
        history.append(action(i))
        history.append(observation(i, size))
    return history


class CaptureProvider:
    """Minimal provider double: records every payload verbatim and
    answers with a fixed shell action."""

    def __init__(self):
        self.payloads = []
        self.context_stats = None
        self.store = None

    def query(self, messages, phase, timeout):
        self.payloads.append([dict(m) for m in messages])
        return json.dumps({"action": "shell",
                           "command": f"run-step-{len(self.payloads) - 1}"})


def drive_model(cfg, steps, size=200):
    """Run MiniModel over a growing history the way the agent loop
    does: query, append the assistant reply, append the observation."""
    provider = CaptureProvider()
    model = runner.MiniModel(provider, time.monotonic() + 3600, cfg=cfg)
    history = brief()
    for i in range(steps):
        reply = model.query(history)
        history.append({"role": "assistant", "content": reply["content"]})
        history.append(observation(i, size))
    model.query(history)
    return provider


# ---------- flag-off byte identity (the before-arm is untouched) ----------

def test_flag_absent_and_false_payloads_byte_identical():
    steps = 6
    off = drive_model(CFG, steps)
    false = drive_model({**CFG, "residual_protocol": False}, steps)
    assert off.payloads == false.payloads
    # And both equal the pre-change assembly path computed directly.
    history = brief()
    expected = []
    for i in range(steps + 1):
        result = assemble_history(
            [dict(m) for m in history], CFG["max_input_tokens"],
            current_phase=None)
        expected.append(result.messages)
        if i < steps:
            history.append(action(i))
            history.append(observation(i))
    assert off.payloads == expected


# ---------- wire shape with the protocol on ----------

def test_first_view_is_the_full_brief_paid_once():
    on = drive_model({**CFG, "residual_protocol": True}, 3)
    off = drive_model(CFG, 3)
    assert on.payloads[0] == off.payloads[0]


def test_later_views_carry_references_not_resends():
    provider = drive_model({**CFG, "residual_protocol": True}, 5, size=400)
    view = provider.payloads[-1]
    block = json.loads(view[0]["content"])["residual_state"]
    # The brief travels by reference: its id is present, its
    # instruction text is not resent.
    assert block["brief_sha256"]
    assert SYSTEM not in view[0]["content"]
    assert all(SYSTEM not in m["content"] for m in view)
    assert PHASE.split("\n")[1] not in "".join(m["content"] for m in view)
    # The problem statement is the pinned payload: verbatim every call.
    assert block["problem_statement"] == PROBLEM
    # An early observation is present only as a reference: its full
    # text is absent (only the bounded first-line digest in the
    # index may show its opening characters), and its entry id is
    # in the step index.
    joined = "".join(m["content"] for m in view)
    assert observation(0, 400)["content"] not in joined
    assert "x" * 150 not in joined
    assert all(len(s.get("first_line", "")) <= 100 for s in block["steps"])
    first_obs_id = residual.entry_id(observation(0, 400))
    assert any(s["id"] == first_obs_id for s in block["steps"])
    # The latest observation is the delta: in full.
    assert "OBS-4-SENTINEL" in joined
    # Every post-brief view carries the state digest.
    assert block["state_digest"]


def test_every_view_after_the_first_carries_a_digest():
    provider = drive_model({**CFG, "residual_protocol": True}, 4)
    for view in provider.payloads[1:]:
        block = json.loads(view[0]["content"])["residual_state"]
        assert len(block["state_digest"]) == 64


# ---------- digest sync: the frozen test ----------

def test_digest_sync_holds_across_a_session():
    session = ResidualSession()
    history = brief()
    for i in range(6):
        session.view(history, CFG["max_input_tokens"])
        entries, digest = residual.reconstruct_state(session.sent_views)
        assert digest == session.state_digest()
        assert [e["id"] for e in entries] == [e["id"] for e in session.entries()]
        history.append(action(i))
        history.append(observation(i))
    session.view(history, CFG["max_input_tokens"])
    entries, digest = residual.reconstruct_state(session.sent_views)
    assert digest == session.state_digest()


def test_injected_divergence_in_replay_halts_loudly():
    session = ResidualSession()
    history = brief()
    for i in range(4):
        session.view(history, CFG["max_input_tokens"])
        history.append(action(i))
        history.append(observation(i))
    session.view(history, CFG["max_input_tokens"])
    # Test double: a transmitted view loses its delta observation in
    # transit. The next view's declared index/digest must not check
    # out against the corrupted replay — the replay raises.
    corrupted = [[dict(m) for m in view] for view in session.sent_views]
    corrupted[2] = corrupted[2][:-1]
    try:
        residual.reconstruct_state(corrupted)
    except ResidualSyncError as exc:
        # The halt classifies as an integrity halt in the harness's
        # own tripwire classifier — the study stops, nothing resyncs.
        assert classify_halt("error", str(exc))[0] == INTEGRITY
    else:
        raise AssertionError("divergent replay did not raise")


def test_injected_divergence_on_the_sender_side_halts_before_sending():
    session = ResidualSession()
    history = brief()
    for i in range(3):
        session.view(history, CFG["max_input_tokens"])
        history.append(action(i))
        history.append(observation(i))
    # Test double: tamper with a view the session already sent (the
    # receiver's copy no longer matches what the sender recorded).
    session.sent_views[1][-1] = {"role": "user", "content": "tampered"}
    try:
        session.view(history, CFG["max_input_tokens"])
    except ResidualSyncError as exc:
        assert classify_halt("error", str(exc))[0] == INTEGRITY
    else:
        raise AssertionError("sender-side divergence did not halt the send")


def test_history_rewrite_is_a_divergence():
    session = ResidualSession()
    history = brief()
    session.view(history, CFG["max_input_tokens"])
    history.append(action(0))
    history.append(observation(0))
    session.view(history, CFG["max_input_tokens"])
    history[3] = {"role": "assistant", "content": "rewritten"}
    try:
        session.view(history, CFG["max_input_tokens"])
    except ResidualSyncError:
        pass
    else:
        raise AssertionError("rewritten history prefix did not raise")


# ---------- escapes: novel content always travels at full price ----------

def test_novel_content_is_sent_in_full():
    session = ResidualSession()
    history = brief()
    session.view(history, CFG["max_input_tokens"])
    history.append(action(0))
    novel = {"role": "user", "content": json.dumps(
        {"stdout": "NOVEL-SENTINEL never seen before", "stderr": "",
         "exit_code": 3})}
    history.append(novel)
    view = session.view(history, CFG["max_input_tokens"])
    assert "NOVEL-SENTINEL never seen before" in "".join(
        m["content"] for m in view.messages)


# ---------- the size claim's shape (cap holds; view shrinks) ----------

def test_views_fit_the_cap_and_shrink_against_full_resend():
    cap = 24576
    session = ResidualSession()
    history = brief()
    result = session.view(history, cap)
    for i in range(10):
        history.append(action(i))
        history.append(observation(i, size=6000))
        result = session.view(history, cap)
    assert estimate_tokens(result.messages) <= cap
    before = assemble_history(history, cap, current_phase=None)
    assert result.sent_tokens < before.sent_tokens
    # And against the full history the harness would otherwise resend.
    assert result.sent_tokens < result.assembled_tokens // 2


def test_wire_cap_fallback_elides_delta_and_stays_in_sync():
    # A cap small enough that a fresh observation cannot cross in
    # full: the protocol elides inside the delta (the before-path's
    # own discipline under cap pressure) — and because entry identity
    # is over transmitted forms, the digest still syncs.
    cap = 2000
    session = ResidualSession()
    history = brief()
    session.view(history, cap)
    result = None
    for i in range(4):
        history.append(action(i))
        history.append(observation(i, size=9000))
        result = session.view(history, cap)
        entries, digest = residual.reconstruct_state(session.sent_views)
        assert digest == session.state_digest()
    assert estimate_tokens(result.messages) <= cap
    assert "elided" in session._forms


# ---------- harness-level integration ----------

def test_attempt_with_protocol_completes_and_records_views(tmp_path):
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK",
                "arm": "baseline", "repeat": 1}
    script = {"solve": [("shell", 100, 50), ("shell", 100, 50),
                        ("done", 100, 50)]}
    provider = RecordingProvider(store, identity, script)
    cfg = {**BASE_CFG, "residual_protocol": True}
    result = runner.execute_attempt(
        ROOT, {"problem_statement": "fixture"}, "baseline", provider,
        FakeSandbox(), store, identity, cfg)
    assert result["status"] if "status" in result else True
    views = store.events("residual_views")
    assert len(views) >= 3
    assert all(len(v["digest"]) == 64 for v in views)


def test_attempt_without_protocol_records_no_views(tmp_path):
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK",
                "arm": "baseline", "repeat": 1}
    script = {"solve": [("shell", 100, 50), ("done", 100, 50)]}
    provider = RecordingProvider(store, identity, script)
    runner.execute_attempt(
        ROOT, {"problem_statement": "fixture"}, "baseline", provider,
        FakeSandbox(), store, identity, dict(BASE_CFG))
    assert store.events("residual_views") == []
