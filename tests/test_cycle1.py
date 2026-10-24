"""Cycle 1 (2026-10-21) acceptance tests for the reconciled plan:
C1-A1 baseline carve-out, C1-A2 banked construction, C1-A3
inactivity-aware per-call deadline, C1-A4 construction/drafting
history leanness, C1-a wire-vs-assembled accounting, C1-b
observation masking, C1-c envelopes with rollover and force-advance.

All offline: scripted providers, stub HTTP servers, and replays of
recorded-history shapes. Every claim is read back from the run store
or from the pure context functions, never from printed output.
"""
import json
import sys
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_runner import (  # noqa: E402
    BASE_CFG, FakeSandbox, RecordingProvider, attempt_script,
    construction_script, done_script, entry, run_attempt)

import benchmark_runner.local_provider as local_mod  # noqa: E402
from benchmark_runner import runner  # noqa: E402
from benchmark_runner.accounting import Budget, attempt_token_usage  # noqa: E402
from benchmark_runner.context import (  # noqa: E402
    cap_observation, estimate_tokens, history_digest, mask_history)
from benchmark_runner.local_provider import (  # noqa: E402
    CallOuterBoundError, LocalProvider, TransportStallError)
from benchmark_runner.store import Store, canonical  # noqa: E402
from benchmark_runner.tripwires import classify_halt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TASKS = [{"instance_id": "TASK_A", "image": "imgA", "base_commit": "baseA",
          "problem_statement": "fixture A"},
         {"instance_id": "TASK_B", "image": "imgB", "base_commit": "baseB",
          "problem_statement": "fixture B"}]
FakeSandbox.BASE_BY_IMAGE = {"imgA": "baseA", "imgB": "baseB"}


def run_campaign_custom(tmp_path, monkeypatch, schedule, factory, cfg_extra=None):
    cfg = {**BASE_CFG, "share_campaign_setup": True, **(cfg_extra or {})}
    manifest = {"freeze_id": "f" * 64, "config": cfg,
                "tasks": {"tasks": TASKS}, "schedule": schedule}
    monkeypatch.setattr(runner, "verify_freeze", lambda root, m: m["freeze_id"])
    monkeypatch.setattr(runner, "validate_live", lambda m, smoke=False: None)
    monkeypatch.setattr(runner, "DockerSandbox", FakeSandbox)
    monkeypatch.setattr(runner, "make_provider", factory)
    out = tmp_path / "store"
    runner.run(ROOT, manifest, out)
    return Store(out)


# ---------------- C1-A1: baseline carve-out ----------------

def test_a1_baseline_only_schedule_never_constructs_or_reads_setup(
        tmp_path, monkeypatch):
    # A task whose schedule holds only baseline entries: construction
    # never runs, no setup record exists to read, and the baseline
    # attempt is admitted and completes on task readiness alone.
    scripts = {"TASK_A--baseline--r1": attempt_script()}

    def factory(cfg_, store, budget, identity):
        return RecordingProvider(store, identity, scripts[identity["attempt_id"]])

    store = run_campaign_custom(tmp_path, monkeypatch,
                                [entry("TASK_A", "baseline")], factory)
    assert store.events("campaign_setups") == []
    assert [c for c in store.events("calls")
            if c.get("purpose") == "campaign_setup"] == []
    terminal = [a for a in store.events("attempts") if a["status"] != "started"]
    assert [a["status"] for a in terminal] == ["completed"]
    assert not any(p.get("setup_reused") for p in store.events("phases"))


def test_a1_construction_failure_replay_baseline_runs_spec_arms_skip(
        tmp_path, monkeypatch):
    # The reconciled plan's A1 acceptance replay (also carried by
    # tests/test_amendment1_runner.py's updated construction-failure
    # test): construction failed for the task — the baseline starts
    # and runs; both spec arms pre-skip with task_setup_failed.
    scripts = {"TASK_A--campaign-setup": {"constitution": [("raise",)]},
               "TASK_A--baseline--r1": attempt_script()}

    def factory(cfg_, store, budget, identity):
        return RecordingProvider(store, identity, scripts[identity["attempt_id"]])

    store = run_campaign_custom(
        tmp_path, monkeypatch,
        [entry("TASK_A", "baseline"), entry("TASK_A", "spec_kit"),
         entry("TASK_A", "spec_kit_aee")], factory)
    terminal = {a["arm"]: a for a in store.events("attempts")
                if a["status"] != "started"}
    assert terminal["baseline"]["status"] == "completed"
    for arm in ("spec_kit", "spec_kit_aee"):
        assert terminal[arm]["status"] == "skipped"
        assert "task_setup_failed" in terminal[arm]["reason"]


