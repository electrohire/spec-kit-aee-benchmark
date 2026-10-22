"""Cycle 2 (2026-10-22) acceptance tests: C2-F1 attempt-wall expiry
as a scored outcome (+ the per-phase wall bound), C2-F2 authored-
turn history discipline, and the frozen capability-probe design
(selection derivation, configs, mechanical checklist judge, budget
accounting).

All offline: stub HTTP servers at scaled clocks (the Cycle 1 A3
pattern), scripted providers, replays of recorded-history shapes,
and the benchmark repo's own selection records. No inference runs;
every claim is read back from a run store, a pure function, or the
committed probe registration.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import (  # noqa: E402
    BASE_CFG, FakeSandbox, RecordingProvider, attempt_script,
    construction_script, done_script, entry)
from test_cycle1 import (  # noqa: E402
    LOCAL_CFG, cycle1_stub, run_campaign_custom, _local_provider)

import benchmark_runner.local_provider as local_mod  # noqa: E402
from benchmark_runner import probe as probe_mod  # noqa: E402
from benchmark_runner import runner  # noqa: E402
from benchmark_runner.context import (  # noqa: E402
    AUTHORED_TURN_EXCERPT_CHARS, assemble_history, estimate_tokens,
    externalize_authored_turns)
from benchmark_runner.local_provider import (  # noqa: E402
    CallOuterBoundError, TransportStallError)
from benchmark_runner.provider import (  # noqa: E402
    AttemptWallExpiredError, ProviderError)
from benchmark_runner.store import Store  # noqa: E402
from benchmark_runner.tripwires import classify_halt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FakeSandbox.BASE_BY_IMAGE = {"imgA": "baseA", "imgB": "baseB"}


# ---------------- C2-F1: classifier-level replays ----------------

def test_f1_stall_and_outer_bound_classifications_unchanged():
    # Stall (600 s silence): a transport-named error record still
    # classifies premise/equipment and halts — C2-F1 does not touch
    # stall semantics (the R-A5 bundle path rides on this class).
    assert classify_halt("error", "TransportStallError: TransportStallSuspected") == (
        "premise_equipment", "infrastructure_error")
    # The 7,200 s per-call outer bound keeps the exact semantics
    # Cycle 1 C1-A3 gave it (a named disclosed limit).
    assert classify_halt("limit", "call_outer_bound") == (
        "model_outcome", "call_outer_bound")
    # The pre-call wall expiry (LimitHit "wall-time limit", raised
    # before a call starts) also keeps its prior classification.
    assert classify_halt("limit", "wall-time limit") == (
        "model_outcome", "disclosed_limit_reached")


# ---------------- C2-F1: local provider, flowing call + wall expiry ---------

def test_f1_flowing_call_wall_expiry_mid_stream_is_scored_limit(
        tmp_path, monkeypatch):
    # The Cycle 1 fatal shape, replayed at scaled clocks: a call
    # that is FLOWING (a token every 0.05 s) when the per-call
    # deadline — the attempt-wall remainder, 1.2 s here — expires
    # mid-stream. Stall bound is far away (60 s), the outer bound
    # farther (72 s): neither may fire. The call must end as the
    # named wall expiry, partial stream recorded, NO transport
    # event, and the raised error must be the wall error type.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 60)
    monkeypatch.setattr(local_mod, "CALL_OUTER_BOUND_SECONDS", 72)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("flow") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.call_deadline_kind = "attempt_wall"
        tick = time.monotonic()
        with pytest.raises(AttemptWallExpiredError):
            provider.query([{"role": "user", "content": "hi"}], "plan", 1.2)
        elapsed = time.monotonic() - tick
    assert 1.0 < elapsed < 10  # the wall remainder, not the stall/outer clocks
    (event,) = store.events("calls")
    assert event["error"] == "AttemptWallExpired"
    assert event["limit_kind"] == "attempt_wall_expired"
    assert event["stream_tokens_received"] > 0  # it was flowing when it died
    assert event["input_tokens"] is None  # unknown usage: reservation charge
    assert event["unknown_reason"] == "AttemptWallExpired"
    artifact = store.root / event["artifacts"]["response"]["path"]
    partial = json.loads(artifact.read_text())
    assert partial["partial"] is True
    assert partial["limit_kind"] == "attempt_wall_expired"
    assert partial["choices"][0]["message"]["content"]  # partial stream kept
    assert store.events("transport_events") == []  # not a transport failure
    # And the attempt record this produces classifies as scored.
    assert classify_halt("limit", "attempt_wall_expired") == (
        "model_outcome", "attempt_wall_expired")


def test_f1_same_deadline_without_wall_binding_stays_generic_timeout(
        tmp_path, monkeypatch):
    # Control: the identical flowing call and deadline, but the
    # deadline is an ordinary per-call bound (not the wall
    # remainder) — the generic timeout semantics are unchanged.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 60)
    monkeypatch.setattr(local_mod, "CALL_OUTER_BOUND_SECONDS", 72)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("flow") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.call_deadline_kind = "per_call"
        with pytest.raises(ProviderError) as raised:
            provider.query([{"role": "user", "content": "hi"}], "plan", 1.2)
    assert not isinstance(raised.value, AttemptWallExpiredError)
    (event,) = store.events("calls")
    assert event["error"] == "TimeoutError"
    assert event["limit_kind"] is None


def test_f1_stall_replay_unchanged_even_when_wall_bound(tmp_path, monkeypatch):
    # Silence after one token, with the deadline wall-bound: the
    # stall clock is checked before the wall at every slice, so the
    # call still dies as a stall with its transport event (the
    # R-A5 bundle machinery attaches to exactly this record).
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 2)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("silent_after_one") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.call_deadline_kind = "attempt_wall"
        with pytest.raises(TransportStallError):
            provider.query([{"role": "user", "content": "hi"}], "plan", 60)
    (event,) = store.events("calls")
    assert event["error"] == "TransportStallSuspected"
    assert event["limit_kind"] is None
    (record,) = store.events("transport_events")
    assert record["kind"] == "transport_stall_suspected"


def test_f1_outer_bound_replay_unchanged_and_wins_over_wall(tmp_path, monkeypatch):
    # A flowing call granted the full outer bound (scaled 3 s) ends
    # as call_outer_bound even when that bound is also the wall:
    # the outer-bound clock keeps its Cycle 1 precedence and
    # semantics, partial stream recorded, transport event written.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 60)
    monkeypatch.setattr(local_mod, "CALL_OUTER_BOUND_SECONDS", 3)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("flow") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.call_deadline_kind = "attempt_wall"
        with pytest.raises(CallOuterBoundError):
            provider.query([{"role": "user", "content": "hi"}], "plan", 3)
    (event,) = store.events("calls")
    assert event["error"] == "CallOuterBound"
    assert event["limit_kind"] == "call_outer_bound"
    (record,) = store.events("transport_events")
    assert record["kind"] == "call_outer_bound"


# ---------------- C2-F1: run-level replay (study continues) -----------------

class WallInPlanProvider(RecordingProvider):
    """RecordingProvider whose first plan-phase call for one
    attempt dies as a wall expiry mid-stream: the call record
    carries the wall limit exactly as the local provider writes
    it, then the wall error is raised."""

    WALL_ATTEMPT = "TASK_A--spec_kit--r1"

    def query(self, messages, phase, timeout):
        if (self.identity["attempt_id"] == self.WALL_ATTEMPT
                and phase == "plan" and self.counts.get(phase, 0) == 0):
            self.counts[phase] = 1
            self.queried.append(phase)
            self.store.append("calls", {
                **self.identity, "phase": phase,
                "call_id": f"{self.identity['attempt_id']}-{phase}-wall",
                "input_tokens": None, "output_tokens": None,
                "usage_status": "unknown", "error": "AttemptWallExpired",
                "limit_kind": "attempt_wall_expired",
                "stream_tokens_received": 6851})
            raise AttemptWallExpiredError("AttemptWallExpired")
        return super().query(messages, phase, timeout)


def test_f1_run_level_wall_expiry_scores_and_study_continues(
        tmp_path, monkeypatch):
    # The Cycle 1 run shape: spec_kit r1 dies in plan when the wall
    # expires mid-call; a baseline attempt is scheduled after it.
    scripts = {"TASK_A--campaign-setup": construction_script(),
               "TASK_A--spec_kit--r1": attempt_script(),
               "TASK_A--baseline--r1": attempt_script()}

    def factory(cfg_, store, budget, identity):
        return WallInPlanProvider(store, identity, scripts[identity["attempt_id"]])

    store = run_campaign_custom(
        tmp_path, monkeypatch,
        [entry("TASK_A", "spec_kit"), entry("TASK_A", "baseline")], factory)
    terminal = {a["attempt_id"]: a for a in store.events("attempts")
                if a["status"] != "started"}
    wall = terminal["TASK_A--spec_kit--r1"]
    assert wall["status"] == "limit"
    assert wall["reason"] == "attempt_wall_expired"
    assert "patch" in wall  # graded as it stands (partial patch preserved)
    (event,) = [e for e in store.events("tripwires")
                if e["attempt_id"] == "TASK_A--spec_kit--r1"]
    assert event["halt_class"] == "model_outcome"
    assert event["halt_kind"] == "attempt_wall_expired"
    assert event["behavior"] == "score_and_continue"
    # The study proceeded to the next scheduled attempt, which ran
    # and completed — the exact behavior Cycle 1 did not have.
    assert terminal["TASK_A--baseline--r1"]["status"] == "completed"


# ---------------- C2-F1: the per-phase wall bound ---------------------------

def test_f1_phase_wall_bound_pure_rules():
    cfg = {**BASE_CFG}  # timeout_seconds 600 -> attempt wall 600 s
    assert runner.phase_wall_bound_seconds(cfg) == 360.0  # 60% of the wall
    assert runner.phase_wall_tripped("specify", 360.0, cfg) is True
    assert runner.phase_wall_tripped("specify", 359.0, cfg) is False
    assert runner.phase_wall_tripped("constitution", 10_000, cfg) is True
    # Implementation is exempt, exactly as under the token guard.
    assert runner.phase_wall_tripped("implement", 10_000, cfg) is False
    # The baseline loop and non-drafting phases are unguarded.
    assert runner.phase_wall_tripped("solve", 10_000, cfg) is False
    assert runner.phase_wall_tripped("converge", 10_000, cfg) is False


class SlowFirstCallProvider(RecordingProvider):
    """Sleeps past the (scaled) phase wall bound on its first call
    in ``slow_phase``, then answers shell; emits the phase artifact
    when the harness's reserved finalize instruction is in view."""

    def __init__(self, store, identity, script, slow_phase, delay=1.3):
        super().__init__(store, identity, script)
        self.slow_phase, self.delay, self.slowed = slow_phase, delay, False

    def query(self, messages, phase, timeout):
        if any("Phase envelope reached" in (m.get("content") or "")
               for m in messages):
            idx = self.counts.get(phase, 0)
            self.counts[phase] = idx + 1
            self.queried.append(phase)
            self.store.append("calls", {**self.identity, "phase": phase,
                                        "call_id": f"{self.identity['attempt_id']}-{phase}-fin{idx}",
                                        "input_tokens": 100, "output_tokens": 50,
                                        "usage_status": "reported"})
            return json.dumps({"action": "done", "summary": "finalized",
                               "claims": {"schema_version": "1.0", "claims": []}})
        if phase == self.slow_phase and not self.slowed:
            self.slowed = True
            time.sleep(self.delay)
        return super().query(messages, phase, timeout)


