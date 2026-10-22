"""Cycle 1 (2026-10-21) context discipline: wire-vs-assembled
accounting (C1-a), read-time observation masking (C1-b), and the
write-time observation cap for drafting/construction histories
(C1-A4).

Cycle 2 C2-F2 (2026-10-22) adds authored-turn history discipline:
model-authored turns from EARLIER phases are replaced in the
assembled view by the phase artifact's identity (workspace path +
hash + a bounded excerpt); the current phase's authored turns
stay intact. The artifact itself lives in the workspace / run
store, where later phases read it (the phase skills direct the
model to the artifact files under /workflow, and the harness's own
phase records carry the artifact identity — no harness code path
re-reads an earlier phase's authored turns out of the history;
see the Cycle 2 change record for the verification). The
assembled <= wire-cap guarantee is restated over the COMBINED
rule — observations masked (C1-b) + earlier authored turns
externalized (C2-F2) + pins: when even that combined remainder
exceeds the cap, the call record flags
``unmaskable_remainder_over_cap`` as a named, countable finding
instead of silently serving an over-cap history.

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

import hashlib
import json
import math
import re

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

# C2-F2: the bounded excerpt of an externalized authored turn that
# stays in the assembled view, in characters. A named constant,
# overridable per freeze via the config key
# ``authored_turn_excerpt_chars``.
AUTHORED_TURN_EXCERPT_CHARS = 512

_PHASE_MARKER_PREFIX = "Current phase:"
_WORKSPACE_PATH_RE = re.compile(r"(/workflow/\S+|specs/\S+)")


def phase_of_prompt(content):
    """The phase named by a ``Current phase: <phase>`` prompt
    message, or None when the content carries no such marker."""
    if not isinstance(content, str) or not content.startswith(_PHASE_MARKER_PREFIX):
        return None
    rest = content[len(_PHASE_MARKER_PREFIX):].strip()
    return rest.split()[0] if rest.split() else None


def message_phases(messages):
    """Attribute every message to the phase segment it sits in: a
    message belongs to the phase named by the most recent
    ``Current phase:`` prompt at or before it; messages before the
    first marker belong to no phase (None) and are never
    externalized (their phase cannot be established)."""
    phases = []
    current = None
    for message in messages:
        named = phase_of_prompt(_content_text(message))
        if named is not None:
            current = named
        phases.append(current)
    return phases


def extract_workspace_path(text):
    """The first workspace artifact path named in a text (the
    adapter prompt requires each phase's done JSON to carry
    artifact references), or None."""
    match = _WORKSPACE_PATH_RE.search(text or "")
    if not match:
        return None
    return match.group(1).rstrip("\"'`,.;)]}")


_extract_workspace_path = extract_workspace_path


def authored_turn_placeholder(message, phase, registry_entry=None,
                              excerpt_chars=AUTHORED_TURN_EXCERPT_CHARS):
    """The assembled-view replacement for one earlier-phase
    authored turn: the phase artifact's identity — workspace path,
    artifact hash, and a bounded excerpt of the turn — instead of
    the turn's full text. The hash is the registry's artifact hash
    when the harness recorded one for the phase (the run-store
    artifact of the phase completion); otherwise it is the
    SHA-256 of the turn's own content, so the identity is always
    checkable against the full history the agent retains."""
    content = _content_text(message)
    entry = registry_entry or {}
    placeholder = {
        "externalized_authored_turn": True,
        "phase": phase,
        "workspace_path": entry.get("workspace_path")
                          or _extract_workspace_path(content),
        "artifact_sha256": entry.get("sha256")
                           or hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "artifact_store_path": entry.get("store_path"),
        "excerpt": content[:excerpt_chars],
        "original_chars": len(content),
        "note": "authored turn from an earlier phase externalized "
                "(C2-F2); the phase artifact lives in the workspace "
                "and the run store, where later phases read it",
    }
    return {"role": message.get("role", "assistant"),
            "content": json.dumps(placeholder, sort_keys=True)}


def externalize_authored_turns(messages, current_phase,
                               artifact_registry=None,
                               excerpt_chars=AUTHORED_TURN_EXCERPT_CHARS):
    """Replace model-authored (assistant) turns attributed to
    phases other than ``current_phase`` with their artifact
    identity placeholders (C2-F2). The current phase's authored
    turns stay byte-identical; non-authored messages are never
    touched; turns whose phase cannot be attributed are kept. The
    input list is never mutated. Returns (messages, count)."""
    if current_phase is None:
        return list(messages), 0
    registry = artifact_registry or {}
    attributed = message_phases(messages)
    out = list(messages)
    count = 0
    for i, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        phase = attributed[i]
        if phase is None or phase == current_phase:
            continue
        out[i] = authored_turn_placeholder(
            message, phase, registry.get(phase), excerpt_chars)
        count += 1
    return out, count

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
    def __init__(self, messages, masked_count, assembled_tokens, sent_tokens,
                 externalized_count=0, unmaskable_remainder_over_cap=False):
        self.messages = messages
        self.masked_count = masked_count
        self.assembled_tokens = assembled_tokens
        self.sent_tokens = sent_tokens
        # C2-F2 combined-rule fields (zero/False under C1-b alone).
        self.externalized_count = externalized_count
        self.unmaskable_remainder_over_cap = unmaskable_remainder_over_cap


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


def assemble_history(messages, wire_cap_tokens, current_phase=None,
                     recent_k=OBSERVATION_MASK_RECENT_K,
                     artifact_registry=None,
                     excerpt_chars=AUTHORED_TURN_EXCERPT_CHARS):
    """The combined assembled view (C1-b + C2-F2): earlier phases'
    authored turns are externalized to their artifact identities,
    then older tool observations are masked, so the sent history
    fits the wire cap whenever the combined remainder (pins +
    current-phase turns + placeholders) fits on its own.

    The guarantee is stated over the combined rule, and its failure
    is never silent: when the sent estimate still exceeds
    ``wire_cap_tokens`` after both mechanisms have done all they
    can, the result's ``unmaskable_remainder_over_cap`` is True and
    the calling model records that named flag on the call record,
    where it is countable in the run store. ``assembled_tokens``
    remains the estimate of the FULL history the harness built
    (before either mechanism), preserving C1-a's meaning."""
    assembled = estimate_tokens(messages)
    externalized, externalized_count = externalize_authored_turns(
        messages, current_phase, artifact_registry, excerpt_chars)
    masked = mask_history(externalized, wire_cap_tokens, recent_k=recent_k)
    return MaskingResult(
        masked.messages, masked.masked_count, assembled, masked.sent_tokens,
        externalized_count=externalized_count,
        unmaskable_remainder_over_cap=masked.sent_tokens > wire_cap_tokens)


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
