"""Explicit retries with exponential backoff; explicit usage, no opaque SDK retries.

Authentication: the Secure Vault connector (custom.openai) via the authd
surrogate exchange when available (managed VM, OpenAI only); otherwise the
provider's key env var (OPENAI_API_KEY / OPENROUTER_API_KEY) from the
environment (operator host). The provider -- base URL, allowed hosts, key env
var, telemetry name -- is driven by cfg["provider"]; OpenAI is the default
when cfg carries no provider section. No raw credential is ever printed,
logged, or persisted to artifacts.

Rate limiting: HTTP 429 and transient 5xx are retried with exponential
backoff and jitter; 429 additionally honors Retry-After (numeric seconds or
HTTP-date) and the verified OpenAI x-ratelimit-reset-requests /
x-ratelimit-reset-tokens headers (Go durations, e.g. "6m0s"; OpenAI only --
absent on other providers, harmless). Ambiguous transport failures (URLError)
and timeouts are NOT retried: without verified idempotency a retried request
may double-execute, so they fail closed.

Per-physical-request accounting: every physical HTTP request gets its own
call_id, its own terminal "calls" telemetry event, and its own budget
reservation and settlement. Physical retries never share a logical call_id.
Failed requests (429-exhausted, 5xx, transport, timeout) record unknown
usage with a real unknown_reason and cost None -- zero fabricated spend.

A process-wide pacer enforces a minimum inter-request gap across ALL
provider traffic (chat completions and /v1/models probes): backoff after
failure is not pacing, and sequential calls must not re-collide with the
rate limiter. All pacing/retry bounds come from the frozen campaign
transport policy (cfg["transport"]), validated before any spend; live runs
fail closed when the policy is missing or malformed.

Non-retryable 4xx (auth, bad request), harness-side KeyError/ValueError,
and model-snapshot mismatches fail fast. Total backoff is bounded so a
sustained outage degrades to the existing fail-closed ProviderError path
instead of hanging the attempt.
"""
import email.utils
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal

try:
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    import dynamic_credentials as dc
except ImportError:
    dc = None  # Secure Vault connector unavailable on this host; env fallback.

from .accounting import TOKEN_FIELDS, cost, native_usage, request_prices
from .store import canonical, utc
from .schema import validate_call, validate_identity


# ---------------------------------------------------------------------------
# Provider registry: OpenAI-compatible chat-completions endpoints.
# ---------------------------------------------------------------------------
# The paid frontier arm is provider-agnostic over OpenAI-compatible HTTP
# APIs. The campaign manifest pins its provider in cfg["provider"]; the name
# drives the base URL, allowed hosts, credential env var, and telemetry.
# OpenAI is the default when cfg carries no provider section, preserving
# every historical freeze byte-for-byte.
PROVIDER_DEFAULTS = {
    "openai": {
        "name": "openai",
        "base_url": "https://api.openai.com/v1",
        "allowed_hosts": ["api.openai.com"],
        "key_env": "OPENAI_API_KEY",
        # Secure Vault connector credential; OpenAI only. Other providers
        # authenticate exclusively via their key_env.
        "connector_credential": "custom.openai",
        "referer": None,
        "title": None,
    },
    "openrouter": {
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "allowed_hosts": ["openrouter.ai"],
        "key_env": "OPENROUTER_API_KEY",
        "connector_credential": None,
        # OpenRouter asks callers to identify the app on every request.
        "referer": "https://github.com/electrohire/spec-kit-aee-benchmark",
        "title": "spec-kit-aee-benchmark",
    },
}


