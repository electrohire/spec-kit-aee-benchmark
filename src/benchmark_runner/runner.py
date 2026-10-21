"""Thin mini-SWE-agent adapter; one persistent agent and budget per attempt."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import tempfile
import shutil
from pathlib import Path

from .accounting import Budget, BudgetExceeded, TOKEN_FIELDS, attempt_token_usage
from .experiment import verify_freeze
from .isolation import DockerSandbox
from .provider import OpenAIProvider, provider_spec, transport_policy
from .local_provider import LocalProvider, check_local_server
from .store import RunLock, Store, canonical, read_json, utc, write_json
from .tripwires import HALT_STUDY, record_tripwire
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


def attempt_wall_seconds(cfg):
    return LOCAL_WALL_TIME_SECONDS if local_backend(cfg) else cfg["timeout_seconds"]


class MiniModel:
    """mini's Model protocol with observable requests and explicit JSON actions."""
    def __init__(self, provider, deadline, call_timeout=FRONTIER_CALL_TIMEOUT_SECONDS):
        self.provider, self.deadline, self.call_timeout = provider, deadline, call_timeout
        self.phase, self.last = None, None

    def query(self, messages):
        cleaned = [{"role": m["role"], "content": m["content"]} for m in messages]
        text = self.provider.query(cleaned, self.phase, min(remaining(self.deadline), self.call_timeout))
        try:
            action = json.loads(text)
            if not isinstance(action, dict) or action.get("action") not in ("shell", "done"):
                raise ValueError("expected shell or done")
            if action["action"] == "shell" and not isinstance(action.get("command"), str):
                raise ValueError("shell command must be string")
            self.last = action
        except (ValueError, TypeError):
            self.last = {"action": "invalid"}
            action = self.last
        return {"role": "assistant", "content": text,
                "extra": {"actions": [action] if action["action"] == "shell" else []}}

    def format_observation_messages(self, message, outputs, template_vars):
        if self.last["action"] == "invalid":
            return [{"role": "user", "content": 'Return one JSON object: {"action":"shell","command":"..."} or {"action":"done","summary":"..."}.'}]
        return [{"role": "user", "content": json.dumps(o)} for o in outputs]

    def get_template_vars(self):
        return {}


class MiniEnvironment:
    def __init__(self, sandbox, deadline, store, identity):
        self.sandbox, self.deadline, self.store, self.identity = sandbox, deadline, store, identity
        self.tool_calls = 0

    def execute(self, action):
        self.tool_calls += 1
        result = self.sandbox.execute(action["command"], timeout=min(60, remaining(self.deadline)))
        artifact = self.store.artifact(canonical({"command": action["command"], **result}))
        self.store.append("tools", {**self.identity, "timestamp": utc(), "artifact": artifact,
                                    "exit_code": result["exit_code"]})
        # Full output retained as artifact; bounded observation prevents context explosion.
        return {**result, "stdout": result["stdout"][-24000:], "stderr": result["stderr"][-8000:],
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
    model = MiniModel(provider, deadline, call_timeout_seconds(cfg))
    environment = MiniEnvironment(sandbox, deadline, store, identity)
    agent = DefaultAgent(model, environment, system_template="", instance_template="", cost_limit=0)
    agent.add_messages({"role": "system", "content": phase_prompt(root, "baseline", "solve")},
                       {"role": "user", "content": task["problem_statement"]})
    outcome, gate_outcome, repairs = None, None, 0
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
    for phase in phases(arm):
        model.phase = phase
        prompt = phase_prompt(root, arm, phase)
        if arm == "spec_kit_aee" and phase in AEE_PHASES:
            prompt += claims_instruction(root, delta=standing_bundle is not None)
        if share_setup and phase == "constitution" and arm != "baseline":
            frozen = campaign_setup(store, setup_key)
            if frozen is not None:
                record = frozen.get("record") or {}
                summary = record.get("summary") if isinstance(record, dict) else None
                agent.add_messages({"role": "user", "content": f"Current phase: {phase}\n{prompt}"},
                                   {"role": "user", "content":
                                    "Campaign setup (constitution) was frozen once for this task "
                                    "and is reused; no new setup calls are made for it. "
                                    "Frozen setup record: "+json.dumps(summary or record)})
                store.append("phases", {**identity, "phase": phase, "timestamp": utc(),
                                        "artifact": frozen["artifact"], "setup_reused": True,
                                        "setup_source_attempt_id": frozen["attempt_id"]})
                continue
        agent.add_messages({"role": "user", "content": f"Current phase: {phase}\n{prompt}"})
        recovery = 0
        while True:
            if (store.root/"CANCEL").exists():
                raise KeyboardInterrupt
            remaining(deadline)
            calls = [c for c in store.events("calls") if c["attempt_id"] == identity["attempt_id"]]
            # Unknown-usage calls (failed physical requests) are charged
            # their full reservation, so the ceiling stays enforceable; a
            # transient provider failure never kills the attempt here.
            used = attempt_token_usage(calls, cfg)
            if used+cfg["max_input_tokens"]+cfg["max_output_tokens"] > cfg["token_cap"]:
                raise LimitHit("next request token reservation exceeds attempt cap")
            if agent.n_calls >= cfg["max_calls"]:
                raise LimitHit("call limit")
            agent.step()
            if model.last["action"] != "done":
                continue
            # Phase completion artifacts are explicit and retained, not inferred from prose.
            artifact = store.artifact(canonical(model.last))
            store.append("phases", {**identity, "phase": phase, "timestamp": utc(), "artifact": artifact})
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
            recovery += 1
            repairs += 1
            agent.add_messages({"role": "user", "content": "Address the result within this phase. Use only task-provided facts; no human assistance. Do not change model. Submit a claims delta scoped to the findings (changed claims as full claim objects under \"delta.upsert\", withdrawals by claim id under \"delta.withdraw\") with revised evidence, or retain gaps."})
    patch = sandbox.execute("git add -N . && git diff --binary HEAD", min(60, remaining(deadline)))
    if patch["exit_code"]:
        raise RuntimeError("patch extraction failed")
    return {"patch": store.artifact(patch["stdout"].encode()), "assessment_outcome": gate_outcome,
            "assessment_headline_outcome": outcome,
            "repair_count": repairs, "tool_calls": environment.tool_calls}


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
            store.append("attempts", {**identity, "status": "started", "timestamp": utc()})
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
            except (BudgetExceeded, LimitHit) as e:
                status, reason = "limit", str(e)
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
            if event is not None and event["behavior"] == HALT_STUDY:
                break
    return store.events("attempts")
