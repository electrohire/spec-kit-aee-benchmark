"""One HTTP request per call; explicit usage, no opaque SDK retries.

Authentication uses the Secure Vault connector (custom.openai) via the
authd surrogate exchange. No raw credential is ever read from the
environment, printed, logged, or persisted.
"""
import sys
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import dynamic_credentials as dc

from .accounting import TOKEN_FIELDS, cost, native_usage, request_prices
from .store import canonical, utc
from .schema import validate_call


CREDENTIAL = "custom.openai"
ALLOWED_HOSTS = ["api.openai.com"]
CHAT_URL = "https://api.openai.com/v1/chat/completions"


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
            dc.ensure_allowed_url(CHAT_URL, ALLOWED_HOSTS)
            req = urllib.request.Request(CHAT_URL, canonical(payload),
                    {"Content-Type": "application/json"})
            dc.add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
            with urllib.request.urlopen(req, timeout=timeout) as handle:
                request_id = handle.headers.get("x-request-id")
                response = dc.read_json_response(handle)
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
