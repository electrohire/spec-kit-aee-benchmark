"""Local inference backend: an OpenAI-compatible server (llama.cpp) on the operator host.

Selected when the frozen manifest config sets ``provider_backend: "local"``.
Model identity comes from the environment, not the manifest::

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
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

from .accounting import TOKEN_FIELDS, native_usage
from .store import canonical, utc
from .schema import validate_call, validate_identity
from .provider import ProviderError


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


def check_local_server():
    """Fail-closed server probe: reachable, and serving the expected model.

    Raises ValueError with an actionable message when the server is down or
    reports a different model. Called once per process before any query and
    from validate_live() before a campaign starts.
    """
    url = base_url() + "/models"
    expected = model_name()
    try:
        req = urllib.request.Request(url, headers=_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as handle:
            data = json.loads(handle.read().decode())
    except Exception as e:
        raise ValueError(
            f"local model server unreachable at {url}: {type(e).__name__}. "
            f"Start it with scripts/local-model-setup.sh (or your llama-server command) "
            f"and set LOCAL_MODEL_BASE_URL if it is not on localhost:8080") from e
    reported = None
    for entry in data.get("data") or []:
        reported = entry.get("id")
        break
    if reported != expected:
        raise ValueError(
            f"local server reports model {reported!r} but LOCAL_MODEL_NAME={expected!r}; "
            f"refusing to run against the wrong checkpoint")
    return reported


class LocalProvider:
    def __init__(self, config, store, budget, identity):
        self.config, self.store, self.budget, self.identity = config, store, budget, identity
        check_local_server()  # Fail before any reservation, never mid-campaign.

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
        try:
            started, tick = utc(), time.monotonic()
            payload = dict(model=model_name(), messages=messages,
                           max_completion_tokens=cfg["max_output_tokens"])
            if cfg.get("temperature") is not None:
                payload["temperature"] = cfg["temperature"]
            request_artifact = self.store.artifact(canonical(payload))
            response, request_id, error, response_artifact = {}, None, None, None
            try:
                req = urllib.request.Request(base_url() + "/chat/completions",
                                             canonical(payload), _headers())
                with urllib.request.urlopen(req, timeout=timeout) as handle:
                    request_id = handle.headers.get("x-request-id")
                    response = json.loads(handle.read().decode())
                response_artifact = self.store.artifact(canonical(response))
                usage = native_usage(response)
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
                error = type(e).__name__  # Never log headers or raw error bodies.
                usage = {**{k: None for k in TOKEN_FIELDS}, "unknown_reason": error}
            charge = Decimal(0)
            event = {**self.identity, "call_id": call_id, "request_id": request_id,
                     "phase": phase, "provider": "local", "model": model_name(),
                     "response_model": response.get("model"), "started_at": started, "ended_at": utc(),
                     "duration_seconds": time.monotonic()-tick, **usage,
                     "price_snapshot_id": "local-inference", "cost_basis": "local_inference",
                     "currency": "USD", "cost": str(charge),
                     "retry": retry, "error": error,
                     "artifacts": {"request": request_artifact, "response": response_artifact}}
            validate_call(event)
            self.store.append("calls", event)
        finally:
            # Settle the zero reservation even when telemetry validation fails.
            self.budget.settle(call_id, charge)
        if error:
            raise ProviderError(error)
        return response["choices"][0]["message"].get("content") or ""
