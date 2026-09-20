"""One HTTP request per call; explicit usage, no opaque SDK retries.

Authentication: the Secure Vault connector (custom.openai) via the authd
surrogate exchange when available (managed VM); otherwise OPENAI_API_KEY
from the environment (operator host). No raw credential is ever printed,
logged, or persisted to artifacts.
"""
import json
import os
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
from .schema import validate_call


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


class OpenAIProvider:
    def __init__(self, config, store, budget, identity):
        self.config, self.store, self.budget, self.identity = config, store, budget, identity

    def query(self, messages, phase, timeout, retry=0):
        cfg = self.config
        # Reserve the model's FULL documented input ceiling, not transcript estimates.
        # No call is permitted until the operator has verified this model-specific bound.
        ceiling_prices = request_prices(cfg)
        reserve = (Decimal(cfg["max_input_tokens"])*Decimal(str(ceiling_prices["input"]))
                   + Decimal(cfg["max_output_tokens"])*Decimal(str(ceiling_prices["output"]))) / 1_000_000
        call_id = uuid.uuid4().hex
        self.budget.reserve(call_id, self.identity["attempt_id"], reserve)
        started, tick = utc(), time.monotonic()
        payload = dict(model=cfg["model"], messages=messages, max_completion_tokens=cfg["max_output_tokens"],
                       reasoning_effort=cfg["reasoning_effort"], service_tier="default")
        if cfg.get("temperature") is not None:
            payload["temperature"] = cfg["temperature"]
        request_artifact = self.store.artifact(canonical(payload))
        response, request_id, error, response_artifact = {}, None, None, None
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
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
            error = type(e).__name__  # Avoid logging headers, keys or raw provider error bodies.
            usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
        charge = cost(usage, request_prices(cfg, usage))
        event = {**self.identity, "call_id": call_id, "request_id": request_id,
                 "phase": phase, "provider": "openai", "model": cfg["model"],
                 "response_model": response.get("model"), "started_at": started, "ended_at": utc(),
                 "duration_seconds": time.monotonic()-tick, **usage,
                 "price_snapshot_id": cfg["price_snapshot_id"], "cost_basis": "list_price_estimate",
                 "currency": "USD", "cost": str(charge) if charge is not None else None,
                 "retry": retry, "error": error,
                 "artifacts": {"request": request_artifact, "response": response_artifact}}
        validate_call(event)
        self.store.append("calls", event)
        self.budget.settle(call_id, charge)
        if error:
            raise ProviderError(error)
        if response.get("model") != cfg["model"]:
            raise ProviderError("provider returned a different model snapshot")
        return response["choices"][0]["message"].get("content") or ""