def _run_attempt(tmp_path, arm, provider, store, identity, cfg_extra):
    cfg = {**BASE_CFG, **cfg_extra}
    return runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                  arm, provider, FakeSandbox(), store,
                                  identity, cfg)


def test_f1_phase_wall_expiry_force_advances_a_drafting_phase(tmp_path):
    # Attempt wall 2 s (scaled) -> phase wall bound 1.2 s. Specify's
    # first call takes 1.3 s and returns shell (the token envelope
    # is nowhere near tripping at these charges): the wall bound
    # alone must spend the reserved finalize call, the phase
    # force-advances with an artifact, and the attempt proceeds.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 100, 0)]
    provider = SlowFirstCallProvider(store, identity, script, "specify")
    result = _run_attempt(tmp_path, "spec_kit", provider, store, identity,
                          {"timeout_seconds": 2})
    assert "phase_exhausted" not in result
    record = [p for p in store.events("phases") if p["phase"] == "specify"][0]
    assert record["force_advanced"] is True
    assert record["artifact"]


def test_f1_phase_wall_expiry_exhausts_a_non_force_advance_drafting_phase(tmp_path):
    # Constitution is a drafting phase but not a force-advance phase
    # (banking handles it in construction): past its wall bound
    # without completing, it ends exhausted exactly as the token
    # guard ends it, and the patch is graded as it stands.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = {"constitution": [("shell", 100, 0)]}
    provider = SlowFirstCallProvider(store, identity, script, "constitution")
    result = _run_attempt(tmp_path, "spec_kit", provider, store, identity,
                          {"timeout_seconds": 2})
    assert result["phase_exhausted"] == "constitution"
    assert not any(p.get("force_advanced") for p in store.events("phases"))
    assert result["patch"]


