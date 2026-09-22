import email.utils
import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest
from jsonschema import ValidationError

from benchmark_runner.accounting import Budget
from benchmark_runner.provider import OpenAIProvider, ProviderError
from benchmark_runner.store import Store


def _mock_transport(monkeypatch, response):
    # Mock the surrogate helper (no real credential exchange in tests).
    class FakeDC:
        @staticmethod
        def ensure_allowed_url(url, hosts): pass
        @staticmethod
        def add_surrogate_to_request(req, cred, allowed_hosts=None): pass
        @staticmethod
        def read_json_response(handle): return json.loads(handle.read())
    monkeypatch.setattr("benchmark_runner.provider.dc", FakeDC())
    # Auth resolution is a separate unit; pin it so the transport test
    # exercises query() without a live /models probe.
    monkeypatch.setattr("benchmark_runner.provider.resolve_auth", lambda: ("connector", None))
    class Handle:
        headers = {"x-request-id": "synthetic-request"}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps(response).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Handle())


def _provider(store, budget, arm="baseline", transport=None):
    # Tests freeze the transport policy explicitly: the process-wide pacer is
    # disabled (0s gap) by default so retry assertions are not polluted by
    # pacing sleeps; pacing has its own dedicated test.
    transport = transport if transport is not None else {"min_request_gap_seconds": 0}
    return OpenAIProvider(dict(model="synthetic-model", reasoning_effort="low", max_input_tokens=1000,
          max_output_tokens=100, prices=dict(input=2, cached_input=1, output=4), price_snapshot_id="synthetic",
          transport=transport),
          store, budget, {"attempt_id": "test", "experiment_id": "synthetic", "run_id": "synthetic",
                          "arm": arm, "task_id": "synthetic", "repeat": 1})