def provider_spec(cfg):
    """Merged provider spec for this campaign.

    cfg["provider"] selects the provider by name and may override individual
    fields of that provider's defaults. Unknown provider names, unknown keys,
    and malformed values fail closed: a campaign can never run against a
    silently misconfigured endpoint.
    """
    raw = cfg.get("provider") or {}
    if not isinstance(raw, dict):
        raise ValueError("provider config must be a mapping")
    name = raw.get("name", "openai")
    defaults = PROVIDER_DEFAULTS.get(name)
    if defaults is None:
        raise ValueError("unknown provider %r: expected one of %s"
                         % (name, sorted(PROVIDER_DEFAULTS)))
    unknown = set(raw) - set(defaults)
    if unknown:
        raise ValueError("unknown provider config keys: %s" % sorted(unknown))
    spec = dict(defaults)
    spec.update(raw)
    if not isinstance(spec["base_url"], str) or not spec["base_url"].startswith("https://"):
        raise ValueError("provider base_url must be an https URL")
    hosts = spec["allowed_hosts"]
    if not isinstance(hosts, list) or not hosts \
            or not all(isinstance(h, str) and h for h in hosts):
        raise ValueError("provider allowed_hosts must be a non-empty list of hostnames")
    if not isinstance(spec["key_env"], str) or not spec["key_env"]:
        raise ValueError("provider key_env must be a non-empty environment variable name")
    for field in ("referer", "title"):
        if spec[field] is not None and not isinstance(spec[field], str):
            raise ValueError("provider %s must be a string or null" % field)
    return spec


def provider_name_from_env():
    """Provider selected by the operator environment (BENCH_PROVIDER).

    Used where no frozen manifest exists yet (preflight). Live runs always
    read the provider from the frozen manifest instead, so the environment
    can never switch endpoints mid-campaign.
    """
    name = os.environ.get("BENCH_PROVIDER", "openai")
    if name not in PROVIDER_DEFAULTS:
        raise ValueError("unknown BENCH_PROVIDER %r: expected one of %s"
                         % (name, sorted(PROVIDER_DEFAULTS)))
    return name


_AUTH = {}  # provider name -> ("connector", None) | ("env", key); resolved once per process.

_PROVIDER_DISPLAY = {"openai": "OpenAI", "openrouter": "OpenRouter"}


def reset_auth_cache():
    """Test seam: clear the per-provider auth cache."""
    _AUTH.clear()


def _models_probe(spec, mutate):
    """One paced GET {base_url}/models through the coordinated retry policy.

    This is a free auth probe: no store or budget exists yet, so it gets no
    per-request call_id or budget reservation. It still gets process-wide
    pacing and the same 429/5xx-only retry discipline (bounded waits),
    because an unpaced probe burst is exactly what the pacer exists to
    prevent. Ambiguous transport failures fail closed with no retry.
    """
    policy = transport_policy({})
    req = urllib.request.Request(spec["base_url"] + "/models", method="GET")
    mutate(req)
    waited, attempt = 0.0, 0
    while True:
        paced_wait(policy)
        try:
            with urllib.request.urlopen(req, timeout=30) as handle:
                return json.loads(handle.read().decode())
        except urllib.error.HTTPError as exc:
            wait = _next_wait(exc, attempt, _server_wait(exc), waited, policy)
            if wait is None:
                raise
            _sleep(wait)
            waited, attempt = waited + wait, attempt + 1
        except (urllib.error.URLError, TimeoutError):
            raise  # Fail closed: no retry on ambiguous transport failures.


def _models_ok(spec, mutate):
    data = _models_probe(spec, mutate)
    return isinstance(data.get("data"), list)


def resolve_auth(spec=None):
    """Fail-closed credential resolution, verified by a free /models probe.

    Prefers the Secure Vault connector when the provider defines one (OpenAI
    only); otherwise uses the provider's key_env. Raises ValueError when
    neither authenticates. The raw key is held in memory only and never logged.
    """
    spec = spec or provider_spec({})
    name = spec["name"]
    if name in _AUTH:
        return _AUTH[name]
    credential = spec["connector_credential"]
    if dc is not None and credential:
        try:
            models_url = spec["base_url"] + "/models"
            dc.ensure_allowed_url(models_url, spec["allowed_hosts"])
            if _models_ok(spec, lambda req: dc.add_surrogate_to_request(
                    req, credential, allowed_hosts=spec["allowed_hosts"])):
                _AUTH[name] = ("connector", None)
                return _AUTH[name]
        except Exception:
            pass
    key = os.environ.get(spec["key_env"])
    if key:
        try:
            if _models_ok(spec, lambda req: req.add_header("Authorization", "Bearer " + key)):
                _AUTH[name] = ("env", key)
                return _AUTH[name]
        except Exception:
            pass
    raise ValueError("no usable %s credential: Secure Vault connector unavailable "
                     "and %s unset or rejected by the API"
                     % (_PROVIDER_DISPLAY.get(name, name), spec["key_env"]))


