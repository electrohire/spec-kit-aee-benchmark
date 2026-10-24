"""Amendment 1 R-A5/R-A6 tests: streamed local transport + worker probe.

Real local stub HTTP servers (http.server in a thread) exercise the SSE
reading path end to end: no external network, no paid calls.
"""
import json
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import benchmark_runner.local_provider as local_mod
from benchmark_runner.accounting import Budget
from benchmark_runner.local_provider import (
    LocalProvider, TransportStallError, probe_worker)
from benchmark_runner.provider import ProviderError
from benchmark_runner.store import Store

MODEL = "qwen3-8b-local"
IDENTITY = {"experiment_id": "exp", "run_id": "run0123456789ab", "arm": "repair_ordinary",
            "task_id": "t1", "repeat": 1, "attempt_id": "a1", "purpose": "test"}
CFG = {"model": MODEL, "max_output_tokens": 64, "provider_backend": "local",
       "transport": {"min_request_gap_seconds": 0}}
USAGE = {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14,
         "prompt_tokens_details": {"cached_tokens": 2},
         "completion_tokens_details": {"reasoning_tokens": 1}}


def _chunk(content=None, reasoning=None, usage=None):
    chunk = {"id": "chatcmpl-1", "model": MODEL, "choices": []}
    if usage is not None:
        chunk["usage"] = usage
    if content is not None or reasoning is not None:
        delta = {}
        if content is not None:
            delta["content"] = content
        if reasoning is not None:
            delta["reasoning_content"] = reasoning
        chunk["choices"] = [{"delta": delta}]
    return chunk


def _sse(handler, chunks):
    for chunk in chunks:
        handler.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        handler.wfile.flush()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"data": [{"id": MODEL}]})
        elif self.path.endswith("/slots"):
            if getattr(self.server, "strict_slots_path", False) and self.path != "/slots":
                # The live endpoint's shape: native routes exist only
                # at the server root, never under the /v1 prefix.
                self._json({"error": "no slots"}, status=404)
            elif self.server.slots_mode == "missing":
                self._json({"error": "no slots"}, status=404)
            elif self.server.slots_mode == "processing":
                self._json([{"id": 0, "is_processing": True},
                            {"id": 1, "is_processing": False}])
            else:
                self._json([{"id": 0, "is_processing": False}])
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            self.server.last_payload = json.loads(body.decode())
        except ValueError:
            self.server.last_payload = None
        mode = self.server.chat_mode
        try:
            if mode == "sse":
                self._sse_headers()
                _sse(self, [_chunk('{"action":'), _chunk(' "done"'), _chunk('}'),
                            _chunk(usage=USAGE)])
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            elif mode == "slow_sse":
                self._sse_headers()
                _sse(self, [_chunk("slow-")])
                time.sleep(1.2)  # gap > read slice, < stall bound
                _sse(self, [_chunk("ok"), _chunk(usage=USAGE)])
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            elif mode == "flow":
                self._sse_headers()
                while True:  # tokens keep flowing until the client deadline
                    _sse(self, [_chunk("x")])
                    time.sleep(0.2)
            elif mode == "stall":
                self._sse_headers()
                _sse(self, [_chunk("x")])
                time.sleep(6)  # silence: the client must declare a stall first
            elif mode in ("slow_headers", "silent_headers"):
                # Prompt-processing silence: no headers at all until the
                # delay passes (the live failure the first construction
                # smoke hit — a 30 s slice used to kill the call here).
                time.sleep(1.5 if mode == "slow_headers" else 6)
                self._sse_headers()
                _sse(self, [_chunk("ok"), _chunk(usage=USAGE)])
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:  # "json": the pre-Amendment non-streaming shape
                self._json({"id": "chatcmpl-1", "model": MODEL,
                            "choices": [{"message": {"role": "assistant",
                                                     "content": "ok"}}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                                      "total_tokens": 12,
                                      "prompt_tokens_details": {"cached_tokens": 0},
                                      "completion_tokens_details": {"reasoning_tokens": 0}}})
        except (BrokenPipeError, ConnectionResetError):
            pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass  # a client that stalls out / times out closes mid-response


