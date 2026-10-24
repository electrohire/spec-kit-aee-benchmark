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
from .context import estimate_tokens
from .store import canonical, utc
from .schema import validate_call, validate_identity
from .provider import (AttemptWallExpiredError, ProviderError, paced_wait,
                       transport_policy)

# Amendment 1 R-A5 streamed transport, with the per-call deadline made
# inactivity-aware by Cycle 1 C1-A3 (2026-10-21): a call dies as a
# suspected transport stall (premise/equipment) only after this many
# consecutive seconds with no streamed token. While tokens flow, a call
# may run to the hard outer bound below, where it ends as the named
# call_outer_bound limit with its partial stream recorded. Reads run in
# slices of this many seconds so both clocks can be observed while a
# streamed response is in flight.
STALL_SECONDS = 600
CALL_OUTER_BOUND_SECONDS = 7200
_READ_SLICE_SECONDS = 30


class TransportStallError(ProviderError):
    pass


class CallOuterBoundError(ProviderError):
    """A flowing call reached the hard outer bound (C1-A3): a named,
    disclosed limit, not a stall and not an invisible timeout."""


class _CallOuterBound(Exception):
    """Internal control-flow signal: the outer-bound path builds its
    own event, with the partial stream recorded."""


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


class _AttemptWallExpired(Exception):
    """Internal control-flow signal (Cycle 2 C2-F1): the per-call
    deadline the caller passed was the attempt-wall remainder and
    it elapsed mid-call. The wall path builds its own event, with
    the partial stream recorded, exactly as the outer-bound path
    does — but it is a scored attempt limit, not a transport event."""


def base_url():
    return os.environ.get("LOCAL_MODEL_BASE_URL", "http://localhost:8080/v1").rstrip("/")


def server_root():
    """The llama.cpp server root: the configured OpenAI base URL
    minus a trailing /v1 segment. The native routes (/slots, /props,
    /health) live at the root, not under the OpenAI prefix — the
    first live probe 404'd on /v1/slots while /slots answered 200."""
    url = base_url()
    return url[:-3] if url.endswith("/v1") else url


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


