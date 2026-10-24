"""Probe-path residual protocol (2026-10-24): P1 residual handoffs
+ P2 codebook references, as a configuration of the probe harness.

The model this implements is the MPCodec shelf's core move: an
observable is a projection of a constraint structure shared by both
ends; the sender transmits only the residual — what picks out the
real message from the ones the shared state still leaves open. Here
the "shared state" is the attempt's step log: the session brief and
every step the model has taken. Once a step has been transmitted in
full exactly once, later calls carry it by reference (entry id,
kind, and a digest-bearing detail line) instead of resending its
full text on every call — the resend pattern the ceiling map
measured at 67–98% of input traffic across the frozen run stores.

Synchronization is a proved invariant, not a hope: both ends derive
the state from the transmitted views alone. The receiver's state is
a pure function of the views (``reconstruct_state``); before any
view after the first is sent, the sender replays the receiver's
reconstruction over its own sent views plus the candidate view and
requires the replayed entry sequence and digest to equal the
canonical ones. Any divergence raises :class:`ResidualSyncError`
before the provider call — no inference is spent on a divergent
view, the attempt records an integrity error, and the study's
tripwire halts. There is no resync path: a divergence never repairs
itself silently.

Escapes and abstention: novel content (the newest step's action and
observation, any injected instruction) is always transmitted in
full, at full price, exactly once — only content already transmitted
may travel by reference. The problem statement is a pinned payload
and is repeated verbatim in every state block; the system and phase
instructions travel by reference after the first call.

The protocol is OFF unless the freeze config carries
``residual_protocol: true``; MiniModel's flag-off path is the
pre-change ``assemble_history`` path, byte-identical (pinned by
tests/test_residual_protocol.py).
"""
from __future__ import annotations

import json

from .context import (AUTHORED_TURN_EXCERPT_CHARS, MaskingResult,
                      OBSERVATION_MASK_RECENT_K, _content_text,
                      assemble_history, elision_for, estimate_tokens,
                      is_observation)
from .store import canonical, sha, utc

STATE_BLOCK_VERSION = 1

_BLOCK_NOTE = (
    "Session state under the residual protocol. The session brief "
    "(system instructions and phase instructions) was transmitted in "
    "full at the start of this session and remains in force; it is "
    "carried here by reference only (brief_sha256). The problem "
    "statement is repeated verbatim. Every step listed below was "
    "transmitted in full when it happened; earlier steps appear by "
    "reference — if you need an earlier step's full output again, "
    "re-run its command or read the file it wrote; do not guess its "
    "contents. The newest step follows this message in full.")


class ResidualSyncError(Exception):
    """A residual-protocol digest divergence. The message carries
    the harness tripwire classifier's integrity marker ("freeze"):
    a state that no longer matches its freeze-sync digest is an
    identity/integrity fact, and the study halts on it."""


def _divergence(detail):
    return ResidualSyncError(
        "residual protocol digest divergence (freeze-sync integrity "
        f"failure): {detail}")


def entry_id(message):
    """Content identity of one transmitted message form."""
    return sha(canonical({"role": message.get("role"),
                          "content": _content_text(message)}))


def classify_transmitted(message, in_brief=False):
    """The digest kind of a transmitted message form: brief entries
    by position; assistant turns are actions; user messages whose
    content is a tool observation (or its elision, which carries the
    elided_observation marker) are observations; anything else is a
    note (phase prompts, scaffold and gate instructions)."""
    if in_brief:
        return "brief"
    if message.get("role") == "assistant":
        return "action"
    if message.get("role") == "user":
        if is_observation(message):
            return "observation"
        try:
            parsed = json.loads(_content_text(message))
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("elided_observation"):
            return "observation"
        return "note"
    return "note"


def state_digest(entries):
    """SHA-256 over the canonical entry sequence ({id, kind})."""
    return sha(canonical([{"id": e["id"], "kind": e["kind"]}
                          for e in entries]))


def brief_digest(brief_entries):
    return sha(canonical([e["id"] for e in brief_entries]))


def _brief_length(messages):
    """The brief is the leading run of messages before the first
    assistant turn (system + problem statement + phase prompt); a
    history with no assistant turn yet is all brief."""
    for i, message in enumerate(messages):
        if message.get("role") == "assistant":
            return i
    return len(messages)


def _first_line(text, limit=100):
    line = (text or "").split("\n", 1)[0].strip()
    return line[:limit]


def _step_detail(message, kind):
    """The digest-bearing detail a reference line carries for one
    earlier step: enough to recognize the step, never its full text."""
    content = _content_text(message)
    if kind == "observation":
        detail = {}
        try:
            parsed = json.loads(content)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            detail["exit_code"] = parsed.get("exit_code")
            detail["first_line"] = _first_line(str(parsed.get("stdout", "")))
        else:
            detail["first_line"] = _first_line(content)
        detail["bytes"] = len(content.encode("utf-8"))
        return detail
    if kind == "action":
        try:
            parsed = json.loads(content)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("command"):
            return {"command": str(parsed["command"])[:100]}
        return {"first_line": _first_line(content)}
    return {"first_line": _first_line(content)}


