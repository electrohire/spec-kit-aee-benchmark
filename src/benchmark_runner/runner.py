"""Thin mini-SWE-agent adapter; one persistent agent and budget per attempt."""
from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import shlex
import subprocess
import tarfile
import time
import tempfile
import shutil
import urllib.request
from pathlib import Path

from .accounting import Budget, BudgetExceeded, TOKEN_FIELDS, attempt_token_usage
from .context import (AUTHORED_TURN_EXCERPT_CHARS, OBSERVATION_MASK_RECENT_K,
                      OBSERVATION_WRITE_CAP_BYTES, assemble_history,
                      cap_observation, extract_workspace_path, history_digest,
                      mask_history)
from .experiment import verify_freeze
from .isolation import DockerSandbox
from .residual import ResidualSession
from .provider import (AttemptWallExpiredError, OpenAIProvider, ProviderError,
                       provider_spec, transport_policy)
from .local_provider import (CALL_OUTER_BOUND_SECONDS, CallOuterBoundError,
                             LocalProvider, TransportStallError, base_url,
                             check_local_server, probe_worker, server_root)
from .store import RunLock, Store, canonical, read_json, sha, utc, write_json
from .token_router import route_observation, try_retrieval
from .tripwires import (HALT_STUDY, attempt_wall_expiry_reason,
                        phase_exhaustion_reason, record_tripwire)
from .workflow import (AEE_PHASES, DeltaFormatError, assess, campaign_setup,
                       compact_feedback, gate_outcome_of, grounded_claims,
                       phase_prompt, phases, resolve_claim_submission)


class LimitHit(RuntimeError):
    pass


def error_reason(e):
    """One-line sanitized error reason for attempt records.

    Preserves the exception message (single-line, truncated) instead of only
    the type name, so a halted campaign can be diagnosed from the attempt
    stream without the host log. Provider adapters already reduce provider
    failures to bare type names before they reach this handler; never put
    credentials, headers, or raw provider error bodies into an exception
    message that flows through here.
    """
    msg = " ".join(str(e).split())
    if len(msg) > 300:
        msg = msg[:297] + "..."
    name = type(e).__name__
    return f"{name}: {msg}" if msg else name


def remaining(deadline):
    seconds = deadline-time.monotonic()
    if seconds <= 0:
        raise LimitHit("wall-time limit")
    return seconds


# Local-backend calibration (2026-09-24): the operator's llama.cpp server is
# dramatically slower than frontier APIs (pilot measured 41-108s per model
# call; every call past the 120s client timeout failed). Local runs therefore
# get a longer per-call timeout and attempt wall-time, gated on the frozen
# manifest's provider_backend == "local". Paid/frontier defaults (120s per
# call, cfg timeout_seconds) are untouched.
LOCAL_CALL_TIMEOUT_SECONDS = 600
LOCAL_WALL_TIME_SECONDS = 7200
FRONTIER_CALL_TIMEOUT_SECONDS = 120


# Needle program Workstream A3: claim-count discipline. The same
# sentence is carried by prompts/adapter.md (so it is part of every
# Spec Kit phase prompt) and by the claims instruction injected for
# AEE phases below.
CLAIM_DISCIPLINE = ("Claim discipline: one claim per independently falsifiable "
                    "requirement; merge duplicates instead of restating a "
                    "requirement; prefer few, load-bearing claims over many "
                    "overlapping ones.")
# A3 soft cap: a phase bundle above this many claims earns exactly
# one in-phase consolidation request before it is assessed.
CLAIM_SOFT_CAP = 12


# Amendment 1 (2026-10-21): phase guard, setup by construction,
# worker-availability probe. The numbers are the amendment's frozen
# values; a campaign manifest may carry the same keys in its config
# (the Stage 1R freeze does), in which case the frozen values govern.
PHASE_GUARD_TOKENS = 900_000   # R-A3: 60% of the 1,500,000 attempt cap
PHASE_GUARD_CALLS = 40         # R-A3: per-phase call cap
# The delivery phase is exempt from the token guard (not the call
# cap): bounding the phase that creates the value, tighter than the
# attempt cap, has no observational basis (Amendment 1 §3).
PHASE_GUARD_TOKEN_EXEMPT = frozenset({"implement"})
CONSTRUCTION_CAP_TOKENS = 900_000  # R-A1: per-task construction cap
WORKER_BLOCK_LIMIT = 3             # R-A6: busy blocks per stage -> halt
CONSTITUTION_PATH = ".specify/memory/constitution.md"

# Cycle 1 (2026-10-21) reconciled plan: C1-A2 banked construction —
# the per-draw cap above is one installment; construction completes
# across at most this many installments under this per-task total on
# the setup line. C1-A4/C1-b: the drafting phases whose histories get
# write-time observation caps; C1-c: the drafting phases governed by
# envelopes with rollover and force-advance (constitution is handled
# by the banked construction structure, not by force-advance).
CONSTRUCTION_TOTAL_CAP_TOKENS = 1_800_000  # C1-A2: per-task total
CONSTRUCTION_MAX_INSTALLMENTS = 3          # C1-A2: installments per task
DRAFTING_PHASES = frozenset({"constitution", "specify", "plan", "tasks"})
FORCE_ADVANCE_PHASES = frozenset({"specify", "plan", "tasks"})
FINALIZE_INSTRUCTION = (
    "Phase envelope reached (Cycle 1 force-advance): stop drafting and "
    "emit this phase's completion artifact NOW, from the draft state "
    "already in this conversation. Reply with exactly one JSON object "
    "{\"action\":\"done\",\"summary\":\"...\"} carrying the phase "
    "artifact in its usual completion form. No further shell calls.")

# Cycle 2 C2-F1: the per-phase wall bound. No drafting phase may
# consume more than this fraction of the attempt wall without
# completing (mirrors the token guard's 60%; the implementation
# phase is exempt, exactly as it is exempt from the token guard).
# Expiry is handled exactly as a token-envelope expiry: a
# force-advance phase spends its one reserved finalize call; any
# other guarded drafting phase ends exhausted and the patch is
# graded as it stands. Overridable per freeze via
# ``phase_wall_fraction``.
PHASE_WALL_FRACTION = 0.6


def phase_wall_fraction(cfg):
    return float(cfg.get("phase_wall_fraction", PHASE_WALL_FRACTION))


def phase_wall_bound_seconds(cfg):
    """The per-phase wall bound in seconds for this freeze."""
    return phase_wall_fraction(cfg) * attempt_wall_seconds(cfg)


def phase_wall_tripped(phase, elapsed_seconds, cfg):
    """C2-F1 per-phase wall bound: drafting phases only; the
    delivery phase (implement) is exempt, as under the token
    guard, and non-drafting phases (the baseline loop) are
    unguarded, also as under the token guard."""
    if phase not in DRAFTING_PHASES or phase in PHASE_GUARD_TOKEN_EXEMPT:
        return False
    return elapsed_seconds >= phase_wall_bound_seconds(cfg)


def construction_total_cap_tokens(cfg):
    return int(cfg.get("construction_total_cap_tokens", CONSTRUCTION_TOTAL_CAP_TOKENS))


def construction_max_installments(cfg):
    return int(cfg.get("construction_max_installments", CONSTRUCTION_MAX_INSTALLMENTS))


def drafting_envelope_tripped(phase, calls, cfg, drafting_completed):
    """C1-c envelope for a force-advance drafting phase: the
    Amendment 1 placeholders (60% guard, 40-call bound), with the
    token envelope cumulative across drafting phases — unused
    envelope from completed drafting phases rolls forward, so a
    phase may spend its own envelope plus every earlier drafting
    phase's unspent remainder."""
    phase_calls = [c for c in calls if c.get("phase") == phase]
    if len(phase_calls) >= phase_guard_calls(cfg):
        return True
    drafting_calls = [c for c in calls if c.get("phase") in FORCE_ADVANCE_PHASES]
    envelope = phase_guard_tokens(cfg) * (drafting_completed + 1)
    return attempt_token_usage(drafting_calls, cfg) >= envelope


# Cycle 5 C5-F1 (2026-10-22): the drafting reserve. Cycle 4's
# confirmation attempt completed specify and plan and still funded
# implementation with 0 tokens — the three drafting phases consumed
# 100% of the 1,500,000 attempt cap between them (31% / 33% / 36%).
# Within the unchanged attempt cap, the drafting phases (specify +
# plan + tasks) hold a cumulative hard sub-cap of 750,000 tokens; on
# exhaustion the attempt force-advances to implementation with
# whatever artifacts exist, and implementation + assessment hold
# the reserved remainder. A drafting force-advance is NOT
# phase_budget_exhausted: no finalize call is spent past the
# sub-cap (the reserve is the point), the phase's partial draft
# state — its workspace files plus every completed drafting phase's
# registered artifact identity — carries into implementation, and
# the advance is recorded as a ``drafting_force_advanced`` phase
# event with the exact drafting charge at the advance.
#
# The sub-cap is a FREEZE-CONFIGURED bound, like the campaign-setup
# sharing opt-in: it applies exactly when the freeze config carries
# ``drafting_sub_cap_tokens`` (the Cycle 5 freeze carries 750000).
# A config without the key keeps the recorded pre-Cycle-5 semantics
# bit-for-bit — a frozen manifest must reproduce its recorded
# behavior, and the Cycle 1 envelope tests pin those semantics for
# reserve-less configs (this discipline was forced by exactly those
# tests failing against a code-level default: the runaway shapes
# force-advanced at 750,000 before their 900,000 envelopes could
# act, and a phase-exhaustion shape completed instead of scoring).
DRAFTING_SUB_CAP_TOKENS = 750_000


def drafting_sub_cap_tokens(cfg):
    """The freeze-configured drafting sub-cap, or None when this
    freeze carries no drafting reserve."""
    if "drafting_sub_cap_tokens" not in cfg:
        return None
    return int(cfg["drafting_sub_cap_tokens"])


def drafting_tokens_used(calls, cfg):
    """Charged tokens across the drafting phases (specify + plan +
    tasks) — the C5-F1 sub-cap's meter, on the harness's own
    accounting, identical to the envelope meter's."""
    drafting_calls = [c for c in calls if c.get("phase") in FORCE_ADVANCE_PHASES]
    return attempt_token_usage(drafting_calls, cfg)


def drafting_sub_cap_tripped(calls, cfg):
    sub_cap = drafting_sub_cap_tokens(cfg)
    if sub_cap is None:
        return False
    return drafting_tokens_used(calls, cfg) >= sub_cap


