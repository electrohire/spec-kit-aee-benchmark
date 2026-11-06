#!/usr/bin/env python3
"""Cycle 5 C5-A1 fixture extraction: every recorded response in the
campaign-c4 store (adapter-visible text, the stats_c4 extraction),
labeled by the FROZEN Cycle 4 code's classification
(native_json / bridged_markup / still_dead), for the pinned replay
fixture tests/fixtures/cycle5_campaign_c4_responses.json."""
import json
import sys
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
    rows = []
    for i, c in enumerate(calls):
        art = (c.get("artifacts") or {}).get("response")
        resp = json.loads((STORE / art["path"]).read_text())
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        text, _fb, _th = _extract_text(msg)
        if strict_live(text) is not None:
            cls = "native_json"
        elif parse_native_tool_call(text) is not None or \
                parse_model_action(text).get("action") in ("shell", "done"):
            cls = "bridged_markup"
        else:
            cls = "still_dead"
        rows.append({"idx": i, "phase": c.get("phase"), "class": cls,
                     "output_tokens": c.get("output_tokens"), "text": text})
    out = Path.home() / "c5work" / "c4-all52.json"
    out.write_text(json.dumps(rows))
    from collections import Counter
    print("CLASSES", dict(Counter(r["class"] for r in rows)), "total", len(rows))
    print("WROTE", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