# ---------------- C1-A2: banked construction ----------------

class StatefulConstructionProvider:
    """A provider whose script cursor is shared across the separate
    provider instances the runner creates per construction
    installment, so a scripted construction can span draws. Records
    the first assembled history of every draw."""

    def __init__(self, store, identity, state):
        self.store, self.identity, self.state = store, identity, state

    def query(self, messages, phase, timeout):
        if self.state.get("await_first"):
            self.state["first_messages"] = [dict(m) for m in messages]
            self.state["await_first"] = False
        idx = self.state["cursor"]
        self.state["cursor"] = idx + 1
        steps = self.state["steps"]
        step = steps[min(idx, len(steps) - 1)]
        _, tin, tout = step
        self.store.append("calls", {**self.identity, "phase": phase,
                                    "call_id": f"{self.identity['attempt_id']}-{idx}",
                                    "input_tokens": tin, "output_tokens": tout,
                                    "usage_status": "reported"})
        if step[0] == "done":
            return json.dumps({"action": "done", "summary": "fixture",
                               "claims": {"schema_version": "1.0", "claims": []}})
        return json.dumps({"action": "shell", "command": "true"})


def construction_factory(state, scripts):
    def factory(cfg_, store, budget, identity):
        if identity["attempt_id"].endswith("campaign-setup"):
            state["await_first"] = True
            return StatefulConstructionProvider(store, identity, state)
        return RecordingProvider(store, identity, scripts[identity["attempt_id"]])
    return factory


def test_a2_two_installment_construction_banks_and_resumes(tmp_path, monkeypatch):
    # Scripted construction force-capped mid-draft: five shell calls
    # then done, charged 150,000 per call, per-draw cap 400,000 — the
    # first draw banks after three calls; the continuation resumes
    # from the bank and completes in the second installment.
    state = {"cursor": 0, "await_first": False,
             "steps": [("shell", 100000, 50000)] * 5 + [("done", 100000, 50000)]}
    scripts = {"TASK_A--spec_kit--r1": attempt_script()}
    store = run_campaign_custom(
        tmp_path, monkeypatch, [entry("TASK_A", "spec_kit")],
        construction_factory(state, scripts),
        cfg_extra={"construction_cap_tokens": 400000})
    # The bank exists, with its phase record.
    (bank,) = store.events("construction_banks")
    assert bank["installment"] == 1
    assert bank["draw_tokens"] == 450000
    banked_phase = [p for p in store.events("phases")
                    if p.get("construction_banked")]
    assert len(banked_phase) == 1
    assert banked_phase[0]["history_digest"] == bank["history_digest"]
    # The continuation's first assembled history carries the banked
    # digest, verbatim.
    assert history_digest(state["first_messages"]) == bank["history_digest"]
    # Exactly one setup record; installment charges sum exactly to
    # the construction line (the identity's charged calls).
    (setup,) = store.events("campaign_setups")
    assert setup["installments"] == [{"installment": 1, "tokens": 450000},
                                     {"installment": 2, "tokens": 450000}]
    construction_calls = [c for c in store.events("calls")
                          if c.get("purpose") == "campaign_setup"]
    line = attempt_token_usage(construction_calls, BASE_CFG)
    assert sum(i["tokens"] for i in setup["installments"]) == line == 900000
    assert setup["construction_tokens"] == line
    # The consumer attempt reused the setup and completed.
    terminal = [a for a in store.events("attempts") if a["status"] != "started"]
    assert [a["status"] for a in terminal] == ["completed"]
    assert any(p.get("setup_reused") for p in store.events("phases"))