# Stage A (2026-10-22) edit-conversion scaffold, plan requirements
# H1-H3. Like the Cycle 5 drafting reserve, every piece is
# FREEZE-CONFIGURED: a behavior applies exactly when the freeze
# config carries its key, and a config without the keys keeps the
# pre-Stage-A semantics bit-for-bit.
#
# H1 phase-forcing (plain loop only): cfg keys
# ``edit_switch_fraction`` (the plan's registered value is 0.40)
# and ``verify_nudge_fraction`` (0.55). Active only in the baseline
# arm's single ``solve`` phase. The attempt's binding budgets are
# cfg["token_cap"] (charged tokens in this phase, read from the
# calls ledger on the harness's own accounting, the way
# drafting_tokens_used reads it) and cfg["max_calls"] (steps in
# this phase). A threshold fires when EITHER measure first reaches
# its fraction; when both cross at the same step the calls measure
# is recorded as the one that fired. Each threshold fires at most
# once per attempt, the verify nudge only after the edit switch
# (the switch is checked first when both would fire at one step),
# and each firing is recorded on the ``scaffold_events`` stream so
# a live probe's records show the firings exactly.
#
# H2 empty-patch gate: cfg key ``empty_patch_gate`` (true). Active
# only in the ``solve`` phase and only on the natural-done
# completion path: a submission whose current diff is empty is
# rejected once with a retry instruction and the phase continues;
# a second empty submission completes and scores empty, as before.
# The gate never fires on finalize/exhaustion/wall paths.
#
# H3 probe solve instruction: cfg key ``solve_instruction_path``
# (a root-relative path, the probe freezes carry
# "prompts/probe-solve.md"). When present, that file's text is the
# baseline arm's initial system content instead of the
# phase_prompt(root, "baseline", "solve") result.
#
# H4 no self-critique: by construction — this scaffold adds no
# critique/reflection step anywhere; the exclusion is stated in
# the Stage A stage record.
EDIT_SWITCH_INSTRUCTION = (
    "Edit mode (Stage A phase-forcing): stop exploring. Write the fix "
    "into the repository files now, using what you have learned. If "
    "your reproduction script is not written yet, write it first, "
    "then edit the source.")
VERIFY_NUDGE_INSTRUCTION = (
    "Verify now (Stage A phase-forcing): rerun your reproduction "
    "script and the relevant existing tests now. Fix what they show "
    "before submitting.")
EMPTY_PATCH_GATE_INSTRUCTION = (
    "Your submission has an empty diff: nothing in the repository "
    "changed, and a done with no changes scores as an empty result. "
    "Produce the fix now: edit the source, rerun your reproduction, "
    "then submit done again.")


def scaffold_threshold_fired_by(steps_done, phase_charged, fraction, cfg):
    """Which budget measure first reaches ``fraction`` of its bound,
    or None. Steps: steps_done >= ceil(fraction * max_calls).
    Tokens: phase_charged >= fraction * token_cap. When both hold,
    the calls measure is reported (the step count is the plainer
    reading of "first" at a single observation point)."""
    if steps_done >= math.ceil(fraction * int(cfg["max_calls"])):
        return "calls"
    token_cap = cfg.get("token_cap")
    if token_cap is not None and phase_charged >= fraction * token_cap:
        return "tokens"
    return None


def phase_guard_tokens(cfg):
    return int(cfg.get("phase_guard_tokens", PHASE_GUARD_TOKENS))


def phase_guard_calls(cfg):
    return int(cfg.get("phase_guard_calls", PHASE_GUARD_CALLS))


def construction_cap_tokens(cfg):
    return int(cfg.get("construction_cap_tokens", CONSTRUCTION_CAP_TOKENS))


def construction_enabled(cfg):
    """Setup by construction (R-A1) applies when the campaign shares
    setup and the manifest does not opt out. The opt-out exists so a
    pre-amendment manifest keeps its recorded semantics; the Stage 1R
    freeze opts in explicitly."""
    return bool(cfg.get("share_campaign_setup")) and bool(
        cfg.get("campaign_setup_construction", True))


def phase_guard_tripped(arm, phase, phase_calls, cfg):
    """R-A3: a phase of a phased arm that reaches the token guard or
    the call cap without a completion artifact ends. The baseline
    arm's single loop is the treatment and is unguarded; the delivery
    phase (implement) is exempt from the token guard only."""
    if arm == "baseline":
        return False
    if len(phase_calls) >= phase_guard_calls(cfg):
        return True
    if phase in PHASE_GUARD_TOKEN_EXEMPT:
        return False
    return attempt_token_usage(phase_calls, cfg) >= phase_guard_tokens(cfg)


def claims_instruction(root, *, delta=False):
    """The claims instruction a frozen AEE run actually carries,
    injected at phase completion in execute_attempt. The first
    assessed phase of an attempt takes a full bundle; every later
    assessed phase (and every repair round) takes a delta against
    the standing bundle (Workstream A2)."""
    schema = (Path(root)/".specify/extensions/aee/templates/aee-claims.json").read_text()
    if not delta:
        return ("\nAt phase completion include claims using this schema example "
                "(replace all example content):\n" + CLAIM_DISCIPLINE + "\n" + schema)
    return ("\nAt phase completion submit a claims delta against the standing bundle "
            "from the earlier assessed phases; do not re-draft the whole bundle. "
            + CLAIM_DISCIPLINE + "\n"
            'Delta form (replace all example content): include in your done JSON '
            '"claims":{"schema_version":"1.0","delta":{"upsert":[<full claim objects '
            'for new or changed claims, each carrying its claim id>],'
            '"withdraw":["<claim id to withdraw>"]}}. Omit "upsert" when nothing '
            "changes and \"withdraw\" when nothing is withdrawn. A repair round "
            "uses the same delta form, scoped to the findings being addressed. "
            "Claim objects inside \"upsert\" follow this schema example:\n" + schema)


def local_backend(cfg):
    return cfg.get("provider_backend") == "local"


def call_timeout_seconds(cfg):
    return LOCAL_CALL_TIMEOUT_SECONDS if local_backend(cfg) else FRONTIER_CALL_TIMEOUT_SECONDS


def workflow_call_timeout_seconds(cfg):
    """Per-call timeout for the phase workflow (execute_attempt and
    construction). Cycle 1 C1-A3: on the local backend a call's
    deadline is the inactivity-aware outer bound — silence declares a
    stall at 600 s and a flowing call may run to 7,200 s — not the
    600 s wall that killed Stage 1R's flowing astropy call. The
    matched-repair protocol keeps call_timeout_seconds unchanged."""
    if local_backend(cfg):
        return CALL_OUTER_BOUND_SECONDS
    return call_timeout_seconds(cfg)


def attempt_wall_seconds(cfg):
    return LOCAL_WALL_TIME_SECONDS if local_backend(cfg) else cfg["timeout_seconds"]


# Cycle 3 C3-F1 — native-format bridge for the plain-loop adapter.
#
# Characterization from the recorded probe-(i) responses (Cycle 2
# freeze store ``probe-c2-i``, all 257 response artifacts, extracted
# exactly as the adapter saw them, i.e. after the local provider's
# text extraction): 243 of 257 responses failed the strict JSON
# parse. 229 of them carry the served model's native tool-call
# markup and 14 are a bare JSON action object preceded by prose
# (the seaborn attempt; no markup — NOT bridged, see below). The
# markup family, as recorded (never the canonical OpenAI
# name/arguments form, which appears nowhere in the records):
#
#   [optional prose] <tool_call> PAYLOAD [stray closers] [</tool_call>]
#
# - PAYLOAD is a flat two-key JSON object naming the action in one
#   of two recorded key styles: {"action": "shell", "command": ...}
#   (155 of the 212 payloads that parse) or {"function": "shell",
#   "command": ...} (57). Every parseable payload in probe (i) is a
#   shell action; the Cycle 1 store additionally records one
#   {"action": "done", "summary": ...} payload in this markup.
# - The closing is unstable: a clean </tool_call> (88 of the dead
#   markup responses), a hybrid tail "</parameter> </function>
#   </tool_call>" (141), or — the Cycle 1 store's dominant forms —
#   stray closers with NO </tool_call> at all ("</parameter>
#   </function>", "</function>", "</parameter> </invoke>").
# - 31 of the 229 markup payloads are not valid JSON at all: the
#   command string contains UNESCAPED double quotes (e.g. an
#   embedded echo "---"), so json parsing fails mid-string. The
#   envelope (kind key, then the payload field key, then a final
#   '" }') is still intact in those records, and the command is
#   recoverable deterministically as everything between the field
#   key's opening quote and that final quote-brace — the only
#   reading consistent with the recorded envelope.
# - Two further recorded terminations replace the closing
#   quote-brace: a literal "</command>" closing the command field
#   (probe (i)'s test_reduction attempt), and — Cycle 1 store — the
#   value running straight into the stray-tag tail. Both are
#   recovered by the envelope rule in _envelope_action. A payload
#   with NO termination at all (the value runs off the end of the
#   response) is NOT recoverable and remains a format correction,
#   exactly as before.
#
# The bridge below accepts exactly this recorded family: the first
# <tool_call> segment in the response (the adapter protocol is one
# action per response, as on the JSON path), its payload parsed
# strictly when possible and by the envelope rule when the payload's
# inner quotes defeat strict parsing. It produces the same action
# dicts the JSON path produces — same validation (shell requires a
# string command), same preservation of extra payload fields — so
# execution, accounting, and limits downstream are unchanged. The
# JSON path is tried first and is untouched; a response parseable
# by neither path (including bare-JSON-in-prose, which is not the
# native markup) remains {"action": "invalid"} — a format
# correction, exactly as today.
#
# Cycle 5 C5-A1 (2026-10-22): the Cycle 4 phase-path store recorded
# a further markup family the Cycle 3 bridge does not reach — 13 of
# its 16 still-dead responses (plan 5, tasks 8). The payload is
# SPLIT across two objects: a complete header object carrying the
# kind with an UNQUOTED value ({"function": shell}), then a second
# object opening the payload field ({"command":) whose value is
# RAW text — never a quoted JSON string — running to the family's
# recorded terminations: the stray-tag tail (</parameter>
# </function> </tool_call>, 11 of 13), a final '"}' before
# </tool_call> (1), or a final '"}' at the end of the response with
# no closing tag at all (1). Neither strict parsing (the header's
# unquoted value defeats it) nor the envelope rule (which requires
# the field value to open with a quote) reaches this shape.
# _split_payload_action below recovers exactly it, under the same
# structural assumption the envelope rule already makes: inside
# this markup the stray closing tags are structural, never payload
# content. A split payload with no termination stays dead. The
# other two Cycle 4 dead classes are NOT this family and stay dead
# by design: prose-prefixed bare JSON (the family Cycle 3
# adjudicated out of the bridge's scope, pinned in
# tests/test_cycle3.py) and a truncated response with no payload
# at all.
_TOOL_CALL_OPEN = "<tool_call>"
_TOOL_CALL_CLOSE = "</tool_call>"
# Stray closing tags the recorded markup leaves after the payload
# object (inside or instead of </tool_call>).
_STRAY_SEGMENT_TAGS = ("</parameter>", "</function>", "</invoke>",
                       "</command>", "</arguments>", "</name>")


def _payload_to_action(payload):
    """One recorded native payload -> the JSON path's action dict.

    Accepts the two recorded key styles (``action`` and
    ``function``); a function-keyed payload is re-keyed to
    ``action`` with every other field preserved. Validation is the
    JSON path's own: the kind must be shell or done, and a shell
    action's command must be a string. Returns None when the
    payload is not an executable action of either style."""
    if not isinstance(payload, dict):
        return None
    if "action" in payload:
        action = dict(payload)
    elif "function" in payload:
        action = {"action": payload.get("function")}
        action.update({k: v for k, v in payload.items() if k != "function"})
    else:
        return None
    if action.get("action") not in ("shell", "done"):
        return None
    if action["action"] == "shell" and not isinstance(action.get("command"), str):
        return None
    return action


def _first_json_object(segment):
    """The first JSON object in a markup segment, parsed strictly.

    raw_decode stops at the object's closing brace, so stray
    closing tags trailing the payload are ignored by construction.
    Returns None when no strict object parses (the recorded
    unescaped-inner-quotes family lands here)."""
    start = segment.find("{")
    if start < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(segment[start:])
    except ValueError:
        return None
    return obj