# ---------------- C2-F2: authored-turn history discipline -------------------

def plan_phase_history(authored_chars=20000, rounds=3):
    """The Cycle 1 plan-phase shape: pinned phase prompts per phase,
    large model-authored turns in the constitution and specify
    segments, tool observations, then the plan segment (current)
    with its own authored turns."""
    messages = [{"role": "system", "content": "system prompt"},
                {"role": "user", "content": "the task statement"}]
    for phase in ("constitution", "specify", "plan"):
        messages.append({"role": "user",
                         "content": f"Current phase: {phase}\nphase prompt"})
        for i in range(rounds):
            messages.append({"role": "assistant", "content": json.dumps(
                {"action": "shell", "command": "cat draft",
                 "draft": f"{phase} authored text {i} " + "a" * authored_chars})})
            messages.append({"role": "user", "content": json.dumps(
                {"exit_code": 0, "stdout": "o" * 4000, "stderr": ""})})
        messages.append({"role": "assistant", "content": json.dumps(
            {"action": "done", "summary": f"{phase} complete; "
                                          f"artifact at /workflow/{phase}.md"})})
    return messages


REGISTRY = {
    "constitution": {"workspace_path": "/workflow/.specify/memory/constitution.md",
                     "sha256": "a" * 64, "store_path": "artifacts/aaa.json"},
    "specify": {"workspace_path": "/workflow/specs/001-fixture/spec.md",
                "sha256": "b" * 64, "store_path": "artifacts/bbb.json"},
}