def _parse_state_block(message):
    """The parsed residual_state block of a view's first message,
    or None when the message is not a state block."""
    if message.get("role") != "user":
        return None
    try:
        parsed = json.loads(_content_text(message))
    except ValueError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("residual_state"), dict):
        return parsed["residual_state"]
    return None


def reconstruct_state(views):
    """Replay transmitted views into the receiver's state: the
    ordered entry sequence and its digest, derived from the views
    alone. Raises ResidualSyncError on any divergence between what a
    view declares and what the earlier views actually transmitted."""
    if not views:
        raise _divergence("empty view transcript")
    first = views[0]
    if _parse_state_block(first[0]) is not None:
        raise _divergence("transcript opens with a state block; "
                          "the genesis view is missing")
    blen = _brief_length(first)
    entries = [{"id": entry_id(m),
                "kind": classify_transmitted(m, in_brief=i < blen)}
               for i, m in enumerate(first)]
    for view in views[1:]:
        block = _parse_state_block(view[0]) if view else None
        if block is None:
            raise _divergence("a later view carries no state block")
        if block.get("version") != STATE_BLOCK_VERSION:
            raise _divergence("state block version mismatch")
        if block.get("brief_sha256") != brief_digest(entries[:blen]):
            raise _divergence("brief reference does not match the "
                              "transmitted brief")
        declared_steps = [{"id": s.get("id"), "kind": s.get("kind")}
                          for s in block.get("steps") or []]
        if declared_steps != entries[blen:]:
            raise _divergence("step index does not match the "
                              "transmitted step sequence")
        entries = entries + [
            {"id": entry_id(m), "kind": classify_transmitted(m)}
            for m in view[1:]]
        if block.get("entries_total") != len(entries):
            raise _divergence("declared entry count does not match "
                              "the replayed sequence")
        if block.get("state_digest") != state_digest(entries):
            raise _divergence("declared state digest does not match "
                              "the replayed state")
    return entries, state_digest(entries)