def _strip_stray_segment_tail(segment):
    """Remove trailing stray closing tags (and whitespace) the
    recorded markup leaves after the payload object."""
    text = segment.strip()
    changed = True
    while changed:
        changed = False
        for tag in _STRAY_SEGMENT_TAGS + (_TOOL_CALL_CLOSE,):
            if text.endswith(tag):
                text = text[: -len(tag)].strip()
                changed = True
    return text


def _envelope_action(segment):
    """Recover an action whose payload defeats strict JSON parsing
    because the command/summary text contains unescaped quotes.

    The recorded envelope is fixed: an opening brace, the kind key
    (``action`` or ``function``) naming shell/done, then the field
    key (``command`` for shell, ``summary`` for done) opening a
    string. Two recorded terminations for the field value:

    - the payload's final '"}' (the value is everything between the
      opening quote and that final quote-brace — deterministic, and
      the only reading the envelope admits), or
    - a markup closing tag where the closing quote/brace should be:
      the records close the command field with a literal
      ``</command>`` (and, in the Cycle 1 store, run the value
      straight into the stray ``</parameter>``/``</function>``/
      ``</invoke>`` tail). Inside this markup those tags are
      structural, never payload content, so the value runs to the
      first of them.

    A segment with neither termination (the value runs off the end
    of the response) is truncated and is NOT recovered (returns
    None), nor is a segment whose kind/field envelope never opens."""
    field_anchor = re.search(r'"(command|summary)"\s*:\s*"', segment)
    if field_anchor is None:
        return None
    field = field_anchor.group(1)
    # One recorded payload writes the kind with an equals sign in
    # place of the key's closing quote and colon —
    # {"function="shell","command":...} — so the key's closing
    # quote is optional and the separator is ':' or '='. Nothing
    # else about the envelope varies.
    kind_match = re.search(r'"(?:action|function)"?\s*[:=]\s*"?(shell|done)"',
                           segment[: field_anchor.start()])
    if kind_match is None:
        return None
    kind = kind_match.group(1)
    if (kind == "shell") != (field == "command"):
        return None
    stripped = _strip_stray_segment_tail(segment)
    if stripped.startswith("{") and stripped.endswith('"}'):
        anchor = re.search(r'"' + field + r'"\s*:\s*"', stripped)
        if anchor is not None:
            return {"action": kind, field: stripped[anchor.end(): -2]}
    rest = segment[field_anchor.end():]
    ends = [rest.find(tag) for tag in _STRAY_SEGMENT_TAGS]
    ends = [e for e in ends if e >= 0]
    if not ends:
        return None
    value = rest[: min(ends)].rstrip()
    if not value:
        return None
    return {"action": kind, field: value}


_SPLIT_HEADER_RE = re.compile(
    r'\s*\{\s*"(?:action|function)"\s*:\s*"?(shell|done)"?\s*\}'
    r'\s*\{\s*"(command|summary)"\s*:\s?')


def _split_payload_action(segment):
    """Cycle 5 C5-A1: recover the Cycle 4 phase path's split-payload
    markup family. The segment opens with a complete header object
    naming the kind (``action``/``function`` key, quoted or unquoted
    shell/done value), immediately followed by a second object that
    opens the payload field (``command`` for shell, ``summary`` for
    done); the field's value is the raw remainder — it is never a
    quoted JSON string in this family. Terminations, mirroring the
    envelope rule's: the first stray closing tag (structural inside
    this markup, never payload content), else a final '"}' at the
    end of the segment. No termination, a kind/field mismatch, or
    an empty value returns None — the response stays dead."""
    match = _SPLIT_HEADER_RE.match(segment)
    if match is None:
        return None
    kind, field = match.group(1), match.group(2)
    if (kind == "shell") != (field == "command"):
        return None
    rest = segment[match.end():]
    ends = [rest.find(tag) for tag in _STRAY_SEGMENT_TAGS]
    ends = [e for e in ends if e >= 0]
    if ends:
        value = rest[: min(ends)].rstrip()
    else:
        value = rest.rstrip()
        if value.endswith('"}'):
            value = value[: -2].rstrip()
        else:
            return None
    if not value:
        return None
    return {"action": kind, field: value}


def parse_native_tool_call(text):
    """Parse the first recorded native <tool_call> segment in a
    response into the JSON path's action dict, or None.

    The segment runs from the first ``<tool_call>`` to its
    ``</tool_call>`` when one is present, else to the end of the
    response (the Cycle 1 store's dominant closing forms omit
    ``</tool_call>`` entirely). Prose before the segment is ignored,
    exactly as the recorded responses present it."""
    if not isinstance(text, str):
        return None
    start = text.find(_TOOL_CALL_OPEN)
    if start < 0:
        return None
    segment = text[start + len(_TOOL_CALL_OPEN):]
    end = segment.find(_TOOL_CALL_CLOSE)
    if end >= 0:
        segment = segment[:end]
    action = _payload_to_action(_first_json_object(segment))
    if action is not None:
        return action
    action = _envelope_action(segment)
    if action is not None:
        return action
    return _split_payload_action(segment)


def parse_model_action(text):
    """The plain-loop adapter's full parse: the frozen JSON path
    first (byte-for-byte its original rule), then the Cycle 3
    native-format bridge, then invalid — a format correction,
    exactly as a response parseable by neither path behaved before
    the bridge."""
    try:
        action = json.loads(text)
        if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
            raise ValueError("expected shell or done")
        if action["action"] == "shell" and not isinstance(action.get("command"), str):
            raise ValueError("shell command must be string")
        return action
    except (ValueError, TypeError):
        pass
    bridged = parse_native_tool_call(text)
    if bridged is not None:
        return bridged
    return {"action": "invalid"}


# C-4 (Benchmarking Improvement Program, 2026-10-25): the
# residual transform applies per phase class only where replay
# evidence shows it saving. The Phase 2 replay measured specify,
# plan and tasks on recorded Stage B traffic (savings 83.8% /
# 79.8% / 57.7%); the probe path's solve class carries the probe
# test's own live measurement. Every other class abstains by
# default — its views are the plain assembled views — until it
# is measured; a freeze config may opt classes in explicitly
# with residual_phases (the list then replaces this default).
RESIDUAL_MEASURED_PHASES = frozenset(
    {"specify", "plan", "tasks", "solve"})


# B-2's gate-loop budget, ratified default value (Defaults
# Tournament, 2026-10-26): the separate sub-budget for
# assessment-gate resubmission churn, in calls. The tournament's
# kill rule would have removed the mechanism on its zero corpus
# main effect; the protective-mechanism carve-out retained it —
# the failure mode it bounds is real (the October attempt that
# motivated B-2, and the adversarial infinite-resubmission
# stream, which terminates on a budget of 6–8 against this
# default), its unbounded cost is a whole phase, and its
# carrying cost is one config key. Freezes carry the key
# explicitly (gate_loop_budget_calls); this constant is the
# ratified value a freeze adopts, and the drift pins hold it.
# execute_attempt's key-absent semantics are unchanged: no key,
# no gate budget (the pre-B-2 behavior, pinned by the B-2
# control test).
GATE_LOOP_BUDGET_DEFAULT_CALLS = 20


class MiniModel:
    """mini's Model protocol with observable requests and explicit JSON actions."""
    def __init__(self, provider, deadline, call_timeout=FRONTIER_CALL_TIMEOUT_SECONDS,
                 cfg=None):
        self.provider, self.deadline, self.call_timeout = provider, deadline, call_timeout
        self.phase, self.last = None, None
        self.cfg = cfg
        # Cycle 2 C2-F2: phase -> {"workspace_path", "sha256",
        # "store_path"} for phases this attempt has completed,
        # recorded by execute_attempt at each phase completion. The
        # assembled view externalizes earlier phases' authored turns
        # to exactly this identity.
        self.phase_artifacts = {}
        # Residual protocol (2026-10-24, probe path; 2026-10-25,
        # workflow path): the synchronized-state session, created
        # lazily on the first query when the freeze config carries
        # residual_protocol, and re-anchored at every phase change
        # (see query()). None (and never created) in every other
        # configuration.
        self._residual = None
        self._residual_phase = None

    def _residual_applies(self):
        """C-4 abstain rule: the transform applies to this
        model's current phase class only when the class is
        measured (RESIDUAL_MEASURED_PHASES) or the freeze
        config's residual_phases list opts it in."""
        if self.phase is None:
            return True
        opted = (self.cfg or {}).get("residual_phases")
        if opted is not None:
            return self.phase in opted
        return self.phase in RESIDUAL_MEASURED_PHASES

    def query(self, messages):
        cleaned = [{"role": m["role"], "content": m["content"]} for m in messages]
        if self.cfg is not None:
            # Cycle 1 C1-b/C1-a + Cycle 2 C2-F2: the assembled history
            # is measured in full, then the combined view is built —
            # earlier phases' authored turns externalized to their
            # artifact identities, older observations masked — a
            # read-time view (the agent's own history is untouched)
            # so the history actually sent fits the frozen wire cap
            # whenever the combined remainder fits. The stats travel
            # to the provider, which records assembled and wire sizes
            # — and, when even the combined remainder exceeds the
            # cap, the named unmaskable_remainder_over_cap flag — on
            # the call event.
            if self.cfg.get("residual_protocol") \
                    and self._residual_applies():
                # Probe-path residual protocol (2026-10-24): the
                # synchronized shared state replaces full-history
                # resends — the brief and each step cross in full
                # exactly once, later calls carry a state block
                # (brief by reference, problem statement verbatim,
                # step index with digests) plus the newest step as
                # the delta. The session verifies sender/receiver
                # digest sync before every send and raises an
                # integrity error on any divergence. Identical
                # stats shape; everything downstream is unchanged.
                if self._residual is None \
                        or self.phase != self._residual_phase:
                    # Re-anchor at a phase boundary (Benchmarking
                    # Improvement Program C-1, 2026-10-25): the
                    # workflow driver edits its history when a
                    # phase completes — the phase's terminal action
                    # is replaced by its artifact record — so a
                    # session carried across the boundary would
                    # meet a history it never transmitted and raise
                    # a divergence. The boundary view is the new
                    # segment's genesis, and the fresh session
                    # indexes from there. On the probe path the
                    # phase never changes inside an attempt, so
                    # this remains the original single session,
                    # byte-identical.
                    #
                    # The genesis is transmitted with preamble
                    # suppression (Defaults Tournament F1, ratified
                    # 2026-10-26): system text in full, the problem
                    # statement verbatim, every other standing brief
                    # message as a digest reference line — the form
                    # the tournament's factorial priced at 250,829
                    # sent tokens below the unsuppressed genesis
                    # over the campaign corpus. This wiring default
                    # is the ratified default stack (see
                    # docs/default-stack.md); a freeze config
                    # carrying genesis_preamble_suppression: false
                    # restores the unsuppressed genesis, paid in
                    # full once exactly as the uncompressed path
                    # sends it, byte-for-byte.
                    self._residual = ResidualSession(
                        store=getattr(self.provider, "store", None),
                        identity=getattr(self.provider, "identity", None),
                        genesis_suppression=bool(
                            self.cfg.get(
                                "genesis_preamble_suppression", True)))
                    self._residual_phase = self.phase
                result = self._residual.view(
                    cleaned, int(self.cfg["max_input_tokens"]),
                    current_phase=self.phase,
                    recent_k=int(self.cfg.get("observation_mask_recent_k",
                                               OBSERVATION_MASK_RECENT_K)),
                    artifact_registry=self.phase_artifacts,
                    excerpt_chars=int(self.cfg.get("authored_turn_excerpt_chars",
                                                   AUTHORED_TURN_EXCERPT_CHARS)),
                    phase=self.phase)
            else:
                result = assemble_history(
                    cleaned, int(self.cfg["max_input_tokens"]),
                    current_phase=self.phase,
                    recent_k=int(self.cfg.get("observation_mask_recent_k",
                                               OBSERVATION_MASK_RECENT_K)),
                    artifact_registry=self.phase_artifacts,
                    excerpt_chars=int(self.cfg.get("authored_turn_excerpt_chars",
                                                   AUTHORED_TURN_EXCERPT_CHARS)))
            self.provider.context_stats = {
                "assembled_tokens": result.assembled_tokens,
                "sent_tokens": result.sent_tokens,
                "observations_masked": result.masked_count,
                "authored_turns_externalized": result.externalized_count,
                "unmaskable_remainder_over_cap": result.unmaskable_remainder_over_cap}
            cleaned = result.messages
        # C2-F1: name the binding deadline for the provider. When
        # the wall remainder is the smaller bound, the per-call
        # deadline IS the attempt wall: its expiry mid-call is a
        # scored wall expiry, not a transport timeout.
        wall_remaining = remaining(self.deadline)
        timeout = min(wall_remaining, self.call_timeout)
        try:
            self.provider.call_deadline_kind = (
                "attempt_wall" if wall_remaining <= self.call_timeout else "per_call")
        except AttributeError:
            pass
        text = self.provider.query(cleaned, self.phase, timeout)
        # Cycle 3 C3-F1: parse_model_action is the frozen JSON rule,
        # then the native-format bridge, then invalid (see above).
        action = parse_model_action(text)
        self.last = action
        return {"role": "assistant", "content": text,
                "extra": {"actions": [action] if action["action"] == "shell" else []}}

    def format_observation_messages(self, message, outputs, template_vars):
        if self.last["action"] == "invalid":
            return [{"role": "user", "content": 'Return one JSON object: {"action":"shell","command":"..."} or {"action":"done","summary":"..."}.'}]
        return [{"role": "user", "content": json.dumps(o)} for o in outputs]

    def get_template_vars(self):
        return {}


