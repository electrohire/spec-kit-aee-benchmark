"""Cycle 3 (2026-10-22) acceptance tests: C3-F1, the native-format
bridge for the plain-loop adapter.

All offline. The recorded-response fixtures in
``tests/fixtures/cycle3_probe_i_responses.json`` are verbatim
adapter-visible texts from the Cycle 2 probe-(i) freeze store
(``probe-c2-i`` on the coordinator host, extracted exactly as the
adapter saw them — after the local provider's text extraction, in
calls.jsonl order; ``idx`` is the call's position in that order).
The subset is faithful and structurally exhaustive: ALL 14
previously live responses, ALL 14 bare-JSON-in-prose responses,
ALL 31 markup responses whose payload defeats strict JSON parsing,
and 10 representatives of the parseable-payload markup family
(both recorded closing families, across attempts). The full
257-response replay through the bridged adapter was run once
against the complete extracted store (see the Cycle 3 report);
this file pins the subset as the standing automated test.

The pre-bridge parse rule is reproduced here as ``old_parse`` —
the frozen JSON-only rule exactly as MiniModel.query applied it
before the bridge — so identical-behavior claims are tested against
the rule itself, not against a paraphrase.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import BASE_CFG, FakeSandbox  # noqa: E402

from benchmark_runner import runner  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads(
    (ROOT / "tests" / "fixtures" / "cycle3_probe_i_responses.json")
    .read_text(encoding="utf-8"))

CORRECTION = ('Return one JSON object: {"action":"shell","command":"..."} '
              'or {"action":"done","summary":"..."}.')


def old_parse(text):
    """The pre-bridge adapter rule, verbatim in effect: strict
    json.loads, action must be shell/done, a shell command must be
    a string; anything else is invalid."""
    try:
        action = json.loads(text)
        if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
            raise ValueError("expected shell or done")
        if action["action"] == "shell" and not isinstance(action.get("command"), str):
            raise ValueError("shell command must be string")
        return action
    except (ValueError, TypeError):
        return {"action": "invalid"}


# ---------------- Recorded-response replay (the plan's direct test) ---------

def test_fixture_subset_is_the_recorded_shape_it_claims():
    subsets = {}
    for fixture in FIXTURES:
        subsets.setdefault(fixture["subset"], []).append(fixture)
    # All previously live and all structurally distinct dead
    # families are present in full; the parseable markup family is
    # represented.
    assert len(subsets["live"]) == 14
    assert len(subsets["bare_json_in_prose"]) == 14
    assert len(subsets["toolcall_payload_unparseable"]) == 31
    assert len(subsets["toolcall_payload_ok"]) >= 10
    for fixture in FIXTURES:
        assert fixture["old_class"] == (
            "json_live_shell" if old_parse(fixture["text"]).get("action") == "shell"
            else "json_live_done" if old_parse(fixture["text"]).get("action") == "done"
            else "dead")


def test_replay_previously_live_responses_are_identical():
    # Every response the pre-bridge adapter could execute produces
    # the IDENTICAL action object through the bridged adapter —
    # the JSON path is first and untouched.
    live = [f for f in FIXTURES if f["subset"] == "live"]
    assert live
    for fixture in live:
        assert runner.parse_model_action(fixture["text"]) == old_parse(fixture["text"])


def test_replay_previously_dead_markup_responses_now_parse():
    # Every recorded markup response in the subset — parseable
    # payload or envelope-rescued — now yields the executable shell
    # action its payload names, with the payload's command intact.
    markup = [f for f in FIXTURES if f["subset"].startswith("toolcall")]
    assert markup
    for fixture in markup:
        action = runner.parse_model_action(fixture["text"])
        assert action["action"] == "shell", fixture["idx"]
        assert isinstance(action["command"], str) and action["command"]
        assert old_parse(fixture["text"]) == {"action": "invalid"}


def test_replay_bare_json_in_prose_is_unchanged():
    # The seaborn attempt's other dead family — a bare JSON action
    # object preceded by prose, with NO native markup — is not the
    # format the bridge accepts: it remains a format correction,
    # exactly as before (identical behavior, by design and by the
    # plan's identical-behavior requirement).
    bare = [f for f in FIXTURES if f["subset"] == "bare_json_in_prose"]
    assert bare
    for fixture in bare:
        assert runner.parse_model_action(fixture["text"]) == {"action": "invalid"}


# ---------------- The recorded markup families (synthetic pins) -------------

def test_bridge_clean_tool_call_function_keyed():
    text = ('<tool_call>\n{"function": "shell", "command": "ls /testbed"}'
            '\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "ls /testbed"}


def test_bridge_hybrid_stray_closing_tail():
    # The dominant probe-(i) closing: the payload, then
    # </parameter> </function> </tool_call>.
    text = ('<tool_call>\n{"action":"shell","command":"ls /testbed"}'
            '\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "ls /testbed"}


def test_bridge_unterminated_block_cycle1_closing():
    # The Cycle 1 store's dominant closing: stray closers and NO
    # </tool_call> at all — the segment runs to the end of the text.
    text = ('<tool_call>\n{"action":"shell","command":"ls /testbed"}'
            '\n</parameter>\n</function>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "ls /testbed"}


def test_bridge_prose_prefix_is_ignored():
    text = ("I'll start by exploring the repository.\n\n<tool_call>\n"
            '{"function": "shell", "command": "pwd"}\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "pwd"}


def test_bridge_unescaped_inner_quotes_quote_brace_termination():
    # Strict JSON fails on the embedded echo "---"; the envelope's
    # final '"}' still delimits the command deterministically.
    text = ('<tool_call>\n{"action":"shell","command":"ls /testbed; '
            'echo "---"; pwd"}\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": 'ls /testbed; echo "---"; pwd'}


def test_bridge_unescaped_inner_quotes_command_tag_termination():
    # The test_reduction family: the command field is closed by a
    # literal </command> instead of the closing quote-brace.
    text = ('<tool_call>\n{"action": "shell", "command": "pwd && ls '
            '/testbed</command>\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "pwd && ls /testbed"}


def test_bridge_equals_sign_kind_variant():
    # One recorded payload: {"function="shell","command":...}.
    text = ('<tool_call>\n{"function="shell","command":"ls && pwd"}'
            '\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "ls && pwd"}


def test_bridge_done_payload_in_markup():
    # Recorded in the Cycle 1 store (campaign setup): a done action
    # carried in the native markup.
    text = ('<tool_call>\n{"action": "done", "summary": "constitution '
            'written"}\n</parameter>\n</function>')
    assert runner.parse_model_action(text) == {
        "action": "done", "summary": "constitution written"}


def test_bridge_truncated_payload_stays_invalid():
    # No termination at all: the value runs off the end of the
    # response. Not recovered — a format correction, as before.
    text = '<tool_call>\n{"action":"shell","command":"ls /testbed && cat'
    assert runner.parse_model_action(text) == {"action": "invalid"}


def test_bridge_unknown_function_stays_invalid():
    text = ('<tool_call>\n{"function": "read_file", "command": "x"}'
            '\n</tool_call>')
    assert runner.parse_model_action(text) == {"action": "invalid"}


def test_bridge_nonstring_command_stays_invalid():
    text = '<tool_call>\n{"action": "shell", "command": 42}\n</tool_call>'
    assert runner.parse_model_action(text) == {"action": "invalid"}


def test_bridge_no_markup_no_json_stays_invalid():
    assert runner.parse_model_action("Let me think about this problem.") == {
        "action": "invalid"}
    assert runner.parse_model_action("") == {"action": "invalid"}


# ---------------- JSON path precedence and preservation ---------------------

def test_json_path_is_first_and_preserves_extra_fields():
    # A strict-JSON action — including the extra fields phase
    # completions carry (claims, summary) — comes back byte-for-byte
    # the parsed object; the bridge never rewrites it.
    text = json.dumps({"action": "done", "summary": "s",
                       "claims": {"schema_version": "1.0", "claims": []}})
    assert runner.parse_model_action(text) == json.loads(text)
    shell = '{"action":"shell","command":"true"}'
    assert runner.parse_model_action(shell) == {"action": "shell", "command": "true"}


def test_json_path_still_rejects_bad_shapes():
    assert runner.parse_model_action('{"action": "shell"}') == {"action": "invalid"}
    assert runner.parse_model_action('{"action": "other"}') == {"action": "invalid"}
    assert runner.parse_model_action('[1, 2]') == {"action": "invalid"}


# ---------------- MiniModel end to end ---------------------------------------

class TextProvider:
    """A provider returning scripted raw response texts, in order."""

    def __init__(self, texts):
        self.texts = list(texts)

    def query(self, messages, phase, timeout):
        return self.texts.pop(0)


def _model(texts):
    model = runner.MiniModel(TextProvider(texts),
                             time.monotonic() + 600, 60, cfg=None)
    return model


def test_minimodel_executes_bridged_shell_action():
    model = _model(['<tool_call>\n{"function": "shell", "command": "ls"}'
                    '\n</tool_call>'])
    reply = model.query([{"role": "user", "content": "task"}])
    assert model.last == {"action": "shell", "command": "ls"}
    assert reply["extra"]["actions"] == [{"action": "shell", "command": "ls"}]
    # A parsed action gets the normal observation path, NOT the
    # format-correction prompt.
    observed = model.format_observation_messages(
        reply, [{"exit_code": 0, "stdout": "ok"}], {})
    assert observed == [{"role": "user", "content": json.dumps(
        {"exit_code": 0, "stdout": "ok"})}]


def test_minimodel_unparseable_response_is_the_same_correction_as_before():
    model = _model(["prose with no action at all"])
    reply = model.query([{"role": "user", "content": "task"}])
    assert model.last == {"action": "invalid"}
    assert reply["extra"]["actions"] == []
    observed = model.format_observation_messages(reply, [], {})
    assert observed == [{"role": "user", "content": CORRECTION}]


def test_minimodel_baseline_attempt_executes_native_markup(tmp_path):
    # Attempt level, the probe-(i) shape: a baseline (plain-loop)
    # attempt whose model answers ONLY in native markup executes
    # its shell commands through the sandbox and completes on its
    # markup-carried done — zero format corrections.
    class MarkupProvider:
        def __init__(self, store, identity):
            self.store, self.identity = store, identity
            self.n = 0

        def query(self, messages, phase, timeout):
            self.n += 1
            self.store.append("calls", {
                **self.identity, "phase": phase,
                "call_id": f"{self.identity['attempt_id']}-{self.n}",
                "input_tokens": 100, "output_tokens": 50,
                "usage_status": "reported"})
            if self.n == 1:
                return ('<tool_call>\n{"function": "shell", "command": "true"}'
                        '\n</parameter>\n</function>\n</tool_call>')
            return ('<tool_call>\n{"action": "done", "summary": "finished"}'
                    '\n</tool_call>')

    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK",
                "arm": "baseline", "repeat": 1}
    provider = MarkupProvider(store, identity)
    sandbox = FakeSandbox()
    result = runner.execute_attempt(
        ROOT, {"problem_statement": "fixture"}, "baseline", provider,
        sandbox, store, identity, {**BASE_CFG})
    assert sandbox.commands, "the bridged shell action must reach the sandbox"
    assert result["tool_calls"] == 1
    assert result["patch"]