def test_f2_replay_assembled_holds_cap_current_phase_intact():
    messages = plan_phase_history()
    assert estimate_tokens(messages) > 24576  # the Cycle 1 regime
    result = assemble_history(messages, 24576, current_phase="plan",
                              artifact_registry=REGISTRY)
    # Combined rule: assembled <= wire cap on the sent view.
    assert result.sent_tokens <= 24576
    assert result.unmaskable_remainder_over_cap is False
    # Every earlier-phase authored turn externalized (3 shell turns
    # + 1 done turn per earlier phase); none of the current phase's.
    assert result.externalized_count == 8
    placeholders = []
    for message in result.messages:
        if message["role"] == "assistant" and \
                "externalized_authored_turn" in message["content"]:
            placeholders.append(json.loads(message["content"]))
    assert len(placeholders) == 8
    by_phase = {p["phase"] for p in placeholders}
    assert by_phase == {"constitution", "specify"}
    for placeholder in placeholders:
        entry = REGISTRY[placeholder["phase"]]
        assert placeholder["workspace_path"] == entry["workspace_path"]
        assert placeholder["artifact_sha256"] == entry["sha256"]
        assert placeholder["artifact_store_path"] == entry["store_path"]
        assert len(placeholder["excerpt"]) <= AUTHORED_TURN_EXCERPT_CHARS
        if placeholder["original_chars"] > AUTHORED_TURN_EXCERPT_CHARS:
            # A large turn is cut to exactly the bound.
            assert len(placeholder["excerpt"]) == AUTHORED_TURN_EXCERPT_CHARS
    # The current phase's authored turns are byte-identical.
    original_plan = [m for m in messages
                     if m["role"] == "assistant" and "plan authored" in m["content"]
                     or (m["role"] == "assistant" and "plan complete" in m["content"])]
    sent_plan = [m for m in result.messages if m in original_plan]
    assert sent_plan == original_plan
    # The agent's own history is never mutated.
    assert estimate_tokens(messages) > 24576
    assert all("externalized_authored_turn" not in m["content"]
               for m in messages if m["role"] == "assistant")


