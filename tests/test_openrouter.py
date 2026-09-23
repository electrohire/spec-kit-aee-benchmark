"""OpenRouter provider support: URL construction, auth, headers, pricing, gates.

All credentials are synthetic; no real key is ever used.
"""
import json

import pytest

import benchmark_runner.provider as provider_mod
from benchmark_runner.accounting import Budget
from benchmark_runner.provider import (
    OpenAIProvider,
    provider_name_from_env,
    provider_spec,
    resolve_auth,
)
from benchmark_runner.store import Store


@pytest.fixture(autouse=True)
def _clean_provider_state(monkeypatch):
    provider_mod.reset_auth_cache()
    provider_mod.reset_pacer()
    # Never let a real key leak in from the ambient environment.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("BENCH_PROVIDER", raising=False)
    yield
    provider_mod.reset_auth_cache()
    provider_mod.reset_pacer()


def test_provider_spec_defaults_to_openai():
    spec = provider_spec({})
    assert spec["name"] == "openai"
    assert spec["base_url"] == "https://api.openai.com/v1"
    assert spec["allowed_hosts"] == ["api.openai.com"]
    assert spec["key_env"] == "OPENAI_API_KEY"
    assert spec["connector_credential"] == "custom.openai"
    assert spec["referer"] is None and spec["title"] is None


def test_provider_spec_openrouter():
    spec = provider_spec({"provider": {"name": "openrouter"}})
    assert spec["name"] == "openrouter"
    assert spec["base_url"] == "https://openrouter.ai/api/v1"
    assert spec["allowed_hosts"] == ["openrouter.ai"]
    assert spec["key_env"] == "OPENROUTER_API_KEY"
    assert spec["connector_credential"] is None  # Connector is OpenAI-only.
    assert spec["referer"] and spec["title"]


def test_provider_spec_allows_explicit_field_overrides():
    spec = provider_spec({"provider": {"name": "openrouter", "title": "custom-title"}})
    assert spec["title"] == "custom-title"
    assert spec["base_url"] == "https://openrouter.ai/api/v1"  # Defaults fill the rest.


def test_provider_spec_rejects_unknown_provider_and_malformed():
    with pytest.raises(ValueError, match="unknown provider"):
        provider_spec({"provider": {"name": "bogus"}})
    with pytest.raises(ValueError, match="unknown provider config keys"):
        provider_spec({"provider": {"name": "openrouter", "nope": 1}})
    with pytest.raises(ValueError, match="https"):
        provider_spec({"provider": {"name": "openrouter",
                                    "base_url": "http://evil.example/v1"}})
    with pytest.raises(ValueError, match="allowed_hosts"):
        provider_spec({"provider": {"name": "openrouter", "allowed_hosts": []}})
    with pytest.raises(ValueError, match="must be a mapping"):
        provider_spec({"provider": "openrouter"})


def test_provider_name_from_env(monkeypatch):
    assert provider_name_from_env() == "openai"
    monkeypatch.setenv("BENCH_PROVIDER", "openrouter")
    assert provider_name_from_env() == "openrouter"
    monkeypatch.setenv("BENCH_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="unknown BENCH_PROVIDER"):
        provider_name_from_env()


def _openrouter_provider(store, budget):
    return OpenAIProvider(
        dict(model="openai/gpt-6-astra", reasoning_effort="low",
             max_input_tokens=1000, max_output_tokens=100,
             prices=dict(input=10.0, cached_input=1.0, output=50.0),
             price_snapshot_id="openrouter-list-2026-09-22",
             provider={"name": "openrouter"},
             transport={"min_request_gap_seconds": 0}),
        store, budget,
        {"attempt_id": "test", "experiment_id": "synthetic", "run_id": "synthetic",
         "arm": "diagnose", "task_id": "synthetic", "repeat": 1})


def test_openrouter_query_hits_configured_url_with_referer_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.setattr(provider_mod, "resolve_auth", lambda *a: ("env", "sk-test-not-a-real-key"))
    seen = {}

    class Handle:
        headers = {"x-request-id": "synthetic-request"}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self):
            return json.dumps({"model": "openai/gpt-6-astra",
                               "choices": [{"message": {"content": "done"}}],
                               "usage": {"prompt_tokens": 100, "completion_tokens": 30}}).encode()

    def capture(req, *a, **k):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        return Handle()

    monkeypatch.setattr("urllib.request.urlopen", capture)
    store = Store(tmp_path)
    provider = _openrouter_provider(store, Budget(store, 100, 100))
    assert provider.query([], "solve", 10) == "done"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert headers["authorization"] == "Bearer sk-test-not-a-real-key"
    assert headers["http-referer"].startswith("https://")
    assert "x-title" in headers
    call = store.events("calls")[0]
    assert call["provider"] == "openrouter"
    assert call["model"] == "openai/gpt-6-astra"


