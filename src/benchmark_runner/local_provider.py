"""Local inference backend: an OpenAI-compatible server (llama.cpp) on the operator host.

Selected when the frozen manifest config sets ``provider_backend: "local"``.
Model identity must match the frozen manifest and the local environment::

    LOCAL_MODEL_BASE_URL  default http://localhost:8080/v1
    LOCAL_MODEL_NAME      required; must match the model the server reports
    LOCAL_MODEL_API_KEY   optional; sent as Bearer when the server requires one

Cost accounting: local inference has zero marginal dollars per call. Events
carry cost_basis "local_inference" and cost "0"; the budget ledger still
records a zero reservation per call so every call is tracked. Fail-closed:
the server is probed once per process via /v1/models before any query, and
the reported model name must match LOCAL_MODEL_NAME, so a campaign can never
silently run against the wrong checkpoint.
"""
import json
import os
import select
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

from .accounting import TOKEN_FIELDS, native_usage
from .store import canonical, utc
from .schema import validate_call, validate_identity
from .provider import ProviderError, paced_wait, transport_policy

# Amendment 1 R-A5 streamed transport: a call with no token for this many
# consecutive seconds is a suspected transport stall (premise/equipment),
# not a slow generation. Reads run in slices of this many seconds so the
# stall clock and the overall per-call deadline can both be observed while
# a streamed response is in flight.
STALL_SECONDS = 180
_READ_SLICE_SECONDS = 30


class TransportStallError(ProviderError):
    pass


def _set_socket_timeout(handle, seconds):
    """Best-effort socket-timeout adjustment on an opened response:
    the opener runs with the full per-call deadline (a slow prompt
    eval sends no headers for minutes), but the read machinery runs
    on slice timeouts. A failure leaves the deadline in place; the
    read loop's own clock checks still bound the call."""
    try:
        handle.fp.raw._sock.settimeout(seconds)
    except (AttributeError, OSError, ValueError):
        pass


class _TransportStall(Exception):
    """Internal control-flow signal: the stall path builds its own event."""


def base_url():
    return os.environ.get("LOCAL_MODEL_BASE_URL", "http://localhost:8080/v1").rstrip("/")


def model_name():
    name = os.environ.get("LOCAL_MODEL_NAME")
    if not name:
        raise ValueError("LOCAL_MODEL_NAME is not set: the local backend refuses to run "
                         "against an unidentified model")
    return name


def _headers():
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LOCAL_MODEL_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    return headers


def _extract_text(message):
    """Action text from a chat-completion message, hardened for reasoning models.

    Qwen3 on llama.cpp may return the answer in ``reasoning_content`` with an
    empty ``content`` (when the server splits reasoning out), or emit
    ``<think>...</think>`` blocks inside ``content`` (default server behavior).
    The agent's action parser is a strict ``json.loads``, so both cases would
    otherwise burn calls on unparseable output. Returns
    (text, reasoning_fallback, think_stripped).
    """
    import re
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    fallback = False
    if not content and reasoning:
        content, fallback = reasoning, True
    stripped, n = re.subn(r"(?is)<think>.*?</think>", "", content)
    text = stripped.strip()
    return text, fallback, n > 0


