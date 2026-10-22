"""Cycle 1 (2026-10-21) context discipline: wire-vs-assembled
accounting (C1-a), read-time observation masking (C1-b), and the
write-time observation cap for drafting/construction histories
(C1-A4).

The harness keeps one persistent conversation per attempt and re-sends
the assembled history on every call, while the provider's wire cap is
the frozen ``max_input_tokens``. Stage 1's fatal call assembled
~55,000 tokens against a 24,576 wire cap: the model worked against
provider-side truncation it could not see. This module makes that
regime observable (C1-a) and then removes it by construction (C1-b):
the history actually sent is masked deterministically until its
estimated size fits the wire cap, while the full assembled size is
still measured and recorded on every call.

Token estimation is a deterministic harness estimate, not a
tokenizer: ``ESTIMATE_FIXED_TOKENS`` per conversation plus
``ESTIMATE_MESSAGE_OVERHEAD`` and one token per
``ESTIMATE_CHARS_PER_TOKEN`` characters per message. It is the same
estimator on both sides of every comparison in this module (assembled
vs sent vs cap), so the masking guarantee and the over-cap flag are
internally consistent; provider-reported usage remains the wire truth
recorded beside it.
"""
from __future__ import annotations

import json
import math

# C1-b: the most recent K tool observations enter the sent history
# intact. Older observations are replaced by one-line elisions. K is
# a named constant, overridable per freeze via the config key
# ``observation_mask_recent_k``.
OBSERVATION_MASK_RECENT_K = 8

# C1-A4: tool observations entering a construction or drafting-phase
# history are capped at write time to this many bytes per stream
# (stdout and stderr separately), deterministically, with the byte
# counts recorded on the observation itself. Overridable per freeze
# via ``observation_write_cap_bytes``.
OBSERVATION_WRITE_CAP_BYTES = 4096

ESTIMATE_CHARS_PER_TOKEN = 4
ESTIMATE_MESSAGE_OVERHEAD = 4
ESTIMATE_FIXED_TOKENS = 3

# Message markers that pin a message as a governing artifact: the
# phase prompts and the frozen-setup record enter every later call
# and are never masked or truncated (C1-b/C1-A4).
_PINNED_PREFIXES = ("Current phase:",)
_PINNED_MARKERS = ("Campaign setup (constitution) was frozen",)


def _content_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


def estimate_tokens(messages):
    """The harness's deterministic token estimate for a message list."""
    total = ESTIMATE_FIXED_TOKENS
    for message in messages:
        total += ESTIMATE_MESSAGE_OVERHEAD
        total += math.ceil(len(_content_text(message)) / ESTIMATE_CHARS_PER_TOKEN)
    return total


def history_digest(messages):
    """SHA-256 of the canonical assembled history (C1-A2 bank check)."""
    from .store import canonical, sha
    return sha(canonical(messages))


def is_observation(message):
    """A tool observation: a user message whose content is the JSON
    object the environment produced for one shell action (it carries
    the tool result's stdout/stderr/exit_code keys)."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, str):
        return False
    try:
        parsed = json.loads(content)
    except ValueError:
        return False
    return isinstance(parsed, dict) and any(
        key in parsed for key in ("stdout", "stderr", "exit_code"))


def is_pinned(message, index, first_user_index):
    """Pinned messages are never masked: the system message, the task
    statement (the first user message), phase prompts, and messages
    carrying a phase's governing artifacts (the frozen setup record)."""
    if index == 0 or index == first_user_index:
        return True
    content = _content_text(message)
    return (content.startswith(_PINNED_PREFIXES)
            or any(marker in content for marker in _PINNED_MARKERS))


def elision_for(message):
    """The one-line replacement for a masked observation, carrying
    the original byte count so the elision is auditable."""
    original_bytes = len(_content_text(message).encode("utf-8"))
    return {"role": message.get("role", "user"),
            "content": json.dumps(
                {"elided_observation": True, "original_bytes": original_bytes,
                 "note": "observation masked at read time (C1-b); "
                         "full output retained in the run store"},
                sort_keys=True)}


class MaskingResult:
    def __init__(self, messages, masked_count, assembled_tokens, sent_tokens):
        self.messages = messages
        self.masked_count = masked_count
        self.assembled_tokens = assembled_tokens
        self.sent_tokens = sent_tokens


def mask_history(messages, wire_cap_tokens, recent_k=OBSERVATION_MASK_RECENT_K):
    """Deterministically mask older tool observations so the sent
    history fits the wire cap (C1-b).

    Rule: pinned messages are never touched. The most recent
    ``recent_k`` observations stay intact; every older observation is
    replaced by its one-line elision. If the result still estimates
    above ``wire_cap_tokens``, further observations are elided,
    oldest first (including inside the recent-K window), until the
    estimate fits or no unmasked observation remains — so the cap
    holds by construction whenever the unmaskable remainder (pinned
    messages, prompts, and model turns) fits on its own. The input
    list is never mutated; masking is a read-time view and the full
    history remains the agent's own state.
    """
    assembled = estimate_tokens(messages)
    first_user_index = next(
        (i for i, m in enumerate(messages) if m.get("role") == "user"), None)
    observation_indexes = [i for i, m in enumerate(messages)
                           if is_observation(m)
                           and not is_pinned(m, i, first_user_index)]
    keep = set(observation_indexes[-recent_k:]) if recent_k > 0 else set()
    masked = list(messages)
    masked_count = 0
    for i in observation_indexes:
        if i not in keep:
            masked[i] = elision_for(messages[i])
            masked_count += 1
    if estimate_tokens(masked) > wire_cap_tokens:
        for i in observation_indexes:
            if estimate_tokens(masked) <= wire_cap_tokens:
                break
            if masked[i] is messages[i]:  # still intact
                masked[i] = elision_for(messages[i])
                masked_count += 1
    return MaskingResult(masked, masked_count, assembled, estimate_tokens(masked))


def cap_observation_text(text, cap_bytes):
    """Deterministic write-time truncation of one observation stream
    (C1-A4). Returns (kept_text, total_bytes, kept_bytes). The kept
    text is the stream's head, followed by a marker line naming the
    truncation and both byte counts; a stream within the cap passes
    through unchanged."""
    data = text.encode("utf-8")
    total = len(data)
    if total <= cap_bytes:
        return text, total, total
    kept = data[:cap_bytes].decode("utf-8", errors="ignore")
    marker = (f"\n[observation truncated at write time (C1-A4): "
              f"kept {cap_bytes} of {total} bytes]")
    return kept + marker, total, cap_bytes


def cap_observation(result, cap_bytes):
    """Apply the C1-A4 write-time cap to one tool result dict as it
    enters a drafting/construction history. Byte counts are recorded
    on the observation itself; the full output remains in the run
    store as the tools artifact (recorded by the caller)."""
    capped = dict(result)
    for stream in ("stdout", "stderr"):
        if isinstance(capped.get(stream), str):
            kept, total, kept_bytes = cap_observation_text(capped[stream], cap_bytes)
            capped[stream] = kept
            capped[f"{stream}_bytes_total"] = total
            capped[f"{stream}_bytes_kept"] = kept_bytes
    return capped
