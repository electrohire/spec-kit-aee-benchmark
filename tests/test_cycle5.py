"""Cycle 5 (2026-10-22) acceptance tests: C5-A1 (the split-payload
bridge rescue) and C5-F1 (the drafting reserve).

All offline. The C5-A1 fixtures in
``tests/fixtures/cycle5_campaign_c4_responses.json`` are verbatim
adapter-visible texts from the Cycle 4 freeze store
(``campaign-c4`` — all 52 recorded responses of the single
confirmation attempt, extracted exactly as the adapter saw them;
``idx`` is the call's position in started-at order). Subsets: all
36 native strict-JSON parses, all 13 split-payload markup
responses (with the expected command's sha256/length, computed at
fixture-build time by an independent extraction), both
prose-prefixed bare-JSON responses, and the one truncated
response. The pre-Cycle-5 parse rule is reproduced here as
``old_parse`` — the Cycle 4 frozen rule (strict JSON, then the
Cycle 3 bridge) exactly — so identical-behavior claims are tested
against the rule itself.

The C5-F1 tests are scripted attempts in the Cycle 1 harness
pattern (RecordingProvider + FakeSandbox): a drafting phase that
would consume the whole attempt cap force-advances at the
750,000 drafting sub-cap and spends in implementation, with the
advance event, the carried artifacts, and the token accounting
all exact.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import BASE_CFG, FakeSandbox, RecordingProvider  # noqa: E402

from benchmark_runner import runner  # noqa: E402
from benchmark_runner.accounting import attempt_token_usage  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads(
    (ROOT / "tests" / "fixtures" / "cycle5_campaign_c4_responses.json")
    .read_text(encoding="utf-8"))


def old_parse(text):
    """The Cycle 4 frozen adapter rule: strict json.loads first
    (action shell/done, shell command a string), then the Cycle 3
    native bridge WITHOUT the Cycle 5 split-payload rescue —
    reproduced by calling the two pre-Cycle-5 stages directly."""
    try:
        action = json.loads(text)
        if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
            raise ValueError("expected shell or done")
        if action["action"] == "shell" and not isinstance(action.get("command"), str):
            raise ValueError("shell command must be string")
        return action
    except (ValueError, TypeError):
        pass
    start = text.find(runner._TOOL_CALL_OPEN)
    if start >= 0:
        segment = text[start + len(runner._TOOL_CALL_OPEN):]
        end = segment.find(runner._TOOL_CALL_CLOSE)
        if end >= 0:
            segment = segment[:end]
        action = runner._payload_to_action(runner._first_json_object(segment))
        if action is not None:
            return action
        action = runner._envelope_action(segment)
        if action is not None:
            return action
    return {"action": "invalid"}


# ---------------- C5-A1: recorded-response replay ----------------

def test_fixture_subset_is_the_recorded_shape_it_claims():
    subsets = {}
    for fixture in FIXTURES:
        subsets.setdefault(fixture["subset"], []).append(fixture)
    assert len(FIXTURES) == 52
    assert len(subsets["native_json"]) == 36
    assert len(subsets["split_payload"]) == 13
    assert len(subsets["bare_json_in_prose"]) == 2
    assert len(subsets["truncated_no_payload"]) == 1
    # The labels are the frozen rule's own verdicts.
    for fixture in FIXTURES:
        old = old_parse(fixture["text"])
        if fixture["subset"] == "native_json":
            assert old.get("action") in ("shell", "done"), fixture["idx"]
        else:
            assert old == {"action": "invalid"}, fixture["idx"]


def test_replay_native_parses_are_identical():
    # Every response the Cycle 4 adapter executed produces the
    # IDENTICAL action object under the Cycle 5 code — the strict
    # path is first and untouched, and the new rescue sits behind
    # both pre-existing bridge stages.
    native = [f for f in FIXTURES if f["subset"] == "native_json"]
    assert len(native) == 36
    for fixture in native:
        assert runner.parse_model_action(fixture["text"]) == old_parse(
            fixture["text"]), fixture["idx"]


def test_replay_split_payload_family_now_parses():
    # Every recorded split-payload response now yields the shell
    # action its payload specifies, command byte-exact (checked by
    # hash + length against the independent fixture extraction).
    split = [f for f in FIXTURES if f["subset"] == "split_payload"]
    assert len(split) == 13
    for fixture in split:
        action = runner.parse_model_action(fixture["text"])
        assert action["action"] == fixture["expected_action"], fixture["idx"]
        command = action["command"]
        assert len(command) == fixture["expected_command_len"], fixture["idx"]
        assert hashlib.sha256(command.encode()).hexdigest() == \
            fixture["expected_command_sha256"], fixture["idx"]


def test_replay_other_dead_classes_stay_dead():
    # The prose-prefixed bare-JSON pair (the family Cycle 3
    # adjudicated out of the bridge's scope) and the truncated
    # response (no payload, no termination) remain format
    # corrections under the Cycle 5 code, exactly as frozen.
    for fixture in FIXTURES:
        if fixture["subset"] in ("bare_json_in_prose", "truncated_no_payload"):
            assert runner.parse_model_action(fixture["text"]) == \
                {"action": "invalid"}, fixture["idx"]


# ---------------- C5-A1: synthetic pins ----------------

def test_bridge_split_payload_stray_tag_tail():
    text = ('<tool_call>\n{"function": shell}\n'
            '{"command": ls -la /workflow\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "ls -la /workflow"}


def test_bridge_split_payload_final_quote_brace_before_close():
    text = ('<tool_call>\n{"function": shell}\n'
            '{"command": cat /workflow/spec.md"}\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "cat /workflow/spec.md"}


def test_bridge_split_payload_final_quote_brace_no_close():
    text = '<tool_call>\n{"action": shell}\n{"command": echo hi"}'
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": "echo hi"}


def test_bridge_split_payload_raw_value_keeps_inner_quotes():
    # The value is raw text: unescaped quotes and newlines inside
    # it are payload, not structure.
    text = ('<tool_call>\n{"function": shell}\n'
            '{"command": python -c "print(1)"\nls /tmp\n'
            '</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "shell", "command": 'python -c "print(1)"\nls /tmp'}


def test_bridge_split_payload_unterminated_stays_dead():
    # No stray-tag tail and no final '"}': the value runs off the
    # end of the response — truncated, not recovered.
    text = '<tool_call>\n{"function": shell}\n{"command": ls /workf'
    assert runner.parse_model_action(text) == {"action": "invalid"}


def test_bridge_split_payload_kind_field_mismatch_stays_dead():
    text = ('<tool_call>\n{"function": done}\n'
            '{"command": ls\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {"action": "invalid"}


def test_bridge_split_payload_done_summary():
    text = ('<tool_call>\n{"function": done}\n'
            '{"summary": drafted the plan\n</parameter>\n</function>\n</tool_call>')
    assert runner.parse_model_action(text) == {
        "action": "done", "summary": "drafted the plan"}


# ---------------- C5-F1: the drafting reserve ----------------

def done_script(phases, tin=100, tout=50):
    return {phase: [("done", tin, tout)] for phase in phases}


def run_attempt_custom(tmp_path, arm, provider, store, identity, cfg_extra=None):
    cfg = {**BASE_CFG, **(cfg_extra or {})}
    return runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                  arm, provider, FakeSandbox(), store,
                                  identity, cfg)


def drafting_calls(store):
    return [c for c in store.events("calls")
            if c["phase"] in runner.FORCE_ADVANCE_PHASES]


def test_f1_runaway_drafting_force_advances_and_implementation_spends(tmp_path):
    # Acceptance (1): drafting scripted to consume the full 1.5M
    # attempt cap (400,000 per specify call, repeating) force-
    # advances at the 750,000 drafting sub-cap — after exactly two
    # drafting calls (800,000 charged) — and implementation then
    # spends tokens and completes. No phase is exhausted.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 400000, 0)]
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity,
                                cfg_extra={"drafting_sub_cap_tokens": 750000})
    assert "phase_exhausted" not in result
    assert result["drafting_force_advanced"]["drafting_tokens_at_advance"] == 800000
    dcalls = drafting_calls(store)
    assert len(dcalls) == 2
    assert all(c["phase"] == "specify" for c in dcalls)
    # Remaining drafting phases were never entered.
    assert not [c for c in store.events("calls") if c["phase"] in ("plan", "tasks")]
    # Implementation was funded and spent.
    impl = [c for c in store.events("calls") if c["phase"] == "implement"]
    assert len(impl) == 1
    assert attempt_token_usage(impl, BASE_CFG) == 150
    completed = {p["phase"] for p in store.events("phases")
                 if not p.get("drafting_force_advanced")}
    assert {"constitution", "implement", "converge"} <= completed


def test_f1_advance_event_carries_artifacts_and_is_not_exhaustion(tmp_path):
    # Acceptance (2): specify completes (its artifact is
    # registered); plan then runs away and the sub-cap catches it —
    # the advance event names plan as the partial phase and carries
    # specify's completed artifact identity, and the attempt's
    # classification is not phase_budget_exhausted.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "tasks", "implement", "converge"))
    script["specify"] = [("done", 100, 50)]
    script["plan"] = [("shell", 400000, 0)]
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity,
                                cfg_extra={"drafting_sub_cap_tokens": 750000})
    assert "phase_exhausted" not in result
    events = [p for p in store.events("phases") if p.get("drafting_force_advanced")]
    assert len(events) == 1
    event = events[0]
    assert event["phase"] == "plan"
    # 150 (specify) + 2 x 400,000 (plan) = 800,150 drafting charged.
    assert event["drafting_tokens_at_advance"] == 800150
    assert event["drafting_sub_cap_tokens"] == 750000
    carried = event["artifact_carried"]
    assert carried["partial_phase"] == "plan"
    assert carried["partial_workspace"] == "/workflow"
    specify_record = [p for p in store.events("phases")
                      if p["phase"] == "specify" and p.get("artifact")][0]
    assert carried["completed_phases"]["specify"]["sha256"] == \
        specify_record["artifact"]["sha256"]
    assert result["drafting_force_advanced"] == event


def test_f1_envelope_and_reserve_accounting_is_exact(tmp_path):
    # Acceptance (3): every figure reconciles to the token against
    # the calls ledger — drafting at the advance, the reserve left
    # for implementation, and the attempt total.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "converge"))
    script["specify"] = [("shell", 375000, 0)]
    script["implement"] = [("shell", 200000, 100), ("done", 100, 50)]
    provider = RecordingProvider(store, identity, script)
    cfg = {**BASE_CFG, "drafting_sub_cap_tokens": 750000}
    result = runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                    "spec_kit", provider, FakeSandbox(), store,
                                    identity, cfg)
    calls = store.events("calls")
    total = attempt_token_usage(calls, cfg)
    drafting = attempt_token_usage(drafting_calls(store), cfg)
    event = result["drafting_force_advanced"]
    # Two specify calls: 750,000 exactly at the sub-cap.
    assert drafting == 750000
    assert event["drafting_tokens_at_advance"] == drafting
    # The reserve: implementation + assessment-side phases held
    # exactly attempt_cap - drafting, and spent from it.
    impl_spend = attempt_token_usage(
        [c for c in calls if c["phase"] == "implement"], cfg)
    assert impl_spend == 200100 + 150
    assert total == 150 + drafting + impl_spend + 150  # constitution + converge
    assert total <= cfg["token_cap"]
    assert cfg["token_cap"] - drafting >= 750000


def test_f1_completing_shape_is_untouched(tmp_path):
    # Every drafting phase completes well inside the sub-cap: no
    # advance event, no result key, all phases run.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "specify", "plan", "tasks",
                          "implement", "converge"))
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity,
                                cfg_extra={"drafting_sub_cap_tokens": 750000})
    assert "drafting_force_advanced" not in result
    assert not [p for p in store.events("phases")
                if p.get("drafting_force_advanced")]
    completed = {p["phase"] for p in store.events("phases")}
    assert {"specify", "plan", "tasks", "implement"} <= completed


def test_f1_sub_cap_override_and_boundary_below_cap(tmp_path):
    # The sub-cap is a hard cumulative bound, not per-phase: two
    # cheap drafting phases complete, the third crosses the
    # (overridden) sub-cap mid-phase and the attempt advances from
    # tasks; implementation still runs.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "implement", "converge"))
    script["specify"] = [("done", 100, 50)]
    script["plan"] = [("done", 100, 50)]
    script["tasks"] = [("shell", 100000, 0)]
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity,
                                cfg_extra={"drafting_sub_cap_tokens": 250000})
    event = result["drafting_force_advanced"]
    assert event["phase"] == "tasks"
    assert event["drafting_tokens_at_advance"] == 150 + 150 + 300000
    assert [c for c in store.events("calls") if c["phase"] == "implement"]


def test_f1_reserve_is_freeze_configured_absent_key_keeps_cycle1_semantics(tmp_path):
    # The drafting reserve is a freeze-configured bound: a config
    # WITHOUT drafting_sub_cap_tokens reproduces the pre-Cycle-5
    # semantics bit-for-bit — the runaway drafting phase spends its
    # C1-c envelope finalize call and completes (the Cycle 1 shape),
    # and no drafting_force_advanced event exists.
    from test_cycle1 import FinalizeAwareProvider
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 400000, 0)]
    provider = FinalizeAwareProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity)
    assert "drafting_force_advanced" not in result
    assert not [p for p in store.events("phases")
                if p.get("drafting_force_advanced")]
    record = [p for p in store.events("phases") if p["phase"] == "specify"][0]
    assert record["force_advanced"] is True