class ProviderError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Transport policy: pacing + retry bounds as frozen campaign configuration.
# ---------------------------------------------------------------------------
# Documented defaults. Live campaigns must freeze explicit bounds:
# validate_live() fails closed when cfg["transport"] is missing or
# malformed. Offline tests and synthetic configs may rely on these defaults.
TRANSPORT_DEFAULTS = {
    "min_request_gap_seconds": 1.0,
    "max_http_attempts": 6,          # 1 initial attempt + 5 retries
    "base_backoff_seconds": 2.0,
    "max_backoff_seconds": 120.0,
    "max_total_backoff_seconds": 300.0,
}


def transport_policy(cfg):
    """Validated transport bounds for this campaign.

    cfg["transport"], when present, overrides TRANSPORT_DEFAULTS key by key.
    Every bound is validated (finite, in range); a malformed value raises
    ValueError so a campaign can never run on a silently misconfigured
    policy. Because the config is frozen into the campaign manifest
    (configs/experiment.yaml via freeze(), smoke_config() for Claim A) and
    verify_freeze() rejects tampering, these bounds are campaign-frozen, not
    ambient module constants.
    """
    raw = dict(TRANSPORT_DEFAULTS)
    override = cfg.get("transport") or {}
    if not isinstance(override, dict):
        raise ValueError("transport policy must be a mapping")
    unknown = set(override) - set(TRANSPORT_DEFAULTS)
    if unknown:
        raise ValueError("unknown transport policy keys: %s" % sorted(unknown))
    raw.update(override)
    for name in ("min_request_gap_seconds", "base_backoff_seconds",
                 "max_backoff_seconds", "max_total_backoff_seconds"):
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value) or value < 0:
            raise ValueError("transport.%s must be a finite number >= 0" % name)
    if raw["base_backoff_seconds"] == 0:
        raise ValueError("transport.base_backoff_seconds must be > 0 (no busy retry loops)")
    attempts = raw["max_http_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int) \
            or not 1 <= attempts <= 1000:
        raise ValueError("transport.max_http_attempts must be an integer in [1, 1000]")
    if raw["max_backoff_seconds"] < raw["base_backoff_seconds"]:
        raise ValueError("transport.max_backoff_seconds must be >= base_backoff_seconds")
    return raw


# Process-wide request pacer: one slot per process, shared by every physical
# provider request (chat completions on both backends, /v1/models probes).
_PACER_LOCK = threading.Lock()
_PACER_LAST_START = 0.0  # monotonic time the most recent request slot began


def reset_pacer():
    """Test seam: clear the process-wide pacing state."""
    global _PACER_LAST_START
    with _PACER_LOCK:
        _PACER_LAST_START = 0.0


def paced_wait(policy):
    """Enforce the process-wide minimum inter-request gap.

    Covers every physical provider request in this process. Backoff after
    failure is not pacing: this gap applies between successful requests too,
    so a burst of sequential calls can never re-collide with the rate
    limiter. Returns the seconds actually slept.
    """
    gap = policy["min_request_gap_seconds"]
    if gap <= 0:
        return 0.0
    with _PACER_LOCK:
        global _PACER_LAST_START
        now = time.monotonic()
        wait = max(0.0, gap - (now - _PACER_LAST_START))
        _PACER_LAST_START = now + wait
    if wait > 0:
        _sleep(wait)
    return wait


RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_sleep = time.sleep  # Injectable seam for tests; production sleeps for real.


def _parse_retry_after(headers):
    """Seconds from a Retry-After response header: numeric delta-seconds or an
    HTTP-date (RFC 7231 IMF-fixdate). None when absent or unparseable.

    urllib response headers are case-insensitive, so the lowercase lookup
    works on real responses; tests pass lowercase dict keys.
    """
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    raw = str(raw).strip()
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


_GO_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(h|ms|us|µs|ns|m|s)")
_GO_DURATION_FULL = re.compile(r"(?:\d+(?:\.\d+)?(?:h|ms|us|µs|ns|m|s))+")
_GO_DURATION_MULT = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 1e-3,
                     "us": 1e-6, "\u00b5s": 1e-6, "ns": 1e-9}