class MiniEnvironment:
    def __init__(self, sandbox, deadline, store, identity, cfg=None):
        self.sandbox, self.deadline, self.store, self.identity = sandbox, deadline, store, identity
        self.tool_calls = 0
        self.phase = None
        self.cfg = cfg or {}
        # Window 4 token-router wiring: per-environment router
        # verification state (the pinned tool is verified once, on
        # this environment's first routed observation). Window 7:
        # the same state dict carries the capped-digest registry
        # for explicit retrieval. Inert — never read — unless the
        # freeze carries token_router: true.
        self._router_state = {"verified": False}

    def execute(self, action):
        self.tool_calls += 1
        # Window 7 explicit retrieval (freeze keys token_router +
        # the delivery-cap pair): a command that is exactly
        # "retrieve-observation <digest>" for a digest this
        # environment previously delivered in capped form is
        # answered by the wiring from the digest-addressed
        # artifact — no sandbox execution and no tools event (no
        # sandbox output exists); the router stream records the
        # retrieval and its full byte charge, and the observation
        # is shaped exactly as an ordinary delivery of the same
        # text would be. Every other command — including a
        # retrieval command for an unregistered digest — falls
        # through to the ordinary path below, byte-identical.
        if self.cfg.get("token_router"):
            retrieval = try_retrieval(
                action["command"], self.store, self.cfg,
                identity=self.identity, state=self._router_state)
            if retrieval is not None:
                delivered, router_event, artifact = retrieval
                self.store.append("router", router_event)
                shaped = {"exit_code": router_event["exit_code"],
                          "stdout": delivered, "stderr": ""}
                if self.phase in DRAFTING_PHASES:
                    observation = cap_observation(
                        shaped, int(self.cfg.get(
                            "observation_write_cap_bytes",
                            OBSERVATION_WRITE_CAP_BYTES)))
                    return {**observation,
                            "evidence_ref": artifact["path"],
                            "source_id": artifact["sha256"]}
                return {**shaped, "stdout": delivered[-24000:],
                        "stderr": "",
                        "evidence_ref": artifact["path"],
                        "source_id": artifact["sha256"]}
        result = self.sandbox.execute(action["command"], timeout=min(60, remaining(self.deadline)))
        artifact = self.store.artifact(canonical({"command": action["command"], **result}))
        self.store.append("tools", {**self.identity, "timestamp": utc(), "artifact": artifact,
                                    "exit_code": result["exit_code"]})
        # Window 4 token-router wiring (freeze key token_router):
        # with the flag absent/false the statements below execute
        # on the original result untouched — no subprocess, no file
        # I/O, no router stream. With the flag on, a COPY of the
        # result is routed (the stored artifact and the tools event
        # above are always the original output) and the shaping
        # branches shape the delivered text exactly as they shape
        # raw text. The observation's evidence_ref/source_id still
        # come from the raw artifact.
        shaped = result
        if self.cfg.get("token_router"):
            shaped, router_event = route_observation(
                result, artifact, self.cfg, store=self.store,
                identity=self.identity, state=self._router_state)
            self.store.append("router", router_event)
        # Full output retained as artifact; bounded observation prevents context explosion.
        if self.phase in DRAFTING_PHASES:
            # Cycle 1 C1-A4: observations entering a construction or
            # drafting-phase history are capped at write time,
            # deterministically, with byte counts recorded on the
            # observation itself.
            observation = cap_observation(
                shaped, int(self.cfg.get("observation_write_cap_bytes",
                                         OBSERVATION_WRITE_CAP_BYTES)))
            return {**observation,
                    "evidence_ref": artifact["path"], "source_id": artifact["sha256"]}
        return {**shaped, "stdout": shaped["stdout"][-24000:], "stderr": shaped["stderr"][-8000:],
                "evidence_ref": artifact["path"], "source_id": artifact["sha256"]}

    def get_template_vars(self):
        return {}