class ResidualSession:
    """Sender side of the protocol for one attempt. Held by
    MiniModel; a fresh session per attempt, exactly as the brief is
    per attempt."""

    def __init__(self, store=None, identity=None):
        self.store = store
        self.identity = dict(identity or {})
        self.sent_views = []
        self._entries = []        # transmitted-form entries, in order
        self._forms = []          # per history position: full|elided|frozen
        self._full_sent = 0       # history positions transmitted so far
        self._brief_len = None
        self._brief_id = None
        self._problem = None
        self._brief_bytes = 0

    # -- recorded state ------------------------------------------------
    def entries(self):
        return list(self._entries)

    def state_digest(self):
        return state_digest(self._entries)

    # -- view construction ---------------------------------------------
    def view(self, messages, wire_cap_tokens, current_phase=None,
             recent_k=OBSERVATION_MASK_RECENT_K, artifact_registry=None,
             excerpt_chars=AUTHORED_TURN_EXCERPT_CHARS, phase=None):
        if not self.sent_views:
            return self._first_view(messages, wire_cap_tokens,
                                    current_phase, recent_k,
                                    artifact_registry, excerpt_chars, phase)
        return self._later_view(messages, wire_cap_tokens, phase)

    def _record(self, result, phase, delta_messages):
        if self.store is not None:
            self.store.append("residual_views", {
                **self.identity, "timestamp": utc(), "phase": phase,
                "view": len(self.sent_views),
                "entries": len(self._entries),
                "delta_messages": delta_messages,
                "assembled_tokens": result.assembled_tokens,
                "sent_tokens": result.sent_tokens,
                "digest": self.state_digest()})

    def _first_view(self, messages, wire_cap_tokens, current_phase,
                    recent_k, artifact_registry, excerpt_chars, phase):
        # The genesis view IS the pre-change assembled view: the
        # brief is paid once, in full, under the existing masking
        # discipline. Transmitted forms are recorded from the result.
        result = assemble_history(
            messages, wire_cap_tokens, current_phase=current_phase,
            recent_k=recent_k, artifact_registry=artifact_registry,
            excerpt_chars=excerpt_chars)
        self._brief_len = _brief_length(messages)
        for i, transmitted in enumerate(result.messages):
            original = messages[i] if i < len(messages) else transmitted
            if _content_text(transmitted) == _content_text(original):
                form = "full"
            elif _content_text(transmitted) == _content_text(elision_for(original)):
                form = "elided"
            else:
                form = "frozen"
            self._forms.append(form)
            self._entries.append({
                "id": entry_id(transmitted),
                "kind": classify_transmitted(transmitted,
                                             in_brief=i < self._brief_len)})
        self._full_sent = len(messages)
        brief_entries = self._entries[:self._brief_len]
        self._brief_id = brief_digest(brief_entries)
        self._brief_bytes = sum(
            len(_content_text(m).encode("utf-8"))
            for m in result.messages[:self._brief_len])
        for i, m in enumerate(messages[:self._brief_len]):
            if m.get("role") == "user":
                self._problem = _content_text(m)
                break
        self.sent_views.append([dict(m) for m in result.messages])
        self._record(result, phase, len(result.messages))
        return result

    def _later_view(self, messages, wire_cap_tokens, phase):
        # Prefix stability: history positions already transmitted
        # must still carry the content they were transmitted with —
        # the recorded transmitted form is recomputed from the
        # current history and compared ("frozen" positions are the
        # genesis view's before-path output, recorded verbatim and
        # not recomputed). Any mismatch is a divergence: the state
        # the receiver holds no longer matches the sender's history.
        if len(messages) < self._full_sent:
            raise _divergence("history shrank below the transmitted "
                              "prefix")
        for pos in range(self._full_sent):
            form = self._forms[pos]
            if form == "frozen":
                continue
            expected = (messages[pos] if form == "full"
                        else elision_for(messages[pos]))
            if entry_id(expected) != self._entries[pos]["id"]:
                raise _divergence(
                    f"history position {pos} no longer matches its "
                    "transmitted form")
        delta_start = self._full_sent
        # Decide the delta's transmitted forms: full, unless the
        # assembled view would exceed the wire cap — then elide
        # delta observations oldest first, never the newest one.
        delta = [dict(m) for m in messages[delta_start:]]
        delta_forms = ["full"] * len(delta)
        steps = []
        for pos in range(self._brief_len, delta_start):
            entry = self._entries[pos]
            detail = _step_detail(messages[pos], entry["kind"])
            steps.append({"step": pos, "kind": entry["kind"],
                          "id": entry["id"], **detail})
        new_entries = list(self._entries) + [
            {"id": entry_id(m), "kind": classify_transmitted(m)}
            for m in delta]
        block = {"residual_state": {
            "version": STATE_BLOCK_VERSION,
            "note": _BLOCK_NOTE,
            "brief_sha256": self._brief_id,
            "brief_bytes": self._brief_bytes,
            "problem_statement": self._problem,
            "steps": steps,
            "entries_total": len(new_entries),
            "state_digest": state_digest(new_entries)}}
        def build_candidate():
            inner = list(self._entries) + [
                {"id": entry_id(m), "kind": classify_transmitted(m)}
                for m in delta]
            block["residual_state"]["state_digest"] = state_digest(inner)
            block["residual_state"]["entries_total"] = len(inner)
            return ([{"role": "user",
                      "content": json.dumps(block, sort_keys=True)}] + delta,
                    inner)

        candidate, new_entries = build_candidate()
        if estimate_tokens(candidate) > wire_cap_tokens:
            # Cap pressure inside the delta: elide its observations
            # oldest first (the before-path's own fallback). Entry
            # identity is over transmitted forms, so an elided delta
            # entry is the elision on both ends and the digest is
            # computed over exactly what crosses.
            for j, m in enumerate(delta):
                if estimate_tokens(candidate) <= wire_cap_tokens:
                    break
                if classify_transmitted(m) == "observation":
                    delta[j] = elision_for(m)
                    delta_forms[j] = "elided"
                    candidate, new_entries = build_candidate()
        # Pre-send digest sync: replay the receiver's reconstruction
        # over every view actually sent plus this candidate, and
        # require it to reproduce the canonical entry sequence and
        # digest exactly. A divergence raises here — the candidate
        # is never transmitted and no inference is spent on it.
        replayed, replay_digest = reconstruct_state(
            self.sent_views + [candidate])
        if ([e["id"] for e in replayed] != [e["id"] for e in new_entries]
                or replay_digest != state_digest(new_entries)):
            raise _divergence("receiver replay does not reproduce "
                              "the canonical state")
        result = MaskingResult(
            candidate,
            masked_count=sum(1 for e in self._entries[self._brief_len:]
                             if e["kind"] == "observation"),
            assembled_tokens=estimate_tokens(messages),
            sent_tokens=estimate_tokens(candidate),
            externalized_count=sum(1 for e in self._entries[self._brief_len:]
                                   if e["kind"] == "action"),
            unmaskable_remainder_over_cap=estimate_tokens(candidate) > wire_cap_tokens)
        self._entries = new_entries
        self._forms.extend(delta_forms)
        self._full_sent = len(messages)
        self.sent_views.append([dict(m) for m in candidate])
        self._record(result, phase, len(delta))
        return result
