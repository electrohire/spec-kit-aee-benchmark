"""Token-router wiring (Window 4 Phase 1, 2026-10-26; Window 5
Phase 1 exit-contract fix, 2026-10-26).

Opt-in observation shaping behind the freeze keys ``token_router``
(bool), ``token_router_script`` (absolute path) and
``token_router_sha256`` (hex of the script file). With the flag
absent or false this module is never called and the runner's
observation path is byte-identical to the pre-wiring behavior.

The routing basis is exactly the defaults tournament's priced
basis: the combined text (stdout, plus "\\n" + stderr when stderr
is non-empty) of one tool result, routed through the pinned
token-router v2.8.1 in error_log mode (focused scope, line numbers,
the six registered failure-vocabulary terms, never --force-model,
never --deterministic). The raw output is stored as a
digest-addressed artifact BEFORE routing (the caller's tools
event); that artifact is the recovery path for every routed
observation.

Delivery rules (fail-closed; there is no silent raw fallback):

- failure outputs (exit_code != 0) bypass routing and the combined
  text is delivered verbatim;
- empty combined text skips routing, fields unchanged;
- an ``auto_candidates`` report delivers the router's packet
  verbatim; an ``auto_full`` report likewise (its packet is the
  whole decoded source);
- a ``needs_targeted_read`` report triggers the targeted read: the
  raw text is retrieved from the digest-addressed artifact, its
  digest re-verified twice (file bytes against the artifact
  record, rebuilt combined text against the in-hand combined
  text), and the combined text is delivered;
- a ``bypass`` report delivers the combined text verbatim (the
  tool rejected the profile and returned no packet; ordinary
  delivery is the documented meaning);
- any router error, timeout, version/hash mismatch, unparseable
  report, unexpected status, or a report with model_called not
  False raises TokenRouterFreezeError — an integrity error whose
  message always carries the freeze marker, so the tripwire
  taxonomy classifies it INTEGRITY and the attempt dies.

The tool's contract is status-first (its README status table):
``auto_full``/``auto_candidates``/``fallback`` exit 0,
``needs_targeted_read``/``bypass``/``usage_error`` exit 2,
``error`` exits 1. Dispatch is on the report's status; the
process exit code is cross-checked against that table and a
status/exit mismatch is itself a freeze violation. (The Window 4
wiring checked ``returncode != 0`` before reading the report, so
every genuine ``needs_targeted_read`` — the dominant live
status — raised a false freeze violation; Window 4 halted on it
at its smoke gate. The Window 5 fix dispatches on status.)
``fallback`` is a freeze violation here: it belongs to the
tool's optional model-selector path, which this wiring never
enables, so its appearance under the pinned invocation is
genuinely unexpected and fails closed.

Window 7 addition (2026-10-29, pre-registered proposal in the
Window 6 router research memo, Part 2): the delivery cap. Behind
the freeze keys ``token_router_cap_threshold_bytes`` and
``token_router_cap_max_delivery_bytes`` (both present and valid,
or both absent — a partial or invalid pair is a freeze
violation), a ``needs_targeted_read`` delivery whose raw size
exceeds the threshold is delivered as a bounded digest instead
of the full text: a header naming the raw size and the artifact
digest, every failure-vocabulary line (the six registered
ROUTER_TERMS) verbatim in order, then head and tail excerpts —
never more than the maximum delivery bytes in total. The
construction is a pure function of the combined text, the
artifact digest, and the two cap parameters, so the analysis can
rebuild any capped delivery byte for byte. A capped digest's
artifact digest is registered on the environment state; a later
command that is exactly ``retrieve-observation <digest>`` for a
registered digest is answered by ``try_retrieval`` with the full
verified text and a router-stream event whose delivered bytes
the accounting charges as clawback in full. Any other command —
including an unregistered digest — is not intercepted. Failure
outputs still bypass verbatim with the cap in place; routing
decisions, entry construction, and every other delivery rule are
unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .store import sha, utc

ROUTER_VERSION = "token-router 2.8.1"
ROUTER_TERMS = ("ERROR", "Error", "error:", "FAILED", "Traceback",
                "AssertionError")
ROUTER_TIMEOUT_SECONDS = 60

# The pinned tool's documented status/exit contract (its README
# status table). Dispatch is on the report's status; the process
# exit code is cross-checked against this table, and a mismatch
# is a freeze violation.
STATUS_EXIT_CODES = {
    "auto_full": 0,
    "auto_candidates": 0,
    "fallback": 0,
    "needs_targeted_read": 2,
    "bypass": 2,
    "usage_error": 2,
    "error": 1,
}

_FREEZE_MARK = "token_router freeze violation"


class TokenRouterFreezeError(RuntimeError):
    """A token-router integrity failure. The word "freeze" in the
    message is the tripwire INTEGRITY marker: every router
    integrity error carries it."""


def _freeze_error(detail):
    return TokenRouterFreezeError(f"{_FREEZE_MARK}: {detail}")


def combined_text(result):
    """The tournament's priced basis, byte-exact: stdout, plus
    "\\n" + stderr when stderr is non-empty."""
    text = result["stdout"]
    if result["stderr"]:
        text += "\n" + result["stderr"]
    return text


def _verify_router_tool(cfg, state):
    """Verify the pinned router tool once per environment (the
    state dict carries the verified flag across calls): the script
    exists, its SHA-256 equals the freeze's token_router_sha256,
    and its --version output is exactly ROUTER_VERSION. Any
    failure — including missing freeze keys — is a freeze
    violation."""
    if state is not None and state.get("verified"):
        return
    script = cfg.get("token_router_script")
    expected_sha = cfg.get("token_router_sha256")
    if not script or not expected_sha:
        raise _freeze_error(
            "freeze is missing token_router_script or "
            "token_router_sha256")
    path = Path(script)
    if not path.is_file():
        raise _freeze_error(f"router script does not exist: {script}")
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise _freeze_error(
            f"router script sha256 mismatch: freeze pins "
            f"{expected_sha}, file hashes to {actual_sha}")
    try:
        proc = subprocess.run(
            [sys.executable, str(path), "--version"],
            capture_output=True, timeout=ROUTER_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _freeze_error(f"router --version failed: {exc}") from exc
    version = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or version != ROUTER_VERSION:
        raise _freeze_error(
            f"router version mismatch: expected {ROUTER_VERSION!r}, "
            f"got exit {proc.returncode} and {version!r}")
    if state is not None:
        state["verified"] = True


def _read_artifact_result(artifact, store):
    """Read the digest-addressed artifact and return its recorded
    tool result: the artifact file's bytes are verified against
    the artifact record's digest, and the content must parse as a
    recorded tool result. Any failure is a freeze violation."""
    if store is None:
        raise _freeze_error(
            "targeted read requires the run store to resolve the "
            "artifact path")
    path = Path(store.root) / artifact["path"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _freeze_error(
            f"targeted read cannot read artifact "
            f"{artifact['path']}: {exc}") from exc
    if sha(data) != artifact["sha256"]:
        raise _freeze_error(
            "targeted read artifact digest mismatch: file bytes do "
            "not hash to the recorded artifact sha256")
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise _freeze_error(
            f"targeted read artifact is not a parseable tool "
            f"result: {exc}") from exc


def _targeted_read(artifact, in_hand_combined, store):
    """Retrieve the raw combined text from the digest-addressed
    artifact and re-verify it twice: the artifact file's bytes
    against the artifact record's digest, and the rebuilt combined
    text (from the artifact's recorded stdout/stderr) against the
    in-hand combined text. Any mismatch is a freeze violation."""
    recorded = _read_artifact_result(artifact, store)
    try:
        rebuilt = combined_text(
            {"stdout": recorded["stdout"],
             "stderr": recorded["stderr"]})
    except (KeyError, TypeError) as exc:
        raise _freeze_error(
            f"targeted read artifact is not a parseable tool "
            f"result: {exc}") from exc
    if sha(rebuilt.encode("utf-8")) != sha(in_hand_combined.encode("utf-8")):
        raise _freeze_error(
            "targeted read combined-text digest mismatch: the "
            "artifact's recorded output differs from the in-hand "
            "output")
    return in_hand_combined


# --- Window 7 delivery cap -------------------------------------
# Freeze keys (both or neither; a partial or invalid pair is a
# freeze violation):
#   token_router_cap_threshold_bytes — raw size above which a
#     needs_targeted_read delivery is capped;
#   token_router_cap_max_delivery_bytes — the maximum bytes a
#     capped delivery may carry.
CAP_THRESHOLD_KEY = "token_router_cap_threshold_bytes"
CAP_MAX_DELIVERY_KEY = "token_router_cap_max_delivery_bytes"

_RETRIEVAL_RE = re.compile(r"^retrieve-observation ([0-9a-f]{64})$")


def _cap_params(cfg):
    """The freeze's cap parameters, or None when the cap is not
    configured. Both keys absent means Window 6 behavior exactly;
    a partial or invalid pair fails closed."""
    threshold = cfg.get(CAP_THRESHOLD_KEY)
    max_delivery = cfg.get(CAP_MAX_DELIVERY_KEY)
    if threshold is None and max_delivery is None:
        return None
    if (not isinstance(threshold, int) or isinstance(threshold, bool)
            or not isinstance(max_delivery, int)
            or isinstance(max_delivery, bool)
            or threshold <= 0 or max_delivery <= 0):
        raise _freeze_error(
            f"invalid delivery-cap freeze keys: {CAP_THRESHOLD_KEY}="
            f"{threshold!r}, {CAP_MAX_DELIVERY_KEY}={max_delivery!r} "
            f"(both must be positive integers, or both absent)")
    return threshold, max_delivery


def capped_delivery(combined, artifact_sha256, threshold, max_delivery):
    """The bounded delivery for an over-threshold targeted read:
    a pure function of (combined text, artifact digest, cap
    parameters), so any capped delivery can be rebuilt byte for
    byte from the artifact. Returns None when the text is within
    the threshold (the caller delivers it in full); otherwise a
    dict with the delivery text (never more than max_delivery
    UTF-8 bytes) and the failure-signal line accounting.

    Construction, in order: a one-line header naming the raw
    size, the threshold, and the explicit-retrieval command for
    this artifact; every line carrying the registered failure
    vocabulary (ROUTER_TERMS), verbatim and in order, while the
    byte budget lasts; a head excerpt; a tail excerpt. Excerpts
    take whole lines only and stop at the first line that does
    not fit their share of the remaining budget.
    """
    raw_bytes = len(combined.encode("utf-8"))
    if raw_bytes <= threshold:
        return None
    lines = combined.split("\n")
    signal_lines = [ln for ln in lines
                    if any(term in ln for term in ROUTER_TERMS)]

    def section(marker, candidates, budget):
        """[marker] + whole candidate lines, in appearance
        order, while the section's own joined byte length stays
        within budget; [] when no candidate fits (a label is
        never delivered for an empty section)."""
        if budget <= 0:
            return []
        picked = []
        size = len(marker.encode("utf-8"))
        for ln in candidates:
            add = len(ln.encode("utf-8")) + 1
            if size + add > budget:
                break
            picked.append(ln)
            size += add
        return [marker] + picked if picked else []

    def tail_section(marker, budget):
        """Like section(), but candidates are picked from the
        END of the text backwards and presented in original
        order."""
        if budget <= 0:
            return []
        picked_rev = []
        size = len(marker.encode("utf-8"))
        for ln in reversed(lines):
            add = len(ln.encode("utf-8")) + 1
            if size + add > budget:
                break
            picked_rev.append(ln)
            size += add
        return [marker] + picked_rev[::-1] if picked_rev else []

    out_lines = []

    def total():
        return len("\n".join(out_lines).encode("utf-8")) if out_lines \
            else 0

    def room():
        # Bytes left under max_delivery, charging the newline
        # that would join a new section to what is already out.
        return max_delivery - total() - (1 if out_lines else 0)

    header = (f"[router digest: {raw_bytes} bytes over the "
              f"{threshold}-byte delivery cap; full text: "
              f"retrieve-observation {artifact_sha256}]")
    if len(header.encode("utf-8")) <= max_delivery:
        out_lines.append(header)
    signals_included = 0
    if signal_lines:
        sec = section("--- failure-signal lines (verbatim) ---",
                      signal_lines, room())
        signals_included = len(sec) - 1 if sec else 0
        out_lines.extend(sec)
    if room() > 0:
        out_lines.extend(section("--- head excerpt ---", lines,
                                 room() // 2))
    if room() > 0:
        out_lines.extend(tail_section("--- tail excerpt ---",
                                      room()))
    text = "\n".join(out_lines)
    encoded = text.encode("utf-8")
    if len(encoded) > max_delivery:
        # Only reachable when the header alone exceeds a
        # pathological max_delivery; the clamp is deterministic,
        # so reconstruction still matches byte for byte.
        text = encoded[:max_delivery].decode("utf-8", errors="ignore")
    return {"text": text,
            "signal_lines_total": len(signal_lines),
            "signal_lines_included": signals_included}


_SELECTED_LINE_RE = re.compile(r"^\d+:", re.MULTILINE)


def route_observation(result, artifact, cfg, *, store=None,
                      identity=None, state=None):
    """Route one tool result's observation text.

    Returns (new_result, event): new_result is a copy of result
    with its stdout/stderr replaced by the delivered text (the
    original result is never mutated), and event is the router
    stream record (identity and timestamp filled here; the caller
    appends it to the store's "router" stream). Raises
    TokenRouterFreezeError on any integrity failure.
    """
    identity = dict(identity or {})
    combined = combined_text(result)
    raw_bytes = len(combined.encode("utf-8"))
    exit_code = result["exit_code"]

    def _event(status, delivered_stdout, delivered_stderr,
               packet_bytes=0, targeted_read=False, packet=None,
               extra=None):
        delivered_bytes = (len(delivered_stdout.encode("utf-8"))
                           + len(delivered_stderr.encode("utf-8")))
        selected_lines = (len(_SELECTED_LINE_RE.findall(packet))
                          if packet else 0)
        return {**identity, "timestamp": utc(),
                "artifact": artifact["sha256"],
                "exit_code": exit_code, "status": status,
                "raw_bytes": raw_bytes, "packet_bytes": packet_bytes,
                "delivered_bytes": delivered_bytes,
                "targeted_read": targeted_read,
                "selected_lines": selected_lines,
                "model_called": False, **(extra or {})}

    if exit_code != 0:
        # Failure outputs bypass routing and are carried verbatim.
        new_result = {**result, "stdout": combined, "stderr": ""}
        return new_result, _event("bypass_failure", combined, "")

    if combined == "":
        new_result = dict(result)
        return new_result, _event(
            "skipped_empty", result["stdout"], result["stderr"])

    _verify_router_tool(cfg, state)
    cap = _cap_params(cfg)
    script = cfg["token_router_script"]
    with tempfile.TemporaryDirectory(prefix="token-router-") as tmp:
        target = Path(tmp) / "combined.txt"
        target.write_bytes(combined.encode("utf-8"))
        report_path = Path(tmp) / "report.json"
        command = [sys.executable, script, "error_log", str(target),
                   "--read-scope", "focused", "--line-numbers",
                   "--report-json", str(report_path),
                   "--compact-status"]
        for term in ROUTER_TERMS:
            command += ["--search-term", term]
        try:
            proc = subprocess.run(
                command, capture_output=True,
                timeout=ROUTER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise _freeze_error(
                f"router timed out after "
                f"{ROUTER_TIMEOUT_SECONDS}s") from exc
        except OSError as exc:
            raise _freeze_error(f"router invocation failed: {exc}") from exc
        # Status-first dispatch (the Window 5 fix): the report is
        # read and parsed BEFORE any exit-code judgment, because
        # exit 2 is the documented code for the dominant live
        # statuses (needs_targeted_read, bypass). The exit code
        # is then cross-checked against the documented contract
        # for the reported status; a mismatch is the violation.
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _freeze_error(
                f"router report unparseable (process exited "
                f"{proc.returncode}): {exc}") from exc
        if not isinstance(report, dict):
            raise _freeze_error("router report is not a JSON object")
        if report.get("model_called") is not False:
            raise _freeze_error(
                f"router report model_called is "
                f"{report.get('model_called')!r}, not False")
        status = report.get("status")
        expected_exit = STATUS_EXIT_CODES.get(status)
        if expected_exit is None:
            raise _freeze_error(
                f"router returned unexpected status {status!r}")
        if proc.returncode != expected_exit:
            raise _freeze_error(
                f"router status/exit mismatch: status {status!r} "
                f"documents exit {expected_exit}, process exited "
                f"{proc.returncode}")
        if status in ("error", "usage_error"):
            raise _freeze_error(
                f"router reported {status}: "
                f"{report.get('reason') or report.get('reason_codes')}")
        if status == "fallback":
            raise _freeze_error(
                "router reported fallback: the optional model "
                "selector path is never enabled by this wiring, so "
                "fallback is unexpected under the pinned invocation")
        if status in ("auto_candidates", "auto_full"):
            packet = proc.stdout.decode("utf-8", errors="replace")
            new_result = {**result, "stdout": packet, "stderr": ""}
            return new_result, _event(
                status, packet, "",
                packet_bytes=len(packet.encode("utf-8")),
                packet=packet)
        if status == "needs_targeted_read":
            delivered = _targeted_read(artifact, combined, store)
            if cap is not None:
                capped = capped_delivery(
                    delivered, artifact["sha256"], cap[0], cap[1])
                if capped is not None:
                    # Window 7: the bounded digest replaces the
                    # full text; the digest's artifact is
                    # registered for explicit retrieval, and the
                    # event carries the cap accounting.
                    if state is not None:
                        state.setdefault("capped_digests", {})[
                            artifact["sha256"]] = dict(artifact)
                    new_result = {**result,
                                  "stdout": capped["text"],
                                  "stderr": ""}
                    return new_result, _event(
                        "needs_targeted_read", capped["text"], "",
                        targeted_read=True,
                        extra={"capped": True,
                               "cap_threshold_bytes": cap[0],
                               "cap_max_delivery_bytes": cap[1],
                               "signal_lines_total":
                                   capped["signal_lines_total"],
                               "signal_lines_included":
                                   capped["signal_lines_included"]})
            new_result = {**result, "stdout": delivered, "stderr": ""}
            return new_result, _event(
                "needs_targeted_read", delivered, "",
                targeted_read=True)
        # status == "bypass": the tool rejected the profile and
        # returned no packet; the documented meaning is ordinary
        # handling, so the combined text is delivered verbatim.
        new_result = {**result, "stdout": combined, "stderr": ""}
        return new_result, _event("bypass", combined, "")


def try_retrieval(command, store, cfg, *, identity=None, state=None):
    """Window 7 explicit retrieval: answer a command that is
    exactly ``retrieve-observation <digest>`` for a digest this
    environment previously delivered in capped form.

    Returns (delivered_text, event, artifact) — the full combined
    text re-verified from the digest-addressed artifact (the same
    digest check the targeted read performs), a router-stream
    event with status ``explicit_retrieval`` whose
    delivered_bytes the accounting charges as clawback in full,
    and the registered artifact record — or None when the command
    is not an explicit retrieval of a registered digest (the
    caller then executes it as an ordinary command, byte-
    identically to the pre-Window-7 path). The router tool is not
    invoked; no model is called. A registered digest whose
    artifact fails verification raises TokenRouterFreezeError,
    like every other integrity failure in this module.
    """
    if not cfg.get("token_router") or _cap_params(cfg) is None:
        return None
    match = _RETRIEVAL_RE.match((command or "").strip())
    if match is None:
        return None
    registry = (state or {}).get("capped_digests") or {}
    artifact = registry.get(match.group(1))
    if artifact is None:
        return None
    recorded = _read_artifact_result(artifact, store)
    try:
        delivered = combined_text(
            {"stdout": recorded["stdout"],
             "stderr": recorded["stderr"]})
        exit_code = recorded["exit_code"]
    except (KeyError, TypeError) as exc:
        raise _freeze_error(
            f"explicit retrieval artifact is not a parseable "
            f"tool result: {exc}") from exc
    delivered_bytes = len(delivered.encode("utf-8"))
    event = {**dict(identity or {}), "timestamp": utc(),
             "artifact": artifact["sha256"],
             "exit_code": exit_code, "status": "explicit_retrieval",
             "raw_bytes": delivered_bytes, "packet_bytes": 0,
             "delivered_bytes": delivered_bytes,
             "targeted_read": False, "selected_lines": 0,
             "model_called": False, "retrieval": True}
    return delivered, event, artifact