def execute_attempt(root, task, arm, provider, sandbox, store, identity, cfg, manifest=None):
    # Matched-repair arms run the ported paired protocol, not the mini-SWE-agent
    # phase workflow. The import is deferred to avoid a module cycle.
    from .matched_repair import MATCHED_ARMS, execute_matched_attempt
    if arm in MATCHED_ARMS:
        return execute_matched_attempt(root, task, arm, provider, sandbox, store, identity, cfg, manifest)
    # mini imports a global .env at import time; replace its discovery root first.
    global_config = Path(tempfile.mkdtemp(prefix="mini-clean-config-"))
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_config)
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    from minisweagent.agents.default import DefaultAgent
    shutil.rmtree(global_config)
    if arm != "baseline":
        sandbox.stage_workflow(root)
    deadline = time.monotonic()+attempt_wall_seconds(cfg)
    model = MiniModel(provider, deadline, workflow_call_timeout_seconds(cfg), cfg=cfg)
    environment = MiniEnvironment(sandbox, deadline, store, identity, cfg=cfg)
    agent = DefaultAgent(model, environment, system_template="", instance_template="", cost_limit=0)
    # Stage A H3: a freeze may carry ``solve_instruction_path``
    # (root-relative); its file text then replaces the baseline
    # solve prompt as the initial system content. Absent the key,
    # the phase_prompt result is used unchanged.
    solve_instruction = phase_prompt(root, "baseline", "solve")
    if cfg.get("solve_instruction_path"):
        solve_instruction = (Path(root) / cfg["solve_instruction_path"]).read_text(
            encoding="utf-8")
    agent.add_messages({"role": "system", "content": solve_instruction},
                       {"role": "user", "content": task["problem_statement"]})
    outcome, gate_outcome, repairs = None, None, 0
    # Cycle 1 C1-c: force-advance drafting phases already completed
    # (their unspent envelope rolls forward into later envelopes).
    drafting_completed = set()
    # Cycle 5 C5-F1: set to the recorded advance event when the
    # drafting sub-cap exhausts; remaining drafting phases are then
    # skipped and the attempt proceeds to implementation on the
    # reserved remainder.
    drafting_force_advanced = None
    # B-2 (2026-10-25): phases whose assessment-gate loop ended on
    # its own budget (freeze-configured gate_loop_budget_calls);
    # the attempt proceeds past such a phase with the artifacts
    # that exist, and the exhaustion is recorded per phase.
    gate_loop_exhausted = []
    # Stage A scaffold state: the H1 kinds that already fired this
    # attempt (each fires at most once), and whether the H2
    # empty-patch gate already fired this attempt (it fires once).
    scaffold_fired = set()
    empty_patch_gate_fired = False

    def record_scaffold_event(kind, phase, step_index, phase_charged, fired_by):
        """Stage A: record one scaffold firing on the
        ``scaffold_events`` stream — attempt identity, phase, the
        step index and phase charged tokens read from the calls
        ledger at firing time, and which budget measure fired."""
        event = {**identity, "kind": kind, "phase": phase, "timestamp": utc(),
                 "step_index": step_index,
                 "phase_charged_tokens": phase_charged,
                 "fired_by": fired_by}
        store.append("scaffold_events", event)
        return event

    def record_drafting_force_advance(phase, calls):
        """C5-F1: record the drafting force-advance event for the
        phase the sub-cap caught, carrying the artifacts that exist
        at the advance — every completed drafting phase's registered
        artifact identity, plus the caught phase's partial draft,
        which lives in the shared workspace implementation reads."""
        event = {**identity, "phase": phase, "timestamp": utc(),
                 "drafting_force_advanced": True,
                 "drafting_tokens_at_advance": drafting_tokens_used(calls, cfg),
                 "drafting_sub_cap_tokens": drafting_sub_cap_tokens(cfg),
                 "artifact_carried": {
                     "completed_phases": {
                         p: model.phase_artifacts[p]
                         for p in sorted(drafting_completed)
                         if p in model.phase_artifacts},
                     "partial_phase": phase,
                     "partial_workspace": "/workflow"}}
        store.append("phases", event)
        return event
    # Workstream A2/A3 state: the standing claims bundle for this
    # attempt (later assessed phases and repair rounds submit deltas
    # merged into it), a pending over-cap candidate awaiting its one
    # consolidation revision, and the phases already asked to
    # consolidate (never more than one request per phase).
    standing_bundle, pending_candidate = None, None
    consolidation_requested = set()
    # PC-3: with campaign setup sharing enabled, the constitution
    # phase is executed once per campaign and task and its frozen
    # completion record is reused by later attempts in either Spec
    # Kit arm, which then issue zero setup calls.
    share_setup = bool(cfg.get("share_campaign_setup"))
    setup_key = task.get("instance_id") or identity.get("task_id")
    # Amendment 1 R-A3: set when the phase guard ends this attempt;
    # the patch is then extracted and graded as it stands.
    phase_exhausted = None
    for phase in phases(arm):
        if drafting_force_advanced is not None and phase in FORCE_ADVANCE_PHASES:
            # C5-F1: the drafting sub-cap already advanced this
            # attempt to implementation; no further drafting phase
            # is entered (or charged) after the advance.
            continue
        model.phase = phase
        environment.phase = phase
        # Cycle 2 C2-F1: this phase's wall clock starts when the
        # phase starts; the per-phase wall bound is checked on the
        # same loop cadence as the token envelope below.
        phase_started = time.monotonic()
        # Cycle 1 C1-c: this phase's one reserved finalize call, spent
        # only if its envelope expires before it completes.
        finalize_attempted = False
        prompt = phase_prompt(root, arm, phase)
        if arm == "spec_kit_aee" and phase in AEE_PHASES:
            prompt += claims_instruction(root, delta=standing_bundle is not None)
        if share_setup and phase == "constitution" and arm != "baseline":
            frozen = campaign_setup(store, setup_key)
            if frozen is not None:
                record = frozen.get("record") or {}
                summary = record.get("summary") if isinstance(record, dict) else None
                # Amendment 1 R-A1: a construction-produced setup also
                # freezes the constitution workspace; place it into
                # this attempt's workspace and verify the constitution
                # file against the frozen hash before reuse.
                placed = place_construction_workspace(sandbox, store, frozen)
                agent.add_messages({"role": "user", "content": f"Current phase: {phase}\n{prompt}"},
                                   {"role": "user", "content":
                                    "Campaign setup (constitution) was frozen once for this task "
                                    "and is reused; no new setup calls are made for it. "
                                    "Frozen setup record: "+json.dumps(summary or record)})
                store.append("phases", {**identity, "phase": phase, "timestamp": utc(),
                                        "artifact": frozen["artifact"], "setup_reused": True,
                                        "setup_source_attempt_id": frozen["attempt_id"],
                                        **placed})
                # C2-F2: register the reused phase's artifact
                # identity so later phases' assembled views
                # externalize this phase's authored turns to it.
                model.phase_artifacts[phase] = {
                    "workspace_path": f"/workflow/{CONSTITUTION_PATH}",
                    "sha256": (frozen.get("constitution_file") or {}).get(
                        "sha256") or frozen["artifact"]["sha256"],
                    "store_path": frozen["artifact"]["path"]}
                continue
        agent.add_messages({"role": "user", "content": f"Current phase: {phase}\n{prompt}"})
        recovery = 0
        # B-2 (2026-10-25): the assessment-gate loop budget state,
        # per phase. Inert unless the freeze config carries
        # gate_loop_budget_calls (see the loop-top accounting).
        gate_loop_budget = cfg.get("gate_loop_budget_calls")
        gate_spent = 0
        gate_open_at = None
        productive_calls = None
        while True:
            if (store.root/"CANCEL").exists():
                raise KeyboardInterrupt
            remaining(deadline)
            calls = [c for c in store.events("calls") if c["attempt_id"] == identity["attempt_id"]]
            # Unknown-usage calls (failed physical requests) are charged
            # their full reservation, so the ceiling stays enforceable; a
            # transient provider failure never kills the attempt here.
            used = attempt_token_usage(calls, cfg)
            # Amendment 1 R-A3: the phase guard, read from the same
            # calls ledger — a harness-side fact, never an inference
            # about the model. Tripping ends the phase and, because
            # every guarded phase's artifact is consumed downstream,
            # the attempt; the patch is graded as it stands.
            # Cycle 1 C1-c: a force-advance drafting phase whose
            # envelope expires does not die here — it spends its one
            # reserved finalize call to emit the phase artifact from
            # the current draft state, and the attempt proceeds. Only
            # if that call fails to emit the artifact does the phase
            # end with the existing exhaustion classification.
            phase_calls = [c for c in calls if c.get("phase") == phase]
            # B-2 (2026-10-25): gate-loop accounting, read from the
            # same calls ledger. A gate iteration opens when a
            # claims submission is rejected or the gate blocks and
            # sends the model back to repair; every call after the
            # first opening is a gate-loop call (the step loop only
            # continues through gate iterations once a submission
            # exists), so the productive prefix of the phase's calls
            # is fixed at the first opening. Gate-loop calls draw on
            # gate_loop_budget_calls, never on the phase guard: the
            # guard below reads the productive prefix only. The
            # attempt cap and the drafting envelope are unchanged —
            # they keep counting every call. When the key is absent
            # from the freeze config, none of this runs and the
            # recorded semantics are bit-for-bit the pre-B-2 ones.
            if gate_loop_budget is not None:
                if gate_open_at is not None:
                    gate_spent = len(phase_calls) - gate_open_at
                if gate_spent >= int(gate_loop_budget):
                    store.append("phases", {
                        **identity, "phase": phase,
                        "kind": "gate_loop_exhausted",
                        "gate_calls": gate_spent,
                        "gate_loop_budget_calls": int(gate_loop_budget),
                        "timestamp": utc()})
                    gate_loop_exhausted.append(phase)
                    break
            guard_calls = phase_calls if productive_calls is None \
                else phase_calls[:productive_calls]
            # Cycle 5 C5-F1: the drafting reserve is checked before
            # every other phase bound — it is the attempt-level
            # bound that funds implementation. On exhaustion the
            # attempt force-advances: no finalize call is spent
            # (that would spend the reserve), the phase's partial
            # artifacts carry, and the advance is recorded. This is
            # not phase_budget_exhausted; that classification keeps
            # its existing semantics below.
            if phase in FORCE_ADVANCE_PHASES and drafting_force_advanced is None \
                    and drafting_sub_cap_tripped(calls, cfg):
                drafting_force_advanced = record_drafting_force_advance(
                    phase, calls)
                break
            # Cycle 2 C2-F1: the per-phase wall bound, handled
            # exactly as a token-envelope expiry — a force-advance
            # phase spends its reserved finalize call; any other
            # guarded drafting phase ends exhausted.
            wall_tripped = phase_wall_tripped(
                phase, time.monotonic() - phase_started, cfg)
            if phase in FORCE_ADVANCE_PHASES and not finalize_attempted:
                if drafting_envelope_tripped(phase, calls, cfg, len(drafting_completed)) \
                        or wall_tripped:
                    finalize_attempted = True
                    agent.add_messages({"role": "user", "content":
                                        FINALIZE_INSTRUCTION})
            elif phase_guard_tripped(arm, phase, guard_calls, cfg) or wall_tripped:
                phase_exhausted = phase
                break
            # Stage A H1 phase-forcing (plain loop only): freeze-
            # configured fractions of the phase's step/token budgets,
            # checked on the same loop cadence and the same calls
            # ledger as the envelope checks above. The edit switch is
            # checked first; the verify nudge fires only once the
            # switch has fired (including at this same step). Keys
            # absent -> nothing here runs and behavior is unchanged.
            if phase == "solve":
                phase_charged = attempt_token_usage(phase_calls, cfg)
                steps_done = len(phase_calls)
                if "edit_switch_fraction" in cfg \
                        and "edit_switch" not in scaffold_fired:
                    fired_by = scaffold_threshold_fired_by(
                        steps_done, phase_charged,
                        float(cfg["edit_switch_fraction"]), cfg)
                    if fired_by is not None:
                        scaffold_fired.add("edit_switch")
                        record_scaffold_event(
                            "edit_switch", phase, steps_done, phase_charged,
                            fired_by)
                        agent.add_messages(
                            {"role": "user", "content": EDIT_SWITCH_INSTRUCTION})
                if "verify_nudge_fraction" in cfg \
                        and "edit_switch" in scaffold_fired \
                        and "verify_nudge" not in scaffold_fired:
                    fired_by = scaffold_threshold_fired_by(
                        steps_done, phase_charged,
                        float(cfg["verify_nudge_fraction"]), cfg)
                    if fired_by is not None:
                        scaffold_fired.add("verify_nudge")
                        record_scaffold_event(
                            "verify_nudge", phase, steps_done, phase_charged,
                            fired_by)
                        agent.add_messages(
                            {"role": "user", "content": VERIFY_NUDGE_INSTRUCTION})
            if used+cfg["max_input_tokens"]+cfg["max_output_tokens"] > cfg["token_cap"]:
                raise LimitHit("next request token reservation exceeds attempt cap")
            if agent.n_calls >= cfg["max_calls"]:
                raise LimitHit("call limit")
            try:
                agent.step()
            except ProviderError as exc:
                if not finalize_attempted:
                    raise
                # The reserved finalize call itself failed: the phase
                # ends with the existing exhaustion classification.
                # Transport stalls, the outer bound, and (C2-F1) an
                # attempt-wall expiry keep their own named semantics
                # and are never reclassified here.
                if isinstance(exc, (TransportStallError, CallOuterBoundError,
                                    AttemptWallExpiredError)):
                    raise
                calls_now = [c for c in store.events("calls")
                             if c["attempt_id"] == identity["attempt_id"]]
                if phase in FORCE_ADVANCE_PHASES \
                        and drafting_sub_cap_tripped(calls_now, cfg):
                    # C5-F1: the failed finalize call was itself the
                    # spend that exhausted the drafting sub-cap — the
                    # outcome is the drafting force-advance, not
                    # phase exhaustion.
                    drafting_force_advanced = record_drafting_force_advance(
                        phase, calls_now)
                    break
                phase_exhausted = phase
                break
            if finalize_attempted and model.last["action"] != "done":
                # The reserved finalize call did not emit the phase
                # artifact: the phase ends with the existing
                # exhaustion classification — no retry loops. C5-F1:
                # unless that call exhausted the drafting sub-cap,
                # in which case the attempt force-advances to
                # implementation instead of ending exhausted.
                calls_now = [c for c in store.events("calls")
                             if c["attempt_id"] == identity["attempt_id"]]
                if phase in FORCE_ADVANCE_PHASES \
                        and drafting_sub_cap_tripped(calls_now, cfg):
                    drafting_force_advanced = record_drafting_force_advance(
                        phase, calls_now)
                    break
                phase_exhausted = phase
                break
            if model.last["action"] != "done":
                continue
            # Stage A H2 empty-patch gate: on the natural-done
            # completion path only (never on finalize/exhaustion/
            # wall paths, which never reach this point), a freeze
            # carrying ``empty_patch_gate`` rejects a first empty
            # submission: the current diff is extracted exactly as
            # the final patch extraction does, and when it is empty
            # the gate records its event, injects the retry
            # instruction, and the phase continues without recording
            # a completion. A non-empty diff, or the gate already
            # fired once this attempt, proceeds unchanged — a second
            # empty done completes and scores empty.
            if phase == "solve" and cfg.get("empty_patch_gate") \
                    and not empty_patch_gate_fired:
                gate_patch = sandbox.execute(
                    "git add -N . && git diff --binary HEAD",
                    min(60, remaining(deadline)))
                if gate_patch["exit_code"]:
                    raise RuntimeError("patch extraction failed")
                if not gate_patch["stdout"]:
                    empty_patch_gate_fired = True
                    calls_now = [c for c in store.events("calls")
                                 if c["attempt_id"] == identity["attempt_id"]]
                    gate_phase_calls = [c for c in calls_now
                                        if c.get("phase") == phase]
                    record_scaffold_event(
                        "empty_patch_gate", phase, len(gate_phase_calls),
                        attempt_token_usage(gate_phase_calls, cfg), None)
                    agent.add_messages(
                        {"role": "user", "content": EMPTY_PATCH_GATE_INSTRUCTION})
                    continue
            # Phase completion artifacts are explicit and retained, not inferred from prose.
            artifact = store.artifact(canonical(model.last))
            store.append("phases", {**identity, "phase": phase, "timestamp": utc(),
                                    "artifact": artifact,
                                    **({"force_advanced": True} if finalize_attempted else {})})
            # Cycle 2 C2-F2: register this phase's artifact identity
            # (workspace path + hash) so later phases' assembled
            # views replace this phase's authored turns with it.
            model.phase_artifacts[phase] = {
                "workspace_path": (
                    f"/workflow/{CONSTITUTION_PATH}" if phase == "constitution"
                    else extract_workspace_path(json.dumps(model.last, sort_keys=True))),
                "sha256": artifact["sha256"],
                "store_path": artifact["path"]}
            if phase in FORCE_ADVANCE_PHASES:
                drafting_completed.add(phase)
            if share_setup and phase == "constitution" and campaign_setup(store, setup_key) is None:
                # Freeze the setup outcome once per campaign and task (PC-3).
                store.append("campaign_setups", {**identity, "setup_key": setup_key,
                                                 "artifact": artifact, "record": model.last,
                                                 "timestamp": utc()})
            if arm != "spec_kit_aee" or phase not in AEE_PHASES:
                break
            # Workstream A2: resolve this completion's submission
            # against the standing bundle — a full bundle on the
            # first assessed phase, a delta (merged here) on every
            # later assessed phase and repair round. A malformed
            # submission is a model outcome: the reason is fed back
            # inside this phase's step flow and the model resubmits;
            # it never escapes as a harness error.
            base = pending_candidate if pending_candidate is not None else standing_bundle
            try:
                candidate = resolve_claim_submission(base, model.last.get("claims") or {})
            except DeltaFormatError as exc:
                if gate_loop_budget is not None and gate_open_at is None:
                    if productive_calls is None:
                        productive_calls = len(phase_calls) + 1
                    gate_open_at = len(phase_calls) + 1
                agent.add_messages({"role": "user", "content":
                    f"Claims submission rejected: {exc}. Resubmit this phase's completion "
                    "with a well-formed submission: the first assessed phase takes a full "
                    "claims bundle; later phases and repair rounds take a delta (changed or "
                    "new claims as full claim objects under \"delta.upsert\", withdrawals "
                    "by claim id under \"delta.withdraw\")."})
                continue
            # Workstream A3(b): one consolidation request per phase
            # when the to-be-assessed bundle exceeds the soft cap;
            # the model revises within the same phase before any
            # assessment runs.
            if (len(candidate.get("claims") or []) > CLAIM_SOFT_CAP
                    and phase not in consolidation_requested):
                consolidation_requested.add(phase)
                pending_candidate = candidate
                agent.add_messages({"role": "user", "content":
                    f"Consolidation requested: this phase's claims bundle has "
                    f"{len(candidate['claims'])} claims, above the soft cap of "
                    f"{CLAIM_SOFT_CAP}. Before assessment, consolidate within this "
                    "phase: merge duplicate claims, keep one claim per independently "
                    "falsifiable requirement, and prefer few, load-bearing claims. "
                    "Resubmit a revised full bundle. This request is made once per phase."})
                continue
            pending_candidate = None
            claims = grounded_claims(candidate, store, identity["attempt_id"])
            result = assess(root, claims, phase, store, identity["attempt_id"])
            standing_bundle = candidate
            outcome = result["outcome"]
            # PC-2: gate eligibility follows lane 1 (machine
            # verification), not the blended headline outcome.
            gate_outcome = gate_outcome_of(result)
            # Workstream A1: only the compact projection enters the
            # persistent conversation; the full composed result
            # remains in the run store (assessments record) for audit.
            agent.add_messages({"role": "user", "content": "AEE/Evaluator result: "+json.dumps(compact_feedback(result))})
            if gate_outcome in ("pass", "warn"):
                break
            if gate_outcome == "block" or recovery >= cfg["max_recovery_rounds"]:
                # Preserve the patch and assessment for independent post-run disagreement analysis.
                patch = sandbox.execute("git add -N . && git diff --binary HEAD", min(60, remaining(deadline)))
                return {"patch": store.artifact(patch["stdout"].encode()), "assessment_outcome": gate_outcome,
                        "assessment_headline_outcome": outcome,
                        "repair_count": repairs, "tool_calls": environment.tool_calls, "blocked": True}
            if finalize_attempted:
                # A force-advanced phase ends after its one artifact
                # and its assessment; recovery rounds belong to
                # phases that completed inside their envelope.
                break
            recovery += 1
            repairs += 1
            if gate_loop_budget is not None and gate_open_at is None:
                if productive_calls is None:
                    productive_calls = len(phase_calls) + 1
                gate_open_at = len(phase_calls) + 1
            agent.add_messages({"role": "user", "content": "Address the result within this phase. Use only task-provided facts; no human assistance. Do not change model. Submit a claims delta scoped to the findings (changed claims as full claim objects under \"delta.upsert\", withdrawals by claim id under \"delta.withdraw\") with revised evidence, or retain gaps."})
        if phase_exhausted is not None:
            break
    patch = sandbox.execute("git add -N . && git diff --binary HEAD", min(60, remaining(deadline)))
    if patch["exit_code"]:
        raise RuntimeError("patch extraction failed")
    result = {"patch": store.artifact(patch["stdout"].encode()), "assessment_outcome": gate_outcome,
              "assessment_headline_outcome": outcome,
              "repair_count": repairs, "tool_calls": environment.tool_calls}
    if phase_exhausted is not None:
        result["phase_exhausted"] = phase_exhausted
    if gate_loop_exhausted:
        result["gate_loop_exhausted"] = gate_loop_exhausted
    if drafting_force_advanced is not None:
        result["drafting_force_advanced"] = drafting_force_advanced
    return result


