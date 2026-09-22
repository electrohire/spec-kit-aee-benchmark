"""Explicit retries with exponential backoff; explicit usage, no opaque SDK retries.

Authentication: the Secure Vault connector (custom.openai) via the authd
surrogate exchange when available (managed VM); otherwise OPENAI_API_KEY
from the environment (operator host). No raw credential is ever printed,
logged, or persisted to artifacts.

Rate limiting: HTTP 429 and transient 5xx (plus network-level URLError /
TimeoutError) are retried with exponential backoff and jitter; 429
additionally honors the Retry-After response header. Every HTTP attempt is
recorded in an `http_attempts` artifact; the single terminal "calls"
telemetry event carries retry=<retries performed>, so the attempt
token-ceiling check sees exactly one outcome per query(). Non-retryable 4xx
(auth, bad request), harness-side KeyError/ValueError, and model-snapshot
mismatches fail fast. Total backoff is bounded so a sustained outage
degrades to the existing fail-closed ProviderError path instead of hanging
the attempt.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

try:
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    import dynamic_credentials as dc
except ImportError:
    dc = None  # Secure Vault connector unavailable on this host; env fallback.

from .accounting import TOKEN_FIELDS, cost, native_usage, request_prices
from .store import canonical, utc
from .schema import validate_call, validate_identity


CREDENTIAL = "custom.openai"
ALLOWED_HOSTS = ["api.openai.com"]
MODELS_URL = "https://api.openai.com/v1/models"
CHAT_URL = "https://api.openai.com/v1/chat/completions"

_AUTH = None  # ("connector", None) or ("env", key); resolved once per process.


def _models_ok(mutate):
    req = urllib.request.Request(MODELS_URL, method="GET")
    mutate(req)
    with urllib.request.urlopen(req, timeout=30) as handle:
        data = json.loads(handle.read().decode())
    return isinstance(data.get("data"), list)


def resolve_auth():
    """Fail-closed credential resolution, verified by a free /models probe.

    Prefers the Secure Vault connector; falls back to OPENAI_API_KEY when the
    connector is unavailable (operator host). Raises ValueError when neither
    authenticates. The raw key is held in memory only and never logged.
    """
    global _AUTH
    if _AUTH is not None:
        return _AUTH
    if dc is not None:
        try:
            dc.ensure_allowed_url(MODELS_URL, ALLOWED_HOSTS)
            if _models_ok(lambda req: dc.add_surrogate_to_request(
                    req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)):
                _AUTH = ("connector", None)
                return _AUTH
        except Exception:
            pass
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        try:
            if _models_ok(lambda req: req.add_header("Authorization", "Bearer " + key)):
                _AUTH = ("env", key)
                return _AUTH
        except Exception:
            pass
    raise ValueError("no usable OpenAI credential: Secure Vault connector unavailable "
                     "and OPENAI_API_KEY unset or rejected by the API")


class ProviderError(RuntimeError):
    pass


# Retry policy for the OpenAI HTTP transport. Module-level constants so tests
# can shrink them; production behavior is the documented default.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_HTTP_ATTEMPTS = 6          # 1 initial attempt + 5 retries
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 120.0
MAX_TOTAL_BACKOFF_SECONDS = 300.0

_sleep = time.sleep  # Injectable seam for tests; production sleeps for real.


def _parse_retry_after(headers):
    """Seconds from a Retry-After response header, or None if absent/unparseable."""
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _backoff_wait(retry_index, retry_after=None):
    """Wait before retry number `retry_index` (0-based). A server-supplied
    Retry-After is honored exactly (capped); otherwise exponential backoff
    with jitter so concurrent clients do not re-collide."""
    if retry_after is not None:
        return min(retry_after, MAX_BACKOFF_SECONDS)
    return min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2 ** retry_index)) * (0.5 + random.random() / 2)


def _retryable(exc):
    """True when the exception merits another HTTP attempt. HTTPError is
    checked first because it subclasses URLError."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_STATUS
    return isinstance(exc, (urllib.error.URLError, TimeoutError))


def _next_wait(exc, retries, retry_after, waited):
    """Seconds to wait before the next attempt, or None if the error is terminal."""
    if not _retryable(exc):
        return None
    if retries >= MAX_HTTP_ATTEMPTS - 1:
        return None
    wait = _backoff_wait(retries, retry_after)
    if waited + wait > MAX_TOTAL_BACKOFF_SECONDS:
        return None
    return wait