def test_f2_excerpt_bound_is_the_named_constant():
    assert AUTHORED_TURN_EXCERPT_CHARS == 512
    messages = plan_phase_history(authored_chars=5000, rounds=1)
    out, count = externalize_authored_turns(messages, "plan", REGISTRY,
                                            excerpt_chars=64)
    assert count == 4
    for message in out:
        if "externalized_authored_turn" in message["content"]:
            assert len(json.loads(message["content"])["excerpt"]) <= 64


def test_f2_current_draft_reachable_via_its_workspace_file(tmp_path):
    # The current phase's draft lives in a workspace file; the
    # assembled view keeps the current authored turn that references
    # it byte-identical, and an earlier phase's placeholder points
    # at ITS workspace file, whose bytes hash to the placeholder's
    # registered identity — drafts are reached via the workspace,
    # not via re-sent history.
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# spec draft\n" + "s" * 3000, encoding="utf-8")
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# plan draft\n" + "p" * 3000, encoding="utf-8")
    registry = {
        "specify": {"workspace_path": str(spec_file),
                    "sha256": hashlib.sha256(
                        spec_file.read_bytes()).hexdigest(),
                    "store_path": "artifacts/bbb.json"},
        "plan": {"workspace_path": str(plan_file),
                 "sha256": hashlib.sha256(plan_file.read_bytes()).hexdigest(),
                 "store_path": "artifacts/ccc.json"},
    }
    messages = plan_phase_history(authored_chars=6000, rounds=1)
    result = assemble_history(messages, 24576, current_phase="plan",
                              artifact_registry=registry)
    spec_placeholders = [json.loads(m["content"]) for m in result.messages
                         if m["role"] == "assistant"
                         and "externalized_authored_turn" in m["content"]
                         and json.loads(m["content"])["phase"] == "specify"]
    assert spec_placeholders  # the earlier phase was externalized
    for placeholder in spec_placeholders:
        assert Path(placeholder["workspace_path"]).is_file()
        assert hashlib.sha256(
            Path(placeholder["workspace_path"]).read_bytes()
        ).hexdigest() == placeholder["artifact_sha256"]
    # No plan placeholder exists: the current draft stays in view.
    assert not any(m["role"] == "assistant"
                   and "externalized_authored_turn" in m["content"]
                   and json.loads(m["content"])["phase"] == "plan"
                   for m in result.messages)


def test_f2_unmaskable_remainder_is_flagged_never_silent():
    # A single current-phase authored turn larger than the cap by
    # itself: nothing in the combined rule can shrink it (current
    # turns stay intact; it is not an observation). The result must
    # carry the named flag instead of silently serving over-cap.
    messages = [{"role": "system", "content": "system"},
                {"role": "user", "content": "task"},
                {"role": "user", "content": "Current phase: plan\nprompt"},
                {"role": "assistant", "content": "x" * 300000}]
    result = assemble_history(messages, 24576, current_phase="plan")
    assert result.sent_tokens > 24576
    assert result.unmaskable_remainder_over_cap is True
    assert result.externalized_count == 0
    # And the flag is a boolean identity in every replay: flagged
    # exactly when the sent view is over cap.
    for history in (messages, plan_phase_history()):
        replay = assemble_history(history, 24576, current_phase="plan",
                                  artifact_registry=REGISTRY)
        assert replay.unmaskable_remainder_over_cap == (
            replay.sent_tokens > 24576)