def freeze_workspace_artifact(store, tar_bytes):
    """Freeze a /workflow tar as a store artifact. The store's
    artifact path redaction-scans content as UTF-8 text, which would
    mangle a binary tar (the first live reuse proof caught exactly
    that corruption), so the tar travels base64-encoded, bound by
    its own SHA-256, and is verified parseable before it freezes."""
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as archive:
            if not archive.getmembers():
                raise RuntimeError("construction workspace capture is empty")
    except tarfile.TarError as e:
        raise RuntimeError(f"construction workspace capture is not a valid tar: {e}")
    return {**store.artifact(base64.b64encode(tar_bytes)),
            "encoding": "base64", "tar_sha256": sha(tar_bytes)}


def read_workspace_artifact(store, workspace):
    """Inverse of freeze_workspace_artifact: returns the tar bytes,
    verified against the frozen tar hash."""
    stored = (store.root/workspace["path"]).read_bytes()
    try:
        data = base64.b64decode(stored)
    except ValueError:
        raise RuntimeError("construction workspace artifact is not valid base64")
    if sha(data) != workspace.get("tar_sha256", workspace["sha256"]):
        raise RuntimeError("construction workspace artifact hash mismatch")
    return data


def transfer_workspace_tar(sandbox, data):
    """Transfer a /workflow tar into the sandbox and extract it at
    the filesystem root (shared by setup reuse and by Cycle 1 C1-A2
    banked-construction continuation)."""
    encoded = base64.b64encode(data).decode()
    sandbox.execute("rm -rf /workflow && mkdir -p /workflow && : > /tmp/workflow.tar.b64",
                    timeout=60)
    for offset in range(0, len(encoded), 60_000):
        chunk = encoded[offset:offset+60_000]
        moved = sandbox.execute(f"printf %s '{chunk}' >> /tmp/workflow.tar.b64", timeout=60)
        if moved["exit_code"]:
            raise RuntimeError("construction workspace transfer failed")
    placed = sandbox.execute(
        "base64 -d /tmp/workflow.tar.b64 | tar -xf - -C / --no-same-owner"
        " && rm -f /tmp/workflow.tar.b64",
        timeout=60)
    if placed["exit_code"]:
        raise RuntimeError("construction workspace placement failed")


def place_construction_workspace(sandbox, store, frozen):
    """Place a construction-frozen /workflow tree into this attempt's
    sandbox (Amendment 1 R-A1) and verify the constitution file
    against its frozen hash. Returns the extra fields for the phases
    record. A setup record without a workspace artifact (the
    pre-amendment PC-3 form) places nothing and records that."""
    workspace = frozen.get("workspace_artifact")
    if not workspace:
        return {"setup_workspace": "not_recorded"}
    data = read_workspace_artifact(store, workspace)
    transfer_workspace_tar(sandbox, data)
    digest = sandbox.execute(
        f"sha256sum /workflow/{CONSTITUTION_PATH} | cut -d' ' -f1", timeout=60)
    measured = digest["stdout"].strip()
    expected = (frozen.get("constitution_file") or {}).get("sha256")
    if digest["exit_code"] or not measured or (expected and measured != expected):
        raise RuntimeError("construction constitution file hash mismatch")
    return {"setup_workspace": "placed",
            "setup_artifact_sha256": workspace.get("tar_sha256", workspace["sha256"]),
            "constitution_sha256": measured}


def capture_construction_workspace(sandbox, store):
    """Capture the sandbox's /workflow tree as a frozen store
    artifact (shared by construction completion and C1-A2 banking)."""
    captured = sandbox.execute("tar -cf - -C / workflow | base64 -w0", timeout=120)
    if captured["exit_code"] or not captured["stdout"].strip():
        raise RuntimeError("construction workspace capture failed")
    tar_bytes = base64.b64decode(captured["stdout"].strip())
    return freeze_workspace_artifact(store, tar_bytes)