def check_local_server(policy=None):
    """Fail-closed server probe: reachable, and serving the expected model.

    Raises ValueError with an actionable message when the server is down or
    reports a different model. Called once per process before any query and
    from validate_live() before a campaign starts. The probe goes through
    the process-wide pacer like all other provider traffic.
    """
    policy = policy or transport_policy({})
    url = base_url() + "/models"
    expected = model_name()
    try:
        paced_wait(policy)
        req = urllib.request.Request(url, headers=_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as handle:
            data = json.loads(handle.read().decode())
    except Exception as e:
        raise ValueError(
            f"local model server unreachable at {url}: {type(e).__name__}. "
            f"Start it with scripts/local-model-setup.sh (or your llama-server command) "
            f"and set LOCAL_MODEL_BASE_URL if it is not on localhost:8080") from e
    reported = [entry.get("id") for entry in data.get("data") or []]
    if expected not in reported:
        raise ValueError(
            f"local server reports model {reported!r} but LOCAL_MODEL_NAME={expected!r}; "
            f"refusing to run against the wrong checkpoint")
    return expected


def probe_worker(policy=None):
    """Non-raising worker probe for the Amendment 1 R-A6 observability bundle.

    Reports which models the endpoint claims to serve, whether the frozen
    model is among them, and whether any llama.cpp slot is currently
    processing. Never raises: any failure is reported as the bare exception
    type name in ``error`` (never headers or bodies), with ``busy`` None
    when slot state is unavailable.
    """
    probed_at = utc()
    reported, slots, busy, error = [], None, None, None
    try:
        expected = model_name()
    except Exception as e:  # noqa: BLE001 - the probe records, never raises
        return {"probed_at": probed_at, "model_ok": False, "reported_models": [],
                "busy": None, "slots": None, "error": type(e).__name__}
    policy = policy or transport_policy({})
    try:
        paced_wait(policy)
        req = urllib.request.Request(base_url() + "/models", headers=_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as handle:
            data = json.loads(handle.read().decode())
        reported = [entry.get("id") for entry in data.get("data") or []]
    except Exception as e:  # noqa: BLE001
        error = type(e).__name__
        reported = []
    try:
        paced_wait(policy)
        req = urllib.request.Request(base_url() + "/slots", headers=_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as handle:
            raw_slots = json.loads(handle.read().decode())
        if isinstance(raw_slots, list):
            slots = [{"id": entry.get("id") if isinstance(entry, dict) else None,
                      "is_processing": entry.get("is_processing") if isinstance(entry, dict) else None}
                     for entry in raw_slots]
            busy = any(bool(slot["is_processing"]) for slot in slots)
    except Exception as e:  # noqa: BLE001
        slots, busy = None, None
        if error is None:
            error = type(e).__name__
    return {"probed_at": probed_at, "model_ok": expected in reported,
            "reported_models": reported, "busy": busy, "slots": slots,
            "error": error}


class LocalProvider:
    def __init__(self, config, store, budget, identity):
        self.config, self.store, self.budget, self.identity = config, store, budget, identity
        self.model, self.url = model_name(), base_url()
        if config["model"] != self.model:
            raise ValueError("local model differs from frozen configuration")
        if config.get("local_base_url", self.url).rstrip("/") != self.url:
            raise ValueError("local endpoint differs from frozen configuration")
        self.policy = transport_policy(config)
        check_local_server(self.policy)  # Fail before any reservation, never mid-campaign.

    @staticmethod
    def _open_stream(req, tick, deadline_seconds, last_token_mono):
        """Open a streaming response under the R-A5 clocks. The server
        sends no headers until prompt processing finishes, which on
        this worker legitimately takes longer than any read slice —
        the first smoke construction died at one 30 s slice with a
        plain TimeoutError before the stall machinery ever ran.
        urlopen therefore runs with the full per-call deadline in a
        daemon thread while this thread enforces both clocks from
        byte zero: silence reaching STALL_SECONDS (counted from the
        request start until the first token) raises the stall, and
        the deadline bounds the whole call. A stall raised here
        abandons the opener thread (a daemon; a transport stall halts
        the study before anything else is sent)."""
        holder = {}

        def _open():
            try:
                holder["handle"] = urllib.request.urlopen(
                    req, timeout=deadline_seconds)
            except BaseException as e:  # surfaced in the calling thread
                holder["error"] = e

        opener = threading.Thread(target=_open, daemon=True)
        opener.start()
        while opener.is_alive():
            opener.join(0.5)
            now = time.monotonic()
            if now - last_token_mono >= STALL_SECONDS:
                raise _TransportStall()
            if now - tick >= deadline_seconds:
                raise TimeoutError("per-call deadline exceeded")
        if "error" in holder:
            raise holder["error"]
        return holder["handle"]

    def query(self, messages, phase, timeout, retry=0):
        cfg = self.config
        # Same fail-fast telemetry discipline as the OpenAI provider: every
        # field known up front is validated before the HTTP request.
        validate_identity({**self.identity, "phase": phase})
        call_id = uuid.uuid4().hex
        charge = None
        # Zero reservation: local inference has no marginal dollar cost, but
        # the ledger still records every call.
        self.budget.reserve(call_id, self.identity["attempt_id"], Decimal(0))
        # Amendment 1 R-A5: the call event is built (and the stall flag
        # raised) after the try/finally below settles the reservation, so
        # the stall state must survive the finally block's scope.
        stall = False
        try:
            started, tick = utc(), time.monotonic()
            payload = dict(model=self.model, messages=messages,
                           max_completion_tokens=cfg["max_output_tokens"],
                           stream=True, stream_options={"include_usage": True})
            if cfg.get("temperature") is not None:
                payload["temperature"] = cfg["temperature"]
            request_artifact = self.store.artifact(canonical(payload))
            response, request_id, error, response_artifact = {}, None, None, None
            # Streamed-transport telemetry (R-A5), recorded on EVERY call
            # event. last_token_mono starts at the request start: a call
            # that never receives a token stalls from its start.
            first_token_seconds, last_token_at = None, None
            last_token_mono = tick
            stream_tokens_received, stream_chunks = 0, 0
            streamed_model, fallback = None, False
            usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": None}
            try:
                req = urllib.request.Request(self.url + "/chat/completions",
                                             canonical(payload), _headers())
                paced_wait(self.policy)  # The process-wide gap covers local traffic too.
                with self._open_stream(req, tick, timeout, last_token_mono) as handle:
                    request_id = handle.headers.get("x-request-id")
                    content_type = handle.headers.get("Content-Type") or ""
                    _set_socket_timeout(
                        handle, _READ_SLICE_SECONDS
                        if "text/event-stream" in str(content_type).lower()
                        else timeout)
                    if "text/event-stream" not in str(content_type).lower():
                        # Compatibility fallback: a non-streaming endpoint
                        # (including the stub servers in the offline tests)
                        # is processed exactly as the pre-Amendment code did.
                        fallback = True
                        response = json.loads(handle.read().decode())
                        response_artifact = self.store.artifact(canonical(response))
                        usage = native_usage(response)
                        if response.get("model") != self.model:
                            error = "ModelIdentityMismatch"
                    else:
                        content_parts, reasoning_parts, usage_raw = [], [], None
                        # Lines are assembled from fills in _READ_SLICE_SECONDS
                        # slices, never by a blocking readline(), for two
                        # reasons in http.client's plumbing: (1) a socket
                        # timeout poisons its buffered reader ("cannot read
                        # from timed out object"), so after one slice a
                        # stalled stream could never be read again; and
                        # (2) header parsing may already have pulled the
                        # first chunk(s) into that buffer, where select() on
                        # the socket cannot see them. The fill therefore
                        # peeks the buffer first: buffered bytes are served
                        # by read1() with no raw read; an empty buffer makes
                        # peek() itself the slice wait, and its timeout
                        # proves the buffer is empty, so reading can safely
                        # switch to a dup'd raw socket (plain socket
                        # timeouts do not poison) for the remaining slices.
                        # Every slice expiry compares the two clocks: the
                        # token gap (stall) vs the overall deadline.
                        buf, eof, done = b"", False, False
                        raw_sock = None
                        try:
                            while not done:
                                # Overall per-call deadline: tokens still
                                # flowing past it is a plain timeout, not a stall.
                                if time.monotonic() - tick >= timeout:
                                    raise TimeoutError("per-call deadline exceeded")
                                newline = buf.find(b"\n")
                                if newline >= 0:
                                    raw_line, buf = buf[:newline], buf[newline + 1:]
                                elif eof:
                                    if not buf:
                                        break  # EOF: stream ended without [DONE].
                                    raw_line, buf = buf, b""
                                else:
                                    if raw_sock is not None:
                                        try:
                                            data = raw_sock.recv(65536)
                                        except TimeoutError:
                                            now = time.monotonic()
                                            if now - last_token_mono >= STALL_SECONDS:
                                                raise _TransportStall() from None
                                            if now - tick >= timeout:
                                                raise
                                            continue  # Next slice.
                                    else:
                                        fp = getattr(handle, "fp", None)
                                        buffered = None
                                        if fp is not None and hasattr(fp, "peek"):
                                            try:
                                                buffered = fp.peek(1)
                                            except TimeoutError:
                                                now = time.monotonic()
                                                if now - last_token_mono >= STALL_SECONDS:
                                                    raise _TransportStall() from None
                                                if now - tick >= timeout:
                                                    raise
                                                # Buffer provably empty: take
                                                # over the raw socket (dup'd fd).
                                                raw_sock = socket.socket(
                                                    fileno=os.dup(handle.fileno()))
                                                raw_sock.settimeout(_READ_SLICE_SECONDS)
                                                continue  # Next slice, raw mode.
                                            except (OSError, ValueError):
                                                buffered = None
                                        if buffered:
                                            data = handle.read1(65536)
                                        elif buffered == b"":
                                            eof = True
                                            continue
                                        else:
                                            try:
                                                readable, _, _ = select.select(
                                                    [handle], [], [], _READ_SLICE_SECONDS)
                                            except (OSError, ValueError):
                                                readable = [handle]
                                            if not readable:
                                                now = time.monotonic()
                                                if now - last_token_mono >= STALL_SECONDS:
                                                    raise _TransportStall() from None
                                                if now - tick >= timeout:
                                                    raise TimeoutError(
                                                        "per-call deadline exceeded") from None
                                                continue  # Next slice.
                                            try:
                                                data = handle.read1(65536) \
                                                    if hasattr(handle, "read1") else handle.read(1)
                                            except TimeoutError:
                                                now = time.monotonic()
                                                if now - last_token_mono >= STALL_SECONDS:
                                                    raise _TransportStall() from None
                                                raise
                                    if data in (b"", ""):
                                        eof = True
                                    elif isinstance(data, bytes):
                                        buf += data
                                    else:
                                        buf += data.encode()
                                    continue
                                line = raw_line.decode("utf-8", errors="replace") \
                                    if isinstance(raw_line, bytes) else raw_line
                                line = line.strip()
                                if not line.startswith("data:"):
                                    continue
                                data = line[len("data:"):].strip()
                                if data == "[DONE]":
                                    done = True
                                    continue
                                if not data:
                                    continue
                                stream_chunks += 1
                                chunk = json.loads(data)
                                if chunk.get("model"):
                                    streamed_model = chunk["model"]
                                if chunk.get("usage") is not None:
                                    usage_raw = chunk["usage"]
                                choices = chunk.get("choices") or []
                                delta = (choices[0].get("delta") or {}) if choices else {}
                                piece, reasoning_piece = delta.get("content"), \
                                    delta.get("reasoning_content")
                                if piece is not None or reasoning_piece is not None:
                                    now = time.monotonic()
                                    if first_token_seconds is None:
                                        first_token_seconds = now - tick
                                    last_token_mono, last_token_at = now, utc()
                                    stream_tokens_received += 1
                                    if piece is not None:
                                        content_parts.append(piece)
                                    if reasoning_piece is not None:
                                        reasoning_parts.append(reasoning_piece)
                        finally:
                            if raw_sock is not None:
                                raw_sock.close()
                        response = {"model": streamed_model,
                                    "choices": [{"message": {
                                        "content": "".join(content_parts),
                                        "reasoning_content": "".join(reasoning_parts)}}],
                                    "usage": usage_raw}
                        response_artifact = self.store.artifact(canonical(response))
                        if usage_raw is not None:
                            usage = native_usage({"usage": usage_raw})
                        else:
                            usage = {**{k: None for k in TOKEN_FIELDS},
                                     "unknown_reason": "stream completed without usage"}
                        if streamed_model != self.model:
                            error = "ModelIdentityMismatch"
            except _TransportStall:
                stall = True
                error = "TransportStallSuspected"
                usage = {**{k: None for k in TOKEN_FIELDS},
                         "unknown_reason": "TransportStallSuspected"}
                response, response_artifact = {}, None
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
                error = type(e).__name__  # Never log headers or raw error bodies.
                usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                response, response_artifact = {}, None
            charge = Decimal(0)
            ended_at, duration = utc(), time.monotonic() - tick
            if fallback:
                first_token_seconds, last_token_at = duration, ended_at
                stream_tokens_received, stream_chunks = 0, 0
            response_model = response.get("model") if response else streamed_model
            message = (response.get("choices") or [{}])[0].get("message") or {}
            text, reasoning_fallback, think_stripped = _extract_text(message)
            event = {**self.identity, "call_id": call_id, "request_id": request_id,
                     "phase": phase, "provider": "local", "model": self.model,
                     "response_model": response_model, "started_at": started,
                     "ended_at": ended_at, "duration_seconds": duration, **usage,
                     "price_snapshot_id": "local-inference", "cost_basis": "local_inference",
                     "currency": "USD", "cost": str(charge),
                     "retry": retry, "error": error,
                     "first_token_seconds": first_token_seconds,
                     "last_token_at": last_token_at,
                     "stream_tokens_received": stream_tokens_received,
                     "stream_chunks": stream_chunks,
                     "reasoning_fallback": reasoning_fallback,
                     "think_stripped": think_stripped,
                     "artifacts": {"request": request_artifact, "response": response_artifact}}
            validate_call(event)
            self.store.append("calls", event)
            if stall:
                self.store.append("transport_events", {
                    "kind": "transport_stall_suspected",
                    **self.identity, "phase": phase, "call_id": call_id,
                    "stall_after_seconds": STALL_SECONDS,
                    "first_token_seconds": first_token_seconds,
                    "last_token_at": last_token_at,
                    "stream_tokens_received": stream_tokens_received,
                    "timestamp": utc()})
        finally:
            # Settle the zero reservation even when telemetry validation fails.
            self.budget.settle(call_id, charge)
        if stall:
            raise TransportStallError("TransportStallSuspected")
        if error:
            raise ProviderError(error)
        return text