def test_f2_unmaskable_flag_lands_on_the_call_record(tmp_path, monkeypatch):
    # End to end through MiniModel + the local provider: an
    # over-cap current-phase remainder is served (the attempt is
    # the model's to lose) but the call record carries the named
    # countable flag — zero silent over-cap calls.
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        cfg = {**LOCAL_CFG}
        model = runner.MiniModel(provider, time.monotonic() + 600, 60, cfg=cfg)
        model.phase = "plan"
        history = [{"role": "system", "content": "system"},
                   {"role": "user", "content": "task"},
                   {"role": "user", "content": "Current phase: plan\nprompt"},
                   {"role": "assistant", "content": "x" * 300000}]
        reply = model.query(history)
    assert reply["role"] == "assistant"
    (event,) = store.events("calls")
    assert event["assembled_tokens"] > 24576
    assert event["unmaskable_remainder_over_cap"] is True
    assert event["authored_turns_externalized"] == 0
    assert event["sent_tokens"] > 24576


def test_f2_combined_view_through_model_records_externalized_count(
        tmp_path, monkeypatch):
    # The Cycle 1 masking end-to-end shape, extended: earlier-phase
    # authored growth is externalized, observations masked, the
    # sent view fits, and both counts land on the call record.
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        cfg = {**LOCAL_CFG}
        model = runner.MiniModel(provider, time.monotonic() + 600, 60, cfg=cfg)
        model.phase = "plan"
        model.phase_artifacts = REGISTRY
        reply = model.query(plan_phase_history())
    assert reply["role"] == "assistant"
    (event,) = store.events("calls")
    assert event["sent_tokens"] <= 24576
    assert event["authored_turns_externalized"] == 8
    assert event["unmaskable_remainder_over_cap"] is False


# ---------------- Probe design: selection derivation ------------------------

def _campaign_registration():
    return probe_mod.load_campaign_registration(ROOT)


def _probe_registration_file():
    path = ROOT / "benchmarks/upstream-coding/probe-cycle2-registration.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_probe_selection_derivation_reproduces_the_list_from_the_rule():
    campaign = _campaign_registration()
    records = probe_mod.derive_probe_tasks(campaign)
    ids = [r["instance_id"] for r in records]
    # The derivation lands exactly on the campaign registration's
    # own runners-up: the next feasible instances in hash order
    # past the selected six (ranks 9, 10, 11, 12, 14, 16 — ranks 13
    # and 15 are recorded infeasible and are skipped by the rule).
    assert [r["hash_rank"] for r in records] == \
        campaign["selection_outcome"]["runners_up_hash_ranks"]
    assert [r["hash_rank"] for r in records] == [9, 10, 11, 12, 14, 16]
    # Every hash re-derives from the plan's rule (the derivation
    # itself raises on any mismatch; assert it explicitly here).
    for record in records:
        assert probe_mod.selection_hash(record["instance_id"]) == \
            record["selection_hash_sha256"]
    # Disjoint from the campaign's six, all level-1, all feasible.
    campaign_ids = {t["instance_id"] for t in campaign["tasks"]}
    assert not (set(ids) & campaign_ids)
    assert all(r["level"] == 1 for r in records)
    assert all(r["feasibility"]["feasible"] is True for r in records)


