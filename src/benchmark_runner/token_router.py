"""Token-router wiring (Window 4 Phase 1, 2026-10-26).

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
  verbatim;
- a ``needs_targeted_read`` report triggers the targeted read: the
  raw text is retrieved from the digest-addressed artifact, its
  digest re-verified twice (file bytes against the artifact
  record, rebuilt combined text against the in-hand combined
  text), and the combined text is delivered;
- any router error, timeout, version/hash mismatch, unparseable
  report, unexpected status, or a report with model_called not
  False raises TokenRouterFreezeError — an integrity error whose
  message always carries the freeze marker, so the tripwire
  taxonomy classifies it INTEGRITY and the attempt dies.
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


def _targeted_read(artifact, in_hand_combined, store):
    """Retrieve the raw combined text from the digest-addressed
    artifact and re-verify it twice: the artifact file's bytes
    against the artifact record's digest, and the rebuilt combined
    text (from the artifact's recorded stdout/stderr) against the
    in-hand combined text. Any mismatch is a freeze violation."""
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
        recorded = json.loads(data.decode("utf-8"))
        rebuilt = combined_text(
            {"stdout": recorded["stdout"],
             "stderr": recorded["stderr"]})
    except (ValueError, KeyError, TypeError) as exc:
        raise _freeze_error(
            f"targeted read artifact is not a parseable tool "
            f"result: {exc}") from exc
    if sha(rebuilt.encode("utf-8")) != sha(in_hand_combined.encode("utf-8")):
        raise _freeze_error(
            "targeted read combined-text digest mismatch: the "
            "artifact's recorded output differs from the in-hand "
            "output")
    return in_hand_combined


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
               packet_bytes=0, targeted_read=False, packet=None):
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
                "model_called": False}

    if exit_code != 0:
        # Failure outputs bypass routing and are carried verbatim.
        new_result = {**result, "stdout": combined, "stderr": ""}
        return new_result, _event("bypass_failure", combined, "")

    if combined == "":
        new_result = dict(result)
        return new_result, _event(
            "skipped_empty", result["stdout"], result["stderr"])

    _verify_router_tool(cfg, state)
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
        if proc.returncode != 0:
            raise _freeze_error(
                f"router exited {proc.returncode}")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _freeze_error(
                f"router report unparseable: {exc}") from exc
        if not isinstance(report, dict):
            raise _freeze_error("router report is not a JSON object")
        if report.get("model_called") is not False:
            raise _freeze_error(
                f"router report model_called is "
                f"{report.get('model_called')!r}, not False")
        status = report.get("status")
        if status == "auto_candidates":
            packet = proc.stdout.decode("utf-8", errors="replace")
            new_result = {**result, "stdout": packet, "stderr": ""}
            return new_result, _event(
                "auto_candidates", packet, "",
                packet_bytes=len(packet.encode("utf-8")),
                packet=packet)
        if status == "needs_targeted_read":
            delivered = _targeted_read(artifact, combined, store)
            new_result = {**result, "stdout": delivered, "stderr": ""}
            return new_result, _event(
                "needs_targeted_read", delivered, "",
                targeted_read=True)
        raise _freeze_error(f"router returned unexpected status "
                            f"{status!r}")