def execute_construction(root, task, provider, sandbox, store, identity, cfg,
                         draw_cap=None, bank=None, installment=1):
    """Run ONE construction installment for a task (Amendment 1 R-A1
    as amended by Cycle 1 C1-A2): the constitution phase as campaign
    setup, not a scored attempt, charged to the construction identity
    (purpose campaign_setup, R-A2) under this draw's cap.

    Returns ("completed", payload) when the completion artifact is
    emitted, or ("banked", bank_record) when the draw reaches its cap
    without completing: the full state — workspace tree, assembled
    history, and a construction_banked phase record — is banked in
    the store instead of discarded, and a continuation installment
    resumes from it. Any other failure raises; the caller records it
    as a task-level premise fault (task_setup_failed, R-A4)."""
    global_config = Path(tempfile.mkdtemp(prefix="mini-clean-config-"))
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_config)
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    from minisweagent.agents.default import DefaultAgent
    shutil.rmtree(global_config)
    sandbox.stage_workflow(root)
    deadline = time.monotonic()+attempt_wall_seconds(cfg)
    model = MiniModel(provider, deadline, workflow_call_timeout_seconds(cfg), cfg=cfg)
    environment = MiniEnvironment(sandbox, deadline, store, identity, cfg=cfg)
    agent = DefaultAgent(model, environment, system_template="", instance_template="", cost_limit=0)
    phase = "constitution"
    model.phase = phase
    environment.phase = phase
    if bank is not None:
        # Resume from the banked state: the banked workspace goes
        # back into the sandbox and the banked assembled history
        # becomes this draw's starting history, verbatim — the
        # continuation's first assembled history therefore carries
        # the banked digest by construction.
        data = read_workspace_artifact(store, bank["workspace_artifact"])
        transfer_workspace_tar(sandbox, data)
        history = json.loads((store.root/bank["history_artifact"]["path"]).read_bytes())
        agent.add_messages(*history)
        if history_digest(agent.messages) != bank["history_digest"]:
            raise RuntimeError("banked construction history digest mismatch")
    else:
        agent.add_messages({"role": "system", "content": phase_prompt(root, "baseline", "solve")},
                           {"role": "user", "content": task["problem_statement"]})
        agent.add_messages({"role": "user", "content":
                            f"Current phase: {phase}\n{phase_prompt(root, 'spec_kit', phase)}"})
    cap = draw_cap if draw_cap is not None else construction_cap_tokens(cfg)
    calls_before = len([c for c in store.events("calls")
                        if c["attempt_id"] == identity["attempt_id"]])

    def draw_calls():
        calls = [c for c in store.events("calls")
                 if c["attempt_id"] == identity["attempt_id"]]
        return calls[calls_before:]

    completion = None
    while True:
        if (store.root/"CANCEL").exists():
            raise KeyboardInterrupt
        remaining(deadline)
        used = attempt_token_usage(draw_calls(), cfg)
        if used+cfg["max_input_tokens"]+cfg["max_output_tokens"] > cap:
            # C1-A2: the draw is capped without its completion
            # artifact — bank the full state instead of discarding it.
            # The banked history is the assembled form (role/content
            # only, exactly what the model assembles per call), so a
            # continuation's first assembled history carries this
            # digest verbatim.
            workspace_artifact = capture_construction_workspace(sandbox, store)
            history = [{"role": m["role"], "content": m["content"]}
                       for m in agent.messages]
            history_artifact = store.artifact(canonical(history))
            digest = history_digest(history)
            installments = list((bank or {}).get("installments") or [])
            installments.append({"installment": installment, "tokens": used})
            store.append("phases", {**identity, "phase": phase, "timestamp": utc(),
                                    "construction": True, "construction_banked": True,
                                    "installment": installment,
                                    "history_digest": digest,
                                    "draw_tokens": used})
            bank_record = {**identity, "setup_key": identity["task_id"],
                           "installment": installment,
                           "workspace_artifact": workspace_artifact,
                           "history_artifact": history_artifact,
                           "history_digest": digest,
                           "draw_tokens": used, "installments": installments,
                           "timestamp": utc()}
            store.append("construction_banks", bank_record)
            return "banked", bank_record
        if agent.n_calls >= cfg["max_calls"]:
            raise LimitHit("call limit")
        agent.step()
        if model.last["action"] == "done":
            completion = model.last
            break
    artifact = store.artifact(canonical(completion))
    store.append("phases", {**identity, "phase": phase, "timestamp": utc(),
                            "artifact": artifact, "construction": True,
                            **({"installment": installment,
                                "resumed_from_bank": True} if bank is not None else {})})
    workspace_artifact = capture_construction_workspace(sandbox, store)
    digest = sandbox.execute(
        f"sha256sum /workflow/{CONSTITUTION_PATH} | cut -d' ' -f1", timeout=60)
    if digest["exit_code"] or not digest["stdout"].strip():
        raise RuntimeError("construction constitution file missing")
    payload = {"completion": completion, "artifact": artifact,
               "workspace_artifact": workspace_artifact,
               "constitution_sha256": digest["stdout"].strip(),
               "draw_tokens": attempt_token_usage(draw_calls(), cfg)}
    return "completed", payload


def capture_transport_bundle(store, identity, cfg, reason):
    """The observability bundle Amendment 1 R-A5 requires on any
    transport halt, captured before anything is restarted: a fresh
    worker probe, the endpoint's slot/props/health state where it
    exposes them, and the worker's server-log tail where one exists
    on the harness host. Absence is recorded explicitly, never
    silently — an unobserved window must not read as an observed one."""
    bundle = {"reason": reason, "captured_at": utc(),
              "attempt_id": identity.get("attempt_id"),
              "task_id": identity.get("task_id"), "arm": identity.get("arm")}
    if local_backend(cfg):
        try:
            bundle["worker_probe"] = probe_worker(transport_policy(cfg))
        except Exception as e:  # the bundle records, never raises
            bundle["worker_probe"] = {"error": type(e).__name__}
        for route in ("/slots", "/props", "/health"):
            try:
                req = urllib.request.Request(server_root()+route, method="GET")
                with urllib.request.urlopen(req, timeout=10) as handle:
                    bundle[route] = handle.read().decode("utf-8", errors="replace")[:4000]
            except Exception as e:
                bundle[route] = {"unavailable": type(e).__name__}
    log_path = os.environ.get("LOCAL_MODEL_LOG_PATH")
    if log_path and Path(log_path).is_file():
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
        bundle["worker_log_tail"] = lines[-50:]
    else:
        bundle["worker_log_tail"] = None
        bundle["worker_log_tail_reason"] = (
            "no per-request worker log on the harness host "
            "(LOCAL_MODEL_LOG_PATH unset or file absent)")
    artifact = store.artifact(canonical(bundle))
    store.append("transport_bundles", {**identity, "artifact": artifact,
                                       "reason": reason, "timestamp": utc()})
    return artifact


def run_construction(root, task, store, cfg, manifest):
    """Execute one task's setup construction (Amendment 1 R-A1) in
    its own sandbox, under the construction identity. Returns True
    when the frozen setup record now exists. Any failure is recorded
    as a construction record plus a tripwire event carrying R-A4's
    kind (task_setup_failed, premise/equipment, admission semantics);
    a transport failure also captures the R-A5 bundle."""
    setup_key = task.get("instance_id")
    identity = {"task_id": setup_key, "arm": "spec_kit", "repeat": 1,
                "attempt_id": f"{setup_key}--campaign-setup",
                "experiment_id": manifest["freeze_id"],
                "run_id": manifest["freeze_id"][:16],
                "purpose": "campaign_setup", "construction": True}
    budget = Budget(store, cfg["global_cap_usd"], cfg["attempt_cap_usd"])
    tick, reason = time.monotonic(), None
    # Cycle 1 C1-A2: construction proceeds in installments. Each draw
    # is capped at the per-draw cap; a capped draw banks its state and
    # the next draw resumes from the bank, across at most
    # CONSTRUCTION_MAX_INSTALLMENTS draws and a per-task total on the
    # setup line. A bank already in the store (an earlier admission
    # pass in this same store) is resumed, never restarted.
    total_cap = construction_total_cap_tokens(cfg)
    max_installments = construction_max_installments(cfg)
    banks = [e for e in store.events("construction_banks")
             if e.get("setup_key") == setup_key]
    bank = banks[-1] if banks else None
    completed_payload = None
    try:
        while completed_payload is None:
            charged = attempt_token_usage(
                [c for c in store.events("calls")
                 if c["attempt_id"] == identity["attempt_id"]], cfg)
            installments_done = len((bank or {}).get("installments") or [])
            if installments_done >= max_installments or charged >= total_cap:
                raise LimitHit(
                    "campaign setup construction exhausted: "
                    f"{installments_done} installments, {charged} of "
                    f"{total_cap} construction tokens charged")
            draw_cap = min(construction_cap_tokens(cfg), total_cap - charged)
            if draw_cap <= cfg["max_input_tokens"] + cfg["max_output_tokens"]:
                raise LimitHit(
                    "campaign setup construction total budget exhausted")
            with DockerSandbox(task["image"]) as sandbox:
                check = sandbox.execute("git rev-parse HEAD && git status --porcelain")
                if check["exit_code"] or check["stdout"].strip() != task["base_commit"]:
                    raise RuntimeError("solver image does not contain a clean base checkout")
                store.append("images", {**identity, **sandbox.details})
                provider = make_provider(cfg, store, budget, identity)
                outcome, payload = execute_construction(
                    root, task, provider, sandbox, store, identity, cfg,
                    draw_cap=draw_cap, bank=bank,
                    installment=installments_done + 1)
            if outcome == "completed":
                completed_payload = payload
            else:
                bank = payload
    except (BudgetExceeded, LimitHit) as e:
        reason = str(e)
    except KeyboardInterrupt:
        raise
    except ImportError:
        # Cycle 2 test-hygiene fix (2026-10-22): an ImportError here
        # is a broken harness installation (e.g. the deferred
        # minisweagent import in execute_attempt running outside the
        # locked environment), never a property of the task, the
        # model, or the worker. Converting it into task_setup_failed
        # pre-skips scored arms and lets a study proceed on a
        # manufactured admission outcome — it is exactly how the
        # Cycle 2 F1 wall-expiry path was shadowed by a construction
        # pre-skip whenever the suite ran without the locked
        # dependencies. Fail loudly instead; no setup record, no
        # pre-skip, no scored data from a broken harness.
        raise
    except Exception as e:
        reason = error_reason(e)
    if reason is None:
        # Freeze the single registered setup record (R-A2 shape
        # preserved): its provenance lists every installment and its
        # charge, and the installment charges sum exactly to the
        # construction line, which is the sum of this identity's
        # charged calls.
        calls = [c for c in store.events("calls")
                 if c["attempt_id"] == identity["attempt_id"]]
        total_tokens = attempt_token_usage(calls, cfg)
        installments = list((bank or {}).get("installments") or [])
        installments.append({"installment": len(installments) + 1,
                               "tokens": completed_payload["draw_tokens"]})
        event = {**identity, "setup_key": setup_key,
                 "artifact": completed_payload["artifact"],
                 "record": completed_payload["completion"],
                 "workspace_artifact": completed_payload["workspace_artifact"],
                 "constitution_file": {"path": CONSTITUTION_PATH,
                                       "sha256": completed_payload["constitution_sha256"]},
                 "construction_tokens": total_tokens,
                 "installments": installments,
                 "timestamp": utc()}
        store.append("campaign_setups", event)
        store.append("construction", {**identity, "setup_key": setup_key,
                                      "status": "completed", "timestamp": utc(),
                                      "installments": installments,
                                      "duration_seconds": time.monotonic()-tick})
        return True
    store.append("construction", {**identity, "setup_key": setup_key,
                                  "status": "failed", "reason": reason,
                                  "timestamp": utc(),
                                  "duration_seconds": time.monotonic()-tick})
    store.append("tripwires", {**identity, "status": "construction_failed",
                                "reason": reason, "halt_class": "premise_equipment",
                                "halt_kind": "task_setup_failed",
                                "behavior": "skip_and_continue",
                                "behavior_changed": False, "timestamp": utc()})
    if transport_halt(store, identity, reason):
        capture_transport_bundle(store, identity, cfg, reason)
    return False


def transport_halt(store, identity, reason):
    """Whether this halt is a transport halt for R-A5 bundle
    purposes: a recorded transport event (e.g. a stall) for the
    identity, or a transport-named reason."""
    if any(e.get("attempt_id") == identity.get("attempt_id")
           for e in store.events("transport_events")):
        return True
    return "transport" in str(reason or "").lower()


def make_provider(cfg, store, budget, identity):
    """Select the inference backend from the frozen manifest config.

    provider_backend "local" routes to the operator's llama.cpp server at zero
    marginal cost; anything else uses the OpenAI-compatible provider selected
    by cfg["provider"] (OpenAI by default). The selection is config-driven
    and frozen, so a campaign can never mix backends mid-run.
    """
    if cfg.get("provider_backend") == "local":
        return LocalProvider(cfg, store, budget, identity)
    return OpenAIProvider(cfg, store, budget, identity)


def check_credential(spec=None):
    """Fail-closed credential check: Secure Vault connector or the provider's key env var.

    resolve_auth() performs a free /models probe and raises ValueError when
    neither credential authenticates.
    """
    from .provider import resolve_auth
    resolve_auth(spec if spec is not None else provider_spec({}))


