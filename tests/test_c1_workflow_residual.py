"""C-1 (Benchmarking Improvement Program, 2026-10-25): the
residual protocol inside the workflow path.

The probe path's session assumed a history that only grows. The
workflow driver edits its history at phase boundaries — a
completed phase's terminal action is replaced by its artifact
record — so a session carried across a boundary would meet a
history it never transmitted and raise a divergence. The
workflow wiring therefore re-anchors the session at each phase
change: the boundary view is the new segment's genesis, paid in
full once, and the fresh session indexes from there. These
tests pin that behavior at the MiniModel seam, plus the
flag-off discipline: without residual_protocol in the freeze
config, the provider receives exactly the pre-change assembled
view, byte for byte.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.context import assemble_history
from benchmark_runner.residual import reconstruct_state
from benchmark_runner.runner import MiniModel

CAP = 57344
SHELL = json.dumps({"action": "shell", "command": "true"})


class CapturingProvider:
    def __init__(self):
        self.views = []
        self.store = None
        self.identity = {}

    def query(self, messages, phase, timeout):
        self.views.append([dict(m) for m in messages])
        return SHELL


def make_model(cfg):
    provider = CapturingProvider()
    model = MiniModel(provider, time.monotonic() + 3600, cfg=cfg)
    return model, provider


def brief():
    return [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Fix the widget."},
        {"role": "user", "content": "Current phase: specify\n"
                                    "Write the specification."},
    ]


def step(model, history, observation):
    reply = model.query(history)
    history.append({"role": "assistant", "content": reply["content"]})
    history.append({"role": "user", "content": observation})
    return history


def is_state_block(message):
    try:
        parsed = json.loads(message["content"])
    except (ValueError, KeyError, TypeError):
        return False
    return isinstance(parsed, dict) and "residual_state" in parsed


def test_flag_off_provider_gets_the_plain_assembled_view():
    model, provider = make_model({"max_input_tokens": CAP})
    model.phase = "specify"
    history = step(model, brief(), '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    for view, expected_history in zip(
            provider.views,
            [brief(), history[:5], history]):
        expected = assemble_history(expected_history, CAP).messages
        assert [m["content"] for m in view] == \
               [m["content"] for m in expected]
    assert not any(is_state_block(m) for v in provider.views
                   for m in v)


def test_flag_on_state_blocks_within_a_phase():
    model, provider = make_model(
        {"max_input_tokens": CAP, "residual_protocol": True})
    model.phase = "specify"
    history = step(model, brief(), '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    genesis, later = provider.views[0], provider.views[-1]
    assert not is_state_block(genesis[0])
    assert is_state_block(later[0])
    # The receiver reconstruction over the segment's views
    # reproduces the sender's entry sequence (the session also
    # checks this pre-send; the pin here is the external form).
    entries, digest = reconstruct_state(provider.views[:2])
    assert digest


def test_unmeasured_phase_abstains_by_default():
    # C-4: implement has no replay measurement, so its views are
    # the plain assembled views even with the protocol on, while
    # the measured specify segment around it compresses.
    model, provider = make_model(
        {"max_input_tokens": CAP, "residual_protocol": True})
    model.phase = "specify"
    history = step(model, brief(), '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    assert is_state_block(provider.views[-1][0])
    history[3] = {"role": "assistant",
                  "content": '{"artifact_sha256": "abc123"}'}
    history.append({"role": "user",
                    "content": "Current phase: implement\n"
                               "Write the code."})
    model.phase = "implement"
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    for view in provider.views[-2:]:
        assert not any(is_state_block(m) for m in view)
    # The last view was assembled from the history as it stood
    # before the final step's reply and observation were added.
    expected = assemble_history(history[:-2], CAP,
                                current_phase="implement").messages
    assert [m["content"] for m in provider.views[-1]] == \
           [m["content"] for m in expected]


def test_freeze_config_can_opt_a_class_in():
    # C-4: residual_phases replaces the default measured set —
    # the route by which a newly measured class ships.
    model, provider = make_model(
        {"max_input_tokens": CAP, "residual_protocol": True,
         "residual_phases": ["implement"]})
    model.phase = "implement"
    history = step(model, brief(), '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    assert is_state_block(provider.views[-1][0])


def test_phase_boundary_reanchors_instead_of_diverging():
    model, provider = make_model(
        {"max_input_tokens": CAP, "residual_protocol": True})
    model.phase = "specify"
    history = step(model, brief(), '{"exit_code": 0, "stdout": "ok"}')
    history = step(model, history, '{"exit_code": 0, "stdout": "ok"}')
    # The workflow boundary edit: the completed phase's terminal
    # action is replaced by its artifact record, and the new
    # phase's prompt block is appended.
    history[3] = {"role": "assistant",
                  "content": '{"artifact_sha256": "abc123", '
                             '"summary": "spec written"}'}
    history.append({"role": "user",
                    "content": "Current phase: plan\n"
                               "Write the plan."})
    model.phase = "plan"
    # Must not raise ResidualSyncError, and the boundary view is
    # a genesis: the full edited history, no state block.
    model.query(history)
    boundary = provider.views[-1]
    expected = assemble_history(history, CAP,
                                current_phase="plan").messages
    assert [m["content"] for m in boundary] == \
           [m["content"] for m in expected]
    assert not is_state_block(boundary[0])
    # The new segment then compresses again.
    history.append({"role": "assistant", "content": SHELL})
    history.append({"role": "user",
                    "content": '{"exit_code": 0, "stdout": "ok"}'})
    model.query(history)
    assert is_state_block(provider.views[-1][0])
    entries, digest = reconstruct_state(provider.views[-2:])
    assert digest