def test_a2_exhausting_installments_is_task_setup_failed(tmp_path, monkeypatch):
    # A construction that never completes banks three installments
    # and then fails as before: task_setup_failed, attempts pre-skip,
    # and the per-task total stays under the 1,800,000 setup line.
    state = {"cursor": 0, "await_first": False,
             "steps": [("shell", 100000, 50000)]}
    scripts = {"TASK_A--spec_kit--r1": attempt_script()}
    store = run_campaign_custom(
        tmp_path, monkeypatch, [entry("TASK_A", "spec_kit")],
        construction_factory(state, scripts),
        cfg_extra={"construction_cap_tokens": 400000})
    assert len(store.events("construction_banks")) == 3
    assert store.events("campaign_setups") == []
    construction_calls = [c for c in store.events("calls")
                          if c.get("purpose") == "campaign_setup"]
    assert attempt_token_usage(construction_calls, BASE_CFG) == 1350000
    assert attempt_token_usage(construction_calls, BASE_CFG) <= 1800000
    terminal = [a for a in store.events("attempts") if a["status"] != "started"]
    assert terminal[0]["status"] == "skipped"
    assert "task_setup_failed" in terminal[0]["reason"]
    failed = [c for c in store.events("construction") if c["status"] == "failed"]
    assert len(failed) == 1


# ---------------- C1-A3: inactivity-aware per-call deadline ----------------

MODEL = "qwen3-8b-local"
IDENTITY = {"experiment_id": "exp", "run_id": "run0123456789ab",
            "arm": "repair_ordinary", "task_id": "t1", "repeat": 1,
            "attempt_id": "a1", "purpose": "test"}
LOCAL_CFG = {"model": MODEL, "max_output_tokens": 64,
             "max_input_tokens": 24576, "provider_backend": "local",
             "transport": {"min_request_gap_seconds": 0}}
USAGE = {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14,
         "prompt_tokens_details": {"cached_tokens": 2},
         "completion_tokens_details": {"reasoning_tokens": 1}}


def _chunk(content=None, usage=None):
    chunk = {"id": "chatcmpl-1", "model": MODEL, "choices": []}
    if usage is not None:
        chunk["usage"] = usage
    if content is not None:
        chunk["choices"] = [{"delta": {"content": content}}]
    return chunk


class _Cycle1Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"data": [{"id": MODEL}]})
        elif self.path.endswith("/slots"):
            self._json([{"id": 0, "is_processing": False}])
        elif self.path.endswith("/health"):
            self._json({"status": "ok"})
        elif self.path.endswith("/props"):
            self._json({"model_path": "stub"})
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        mode = self.server.chat_mode
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            def send(chunk):
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                self.wfile.flush()

            if mode == "drip":
                # One token every 0.3 s for ~7.5 s, then completion:
                # the scaled shape of one token every 300 s surviving
                # past the old 5,400 s wall (scale 1:1000).
                for _ in range(25):
                    send(_chunk("x"))
                    time.sleep(0.3)
                send(_chunk(usage=USAGE))
            elif mode == "silent_after_one":
                send(_chunk("x"))
                time.sleep(30)  # silence: the stall clock must fire
            elif mode == "flow":
                while True:
                    send(_chunk("x"))
                    time.sleep(0.05)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class _Cycle1Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass


@contextmanager
def cycle1_stub(chat_mode):
    server = _Cycle1Server(("127.0.0.1", 0), _Cycle1Handler)
    server.chat_mode = chat_mode
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def _local_provider(tmp_path, monkeypatch, base_url):
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    store = Store(tmp_path / "store")
    budget = Budget(store, Decimal("100"), Decimal("25"))
    return LocalProvider(LOCAL_CFG, store, budget, IDENTITY), store


def test_a3_flowing_call_survives_past_the_old_wall_and_completes(
        tmp_path, monkeypatch):
    # Stub shape 1 (scaled 1:1000): a token every 300 s against a
    # 600 s stall bound survives past 5,400 s and completes.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 0.6)
    monkeypatch.setattr(local_mod, "CALL_OUTER_BOUND_SECONDS", 72)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        tick = time.monotonic()
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 60)
        elapsed = time.monotonic() - tick
    assert text == "x" * 25
    assert elapsed > 5.4  # past the old wall, still flowing, completed
    (event,) = store.events("calls")
    assert event["error"] is None
    assert event["stream_tokens_received"] == 25
    assert store.events("transport_events") == []