def test_openrouter_auth_uses_configured_key_env_and_models_url(monkeypatch):
    monkeypatch.setattr(provider_mod, "dc", None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(provider_mod, "_sleep", lambda s: None)
    seen = {}

    class Handle:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self):
            return json.dumps({"data": [{"id": "openai/gpt-6-astra"}]}).encode()

    def capture(req, *a, **k):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return Handle()

    monkeypatch.setattr("urllib.request.urlopen", capture)
    spec = provider_spec({"provider": {"name": "openrouter"}})
    assert resolve_auth(spec) == ("env", "sk-test-not-a-real-key")
    assert seen["url"].endswith("/credits")  # credits check runs after models probe
    assert seen["auth"] == "Bearer sk-test-not-a-real-key"


def test_openrouter_never_uses_connector_surrogate(monkeypatch):
    calls = []

    class FakeDC:
        @staticmethod
        def ensure_allowed_url(url, hosts): calls.append(("allow", url, hosts))
        @staticmethod
        def add_surrogate_to_request(req, cred, allowed_hosts=None):
            calls.append(("surrogate", cred))
        @staticmethod
        def read_json_response(handle): return json.loads(handle.read())

    monkeypatch.setattr(provider_mod, "dc", FakeDC())
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(provider_mod, "_sleep", lambda s: None)

    class Handle:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps({"data": []}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Handle())
    spec = provider_spec({"provider": {"name": "openrouter"}})
    assert resolve_auth(spec) == ("env", "sk-test-not-a-real-key")
    assert calls == []  # No surrogate exchange attempted for OpenRouter.


def test_openrouter_auth_fails_closed_without_key(monkeypatch):
    monkeypatch.setattr(provider_mod, "dc", None)
    spec = provider_spec({"provider": {"name": "openrouter"}})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        resolve_auth(spec)


def test_openrouter_price_snapshot_matches_openai_list():
    from benchmark_runner.matched_repair import (
        OPENROUTER_LONG_CONTEXT_PRICES,
        OPENROUTER_PRICE_SNAPSHOT_ID,
        OPENROUTER_PRICE_SOURCE,
        OPENROUTER_PRICES,
        smoke_config,
    )
    assert OPENROUTER_PRICE_SNAPSHOT_ID == "openrouter-list-2026-09-22"
    assert "2026-09-22" in OPENROUTER_PRICE_SOURCE
    assert "openrouter.ai" in OPENROUTER_PRICE_SOURCE
    assert OPENROUTER_PRICES == {"input": 10.0, "cached_input": 1.0, "output": 50.0}
    assert OPENROUTER_LONG_CONTEXT_PRICES == {"input": 20.0, "cached_input": 2.0, "output": 75.0}
    # The provider switch must not move any dollar amount: identical tiers.
    base = smoke_config()
    assert base["price_snapshot_id"] == "openai-list-2026-09-20"
    assert OPENROUTER_PRICES == base["prices"]
    assert OPENROUTER_LONG_CONTEXT_PRICES == base["long_context_prices"]


def test_reservation_gate_accepts_openrouter_model_id():
    from benchmark_runner.matched_repair import (
        OPENROUTER_LONG_CONTEXT_PRICES,
        OPENROUTER_PRICE_SNAPSHOT_ID,
        OPENROUTER_PRICE_SOURCE,
        OPENROUTER_PRICES,
        smoke_config,
        verify_reservation_bounds,
    )
    cfg = smoke_config()
    cfg.update({
        "model": "openai/gpt-6-astra",
        "provider": {"name": "openrouter"},
        "price_snapshot_id": OPENROUTER_PRICE_SNAPSHOT_ID,
        "price_source": OPENROUTER_PRICE_SOURCE,
        "prices": dict(OPENROUTER_PRICES),
        "long_context_prices": dict(OPENROUTER_LONG_CONTEXT_PRICES),
    })
    worst = verify_reservation_bounds(cfg)
    assert set(worst) == {"per_call_usd", "diagnostic_attempt_usd", "repair_attempt_usd"}
    # An unrelated model still fails closed.
    cfg["model"] = "other-model"
    with pytest.raises(ValueError, match="GPT-6 Astra"):
        verify_reservation_bounds(cfg)


def test_calibration_config_selects_openrouter_from_env(monkeypatch):
    from benchmark_runner.claim_a import calibration_config
    cfg = calibration_config()
    assert cfg["model"] == "gpt-6-astra"
    assert "provider" not in cfg
    assert cfg["price_snapshot_id"] == "openai-list-2026-09-20"
    monkeypatch.setenv("BENCH_PROVIDER", "openrouter")
    cfg = calibration_config()
    assert cfg["model"] == "openai/gpt-6-astra"
    assert cfg["provider"] == {"name": "openrouter"}
    assert cfg["price_snapshot_id"] == "openrouter-list-2026-09-22"
    assert cfg["prices"] == {"input": 10.0, "cached_input": 1.0, "output": 50.0}
    assert cfg["price_source"].startswith("https://openrouter.ai")
    monkeypatch.setenv("BENCH_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="unknown BENCH_PROVIDER"):
        calibration_config()
