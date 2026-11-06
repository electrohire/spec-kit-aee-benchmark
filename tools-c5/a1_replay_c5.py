#!/usr/bin/env python3
"""Cycle 5 C5-A1 replay acceptance: every recorded response in the
campaign-c4 store through the CYCLE 5 adapter (benchmark-c5 tree),
compared against the frozen Cycle 4 rule reproduced from its two
pre-Cycle-5 stages. Expected: the 36 native parses identical; the
13 split-payload responses parse into their payloads' actions; the
2 prose-prefixed bare-JSON and the 1 truncated response stay dead."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path.home() / "needle-campaign"
REPO = BASE / "code" / "benchmark-c5"
STORE = BASE / "runs" / "campaign-c4"
sys.path.insert(0, str(REPO / "src"))

from benchmark_runner import runner  # noqa: E402
from benchmark_runner.local_provider import _extract_text  # noqa: E402
from benchmark_runner.store import Store  # noqa: E402


def old_parse(text):
    try:
        action = json.loads(text)
        if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
            raise ValueError("expected shell or done")
        if action["action"] == "shell" and not isinstance(action.get("command"), str):
            raise ValueError("shell command must be string")
        return action
    except (ValueError, TypeError):
        pass
    start = text.find(runner._TOOL_CALL_OPEN)
    if start >= 0:
        segment = text[start + len(runner._TOOL_CALL_OPEN):]
        end = segment.find(runner._TOOL_CALL_CLOSE)
        if end >= 0:
            segment = segment[:end]
        action = runner._payload_to_action(runner._first_json_object(segment))
        if action is not None:
            return action
        action = runner._envelope_action(segment)
        if action is not None:
            return action
    return {"action": "invalid"}


def main():
    store = Store(STORE)
    calls = sorted(store.events("calls"), key=lambda c: c.get("started_at") or "")
    counts = Counter()
    rescued = []
    for i, c in enumerate(calls):
        art = (c.get("artifacts") or {}).get("response")
        resp = json.loads((STORE / art["path"]).read_text())
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        text, _fb, _th = _extract_text(msg)
        old = old_parse(text)
        new = runner.parse_model_action(text)
        if old.get("action") in ("shell", "done"):
            counts["old_live"] += 1
            assert new == old, f"idx {i}: live behavior changed"
            counts["live_identical"] += 1
        elif new.get("action") in ("shell", "done"):
            counts["rescued"] += 1
            rescued.append({"idx": i, "phase": c.get("phase"),
                            "action": new["action"],
                            "command_sha256": hashlib.sha256(
                                new["command"].encode()).hexdigest(),
                            "command_len": len(new["command"])})
        else:
            counts["still_dead"] += 1
            print(f"STILL DEAD idx={i} phase={c.get('phase')}")
    print("REPLAY_COUNTS", dict(counts), "total", len(calls))
    for r in rescued:
        print("RESCUED", json.dumps(r))
    assert counts["live_identical"] == 36
    assert counts["rescued"] == 13
    assert counts["still_dead"] == 3
    print("A1_REPLAY_OK")


if __name__ == "__main__":
    main()