def test_a3_silent_after_t_stalls_at_600s_with_event_and_bundle(
        tmp_path, monkeypatch):
    # Stub shape 2 (scaled): silence after one token dies at ~600 s
    # of silence with the named event; the R-A5 bundle machinery
    # captures against the same store and identity.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 2)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("silent_after_one") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        tick = time.monotonic()
        with pytest.raises(TransportStallError):
            provider.query([{"role": "user", "content": "hi"}], "repair", 60)
        elapsed = time.monotonic() - tick
        assert 1.5 < elapsed < 10  # ~the stall bound, not the deadline
        (record,) = store.events("transport_events")
        assert record["kind"] == "transport_stall_suspected"
        (event,) = store.events("calls")
        assert event["error"] == "TransportStallSuspected"
        artifact = runner.capture_transport_bundle(
            store, IDENTITY, {"provider_backend": "local"},
            "TransportStallSuspected")
        (bundle_event,) = store.events("transport_bundles")
        assert bundle_event["artifact"] == artifact
        bundle = json.loads(
            (store.root / artifact["path"]).read_text())
        assert bundle["reason"] == "TransportStallSuspected"
        assert bundle["/health"] is not None


def test_a3_flowing_past_outer_bound_ends_as_call_outer_bound(
        tmp_path, monkeypatch):
    # Stub shape 3 (scaled): tokens keep flowing past the 7,200 s
    # hard outer bound — the call ends as the named call_outer_bound
    # limit, partial stream recorded, charged at reservation.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 60)
    monkeypatch.setattr(local_mod, "CALL_OUTER_BOUND_SECONDS", 3)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("flow") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        with pytest.raises(CallOuterBoundError):
            provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    (event,) = store.events("calls")
    assert event["error"] == "CallOuterBound"
    assert event["limit_kind"] == "call_outer_bound"
    assert event["input_tokens"] is None  # unknown usage: reservation charge
    assert event["unknown_reason"] == "CallOuterBound"
    assert event["stream_tokens_received"] > 0
    artifact = store.root / event["artifacts"]["response"]["path"]
    partial = json.loads(artifact.read_text())
    assert partial["partial"] is True
    assert partial["limit_kind"] == "call_outer_bound"
    assert partial["choices"][0]["message"]["content"]  # partial stream kept
    (record,) = store.events("transport_events")
    assert record["kind"] == "call_outer_bound"
    assert record["partial_stream_recorded"] is True
    # The named limit classifies as a disclosed model outcome.
    assert classify_halt("limit", "call_outer_bound") == (
        "model_outcome", "call_outer_bound")


# ---------------- C1-A4: write-time observation cap ----------------

def recorded_construction_history():
    """A recorded-history shape in the Stage 1R style: pinned items
    plus tool observations with large outputs."""
    big = json.dumps({"exit_code": 0, "stdout": "y" * 100000,
                      "stderr": "e" * 5000})
    messages = [{"role": "system", "content": "system prompt"},
                {"role": "user", "content": "the task statement"}]
    for _ in range(6):
        messages.append({"role": "user",
                         "content": "Current phase: constitution\nprompt"})
        messages.append({"role": "assistant",
                         "content": '{"action":"shell","command":"ls"}'})
        messages.append({"role": "user", "content": big})
    return messages


def test_a4_write_time_cap_shrinks_recorded_history_pinned_intact():
    messages = recorded_construction_history()
    before = estimate_tokens(messages)
    capped = []
    for message in messages:
        if message["role"] == "user" and message["content"].startswith("{"):
            parsed = json.loads(message["content"])
            if "stdout" in parsed:
                capped.append({"role": "user",
                               "content": json.dumps(cap_observation(parsed, 4096))})
                continue
        capped.append(message)
    after = estimate_tokens(capped)
    assert after < before // 4
    # Pinned items pass through byte-identical.
    assert capped[0] == messages[0] and capped[1] == messages[1]
    assert all(c == m for c, m in zip(capped, messages)
               if m["content"].startswith("Current phase:"))
    # Byte counts are recorded on the capped observation itself.
    obs = json.loads(next(c["content"] for c in capped
                          if "stdout_bytes_total" in c["content"]))
    assert obs["stdout_bytes_total"] == 100000
    assert obs["stdout_bytes_kept"] == 4096
    assert "truncated at write time" in obs["stdout"]


