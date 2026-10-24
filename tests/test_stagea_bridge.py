"""Stage A bridge (2026-10-22): freeze-configured coalescing of
consecutive same-role messages for strict chat templates.

Origin: Pair B's first smoke call died with a server-side Jinja
template error (HTTP 500) — the Mistral template serving Devstral
requires alternating roles after the system message, while the loop
legitimately sends [system, user, user] (instruction, then task).
That is an equipment failure, never a model behavior; the plan's
remedy is to fix the bridge for the pair and re-probe inside its
allocation. The fix is wire-only and flag-gated: absent
``coalesce_same_role_messages`` the payload is byte-identical to the
pre-change payload (pinned below), and the recorded conversation is
never mutated.
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_amendment1_transport import (  # noqa: E402
    CFG as LOCAL_CFG, IDENTITY as LOCAL_IDENTITY, MODEL, stub_server)

from benchmark_runner.accounting import Budget  # noqa: E402
from benchmark_runner.local_provider import (  # noqa: E402
    LocalProvider, _coalesce_same_role)
from benchmark_runner.store import Store  # noqa: E402


def _local_provider(tmp_path, monkeypatch, base_url, cfg_extra=None):
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    store = Store(tmp_path / "store")
    budget = Budget(store, Decimal("100"), Decimal("25"))
    cfg = {**LOCAL_CFG, **(cfg_extra or {})}
    return LocalProvider(cfg, store, budget, LOCAL_IDENTITY), store


DOUBLE_USER = [{"role": "system", "content": "sys"},
               {"role": "user", "content": "instruction"},
               {"role": "user", "content": "task"},
               {"role": "assistant", "content": "act"},
               {"role": "user", "content": "obs"},
               {"role": "user", "content": "nudge"}]


def test_coalesce_merges_consecutive_same_role_strings():
    out = _coalesce_same_role(DOUBLE_USER)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
    assert out[1]["content"] == "instruction\n\ntask"
    assert out[3]["content"] == "obs\n\nnudge"


def test_coalesce_is_identity_on_alternating_roles():
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "u2"}]
    assert _coalesce_same_role(msgs) == msgs


def test_coalesce_passes_non_string_content_through():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "x"}]},
            {"role": "user", "content": "y"}]
    assert _coalesce_same_role(msgs) == msgs


def test_coalesce_does_not_mutate_the_input():
    msgs = [dict(m) for m in DOUBLE_USER]
    _coalesce_same_role(msgs)
    assert msgs == DOUBLE_USER


def test_payload_without_flag_is_the_pre_change_payload(tmp_path, monkeypatch):
    with stub_server("sse") as (server, base_url):
        provider, _store = _local_provider(tmp_path, monkeypatch, base_url)
        provider.query([dict(m) for m in DOUBLE_USER], "solve", 30)
    assert server.last_payload["messages"] == DOUBLE_USER


def test_payload_with_flag_coalesces_on_the_wire_only(tmp_path, monkeypatch):
    messages = [dict(m) for m in DOUBLE_USER]
    with stub_server("sse") as (server, base_url):
        provider, _store = _local_provider(
            tmp_path, monkeypatch, base_url,
            {"coalesce_same_role_messages": True})
        provider.query(messages, "solve", 30)
    wire = server.last_payload["messages"]
    assert [m["role"] for m in wire] == ["system", "user", "assistant", "user"]
    assert wire[1]["content"] == "instruction\n\ntask"
    assert messages == DOUBLE_USER  # recorded conversation unchanged
