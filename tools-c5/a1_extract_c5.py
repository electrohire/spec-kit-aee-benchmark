#!/usr/bin/env python3
"""Cycle 5 Phase 1 (C5-A1): extract every recorded response from the
campaign-c4 store, classify with the frozen Cycle 4 code's own parse
functions (native strict JSON / bridged markup / still-dead — the
stats_c4 method), and dump the still-dead adapter-visible texts in
full, with response metadata (finish_reason, usage) for the manual
classification pass."""
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path.home() / "needle-campaign"
REPO = BASE / "code" / "benchmark-c3r1"
STORE = BASE / "runs" / "campaign-c4"
sys.path.insert(0, str(REPO / "src"))

from benchmark_runner.local_provider import _extract_text  # noqa: E402
from benchmark_runner.runner import parse_model_action, parse_native_tool_call  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402


def strict_live(text):
    try:
        action = json.loads(text)
        if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
            return None
        if action["action"] == "shell" and not isinstance(action.get("command"), str):
            return None
        return action
    except (ValueError, TypeError):
        return None


def main():
    store = Store(STORE)
    calls = sorted(store.events("calls"), key=lambda c: c.get("started_at") or "")
    counts = Counter()
    dead = []
    for i, c in enumerate(calls):
        art = (c.get("artifacts") or {}).get("response")
        row = {"idx": i, "call_id": c.get("call_id"),
               "attempt_id": c.get("attempt_id"), "phase": c.get("phase"),
               "input_tokens": c.get("input_tokens"),
               "output_tokens": c.get("output_tokens")}
        if not art or not art.get("path"):
            counts["no_response"] += 1
            continue
        resp = json.loads((STORE / art["path"]).read_text())
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text, fb, think = _extract_text(msg)
        row["finish_reason"] = choice.get("finish_reason")
        row["reasoning_fallback"] = fb
        row["think_stripped"] = think
        row["usage"] = resp.get("usage")
        if text is None:
            counts["no_response"] += 1
            continue
        if strict_live(text) is not None:
            counts["native_json"] += 1
            continue
        bridged = parse_native_tool_call(text)
        if bridged is not None:
            counts["bridged_markup"] += 1
            continue
        full = parse_model_action(text)
        if full.get("action") in ("shell", "done"):
            counts["bridged_markup"] += 1
            continue
        counts["still_dead"] += 1
        row["text"] = text
        dead.append(row)
    print("COUNTS", dict(counts), "total_calls", len(calls))
    out = Path.home() / "c5work"
    out.mkdir(exist_ok=True)
    dest = out / "c4-dead.jsonl"
    dest.write_text("".join(json.dumps(r) + "\n" for r in dead))
    print(f"WROTE {dest} rows={len(dead)}")
    for r in dead:
        print(f"--- dead idx={r['idx']} phase={r['phase']} "
              f"out_tok={r['output_tokens']} finish={r['finish_reason']} "
              f"len={len(r['text'])}")


if __name__ == "__main__":
    main()
