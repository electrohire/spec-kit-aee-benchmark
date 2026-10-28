"""F1 (Defaults Tournament, ratified 2026-10-26): genesis
preamble suppression in the residual protocol.

The tournament's factorial priced one stream transform beyond
the champion stack: at every segment genesis, the brief's
standing messages travel as digest reference lines instead of
full text (system messages in full, the problem statement
verbatim). Priced exactly over the frozen campaign corpus:
3,047,322 sent against the champion's 3,298,151 — a margin of
250,829, separated by arithmetic, not noise (tournament record,
Phases 0–2). These tests pin the transform's shape at the
session seam and the wiring default at the MiniModel seam; the
full-corpus acceptance replay that reproduces the priced cell
with this machinery is desktop evidence, cited in
docs/default-stack.md.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner import residual
from benchmark_runner.context import assemble_history, estimate_tokens
from benchmark_runner.residual import (
    ResidualSession, ResidualSyncError, apply_genesis_plan,
    entry_id, genesis_reference_line, suppress_genesis_brief)
from benchmark_runner.runner import MiniModel

CAP = 57344
SYSTEM = "SYSTEM-INSTRUCTIONS-SENTINEL: act as the agent. " + (
    "Follow the steps. " * 20)
PROBLEM = "PROBLEM-SENTINEL: the widget frobnicate() returns None."
PHASE = ("Current phase: specify\n"
         "PHASE-PROMPT-SENTINEL: write the specification. "
         + "Standing instruction text for the phase. " * 60)
CFG = {"max_input_tokens": CAP, "residual_protocol": True}
SHELL = json.dumps({"action": "shell", "command": "true"})


def brief():
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROBLEM},
            {"role": "user", "content": PHASE}]


def action(i):
    return {"role": "assistant",
            "content": json.dumps({"action": "shell",
                                   "command": f"run-step-{i}"})}


def observation(i):
    return {"role": "user", "content": json.dumps(
        {"stdout": f"OBS-{i}-SENTINEL", "stderr": "", "exit_code": 0})}


class CaptureProvider:
    def __init__(self):
        self.payloads = []
        self.store = None
        self.identity = {}

    def query(self, messages, phase, timeout):
        self.payloads.append([dict(m) for m in messages])
        return SHELL


def drive_model(cfg, steps=2):
    provider = CaptureProvider()
    model = MiniModel(provider, time.monotonic() + 3600, cfg=cfg)
    model.phase = "specify"
    history = brief()
    for i in range(steps):
        reply = model.query(history)
        history.append({"role": "assistant", "content": reply["content"]})
        history.append(observation(i))
    model.query(history)
    return provider


# ---------- the transform itself ----------

def test_transform_shape_system_and_problem_kept_phase_referenced():
    original = brief()
    effective, plan = suppress_genesis_brief(original)
    # System text in full; the problem statement verbatim.
    assert effective[0] == original[0]
    assert effective[1] == original[1]
    # The standing phase prompt is now a reference line: its body
    # is absent, its identity recoverable from the line's id.
    ref = effective[2]
    assert ref["role"] == "user"
    assert "PHASE-PROMPT-SENTINEL" not in ref["content"]
    parsed = json.loads(ref["content"])
    assert parsed["id"] == entry_id(original[2])
    assert parsed["kind"] == "brief"
    assert parsed["step"] == 1  # position within the standing list
    assert parsed["first_line"] == "Current phase: specify"
    # The reference line is the shared constructor's output.
    assert ref == genesis_reference_line(original[2], 1)
    # Plan accounting matches the tournament's construction.
    assert plan["standing_ids"].keys() == {0, 2}
    assert plan["refs_by_idx"].keys() == {2}
    assert plan["before_tokens"] == estimate_tokens(
        [original[0], original[2]])
    assert plan["after_tokens"] == estimate_tokens(
        [original[0], ref])
    assert plan["after_tokens"] < plan["before_tokens"]


def test_transform_passes_post_brief_messages_through():
    history = brief() + [action(0), observation(0)]
    effective, plan = suppress_genesis_brief(history)
    assert effective[3:] == history[3:]
    assert apply_genesis_plan(history, plan) == effective


def test_transform_on_a_history_with_no_problem_message():
    history = [{"role": "system", "content": SYSTEM},
               {"role": "assistant", "content": SHELL}]
    effective, plan = suppress_genesis_brief(history)
    # The system message is the only standing message and is kept.
    assert effective == history
    assert plan["refs_by_idx"] == {}


# ---------- the session seam ----------

def test_session_suppressed_genesis_syncs_and_references():
    session = ResidualSession(genesis_suppression=True)
    history = brief()
    for i in range(3):
        session.view(history, CAP, phase="specify")
        entries, digest = residual.reconstruct_state(session.sent_views)
        assert digest == session.state_digest()
        assert [e["id"] for e in entries] == \
            [e["id"] for e in session.entries()]
        history.append(action(i))
        history.append(observation(i))
    genesis = session.sent_views[0]
    joined = "".join(m["content"] for m in genesis)
    assert "PHASE-PROMPT-SENTINEL" not in joined
    assert SYSTEM in joined
    assert PROBLEM in joined
    stats = session.genesis_suppression_stats
    assert stats["reference_lines"] == 1
    assert stats["preamble_after_tokens"] < stats["preamble_before_tokens"]


def test_session_class_default_keeps_the_full_genesis():
    session = ResidualSession()
    result = session.view(brief(), CAP, phase="specify")
    assert "PHASE-PROMPT-SENTINEL" in "".join(
        m["content"] for m in result.messages)
    plain = assemble_history(brief(), CAP)
    assert result.messages == plain.messages
    assert session.genesis_suppression_stats is None


def test_edited_genesis_standing_message_is_a_divergence():
    session = ResidualSession(genesis_suppression=True)
    history = brief()
    session.view(history, CAP, phase="specify")
    history.append(action(0))
    history.append(observation(0))
    history[2] = {"role": "user",
                  "content": "Current phase: specify\nedited"}
    try:
        session.view(history, CAP, phase="specify")
    except ResidualSyncError:
        pass
    else:
        raise AssertionError("edited genesis standing message "
                             "did not raise a divergence")


# ---------- the wiring seam (the ratified default) ----------

def test_wiring_default_suppresses_the_genesis():
    provider = drive_model(CFG)
    genesis = provider.payloads[0]
    joined = "".join(m["content"] for m in genesis)
    assert "PHASE-PROMPT-SENTINEL" not in joined
    assert SYSTEM in joined and PROBLEM in joined


def test_wiring_opt_out_restores_the_unsuppressed_genesis():
    provider = drive_model(
        {**CFG, "genesis_preamble_suppression": False})
    plain = assemble_history(brief(), CAP)
    assert provider.payloads[0] == plain.messages
    assert "PHASE-PROMPT-SENTINEL" in "".join(
        m["content"] for m in provider.payloads[0])


def test_wiring_suppresses_every_segment_genesis():
    provider = CaptureProvider()
    model = MiniModel(provider, time.monotonic() + 3600, cfg=CFG)
    history = brief()
    model.phase = "specify"
    reply = model.query(history)
    history.append({"role": "assistant", "content": reply["content"]})
    history.append(observation(0))
    # Phase boundary: the wiring re-anchors with a fresh session,
    # whose genesis is the boundary view — suppressed as well.
    model.phase = "plan"
    model.query(history)
    boundary_genesis = provider.payloads[-1]
    joined = "".join(m["content"] for m in boundary_genesis)
    assert "PHASE-PROMPT-SENTINEL" not in joined
    assert SYSTEM in joined and PROBLEM in joined