def test_probe_registration_file_matches_the_frozen_builder():
    # The committed registration is exactly the builder's output on
    # the campaign registration: regenerating it reproduces it, so
    # the frozen design cannot drift from the code that derives it.
    built = probe_mod.build_probe_registration(_campaign_registration())
    assert _probe_registration_file() == built
    assert [t["instance_id"] for t in built["tasks"]] == [
        "pandas-dev__pandas.82fa2715.test_sample.5d2ba03e.lv1",
        "pandas-dev__pandas.82fa2715.test_iceberg.85771c70.lv1",
        "pydata__xarray.97f3a746.test_coordinate_transform.6cacb660.lv1",
        "pandas-dev__pandas.82fa2715.test_reduction.3ac3b298.lv1",
        "mwaskom__seaborn.7001ebe7.test_relational.f23eb542.lv1",
        "astropy__astropy.b0db0daa.test_tilde_path.383d7c0c.lv1",
    ]
    for task in built["tasks"]:
        assert task["selection_hash_sha256"]
        assert task["solver_image_id"].startswith("sha256:")
        assert task["prepared_baseline_commit"]
        assert task["prepared_baseline_tree"]


def test_probe_configs_refuse_campaign_task_ids():
    campaign = _campaign_registration()
    campaign_ids = [t["instance_id"] for t in campaign["tasks"]]
    probe_ids = [t["instance_id"]
                 for t in _probe_registration_file()["tasks"]]
    # Any list containing a campaign id is refused, however it is
    # padded to the right count.
    for campaign_id in campaign_ids:
        with pytest.raises(ValueError):
            probe_mod.validate_probe_task_ids(
                probe_ids[:-1] + [campaign_id], campaign_ids)
    with pytest.raises(ValueError):
        probe_mod.validate_probe_task_ids(probe_ids[:-1], campaign_ids)
    with pytest.raises(ValueError):
        probe_mod.validate_probe_task_ids(
            probe_ids[:-1] + [probe_ids[0]], campaign_ids)
    assert probe_mod.validate_probe_task_ids(probe_ids, campaign_ids) == probe_ids
    # Both frozen configs carry exactly the probe tasks and caps.
    configs = _probe_registration_file()["configs"]
    assert configs == probe_mod.probe_configs(probe_ids)
    direct = configs["probe_i_direct_implementation"]
    assert direct["phases"] == ["solve"] and direct["test_feedback"] is True
    assert direct["per_attempt_cap_tokens"] == 400000
    spec = configs["probe_ii_standalone_specification"]
    assert spec["phases"] == ["constitution", "specify"]
    assert spec["per_attempt_cap_tokens"] == 400000
    assert not (set(direct["tasks"]) & set(campaign_ids))
    assert not (set(spec["tasks"]) & set(campaign_ids))


# ---------------- Probe design: the mechanical checklist judge --------------

GOOD_CONSTITUTION = """# Fixture Constitution

## Core Principles

### I. Test-First
Every change begins with a failing test that proves the need.

### II. Simplicity
Prefer the smallest design that satisfies the requirements.

## Governance
This constitution governs all specification work on the project;
amendments require a recorded rationale and a version bump.
"""

GOOD_SPEC = """# Feature Specification: Fixture Feature

## User Scenarios & Testing

### User Story 1 - Import a file (Priority: P1)
A user imports a data file and sees its rows parsed into records.

## Requirements

The feature must satisfy the following requirements in full.

### Functional Requirements
- FR-001: The system MUST parse the imported file into records.
- FR-002: The system MUST reject a malformed file with an error.

## Success Criteria

### Measurable Outcomes
- SC-001: 95% of valid files import without manual correction.
"""

DONE_BOTH = {"constitution": "done", "specify": "done"}


def test_probe_checklist_judge_passes_a_complete_specification():
    verdict = probe_mod.judge_specification_completion(
        {"constitution": GOOD_CONSTITUTION, "specification": GOOD_SPEC},
        DONE_BOTH)
    assert verdict["completed"] is True
    assert verdict["missing"] == []
    assert all(check["ok"] for check in verdict["checks"].values())