def _parse_go_duration(raw):
    """Go-style duration ("6m0s", "2s", "9ms") to seconds; None if malformed.

    OpenAI's x-ratelimit-reset-requests / x-ratelimit-reset-tokens headers use
    this format (confirmed against OpenAI-compatible rate-limit documentation).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not _GO_DURATION_FULL.fullmatch(text):
        return None
    return sum(float(n) * _GO_DURATION_MULT[u] for n, u in _GO_DURATION_RE.findall(text))


def _reset_wait_from_headers(headers):
    """Seconds until the OpenAI rate-limit window resets, from the verified
    x-ratelimit-reset-requests / x-ratelimit-reset-tokens headers. Only
    consulted on 429 responses. None when absent or unparseable."""
    if not headers:
        return None
    waits = []
    for name in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        value = _parse_go_duration(headers.get(name))
        if value is not None:
            waits.append(value)
    return max(waits) if waits else None


def _server_wait(exc):
    """Server-directed wait before a retry, or None. On a 429, Retry-After
    wins; the OpenAI reset headers are the fallback. Other statuses and
    non-HTTP errors get no server direction (exponential backoff applies)."""
    if not isinstance(exc, urllib.error.HTTPError) or exc.code != 429:
        return None
    headers = exc.headers
    after = _parse_retry_after(headers)
    if after is not None:
        return after
    return _reset_wait_from_headers(headers)


def _retryable(exc):
    """True only for confirmed safe/pre-execution rejections: HTTP 429 and
    transient 5xx. HTTPError subclasses URLError, so it is checked first.
    Ambiguous transport failures (URLError) and timeouts fail closed with no
    retry: without verified idempotency a retried request may double-execute."""
    return isinstance(exc, urllib.error.HTTPError) and exc.code in RETRYABLE_STATUS


def _next_wait(exc, attempt_index, server_wait, waited, policy):
    """Seconds to wait before the next physical attempt (`attempt_index`
    attempts already made, 0-based), or None when the error is terminal:
    non-retryable, attempts exhausted, or the total backoff budget spent."""
    if not _retryable(exc):
        return None
    if attempt_index >= policy["max_http_attempts"] - 1:
        return None
    if server_wait is not None:
        wait = min(server_wait, policy["max_backoff_seconds"])
    else:
        wait = min(policy["max_backoff_seconds"],
                   policy["base_backoff_seconds"] * (2 ** attempt_index)) * (0.5 + random.random() / 2)
    if waited + wait > policy["max_total_backoff_seconds"]:
        return None
    return wait


class OpenAIProvider:
    """OpenAI-compatible chat-completions provider.

    The endpoint, auth, and telemetry provider name come from cfg["provider"]
    (see provider_spec); OpenAI is the default when cfg carries no provider
    section. One class serves every OpenAI-compatible backend so
    retry/pacing/accounting behavior is identical across providers.
    """

    def __init__(self, config, store, budget, identity):
        self.config, self.store, self.budget, self.identity = config, store, budget, identity
        self.spec = provider_spec(config)
        self.policy = transport_policy(config)

    def _one_request(self, payload, timeout):
        """Exactly one physical HTTP POST: paced, never retried.

        Returns (response, None, request_id) on success or (None, exc,
        request_id) on failure. Harness-side parsing failures surface as exc
        and fail fast in the caller; KeyboardInterrupt is never swallowed.
        """
        spec = self.spec
        mode, key = resolve_auth(spec)
        chat_url = spec["base_url"] + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if mode == "connector":
            dc.ensure_allowed_url(chat_url, spec["allowed_hosts"])
            req = urllib.request.Request(chat_url, canonical(payload), headers)
            dc.add_surrogate_to_request(req, spec["connector_credential"],
                                        allowed_hosts=spec["allowed_hosts"])
        else:
            headers["Authorization"] = "Bearer " + key
            if spec["referer"]:
                headers["HTTP-Referer"] = spec["referer"]
            if spec["title"]:
                headers["X-Title"] = spec["title"]
            req = urllib.request.Request(chat_url, canonical(payload), headers)
        paced_wait(self.policy)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as handle:
                request_id = handle.headers.get("x-request-id")
                response = (dc.read_json_response(handle) if mode == "connector"
                            else json.loads(handle.read().decode()))
            return response, None, request_id
        except Exception as exc:  # HTTPError, URLError, TimeoutError, parse errors
            request_id = None
            headers = getattr(exc, "headers", None)
            if headers is not None:
                try:
                    request_id = headers.get("x-request-id")
                except Exception:
                    request_id = None
            return None, exc, request_id

    def query(self, messages, phase, timeout, retry=0):
        cfg = self.config
        # Fail fast before spending: every telemetry field known up front is
        # validated now, so a schema/arm mismatch raises before the HTTP
        # request instead of after it (when the spend is invisible).
        validate_identity({**self.identity, "phase": phase})
        # Reserve the model's FULL documented input ceiling, not transcript estimates.
        # No call is permitted until the operator has verified this model-specific bound.
        ceiling_prices = request_prices(cfg)
        reserve = (Decimal(cfg["max_input_tokens"])*Decimal(str(ceiling_prices["input"]))
                   + Decimal(cfg["max_output_tokens"])*Decimal(str(ceiling_prices["output"]))) / 1_000_000
        payload = dict(model=cfg["model"], messages=messages, max_completion_tokens=cfg["max_output_tokens"],
                       reasoning_effort=cfg["reasoning_effort"], service_tier="default")
        if cfg.get("temperature") is not None:
            payload["temperature"] = cfg["temperature"]
        request_artifact = self.store.artifact(canonical(payload))

        waited, attempt_index, terminal_error = 0.0, 0, None
        while True:
            # Every physical request gets its own call_id, its own terminal
            # "calls" telemetry event, and its own budget reservation and
            # settlement. Physical retries never share a logical call_id.
            call_id = uuid.uuid4().hex
            self.budget.reserve(call_id, self.identity["attempt_id"], reserve)
            started, tick = utc(), time.monotonic()
            charge = None
            try:
                response, exc, request_id = self._one_request(payload, timeout)
                if exc is None:
                    response_artifact = self.store.artifact(canonical(response))
                    usage = native_usage(response)
                    error = None
                else:
                    # Never fabricate usage or spend for a failed request:
                    # 429-exhausted, 5xx, transport failures, timeouts and
                    # harness errors all record unknown usage with a real
                    # reason and cost None.
                    response_artifact = None
                    error = type(exc).__name__  # Never log headers, keys, or raw provider error bodies.
                    usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                charge = cost(usage, request_prices(cfg, usage))
                event = {**self.identity, "call_id": call_id, "request_id": request_id,
                         "phase": phase, "provider": self.spec["name"], "model": cfg["model"],
                         "response_model": (response or {}).get("model"),
                         "started_at": started, "ended_at": utc(),
                         "duration_seconds": time.monotonic()-tick, **usage,
                         "price_snapshot_id": cfg["price_snapshot_id"], "cost_basis": "list_price_estimate",
                         "currency": "USD", "cost": str(charge) if charge is not None else None,
                         "retry": retry + attempt_index, "physical_attempt": attempt_index,
                         "error": error,
                         "artifacts": {"request": request_artifact, "response": response_artifact}}
                validate_call(event)
                self.store.append("calls", event)
            finally:
                # Each physical request settles its own reservation, even when
                # post-request telemetry validation rejects the event (the
                # spend still happened). settle(call_id, None) keeps the
                # reservation open for unknown requests, preserving the
                # existing fail-closed behavior.
                self.budget.settle(call_id, charge)
            if exc is None:
                break
            wait = _next_wait(exc, attempt_index, _server_wait(exc), waited, self.policy)
            if wait is None:
                terminal_error = error
                break
            _sleep(wait)
            waited, attempt_index = waited + wait, attempt_index + 1
        if terminal_error is not None:
            raise ProviderError(terminal_error)
        if response.get("model") != cfg["model"]:
            raise ProviderError("provider returned a different model snapshot")
        return response["choices"][0]["message"].get("content") or ""