def test_a4_environment_caps_only_drafting_phase_observations(tmp_path):
    store = Store(tmp_path)

    class BigSandbox:
        def execute(self, command, timeout=60):
            return {"exit_code": 0, "stdout": "z" * 50000, "stderr": ""}

    env = runner.MiniEnvironment(BigSandbox(), time.monotonic() + 600,
                                   store, {"attempt_id": "a"}, cfg={})
    env.phase = "constitution"
    drafting = env.execute({"command": "ls"})
    assert drafting["stdout_bytes_total"] == 50000
    assert drafting["stdout_bytes_kept"] == 4096
    env.phase = "implement"
    delivery = env.execute({"command": "ls"})
    assert len(delivery["stdout"]) == 24000  # pre-Cycle-1 bound, unchanged
    assert "stdout_bytes_total" not in delivery


# ---------------- C1-a: wire-vs-assembled accounting ----------------

def test_a1a_call_records_carry_assembled_and_wire_with_over_cap_flag(
        tmp_path, monkeypatch):
    # Offline fixture with a scripted over-cap history: the assembled
    # history estimates far above the wire cap; the call record must
    # carry both the assembled and the wire numbers and the flag.
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.context_stats = {"assembled_tokens": 55000,
                                  "sent_tokens": 20000,
                                  "observations_masked": 9}
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 60)
    assert text
    (event,) = store.events("calls")
    assert event["assembled_tokens"] == 55000
    assert event["wire_tokens"] == 11  # the provider's reported input usage
    assert event["assembled_over_wire_cap"] is True  # 55,000 > 24,576


def test_a1a_under_cap_call_records_both_series_unflagged(tmp_path, monkeypatch):
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.query([{"role": "user", "content": "hi"}], "repair", 60)
    (event,) = store.events("calls")
    assert event["assembled_tokens"] < 24576
    assert event["wire_tokens"] == 11
    assert event["assembled_over_wire_cap"] is False


# ---------------- C1-b: observation masking ----------------

def stage1_shaped_history(rounds=30, observation_chars=8000):
    messages = [{"role": "system", "content": "system prompt"},
                {"role": "user", "content": "the task statement"},
                {"role": "user", "content": "Current phase: constitution\nprompt"}]
    for i in range(rounds):
        messages.append({"role": "assistant",
                         "content": '{"action":"shell","command":"ls"}'})
        messages.append({"role": "user", "content": json.dumps(
            {"exit_code": 0, "stdout": f"output {i} " + "y" * observation_chars,
             "stderr": ""})})
    return messages


def test_b_masking_replay_holds_the_wire_cap_and_pins():
    messages = stage1_shaped_history()
    assert estimate_tokens(messages) > 24576 * 2  # the Stage 1 regime
    result = mask_history(messages, 24576)
    assert result.sent_tokens <= 24576
    # Pinned items survive byte-identical: system, task statement,
    # phase prompt.
    assert result.messages[0] == messages[0]
    assert result.messages[1] == messages[1]
    assert result.messages[2] == messages[2]
    # The most recent K=8 observations are intact; older ones are
    # one-line elisions carrying their byte counts.
    intact = [m for m in result.messages
              if '"stdout"' in m["content"] and "elided" not in m["content"]]
    assert len(intact) == 8
    elisions = [json.loads(m["content"]) for m in result.messages
                if "elided_observation" in m["content"]]
    assert len(elisions) == 22
    assert all(e["original_bytes"] > 8000 for e in elisions)
    # Deterministic, and the agent's own history is never mutated.
    again = mask_history(messages, 24576)
    assert again.messages == result.messages
    assert estimate_tokens(messages) > 24576 * 2
    # By construction: even when K intact observations alone would
    # exceed the cap (20,000-char observations), masking escalates
    # oldest-first until the sent history fits.
    heavy = mask_history(stage1_shaped_history(observation_chars=20000), 24576)
    assert heavy.sent_tokens <= 24576
    assert heavy.masked_count > 22


def test_b_masking_through_the_model_records_stats(tmp_path, monkeypatch):
    # End to end through MiniModel + the local provider: a bloated
    # assembled history is measured in full, masked for the wire, and
    # both numbers land on the call record.
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.2)
    with cycle1_stub("drip") as (server, base_url):
        provider, store = _local_provider(tmp_path, monkeypatch, base_url)
        cfg = {**LOCAL_CFG}
        model = runner.MiniModel(provider, time.monotonic() + 600, 60, cfg=cfg)
        model.phase = "repair"
        reply = model.query(stage1_shaped_history(
            rounds=12, observation_chars=20000))
    assert reply["role"] == "assistant"
    (event,) = store.events("calls")
    assert event["assembled_tokens"] > 24576
    assert event["assembled_over_wire_cap"] is True
    assert event["sent_tokens"] <= 24576
    assert event["observations_masked"] > 0
    assert event["wire_tokens"] == 11