_SYNTHETIC_RESPONSE = {"model": "synthetic-model", "choices": [{"message": {"content": "done"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30,
                      "prompt_tokens_details": {"cached_tokens": 20},
                      "completion_tokens_details": {"reasoning_tokens": 10}}}


def test_real_transport_adapter_with_mock_response(tmp_path, monkeypatch):
    _mock_transport(monkeypatch, _SYNTHETIC_RESPONSE)
    store = Store(tmp_path)
    budget = Budget(store, 1, 1)
    provider = _provider(store, budget)
    assert provider.query([], "solve", 10) == "done"
    call = store.events("calls")[0]
    from benchmark_runner.schema import validate_call
    validate_call(call)
    with pytest.raises(ValidationError):
        validate_call({k: v for k, v in call.items() if k != "phase"})
    assert call["cost"] == "0.0003" and call["request_id"] == "synthetic-request"
    assert call["reasoning_tokens"] == 10
    # No credential material should appear in stored artifacts.
    assert "hsurr" not in "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())


def _http_error(code, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://api.openai.com/v1/chat/completions",
                                  code, "synthetic", headers, None)


def _mock_flaky(monkeypatch, behaviors):
    """Mock transport where each urlopen call consumes one behavior: an
    exception to raise, or None for a successful synthetic response."""
    class FakeDC:
        @staticmethod
        def ensure_allowed_url(url, hosts): pass
        @staticmethod
        def add_surrogate_to_request(req, cred, allowed_hosts=None): pass
        @staticmethod
        def read_json_response(handle): return json.loads(handle.read())
    monkeypatch.setattr("benchmark_runner.provider.dc", FakeDC())
    monkeypatch.setattr("benchmark_runner.provider.resolve_auth", lambda: ("connector", None))
    class Handle:
        headers = {"x-request-id": "synthetic-request"}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps(_SYNTHETIC_RESPONSE).encode()
    state = {"n": 0}
    def flaky(*a, **k):
        behavior = behaviors[min(state["n"], len(behaviors) - 1)]
        state["n"] += 1
        if isinstance(behavior, BaseException):
            raise behavior
        return Handle()
    monkeypatch.setattr("urllib.request.urlopen", flaky)
    sleeps = []
    monkeypatch.setattr("benchmark_runner.provider._sleep", sleeps.append)
    return sleeps


def test_429_retries_with_backoff_then_succeeds(tmp_path, monkeypatch):
    sleeps = _mock_flaky(monkeypatch, [_http_error(429), None])
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget)
    assert provider.query([], "solve", 10) == "done"
    # One backoff sleep, jittered exponential: 0.5x-1.0x of the 2s base.
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 2.0
    calls = store.events("calls")
    # One terminal event per physical request; the attempt's token accounting
    # charges the failed request's reservation and the successful one's usage.
    assert len(calls) == 2
    assert len({c["call_id"] for c in calls}) == 2  # Physical retries never share a call_id.
    failed, succeeded = calls
    assert failed["error"] == "HTTPError" and failed["cost"] is None
    assert failed["input_tokens"] is None and failed["unknown_reason"] == "HTTPError"
    assert succeeded["retry"] == 1 and succeeded["error"] is None and succeeded["cost"] == "0.0003"
    # Each physical request settles its own reservation.
    assert budget.charges()[failed["call_id"]]["status"] == "reserved"
    assert budget.charges()[succeeded["call_id"]]["status"] == "settled"


def test_429_honors_retry_after_header(tmp_path, monkeypatch):
    sleeps = _mock_flaky(monkeypatch, [_http_error(429, retry_after=7), None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    assert sleeps == [7.0]  # Server-supplied delay honored exactly, not jittered.


def test_429_honors_http_date_retry_after(tmp_path, monkeypatch):
    # HTTP-date Retry-After: a date 30s in the future is honored as ~30s.
    future = email.utils.format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    err = urllib.error.HTTPError("https://api.openai.com/v1/chat/completions",
                                 429, "synthetic", {"Retry-After": future}, None)
    sleeps = _mock_flaky(monkeypatch, [err, None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 30.0


def test_429_honors_openai_reset_headers(tmp_path, monkeypatch):
    # OpenAI x-ratelimit-reset-requests: Go duration "2s" -> 2s wait.
    err = urllib.error.HTTPError("https://api.openai.com/v1/chat/completions",
                                 429, "synthetic",
                                 {"x-ratelimit-reset-requests": "2s"}, None)
    sleeps = _mock_flaky(monkeypatch, [err, None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    assert sleeps == [2.0]


def test_429_malformed_headers_fall_back_to_backoff(tmp_path, monkeypatch):
    # A bogus Retry-After and a non-duration reset header must not corrupt
    # the wait: fall back to jittered backoff.
    err = urllib.error.HTTPError("https://api.openai.com/v1/chat/completions",
                                 429, "synthetic",
                                 {"Retry-After": "not-a-number",
                                  "x-ratelimit-reset-requests": "soonish"}, None)
    sleeps = _mock_flaky(monkeypatch, [err, None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 2.0


def test_429_exhausts_retries_then_fails_closed(tmp_path, monkeypatch):
    transport = {"min_request_gap_seconds": 0, "max_http_attempts": 3}
    sleeps = _mock_flaky(monkeypatch, [_http_error(429)])
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget, transport=transport)
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10)
    assert len(sleeps) == 2  # 3 attempts, 2 backoffs between them.
    calls = store.events("calls")
    assert len(calls) == 3  # Every physical request gets a terminal event.
    assert len({c["call_id"] for c in calls}) == 3
    for i, call in enumerate(calls):
        assert call["error"] == "HTTPError" and call["retry"] == i
        assert call["cost"] is None  # Never fabricate spend for a failed request.
        assert call["input_tokens"] is None and call["unknown_reason"] == "HTTPError"
        # Unknown usage keeps each physical request's reservation open
        # (existing fail-closed behavior, per physical call now).
        assert budget.charges()[call["call_id"]]["status"] == "reserved"


def test_retry_exhaustion_honors_total_backoff_budget(tmp_path, monkeypatch):
    # The total-wait bound is a hard stop even when attempts remain.
    transport = {"min_request_gap_seconds": 0, "max_http_attempts": 100,
                 "max_total_backoff_seconds": 3.0}
    sleeps = _mock_flaky(monkeypatch, [_http_error(429, retry_after=60)])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100), transport=transport)
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10)
    assert len(store.events("calls")) == 1  # Stopped after one attempt: 60s > 3s budget.
    assert sleeps == []


def test_non_retryable_400_fails_fast_without_sleep(tmp_path, monkeypatch):
    sleeps = _mock_flaky(monkeypatch, [_http_error(400)])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10)
    assert sleeps == []
    calls = store.events("calls")
    assert len(calls) == 1  # One physical request, one terminal event, no retry.
    assert calls[0]["error"] == "HTTPError" and calls[0]["retry"] == 0
    assert calls[0]["cost"] is None and calls[0]["unknown_reason"] == "HTTPError"


def test_transient_5xx_is_retried_but_timeout_fails_fast(tmp_path, monkeypatch):
    # 503 is retryable; an ambiguous timeout is NOT retried (the request may
    # have executed server-side). Two physical events, one backoff.
    transport = {"min_request_gap_seconds": 0, "max_http_attempts": 4}
    sleeps = _mock_flaky(monkeypatch, [_http_error(503), TimeoutError(), None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100), transport=transport)
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10)
    assert len(sleeps) == 1
    calls = store.events("calls")
    assert len(calls) == 2
    assert calls[0]["error"] == "HTTPError" and calls[0]["unknown_reason"] == "HTTPError"
    assert calls[1]["error"] == "TimeoutError" and calls[1]["unknown_reason"] == "TimeoutError"
    assert all(c["cost"] is None for c in calls)  # No fabricated spend, no success.


def test_urlerror_is_not_retried(tmp_path, monkeypatch):
    # An ambiguous transport failure is never retried, whatever the attempt budget.
    transport = {"min_request_gap_seconds": 0, "max_http_attempts": 4}
    sleeps = _mock_flaky(monkeypatch, [urllib.error.URLError("synthetic"), None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100), transport=transport)
    with pytest.raises(ProviderError):
        provider.query([], "solve", 10)
    assert sleeps == []
    calls = store.events("calls")
    assert len(calls) == 1
    assert calls[0]["error"] == "URLError" and calls[0]["unknown_reason"] == "URLError"


def test_process_wide_pacing_separates_physical_requests(tmp_path, monkeypatch):
    # Two physical requests (initial + one retry) issued 0.05s apart must be
    # spaced by the process-wide minimum gap: the second request is delayed.
    import benchmark_runner.provider as provider_mod
    transport = {"min_request_gap_seconds": 0.05, "max_http_attempts": 6}
    provider_mod.reset_pacer()
    sleeps = _mock_flaky(monkeypatch, [_http_error(429), None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100), transport=transport)
    assert provider.query([], "solve", 10) == "done"
    # One backoff sleep for the 429 plus one pacing sleep before the retry.
    assert len(sleeps) == 2
    pacing_sleeps = [s for s in sleeps if s <= 0.05]
    assert len(pacing_sleeps) == 1 and pacing_sleeps[0] > 0
    provider_mod.reset_pacer()


def test_models_probe_applies_pacing_and_retry(tmp_path, monkeypatch):
    # /v1/models goes through the same paced, retried path: a first 429 then a
    # success must resolve auth instead of failing closed.
    import benchmark_runner.provider as provider_mod
    provider_mod._AUTH = None
    provider_mod.reset_pacer()
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    sleeps = []
    monkeypatch.setattr(provider_mod, "_sleep", sleeps.append)
    state = {"n": 0}
    class Handle:
        headers = {}
        def __init__(self, payload): self._payload = payload
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps(self._payload).encode()
    def flaky(*a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise _http_error(429, retry_after=0)
        return Handle({"data": [{"id": "gpt-6-astra"}]})
    monkeypatch.setattr("urllib.request.urlopen", flaky)
    assert provider_mod.resolve_auth() == ("env", "sk-test-not-a-real-key")
    assert state["n"] == 2  # Retried through the 429.
    provider_mod._AUTH = None
    provider_mod.reset_pacer()


def test_query_validates_identity_before_spending(tmp_path, monkeypatch):
    # Fail-fast: an identity that cannot pass telemetry validation must raise
    # before any HTTP request (no spend) and before any budget reservation.
    def boom(*a, **k): raise AssertionError("HTTP request must not happen")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget, arm="not_an_arm")
    with pytest.raises(ValidationError):
        provider.query([], "solve", 10)
    assert store.events("calls") == []
    assert budget.charges() == {}


def test_query_settles_budget_when_post_request_validation_fails(tmp_path, monkeypatch):
    # If post-request telemetry validation rejects the event, the reservation
    # must still settle (no leaked reservation) and the error must propagate;
    # the invalid event itself is not logged.
    _mock_transport(monkeypatch, _SYNTHETIC_RESPONSE)
    def reject(event): raise ValidationError("synthetic telemetry rejection")
    monkeypatch.setattr("benchmark_runner.provider.validate_call", reject)
    store = Store(tmp_path)
    budget = Budget(store, 100, 100)
    provider = _provider(store, budget)
    with pytest.raises(ValidationError):
        provider.query([], "solve", 10)
    assert store.events("calls") == []
    charges = budget.charges()
    assert len(charges) == 1
    charge = next(iter(charges.values()))
    assert charge["status"] == "settled" and charge["amount"] == "0.0003"
def test_validate_call_accepts_matched_repair_arms():
    # Regression: the matched-repair cloud port logs calls with its own arm
    # vocabulary; the shared CALL_SCHEMA enum must accept them, otherwise paid
    # calls fail telemetry validation after the HTTP request (spend invisible).
    from benchmark_runner.schema import validate_call
    from benchmark_runner.matched_repair import MATCHED_ARMS
    base = {
        "experiment_id": "e", "run_id": "r", "task_id": "t", "repeat": 1,
        "attempt_id": "a", "phase": "p", "call_id": "c", "request_id": None,
        "provider": "openai", "model": "m", "response_model": "m",
        "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:00:01+00:00",
        "duration_seconds": 1.0, "input_tokens": 10, "cached_input_tokens": 0,
        "output_tokens": 5, "reasoning_tokens": 0, "unknown_reason": None,
        "price_snapshot_id": "s", "cost_basis": "list_price_estimate",
        "currency": "USD", "cost": "0.0001", "retry": 0, "error": None,
        "artifacts": {},
    }
    assert set(MATCHED_ARMS) == {"diagnose", "repair_ordinary", "repair_guided", "repair_workflow"}
    for arm in MATCHED_ARMS:
        validate_call({**base, "arm": arm})


# ---------------------------------------------------------------------------
# transport_policy: frozen, validated pacing/retry configuration.


def _policy(**over):
    from benchmark_runner.provider import transport_policy
    base = {
        "min_request_gap_seconds": 1.0,
        "max_http_attempts": 6,
        "base_backoff_seconds": 2.0,
        "max_backoff_seconds": 120.0,
        "max_total_backoff_seconds": 300.0,
    }
    base.update(over)
    return transport_policy({"transport": base})


def test_transport_policy_defaults():
    from benchmark_runner.provider import transport_policy, TRANSPORT_DEFAULTS
    assert transport_policy({}) == TRANSPORT_DEFAULTS
    assert TRANSPORT_DEFAULTS["min_request_gap_seconds"] >= 1.0
    assert TRANSPORT_DEFAULTS["max_http_attempts"] >= 2


def test_transport_policy_accepts_explicit_bounds():
    p = _policy(min_request_gap_seconds=0.5, max_http_attempts=3)
    assert p["min_request_gap_seconds"] == 0.5 and p["max_http_attempts"] == 3


def test_transport_policy_rejects_malformed_bounds():
    from benchmark_runner.provider import transport_policy
    bad = [
        {"min_request_gap_seconds": -1},
        {"min_request_gap_seconds": "fast"},
        {"max_http_attempts": 0},
        {"max_http_attempts": 1.5},
        {"max_http_attempts": 10**7},
        {"base_backoff_seconds": 0},
        {"max_backoff_seconds": 1, "base_backoff_seconds": 2},  # max < base
        {"max_total_backoff_seconds": -5},
        {"unknown_key": 1},  # Fail closed on unrecognized knobs, never silently ignore.
    ]
    for over in bad:
        cfg = {"transport": {**{"min_request_gap_seconds": 1.0, "max_http_attempts": 6,
                                "base_backoff_seconds": 2.0, "max_backoff_seconds": 120.0,
                                "max_total_backoff_seconds": 300.0}, **over}}
        with pytest.raises(ValueError):
            transport_policy(cfg)


def test_transport_policy_live_manifest_must_freeze_transport(tmp_path):
    # A live campaign cannot run on implicit transport defaults.
    from benchmark_runner.runner import validate_live
    from benchmark_runner.matched_repair import smoke_config
    cfg = smoke_config()
    manifest = {"config": {k: v for k, v in cfg.items() if k != "transport"},
                "freeze_id": "x" * 16, "tasks": [], "schedule": [], "diagnostic": {}}
    with pytest.raises(ValueError, match="frozen transport policy"):
        validate_live(manifest)
    manifest["config"]["transport"] = cfg["transport"]
    # Still fails on the other missing live fields, not on transport.
    with pytest.raises(ValueError):
        validate_live(manifest)


def test_reset_openai_headers_rejects_malformed():
    from benchmark_runner.provider import _reset_wait_from_headers
    assert _reset_wait_from_headers({"x-ratelimit-reset-requests": "6m0s"}) == 360.0
    assert _reset_wait_from_headers({"x-ratelimit-reset-tokens": "2s"}) == 2.0
    assert _reset_wait_from_headers({"x-ratelimit-reset-requests": "9ms"}) == pytest.approx(0.009)  # Sub-second honored as-is.
    assert _reset_wait_from_headers({"x-ratelimit-reset-requests": "soonish"}) is None
    assert _reset_wait_from_headers({}) is None


def test_secret_leakage_scan_of_telemetry_and_artifacts(tmp_path, monkeypatch):
    # Neither the calls stream nor any stored artifact may contain credential
    # material: Authorization headers, bearer tokens, or surrogate markers.
    # The failed-request events (unknown usage) must also be clean.
    _mock_flaky(monkeypatch, [_http_error(429), None])
    store = Store(tmp_path)
    provider = _provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    blob = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    for marker in ("hsurr", "Bearer", "sk-test", "Authorization"):
        assert marker not in blob
    for call in store.events("calls"):
        text = json.dumps(call)
        for marker in ("hsurr", "Bearer", "sk-test", "Authorization"):
            assert marker not in text