class OpenAIProvider:
    def __init__(self, config, store, budget, identity):
        self.config, self.store, self.budget, self.identity = config, store, budget, identity

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
        call_id = uuid.uuid4().hex
        charge = None
        self.budget.reserve(call_id, self.identity["attempt_id"], reserve)
        try:
            started, tick = utc(), time.monotonic()
            payload = dict(model=cfg["model"], messages=messages, max_completion_tokens=cfg["max_output_tokens"],
                           reasoning_effort=cfg["reasoning_effort"], service_tier="default")
            if cfg.get("temperature") is not None:
                payload["temperature"] = cfg["temperature"]
            request_artifact = self.store.artifact(canonical(payload))
            response, request_id, error, response_artifact = {}, None, None, None
            attempts, retries, waited = [], 0, 0.0
            while True:
                attempt_no = len(attempts)
                try:
                    mode, key = resolve_auth()
                    if mode == "connector":
                        dc.ensure_allowed_url(CHAT_URL, ALLOWED_HOSTS)
                        req = urllib.request.Request(CHAT_URL, canonical(payload),
                                {"Content-Type": "application/json"})
                        dc.add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
                    else:
                        req = urllib.request.Request(CHAT_URL, canonical(payload),
                                {"Content-Type": "application/json",
                                 "Authorization": "Bearer " + key})
                    with urllib.request.urlopen(req, timeout=timeout) as handle:
                        request_id = handle.headers.get("x-request-id")
                        response = (dc.read_json_response(handle) if mode == "connector"
                                    else json.loads(handle.read().decode()))
                    response_artifact = self.store.artifact(canonical(response))
                    usage = native_usage(response)
                    attempts.append({"attempt": attempt_no, "http_status": 200})
                    break
                except urllib.error.HTTPError as e:
                    retry_after = _parse_retry_after(e.headers) if e.code == 429 else None
                    wait = _next_wait(e, retries, retry_after, waited)
                    attempts.append({"attempt": attempt_no, "http_status": e.code,
                                     "retry_after": retry_after, "wait_seconds": wait})
                    if wait is None:
                        error = type(e).__name__  # Avoid logging headers, keys or raw provider error bodies.
                        usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                        break
                    _sleep(wait)
                    waited, retries = waited + wait, retries + 1
                except (urllib.error.URLError, TimeoutError) as e:
                    wait = _next_wait(e, retries, None, waited)
                    attempts.append({"attempt": attempt_no, "error": type(e).__name__,
                                     "wait_seconds": wait})
                    if wait is None:
                        error = type(e).__name__
                        usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                        break
                    _sleep(wait)
                    waited, retries = waited + wait, retries + 1
                except (KeyError, ValueError) as e:
                    # Harness-side failures (response parsing, telemetry): fail fast, never retry.
                    attempts.append({"attempt": attempt_no, "error": type(e).__name__})
                    error = type(e).__name__
                    usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
                    break
            charge = cost(usage, request_prices(cfg, usage))
            attempts_artifact = self.store.artifact(canonical(attempts))
            event = {**self.identity, "call_id": call_id, "request_id": request_id,
                     "phase": phase, "provider": "openai", "model": cfg["model"],
                     "response_model": response.get("model"), "started_at": started, "ended_at": utc(),
                     "duration_seconds": time.monotonic()-tick, **usage,
                     "price_snapshot_id": cfg["price_snapshot_id"], "cost_basis": "list_price_estimate",
                     "currency": "USD", "cost": str(charge) if charge is not None else None,
                     "retry": retry + retries, "error": error,
                     "artifacts": {"request": request_artifact, "response": response_artifact,
                                   "http_attempts": attempts_artifact}}
            validate_call(event)
            self.store.append("calls", event)
        finally:
            # The reservation must never leak: settle even when post-request
            # telemetry validation rejects the event (the spend still happened).
            # settle(call_id, None) keeps the reservation open for unknown
            # requests, preserving the existing fail-closed behavior.
            self.budget.settle(call_id, charge)
        if error:
            raise ProviderError(error)
        if response.get("model") != cfg["model"]:
            raise ProviderError("provider returned a different model snapshot")
        return response["choices"][0]["message"].get("content") or ""