def validate_live(manifest, smoke=False):
    cfg = manifest["config"]
    local = cfg.get("provider_backend") == "local"
    required = ["model", "price_snapshot_id", "price_source", "budget_authorization",
                "global_cap_usd", "attempt_cap_usd", "max_input_tokens", "max_output_tokens", "token_cap"]
    if not local:
        # reasoning_effort is an OpenAI-only parameter; local manifests omit it.
        required.insert(1, "reasoning_effort")
    for key in required:
        if not cfg.get(key):
            raise ValueError(f"live execution requires frozen {key}")
    # Pacing/retry bounds are frozen campaign configuration, never ambient
    # module constants: a live campaign cannot run on implicit defaults.
    if not cfg.get("transport"):
        raise ValueError("live execution requires frozen transport policy (pacing/retry bounds)")
    transport_policy(cfg)  # raises on malformed bounds
    if not cfg.get("reservation_bound_verified"):
        raise ValueError("verify model context and output reservation bounds before spending")
    if not cfg.get("grader_smoke_verified"):
        raise ValueError("successful independent grader smoke required before model spending")
    if not cfg.get("solver_image_audit_verified"):
        raise ValueError("audit images for hidden grader material before model spending")
    if not smoke and not cfg.get("real_smoke_verified"):
        raise ValueError("successful real adapter/usage smoke required before scored generation")
    if smoke and cfg.get("purpose") != "development_smoke":
        raise ValueError("smoke must use a separately frozen development manifest")
    if local:
        # Local backend: no provider credential, no dollar reservation. The
        # server must be up and serving the expected model before any attempt.
        check_local_server()
    else:
        from .provider import resolve_auth
        spec = provider_spec(cfg)
        mode, _ = resolve_auth(spec)
        if mode == "connector" and spec["key_env"] in os.environ:
            raise ValueError("remove %s from environment; connector credential is active"
                             % spec["key_env"])
        check_credential(spec)
    if os.name == "nt":
        raise ValueError("live runs require Linux/WSL2 with Docker; offline commands support Windows")
    subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=30)
    for task in manifest["tasks"]["tasks"]:
        if task.get("problem_statement", "").startswith("REHYDRATE_"):
            raise ValueError("hydrate issue text from pinned upstream before freezing live runs")
        from .isolation import docker_args
        docker_args(task.get("image", ""), "preflight")
        subprocess.run(["docker", "image", "inspect", task["image"]], check=True, capture_output=True, timeout=30)


def run(root, manifest, output, arm=None, smoke=False):
    verify_freeze(root, manifest)
    validate_live(manifest, smoke)
    # Deferred to avoid a module cycle (see execute_attempt).
    from .matched_repair import REPAIR_DEPENDENT_ARMS, diagnostic_available
    store = Store(output)
    with RunLock(output):
        path = Path(output)/"freeze.json"
        if path.exists():
            if read_json(path) != manifest:
                raise ValueError("resume configuration mismatch")
        else:
            write_json(path, manifest, exclusive=True)
        cfg = manifest["config"]
        budget = Budget(store, cfg["global_cap_usd"], cfg["attempt_cap_usd"])
        outcomes = {e["attempt_id"]: e for e in store.events("attempts")}
        tasks = {t["instance_id"]: t for t in manifest["tasks"]["tasks"]}
        # Amendment 1 R-A1/R-A4: the construction gate. Construction
        # runs lazily, once per task, before that task's first scored
        # attempt of any arm — so the frozen setup exists before its
        # first consumer by construction, and a stage only pays for
        # the tasks it actually reaches. A failed construction is a
        # task-level premise fault: the task's attempts never start.
        construction_state = {}

        def ensure_setup(entry):
            if not construction_enabled(cfg):
                return "proceed"
            # Cycle 1 C1-A1: baseline carve-out. Construction gating
            # applies only to arms whose phase plan consumes the
            # campaign setup; a baseline attempt is admitted on task
            # readiness alone, never triggers construction, and never
            # reads the setup record.
            if entry["arm"] == "baseline":
                return "proceed"
            task = tasks[entry["task_id"]]
            setup_key = task.get("instance_id") or entry["task_id"]
            if not any(e["task_id"] == entry["task_id"] and e["arm"] != "baseline"
                       for e in manifest["schedule"]):
                return "proceed"
            if setup_key not in construction_state:
                # R-A4's all-tasks-failed case needs no special halt:
                # every task's construction is tried on its own first
                # entry, and if all fail the loop simply scores
                # nothing — the manufactured-nil path at the gate.
                if campaign_setup(store, setup_key) is not None:
                    construction_state[setup_key] = True
                else:
                    construction_state[setup_key] = run_construction(
                        root, task, store, cfg, manifest)
            return "proceed" if construction_state[setup_key] else "skip"

        for entry in manifest["schedule"]:
            if arm and arm != entry["arm"]:
                continue
            if (Path(output)/"CANCEL").exists():
                break
            identity = {**entry, "experiment_id": manifest["freeze_id"], "run_id": manifest["freeze_id"][:16],
                        "purpose": cfg["purpose"]}
            if entry["attempt_id"] in outcomes:
                if outcomes[entry["attempt_id"]]["status"] == "started":
                    store.append("attempts", {**identity, "status": "infrastructure_failure",
                                              "reason": "interrupted; no automatic rerun", "timestamp": utc()})
                    event = record_tripwire(store, identity, "infrastructure_failure",
                                            "interrupted; no automatic rerun")
                    # Stop policy (2026-10-21, PC-8): an interrupted
                    # attempt's cause was never established, so its
                    # class is unknown and the study halts after
                    # recording it; no later attempt starts.
                    if event is not None and event["behavior"] == HALT_STUDY:
                        break
                continue
            if entry["arm"] in REPAIR_DEPENDENT_ARMS and not diagnostic_available(
                    store, manifest, tasks[entry["task_id"]]):
                # Pre-skip BEFORE any attempt-start event: the task's
                # diagnostic evidence is unavailable, so this dependent
                # repair arm cannot run. No inference is issued; the record
                # is an honest skip rather than started-then-error.
                # Downstream band selection fails closed on the missing
                # attempts. The stop policy does not govern this admission
                # decision (PC-8 exclusion): the schedule continues past
                # a pre-skip exactly as before the revision.
                store.append("attempts", {**identity, "status": "skipped",
                                          "reason": "pre-skipped: diagnostic evidence not recorded; "
                                                    "no inference issued",
                                          "timestamp": utc()})
                record_tripwire(store, identity, "skipped",
                                "pre-skipped: diagnostic evidence not recorded; no inference issued")
                continue
            try:
                gate = ensure_setup(entry)
            except KeyboardInterrupt:
                break
            if gate == "skip":
                # The task's setup construction failed: this attempt
                # never starts. The record mirrors the pre-skip's
                # admission semantics (PC-8 exclusion) but carries
                # R-A4's named kind, task_setup_failed.
                skip_reason = ("pre-skipped: campaign setup construction failed "
                               "(task_setup_failed); no inference issued")
                store.append("attempts", {**identity, "status": "skipped",
                                          "reason": skip_reason, "timestamp": utc()})
                store.append("tripwires", {**identity, "status": "skipped",
                                           "reason": skip_reason,
                                           "halt_class": "premise_equipment",
                                           "halt_kind": "task_setup_failed",
                                           "behavior": "skip_and_continue",
                                           "behavior_changed": False,
                                           "timestamp": utc()})
                continue
            # Amendment 1 R-A6: probe the shared worker immediately
            # before the attempt starts. A busy worker (or a failed
            # probe, which cannot prove the worker free) means the
            # attempt does not start and a premise event is recorded;
            # three blocks in a stage halt the stage for owner review.
            # Like setup sharing, the probe is a declared campaign
            # behavior: the manifest's config opts in (the Stage 1R
            # freeze does); other harnesses' manifests are untouched.
            probe = None
            if local_backend(cfg) and cfg.get("worker_availability_probe"):
                probe = probe_worker(transport_policy(cfg))
                if probe.get("busy") or probe.get("error"):
                    blocks = sum(1 for e in store.events("worker_probes")
                                 if e.get("kind") == "worker_busy_block")
                    store.append("worker_probes", {**identity,
                                                   "kind": "worker_busy_block",
                                                   "probe": probe, "timestamp": utc()})
                    if blocks + 1 >= WORKER_BLOCK_LIMIT:
                        store.append("worker_probes", {**identity,
                                                       "kind": "worker_busy_stage_halt",
                                                       "blocks": blocks + 1,
                                                       "timestamp": utc()})
                        break
                    continue
            started = {**identity, "status": "started", "timestamp": utc()}
            if probe is not None:
                started["worker_probe"] = probe
            store.append("attempts", started)
            tick, result = time.monotonic(), {}
            status, reason = "completed", None
            try:
                with DockerSandbox(tasks[entry["task_id"]]["image"]) as sandbox:
                    # base commit equality prevents a patched image from masquerading as clean.
                    check = sandbox.execute("git rev-parse HEAD && git status --porcelain")
                    if check["exit_code"] or check["stdout"].strip() != tasks[entry["task_id"]]["base_commit"]:
                        raise RuntimeError("solver image does not contain a clean base checkout")
                    store.append("images", {**identity, **sandbox.details})
                    provider = make_provider(cfg, store, budget, identity)
                    try:
                        result = execute_attempt(root, tasks[entry["task_id"]], entry["arm"], provider,
                                                 sandbox, store, identity, cfg, manifest)
                    except BaseException:
                        # Preserve partial work before the container is destroyed. This host-only
                        # extraction issues no model request and is separately timed.
                        partial = sandbox.execute("git add -N . && git diff --binary HEAD", 30)
                        if partial["exit_code"] == 0:
                            result["patch"] = store.artifact(partial["stdout"].encode())
                        raise
                    if result.get("blocked"):
                        status, reason = "limit", "AEE recovery bound"
                    if result.get("phase_exhausted"):
                        # Amendment 1 R-A3/R-A4: the protocol reason
                        # classifies via classify_halt's explicit
                        # phase-exhaustion branch (a model outcome).
                        status, reason = "limit", phase_exhaustion_reason(
                            result["phase_exhausted"])
            except (BudgetExceeded, LimitHit) as e:
                status, reason = "limit", str(e)
            except AttemptWallExpiredError:
                # Cycle 2 C2-F1: the attempt wall expired, including
                # mid-call under the wall-remainder per-call deadline
                # (Cycle 1's fatal shape). A scored limit outcome
                # via the explicit classifier branch — the partial
                # patch extracted above is graded as it stands and
                # the study proceeds to the next scheduled attempt.
                status, reason = "limit", attempt_wall_expiry_reason()
            except CallOuterBoundError:
                # Cycle 1 C1-A3: a flowing call reached the hard
                # outer bound — a named, disclosed limit (the partial
                # stream is recorded on the call event).
                status, reason = "limit", "call_outer_bound"
            except KeyboardInterrupt:
                status, reason = "cancelled", "operator interrupt"
            except Exception as e:
                status, reason = "error", error_reason(e)
            store.append("attempts", {**identity, **result, "status": status, "reason": reason,
                                      "timestamp": utc(), "duration_seconds": time.monotonic()-tick})
            # Stop policy (2026-10-21, PC-8): the halt is classified
            # and recorded as a tripwire event, and behavior follows
            # the classification. A proven model outcome stands as
            # scored and the schedule continues to the next entry; a
            # premise or equipment fault, an integrity fault, or
            # anything unclassified halts the study here, retaining
            # all charges.
            event = record_tripwire(store, identity, status, reason)
            # Amendment 1 R-A5: on a transport halt, capture the
            # observability bundle into the run store before
            # anything is restarted.
            if (event is not None and event["behavior"] == HALT_STUDY
                    and event["halt_class"] == "premise_equipment"
                    and transport_halt(store, identity, reason)):
                capture_transport_bundle(store, identity, cfg, reason)
            if event is not None and event["behavior"] == HALT_STUDY:
                break
    return store.events("attempts")