def test_probe_checklist_judge_fails_missing_and_placeholder_sections():
    # Governance missing entirely.
    no_governance = GOOD_CONSTITUTION.split("## Governance")[0]
    verdict = probe_mod.judge_specification_completion(
        {"constitution": no_governance, "specification": GOOD_SPEC}, DONE_BOTH)
    assert verdict["completed"] is False
    assert "constitution:Governance" in verdict["missing"]
    # Sections present but still template placeholders: not content.
    placeholder_constitution = (
        "# X Constitution\n\n## Core Principles\n\n"
        "### [PRINCIPLE_1_NAME]\n[PRINCIPLE_1_DESCRIPTION]\n\n"
        "## Governance\n[GOVERNANCE_RULES]\n")
    verdict = probe_mod.judge_specification_completion(
        {"constitution": placeholder_constitution,
         "specification": GOOD_SPEC}, DONE_BOTH)
    assert verdict["completed"] is False
    assert "constitution:Core Principles" in verdict["missing"]
    assert "constitution:Governance" in verdict["missing"]
    # Missing specification artifact entirely.
    verdict = probe_mod.judge_specification_completion(
        {"constitution": GOOD_CONSTITUTION, "specification": None}, DONE_BOTH)
    assert verdict["completed"] is False
    assert "specification:Success Criteria" in verdict["missing"]


def test_probe_checklist_judge_requires_self_termination():
    # Perfect artifacts, but specify ended on a limit instead of
    # the model's own done: not a completion.
    verdict = probe_mod.judge_specification_completion(
        {"constitution": GOOD_CONSTITUTION, "specification": GOOD_SPEC},
        {"constitution": "done", "specify": "limit"})
    assert verdict["completed"] is False
    assert verdict["missing"] == ["self_termination:specify"]
    verdict = probe_mod.judge_specification_completion(
        {"constitution": GOOD_CONSTITUTION, "specification": GOOD_SPEC},
        {"constitution": None, "specify": None})
    assert verdict["completed"] is False
    assert "self_termination:constitution" in verdict["missing"]


# ---------------- Probe design: budget accounting ---------------------------

def _write_store(root, calls, cfg):
    root.mkdir(parents=True, exist_ok=True)
    (root / "calls.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in calls), encoding="utf-8")
    (root / "freeze.json").write_text(
        json.dumps({"config": cfg}), encoding="utf-8")
    return root


def test_probe_budget_verdict_counts_against_both_caps(tmp_path):
    cfg = {"max_input_tokens": 24576, "max_output_tokens": 8192}
    probe_store = _write_store(
        tmp_path / "probe", [{"input_tokens": 100, "output_tokens": 30}], cfg)
    prior = _write_store(
        tmp_path / "prior", [{"input_tokens": 50, "output_tokens": 10}], cfg)
    verdict = probe_mod.probe_budget_verdict(probe_store, [prior])
    assert verdict["probe_tokens"] == 130
    assert verdict["program_tokens"] == 190
    assert verdict["probe_sub_bound_tokens"] == 4800000
    assert verdict["program_cap"] == 48000000
    assert verdict["probe_sub_bound_reached"] is False
    assert verdict["program_cap_reached"] is False
    # At the sub-bound exactly, the sub-bound is reached; with the
    # program's prior spend added, the 48M cap is reached too.
    probe_full = _write_store(
        tmp_path / "probe-full",
        [{"input_tokens": 4800000, "output_tokens": 0}], cfg)
    prior_big = _write_store(
        tmp_path / "prior-big",
        [{"input_tokens": 43200000, "output_tokens": 0}], cfg)
    verdict = probe_mod.probe_budget_verdict(probe_full, [prior_big])
    assert verdict["probe_tokens"] == 4800000
    assert verdict["probe_sub_bound_reached"] is True
    assert verdict["program_tokens"] == 48000000
    assert verdict["program_cap_reached"] is True
    # The frozen arithmetic: worst case (12 attempts x 400,000)
    # equals the sub-bound exactly — the probe can never exceed it
    # while its per-attempt caps hold.
    budget = _probe_registration_file()["budget"]
    assert budget["worst_case_probe_tokens"] == 4800000
    assert budget["worst_case_within_sub_bound"] is True