# ---------------- C1-c: envelopes, rollover, force-advance ----------------

class FinalizeAwareProvider(RecordingProvider):
    """Answers shell from its script, but emits the phase artifact
    when the harness's reserved finalize instruction is in view."""

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
        return super().query(messages, phase, timeout)


def run_attempt_custom(tmp_path, arm, provider, store, identity, cfg_extra=None):
    cfg = {**BASE_CFG, **(cfg_extra or {})}
    return runner.execute_attempt(ROOT, {"problem_statement": "fixture"},
                                  arm, provider, FakeSandbox(), store,
                                  identity, cfg)


def test_c_runaway_drafting_phase_force_advances_with_artifact(tmp_path):
    # The runaway shape, in a drafting phase: specify shells at
    # 400,000 a call past its envelope — the reserved finalize call
    # emits the artifact and the attempt proceeds to completion.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 400000, 0)]
    provider = FinalizeAwareProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity)
    assert "phase_exhausted" not in result
    record = [p for p in store.events("phases") if p["phase"] == "specify"][0]
    assert record["force_advanced"] is True
    assert record["artifact"]
    completed = {p["phase"] for p in store.events("phases")}
    assert {"plan", "tasks", "implement", "converge"} <= completed


def test_c_finalize_failure_ends_with_exhaustion_classification(tmp_path):
    # The finalize call itself fails to emit an artifact (the model
    # keeps shelling): the phase ends with the existing exhaustion
    # classification — no retry loops.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "plan", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 400000, 0)]
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity)
    assert result["phase_exhausted"] == "specify"
    specify_calls = [c for c in store.events("calls") if c["phase"] == "specify"]
    assert len(specify_calls) == 4  # 3 drafting + exactly 1 finalize call


def test_c_unused_envelope_rolls_forward_to_the_next_drafting_phase(tmp_path):
    # Specify completes nearly free; plan then spends 1,000,000 —
    # past one phase's 900,000 envelope, inside the rolled-forward
    # cumulative envelope (2 x 900,000). It completes untouched.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "tasks", "implement", "converge"))
    script["specify"] = [("shell", 100000, 0), ("done", 100, 50)]
    script["plan"] = [("shell", 200000, 0)] * 5 + [("done", 100, 50)]
    provider = RecordingProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity)
    assert "phase_exhausted" not in result
    plan_calls = [c for c in store.events("calls") if c["phase"] == "plan"]
    assert sum(c["input_tokens"] for c in plan_calls) == 1000100
    assert not any(p.get("force_advanced") for p in store.events("phases"))


def test_c_completing_shape_is_untouched(tmp_path):
    # Every phase completes inside its envelope: no finalize call is
    # ever requested and no phase record carries the flag.
    store = Store(tmp_path)
    identity = {"attempt_id": "att-1", "task_id": "TASK", "arm": "spec_kit",
                "repeat": 1}
    script = done_script(("constitution", "specify", "plan", "tasks",
                          "implement", "converge"))
    provider = FinalizeAwareProvider(store, identity, script)
    result = run_attempt_custom(tmp_path, "spec_kit", provider, store, identity)
    assert "phase_exhausted" not in result
    assert not any(p.get("force_advanced") for p in store.events("phases"))
    assert provider.counts == {phase: 1 for phase in
                               ("constitution", "specify", "plan", "tasks",
                                "implement", "converge")}


def test_c_constitution_keeps_the_guard_no_force_advance(tmp_path):
    # Constitution is handled by the banked construction structure
    # (C1-A2), not by force-advance: the in-attempt runaway shape
    # still ends at the Amendment 1 guard, unchanged.
    script = {"constitution": [("shell", 40000, 0)]}
    store, provider, result = run_attempt(tmp_path, "spec_kit", script)
    assert result["phase_exhausted"] == "constitution"
    assert not any(p.get("force_advanced") for p in store.events("phases"))