@contextmanager
def stub_server(chat_mode="sse", slots_mode="processing", strict_slots_path=False):
    server = _Server(("127.0.0.1", 0), _Handler)
    server.chat_mode, server.slots_mode = chat_mode, slots_mode
    server.strict_slots_path = strict_slots_path
    server.last_payload = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def _provider(tmp_path, monkeypatch, base_url):
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    store = Store(tmp_path / "store")
    budget = Budget(store, Decimal("100"), Decimal("25"))
    return LocalProvider(CFG, store, budget, IDENTITY), store


def _env(monkeypatch, base_url):
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)


def test_streamed_query_assembles_text_and_records_telemetry(tmp_path, monkeypatch):
    with stub_server("sse") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    assert text == '{"action": "done"}'
    # The request itself went out streamed, with usage requested.
    assert server.last_payload["stream"] is True
    assert server.last_payload["stream_options"] == {"include_usage": True}
    (event,) = store.events("calls")
    assert event["error"] is None
    assert event["response_model"] == MODEL
    # Usage came from the usage-bearing chunk, not from token counting.
    assert event["input_tokens"] == 11 and event["output_tokens"] == 3
    assert event["cached_input_tokens"] == 2 and event["reasoning_tokens"] == 1
    assert event["unknown_reason"] is None
    assert event["first_token_seconds"] is not None
    assert event["first_token_seconds"] >= 0
    assert event["last_token_at"] is not None
    assert event["stream_tokens_received"] == 3  # the three content chunks
    assert event["stream_chunks"] == 4  # three token chunks + the usage chunk
    # The response artifact holds the assembled completion.
    artifact = tmp_path / "store" / event["artifacts"]["response"]["path"]
    assembled = json.loads(artifact.read_text())
    assert assembled["model"] == MODEL
    assert assembled["choices"][0]["message"]["content"] == '{"action": "done"}'
    assert assembled["usage"] == USAGE


def test_stalled_stream_raises_transport_stall_and_records_event(tmp_path, monkeypatch):
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 2)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.5)
    with stub_server("stall") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        with pytest.raises(TransportStallError):
            provider.query([{"role": "user", "content": "hi"}], "repair", 60)
    (event,) = store.events("calls")
    assert event["error"] == "TransportStallSuspected"
    for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
        assert event[field] is None
    assert event["unknown_reason"] == "TransportStallSuspected"
    assert event["cost"] == "0"  # charged at its (zero-dollar) reservation
    assert event["stream_tokens_received"] == 1
    assert event["first_token_seconds"] is not None
    assert event["last_token_at"] is not None
    (record,) = store.events("transport_events")
    assert record["kind"] == "transport_stall_suspected"
    assert record["call_id"] == event["call_id"]
    assert record["attempt_id"] == IDENTITY["attempt_id"]
    assert record["task_id"] == IDENTITY["task_id"]
    assert record["arm"] == IDENTITY["arm"]
    assert record["phase"] == "repair"
    assert record["stall_after_seconds"] == 2
    assert record["stream_tokens_received"] == 1
    assert record["first_token_seconds"] is not None
    assert record["last_token_at"] is not None
    assert record["timestamp"] is not None
    budget = store.events("budget")
    assert [e["status"] for e in budget] == ["reserved", "settled"]
    assert all(Decimal(e["amount"]) == 0 for e in budget)


def test_non_stream_json_fallback_records_zero_stream_telemetry(tmp_path, monkeypatch):
    with stub_server("json") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    assert text == "ok"
    (event,) = store.events("calls")
    assert event["error"] is None
    assert event["input_tokens"] == 10 and event["output_tokens"] == 2
    assert event["stream_tokens_received"] == 0
    assert event["stream_chunks"] == 0
    assert event["first_token_seconds"] == event["duration_seconds"]
    assert event["last_token_at"] == event["ended_at"]


def test_slow_tokens_within_stall_bound_complete(tmp_path, monkeypatch):
    # Read slices expire between tokens, but the token gap stays under the
    # stall bound: the call must complete, not stall and not time out.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 5)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.5)
    with stub_server("slow_sse") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    assert text == "slow-ok"
    (event,) = store.events("calls")
    assert event["error"] is None
    assert event["stream_tokens_received"] == 2
    assert store.events("transport_events") == []


