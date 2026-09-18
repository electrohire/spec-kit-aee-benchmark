"""Provider-native usage semantics and conservative pre-request reservations."""
from __future__ import annotations

import math
from decimal import Decimal

TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")


def validate_usage(usage):
    for key in TOKEN_FIELDS:
        n = usage.get(key)
        if n is not None and (type(n) is not int or n < 0):
            raise ValueError(f"invalid {key}")
    i, c = usage.get("input_tokens"), usage.get("cached_input_tokens")
    if i is not None and c is not None and c > i:
        raise ValueError("cached input exceeds input")
    r, o = usage.get("reasoning_tokens"), usage.get("output_tokens")
    if r is not None and o is not None and r > o:
        raise ValueError("reasoning subset exceeds output")
    if any(usage.get(k) is None for k in TOKEN_FIELDS) and not usage.get("unknown_reason"):
        raise ValueError("unknown usage requires a reason")
    return usage


def native_usage(response):
    u = response.get("usage") or {}
    result = {
        "input_tokens": u.get("prompt_tokens"),
        "cached_input_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "output_tokens": u.get("completion_tokens"),
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "unknown_reason": "provider omitted one or more usage details",
    }
    if all(result[k] is not None for k in TOKEN_FIELDS):
        result["unknown_reason"] = None
    return validate_usage(result)


def cumulative_delta(current, previous):
    validate_usage(current)
    validate_usage(previous)
    result = {k: None if current[k] is None or previous[k] is None else current[k] - previous[k]
              for k in TOKEN_FIELDS}
    result["unknown_reason"] = "cumulative category unavailable" if None in result.values() else None
    return validate_usage(result)


def money(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("price/cap must be finite and nonnegative")
    return n


def cost(usage, prices, tool_fees=0):
    validate_usage(usage)
    i, c, o = (usage[k] for k in TOKEN_FIELDS[:3])
    if None in (i, c, o):
        return None
    return ((i-c)*money(prices["input"]) + c*money(prices["cached_input"])
            + o*money(prices["output"])) / Decimal(1_000_000) + money(tool_fees)


def request_prices(config, usage=None):
    """Return actual tier, or conservative maximum rates for a reservation."""
    short = config["prices"]
    long = config.get("long_context_prices")
    if long is None:
        return short
    threshold = config["long_context_threshold"]
    if usage is None or usage.get("input_tokens") is None:
        return {k: max(money(short[k]), money(long[k])) for k in short}
    return long if usage["input_tokens"] > threshold else short


def unique_calls(calls):
    seen = {}
    for call in calls:
        key = call.get("request_id") or call["call_id"]
        if key in seen:
            if call != seen[key]:
                raise ValueError("conflicting duplicate call")
            continue
        seen[key] = call
    return list(seen.values())


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, store, global_cap, attempt_cap):
        self.store = store
        self.global_cap, self.attempt_cap = money(global_cap), money(attempt_cap)
        if not self.global_cap or not self.attempt_cap:
            raise ValueError("positive explicit caps required")

    def charges(self):
        reservations = {}
        for e in self.store.events("budget"):
            reservations[e["call_id"]] = e
        return reservations

    def reserve(self, call_id, attempt_id, amount):
        amount = money(amount)
        charges = self.charges()
        if call_id in charges:
            raise ValueError("call ID already reserved")
        total = sum((money(e["amount"]) for e in charges.values()), Decimal(0))
        attempt = sum((money(e["amount"]) for e in charges.values()
                       if e["attempt_id"] == attempt_id), Decimal(0))
        if total+amount > self.global_cap or attempt+amount > self.attempt_cap:
            raise BudgetExceeded("next request reservation would exceed cap")
        self.store.append("budget", dict(call_id=call_id, attempt_id=attempt_id,
                                        amount=str(amount), status="reserved"))

    def settle(self, call_id, actual):
        e = self.charges()[call_id]
        if actual is None:
            return  # Never release a possibly billable unknown request.
        actual = money(actual)
        if actual > money(e["amount"]):
            self.store.append("budget", {**e, "amount": str(actual), "status": "bound_violation"})
            raise RuntimeError("provider exceeded verified reservation bound; stop experiment")
        self.store.append("budget", {**e, "amount": str(actual), "status": "settled"})