def _coalesce_same_role(messages):
    """Merge consecutive messages that share a role into one message
    (string contents joined by a blank line). Non-string contents and
    role changes pass through untouched; message order is preserved.
    Pure: the input list and its dicts are never mutated."""
    merged = []
    for message in messages:
        if (merged and merged[-1].get("role") == message.get("role")
                and isinstance(merged[-1].get("content"), str)
                and isinstance(message.get("content"), str)):
            merged[-1] = {**merged[-1],
                          "content": merged[-1]["content"] + "\n\n"
                                     + message["content"]}
        else:
            merged.append(message)
    return merged


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
        req = urllib.request.Request(server_root() + "/slots", headers=_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as handle:
            raw_slots = json.loads(handle.read().decode())
        if isinstance(raw_slots, list):
            slots = [{"id": entry.get("id") if isinstance(entry, dict) else None,
                      "is_processing": entry.get("is_processing") if isinstance(entry, dict) else None}
                     for entry in raw_slots]
            busy = any(bool(slot["is_processing"]) for slot in slots)
    except Exception:  # noqa: BLE001
        # Slot state unavailable is a recorded None, not a probe
        # failure: an endpoint that does not expose /slots must not
        # block every attempt. A worker that cannot be identified at
        # all already failed the /models fetch above, which is the
        # failure that sets the probe error.
        slots, busy = None, None
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
    def _open_stream(req, tick, deadline_seconds, last_token_mono,
                     deadline_is_wall=False):
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
            if deadline_seconds >= CALL_OUTER_BOUND_SECONDS \
                    and now - tick >= CALL_OUTER_BOUND_SECONDS:
                raise _CallOuterBound()
            if now - tick >= deadline_seconds:
                if deadline_is_wall:
                    raise _AttemptWallExpired()
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
        outer_bound = False
        wall_expired = False
        # C1-a: context stats handed in by the calling model (assembled
        # size before read-time masking, masked count, sent size).
        # Absent (direct provider use), the assembled size is estimated
        # from the messages as received.
        context_stats = getattr(self, "context_stats", None) or {}
        self.context_stats = None
        # C2-F1: the calling model names the binding deadline. When
        # it is the attempt wall ("attempt_wall"), the per-call
        # deadline expiring mid-call is a wall expiry (scored),
        # never the generic per-call timeout (premise/equipment).
        deadline_is_wall = getattr(self, "call_deadline_kind", None) == "attempt_wall"
        self.call_deadline_kind = None
        try:
            started, tick = utc(), time.monotonic()
            # Stage A bridge (2026-10-22): strict chat templates (the
            # Mistral family serving Pair B) reject consecutive
            # same-role messages with a server-side template error —
            # an equipment failure, never a model behavior. Under the
            # freeze-configured flag, consecutive same-role string
            # messages are coalesced for the wire only; the recorded
            # conversation is unchanged. Absent the flag the payload
            # is byte-identical to the pre-change payload.
            if cfg.get("coalesce_same_role_messages"):
                messages = _coalesce_same_role(messages)
            payload = dict(model=self.model, messages=messages,
                           max_completion_tokens=cfg["max_output_tokens"],
                           stream=True, stream_options={"include_usage": True})
            if cfg.get("temperature") is not None:
                payload["temperature"] = cfg["temperature"]
            # Stage A H5-P (2026-10-22): freeze-configured passthrough
            # for Pair D's registered serving — grammar-constrained
            # tool calls and chat-template kwargs (e.g.
            # preserve_thinking). Each key is copied verbatim into
            # the payload exactly when the freeze config carries it;
            # absent keys introduce no defaults and the payload is
            # byte-identical to the pre-change payload. Whether the
            # server honors these fields is a serve-time question,
            # not decided here.
            if "request_grammar" in cfg:
                payload["grammar"] = cfg["request_grammar"]
            if "chat_template_kwargs" in cfg:
                payload["chat_template_kwargs"] = cfg["chat_template_kwargs"]
            request_artifact = self.store.artifact(canonical(payload))
            response, request_id, error, response_artifact = {}, None, None, None
            # Streamed-transport telemetry (R-A5), recorded on EVERY call
            # event. last_token_mono starts at the request start: a call
            # that never receives a token stalls from its start.
            first_token_seconds, last_token_at = None, None
            last_token_mono = tick
            stream_tokens_received, stream_chunks = 0, 0
            streamed_model, fallback = None, False
            content_parts, reasoning_parts = [], []
            usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": None}

            def _bound_error():
                """The elapsed-time bound that applies right now
                (C1-A3): the hard outer bound when the caller granted
                it, otherwise the caller's own deadline. Stall is
                checked separately at every slice, before this."""
                now = time.monotonic()
                if timeout >= CALL_OUTER_BOUND_SECONDS \
                        and now - tick >= CALL_OUTER_BOUND_SECONDS:
                    return _CallOuterBound()
                if now - tick >= timeout:
                    if deadline_is_wall:
                        return _AttemptWallExpired()
                    return TimeoutError("per-call deadline exceeded")
                return None
            try:
                req = urllib.request.Request(self.url + "/chat/completions",
                                             canonical(payload), _headers())
                paced_wait(self.policy)  # The process-wide gap covers local traffic too.
                with self._open_stream(req, tick, timeout, last_token_mono,
                                       deadline_is_wall=deadline_is_wall) as handle:
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
                                # Overall per-call bound: tokens still
                                # flowing past it is a plain timeout (or
                                # the C1-A3 outer bound), not a stall.
                                bound = _bound_error()
                                if bound is not None:
                                    raise bound
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
                                            bound = _bound_error()
                                            if bound is not None:
                                                raise bound from None
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
                                                bound = _bound_error()
                                                if bound is not None:
                                                    raise bound from None
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
                                                bound = _bound_error()
                                                if bound is not None:
                                                    raise bound from None
                                                continue  # Next slice.
                                            try:
                                                data = handle.read1(65536) \
                                                    if hasattr(handle, "read1") else handle.read(1)
                                            except TimeoutError:
                                                now = time.monotonic()
                                                if now - last_token_mono >= STALL_SECONDS:
                                                    raise _TransportStall() from None
                                                bound = _bound_error()
                                                if bound is not None:
                                                    raise bound from None
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
            except _CallOuterBound:
                # C1-A3: a demonstrably flowing call reached the hard
                # outer bound. The partial stream is recorded as the
                # response artifact; usage is unknown, so the call is
                # charged at its reservation, as for any unknown-usage
                # call. This is a named limit, not a stall.
                outer_bound = True
                error = "CallOuterBound"
                usage = {**{k: None for k in TOKEN_FIELDS},
                         "unknown_reason": "CallOuterBound"}
                response = {"model": streamed_model,
                            "choices": [{"message": {
                                "content": "".join(content_parts),
                                "reasoning_content": "".join(reasoning_parts)}}],
                            "usage": None, "partial": True,
                            "limit_kind": "call_outer_bound"}
                response_artifact = self.store.artifact(canonical(response))
            except _AttemptWallExpired:
                # C2-F1: the wall remainder the harness passed as
                # this call's deadline elapsed while the call was
                # flowing (the stall clock, checked first at every
                # slice, never fired). The partial stream is
                # recorded as the response artifact and the call is
                # charged at its reservation, exactly as for the
                # outer bound — but the outcome is the scored
                # attempt-wall expiry, so NO transport event is
                # written: this is not a transport failure and no
                # R-A5 bundle attaches to it.
                wall_expired = True
                error = "AttemptWallExpired"
                usage = {**{k: None for k in TOKEN_FIELDS},
                         "unknown_reason": "AttemptWallExpired"}
                response = {"model": streamed_model,
                            "choices": [{"message": {
                                "content": "".join(content_parts),
                                "reasoning_content": "".join(reasoning_parts)}}],
                            "usage": None, "partial": True,
                            "limit_kind": "attempt_wall_expired"}
                response_artifact = self.store.artifact(canonical(response))
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
                error = type(e).__name__  # Never log headers or raw error bodies.
                usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                response, response_artifact = {}, None
            charge = Decimal(0)
            ended_at, duration = utc(), time.monotonic() - tick
            if fallback:
                first_token_seconds, last_token_at = duration, ended_at
                stream_tokens_received, stream_chunks = 0, 0
            # C1-a wire-vs-assembled accounting: the assembled size of
            # the history the harness built for this call, the wire
            # size the provider actually processed (its reported input
            # usage; None when usage is unknown), and the over-cap
            # flag against the frozen wire cap.
            assembled_tokens = context_stats.get(
                "assembled_tokens", estimate_tokens(messages))
            wire_tokens = usage.get("input_tokens")
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
                     "assembled_tokens": assembled_tokens,
                     "wire_tokens": wire_tokens,
                     "assembled_over_wire_cap": bool(
                         cfg.get("max_input_tokens") is not None
                         and assembled_tokens > cfg["max_input_tokens"]),
                     "sent_tokens": context_stats.get("sent_tokens"),
                     "observations_masked": context_stats.get("observations_masked"),
                     "authored_turns_externalized": context_stats.get(
                         "authored_turns_externalized"),
                     "unmaskable_remainder_over_cap": bool(
                         context_stats.get("unmaskable_remainder_over_cap")),
                     "limit_kind": ("attempt_wall_expired" if wall_expired
                                    else "call_outer_bound" if outer_bound else None),
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
            if outer_bound:
                self.store.append("transport_events", {
                    "kind": "call_outer_bound",
                    **self.identity, "phase": phase, "call_id": call_id,
                    "outer_bound_seconds": CALL_OUTER_BOUND_SECONDS,
                    "first_token_seconds": first_token_seconds,
                    "last_token_at": last_token_at,
                    "stream_tokens_received": stream_tokens_received,
                    "partial_stream_recorded": True,
                    "timestamp": utc()})
        finally:
            # Settle the zero reservation even when telemetry validation fails.
            self.budget.settle(call_id, charge)
        if stall:
            raise TransportStallError("TransportStallSuspected")
        if outer_bound:
            raise CallOuterBoundError("CallOuterBound")
        if wall_expired:
            raise AttemptWallExpiredError("AttemptWallExpired")
        if error:
            raise ProviderError(error)
        return text