def test_flowing_stream_past_deadline_is_timeout_not_stall(tmp_path, monkeypatch):
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 30)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.5)
    with stub_server("flow") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        with pytest.raises(ProviderError) as caught:
            provider.query([{"role": "user", "content": "hi"}], "repair", 1)
    assert not isinstance(caught.value, TransportStallError)
    (event,) = store.events("calls")
    assert event["error"] == "TimeoutError"
    assert event["unknown_reason"] == "TimeoutError"
    assert event["input_tokens"] is None
    assert event["stream_tokens_received"] > 0
    assert store.events("transport_events") == []


def test_slow_first_headers_within_stall_bound_complete(tmp_path, monkeypatch):
    # Regression for the first construction smoke (2026-10-21): the
    # worker sends no headers until prompt processing finishes. A
    # pre-header silence shorter than the stall bound must not kill
    # the call (it used to die at one 30 s read slice, TimeoutError).
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 10)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.5)
    with stub_server("slow_headers") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        text = provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    assert text == "ok"
    (event,) = store.events("calls")
    assert event["error"] is None
    assert event["stream_tokens_received"] == 1
    assert store.events("transport_events") == []


def test_silence_before_headers_past_stall_bound_is_a_stall(tmp_path, monkeypatch):
    # The same silence, past the 180 s rule (patched down): the named
    # stall event, premise accounting, never a bare TimeoutError.
    monkeypatch.setattr(local_mod, "STALL_SECONDS", 2)
    monkeypatch.setattr(local_mod, "_READ_SLICE_SECONDS", 0.5)
    with stub_server("silent_headers") as (server, base_url):
        provider, store = _provider(tmp_path, monkeypatch, base_url)
        with pytest.raises(TransportStallError):
            provider.query([{"role": "user", "content": "hi"}], "repair", 30)
    (event,) = store.events("calls")
    assert event["error"] == "TransportStallSuspected"
    assert event["input_tokens"] is None
    assert event["stream_tokens_received"] == 0
    (stall,) = store.events("transport_events")
    assert stall["kind"] == "transport_stall_suspected"


def test_probe_worker_reports_busy_slot(tmp_path, monkeypatch):
    with stub_server("sse", slots_mode="processing") as (server, base_url):
        _env(monkeypatch, base_url)
        result = probe_worker({"min_request_gap_seconds": 0})
    assert result["model_ok"] is True
    assert result["reported_models"] == [MODEL]
    assert result["busy"] is True
    assert result["slots"] == [{"id": 0, "is_processing": True},
                               {"id": 1, "is_processing": False}]
    assert result["error"] is None
    assert result["probed_at"] is not None


def test_probe_worker_slots_unavailable_gives_busy_none(tmp_path, monkeypatch):
    with stub_server("sse", slots_mode="missing") as (server, base_url):
        _env(monkeypatch, base_url)
        result = probe_worker({"min_request_gap_seconds": 0})
    assert result["model_ok"] is True
    assert result["busy"] is None
    assert result["slots"] is None
    # Unavailable slot state is not a probe failure: an endpoint that
    # does not expose /slots must not block every attempt (the first
    # live smoke attempt was blocked exactly this way).
    assert result["error"] is None


def test_probe_worker_finds_slots_at_the_server_root(tmp_path, monkeypatch):
    # Regression for the first live smoke: the configured base URL
    # ends in /v1, but /slots lives at the server root. The stub 404s
    # /v1/slots exactly as the real endpoint does.
    with stub_server("sse", slots_mode="processing",
                     strict_slots_path=True) as (server, base_url):
        assert base_url.endswith("/v1")
        _env(monkeypatch, base_url)
        result = probe_worker({"min_request_gap_seconds": 0})
    assert result["model_ok"] is True
    assert result["busy"] is True
    assert result["error"] is None


def test_probe_worker_idle_slots_not_busy(tmp_path, monkeypatch):
    with stub_server("sse", slots_mode="idle") as (server, base_url):
        _env(monkeypatch, base_url)
        result = probe_worker({"min_request_gap_seconds": 0})
    assert result["model_ok"] is True
    assert result["busy"] is False
    assert result["error"] is None
