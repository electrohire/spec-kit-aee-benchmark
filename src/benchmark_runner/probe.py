"""Cycle 2 (2026-10-22) capability probe — frozen DESIGN, no inference.

The probe (staged discriminator D3) locates the frozen model's
ceiling before Cycle 3 spends on a binding constraint:

- Probe (i) — direct implementation: the frozen model, plain loop,
  test feedback, per-attempt cap 400,000 tokens, on the probe tasks.
- Probe (ii) — standalone specification: the same model on the same
  tasks, constitution+specify only, per-attempt cap 400,000 tokens,
  completion judged by the mechanical external checklist in this
  module (required sections present and non-empty, self-termination).

This module is the probe's frozen design as code: the task
selection derivation, the two probe configs, the checklist judge,
and the budget accounting. It contains no inference path and no
runner; the coordinator builds the probe freeze from the emitted
registration (``benchmarks/upstream-coding/probe-cycle2-registration.json``)
and runs it under the program-cap guard.

Selection derivation (mechanical, from the benchmark repo's own
selection records): the original plan's rule (Workstream B, B1)
orders FeatureBench Fast v1.1 level-1 instances by the SHA-256 of
``"needle-01:" + instance_id`` ascending, after the pre-named
exclusions, taking the first instances that pass the pre-registered
resource-feasibility check — that produced the campaign's six
(registration-needle-v2 hash ranks 2, 3, 4, 5, 7, 8). The probe set
is that same order EXTENDED PAST the campaign set: the next
feasible instances in hash order, disjoint from the campaign's
six. Every evaluated instance's recorded ``selection_hash_sha256``
is re-verified against the rule here, so the derivation is checked,
not transcribed.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .budget_guard import BudgetGuard

# --- Frozen probe numbers (Cycle 2 plan) -------------------------------------

PROBE_PER_ATTEMPT_CAP_TOKENS = 400_000
PROBE_SUB_BOUND_TOKENS = 4_800_000       # inside Cycle 2's 7,000,000 sub-cap
PROGRAM_CAP_TOKENS = 48_000_000          # the needle program hard cap
PROBE_TASK_COUNT = 6
SELECTION_HASH_PREFIX = "needle-01:"

# The campaign registration this derivation extends.
CAMPAIGN_REGISTRATION = "registration-needle-v2.json"

# Shared frozen model/context facts, copied from the campaign freeze
# (freeze-needle-campaign-v2 config); the probe runs the same frozen
# model on the same wire cap — only the phase plans and the
# per-attempt cap differ.
PROBE_MODEL = "qwen3.8-27b"
PROBE_PROVIDER_BACKEND = "local"
PROBE_MAX_INPUT_TOKENS = 24_576
PROBE_MAX_OUTPUT_TOKENS = 8_192
PROBE_CONTEXT_TOKENS = 32_768


def selection_hash(instance_id):
    """The plan's hash-order key for one instance id."""
    return hashlib.sha256(
        (SELECTION_HASH_PREFIX + instance_id).encode("utf-8")).hexdigest()


def derive_probe_tasks(registration):
    """Derive the probe task list from a campaign registration dict.

    Mechanical steps, in order: (1) re-verify every evaluated
    instance's recorded selection hash against the hash-order rule
    (a mismatch is a data-integrity failure and raises); (2) sort
    the evaluated instances by that hash ascending — the plan's
    hash order; (3) drop the pre-named exclusions; (4) drop every
    instance whose recorded feasibility check did not pass
    (``feasible`` is not True — including instances never
    evaluated, whose feasibility is unrecorded); (5) drop the
    campaign's selected tasks; (6) take the first
    ``PROBE_TASK_COUNT``. Returns the selected evaluated records,
    in hash order.
    """
    campaign_ids = {t["instance_id"] for t in registration["tasks"]}
    excluded_ids = {e["instance_id"] for e in registration.get("exclusions", [])}
    evaluated = list(registration["evaluated_instances"])
    for record in evaluated:
        if selection_hash(record["instance_id"]) != record["selection_hash_sha256"]:
            raise ValueError(
                "selection hash mismatch for %s: the registration's "
                "recorded hash does not reproduce from the plan's rule"
                % record["instance_id"])
    ordered = sorted(evaluated, key=lambda r: r["selection_hash_sha256"])
    selected = []
    for record in ordered:
        if record["instance_id"] in excluded_ids:
            continue
        if (record.get("feasibility") or {}).get("feasible") is not True:
            continue
        if record["instance_id"] in campaign_ids:
            continue
        selected.append(record)
        if len(selected) == PROBE_TASK_COUNT:
            break
    if len(selected) < PROBE_TASK_COUNT:
        raise ValueError(
            "the hash order extended past the campaign set yields only "
            "%d feasible disjoint instances in the registration's "
            "evaluated records; the probe design cannot be frozen "
            "from these records alone" % len(selected))
    return selected


def probe_task_entry(record):
    """One probe task's registration entry: the instance identity
    with every digest the campaign registration records for it."""
    feasibility = record.get("feasibility") or {}
    return {
        "instance_id": record["instance_id"],
        "hash_rank": record["hash_rank"],
        "selection_hash_sha256": record["selection_hash_sha256"],
        "repo": record["repo"],
        "level": record["level"],
        "raw_base_commit": record["base_commit"],
        "prepared_baseline_commit": feasibility.get("prepared_baseline_commit"),
        "prepared_baseline_tree": feasibility.get("prepared_baseline_tree"),
        "solver_image_reference": record["solver_image_reference"],
        "solver_image_id": record["solver_image_id"],
        "solver_image_repo_digests": record["solver_image_repo_digests"],
        "fail_to_pass_test_files": record["fail_to_pass_test_files"],
        "pass_to_pass_test_file_count": record["pass_to_pass_test_file_count"],
        "feasibility": {
            "feasible": feasibility.get("feasible"),
            "offline_preparation_ok": feasibility.get("offline_preparation_ok"),
            "solver_image_audit_pass": feasibility.get("solver_image_audit_pass"),
            "prepared_tree_fail_to_pass_masked":
                feasibility.get("prepared_tree_fail_to_pass_masked"),
            "grader_smoke_pass": (feasibility.get("grader_smoke") or {}).get(
                "grader_smoke_pass"),
        },
    }


# --- The mechanical specification checklist (probe ii) -------------------------
#
# Required sections are the mandatory named sections of the repo's
# own frozen Spec Kit templates (.specify/templates/): the
# constitution template's "Core Principles" and "Governance", and
# the spec template's mandatory "User Scenarios & Testing",
# "Requirements" (with "Functional Requirements") and
# "Success Criteria". A section passes when a heading naming it is
# present AND the body under that heading carries real content —
# at least MIN_SECTION_CONTENT_CHARS non-placeholder characters
# (template bracket placeholders such as [PRINCIPLE_1_NAME] do not
# count as content).

CONSTITUTION_REQUIRED_SECTIONS = ("Core Principles", "Governance")
SPECIFICATION_REQUIRED_SECTIONS = (
    "User Scenarios & Testing", "Requirements", "Functional Requirements",
    "Success Criteria")
MIN_SECTION_CONTENT_CHARS = 10

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")


def _section_bodies(text):
    """The markdown artifact as an ordered list of (level, heading,
    body): a body runs until the next heading of any level."""
    sections = []
    current, body = None, []
    for line in (text or "").splitlines():
        match = _HEADING_RE.match(line)
        if match:
            if current is not None:
                sections.append((*current, "\n".join(body)))
            heading = match.group(0)
            level = len(heading) - len(heading.lstrip("#"))
            current = (level, " ".join(match.group(1).split()).lower())
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections.append((*current, "\n".join(body)))
    return sections


def _section_present(sections, required):
    """(found, content_chars) for one required section: the first
    heading whose text contains the required name counts, and its
    content is its own body plus the bodies of every deeper
    heading nested under it (up to the next heading at its level
    or above) — the constitution template, for example, puts the
    principle text under sub-headings of "Core Principles"."""
    wanted = " ".join(required.split()).lower()
    for index, (level, heading, body) in enumerate(sections):
        if wanted not in heading:
            continue
        parts = [body]
        for next_level, _next_heading, next_body in sections[index + 1:]:
            if next_level <= level:
                break
            parts.append(next_body)
        content = _PLACEHOLDER_RE.sub("", "\n".join(parts))
        chars = len("".join(content.split()))
        return True, chars
    return False, 0


def judge_specification_completion(artifacts, termination):
    """The probe (ii) mechanical external checklist, as code.

    ``artifacts``: {"constitution": text|None, "specification":
    text|None} — the two phase artifacts as written in the
    workspace. ``termination``: {"constitution": how the phase
    ended, "specify": how the phase ended} — completion counts
    only on SELF-TERMINATION: each phase ended by the model's own
    "done" action, not by a limit, an envelope, or an error.

    Returns {"completed": bool, "checks": {...}, "missing": [...]}:
    completed is True exactly when every required section is
    present with real content and both phases self-terminated.
    Judged mechanically from the artifacts alone — no model, no
    inference.
    """
    checks = {}
    missing = []
    for label, text, required in (
            ("constitution", (artifacts or {}).get("constitution"),
             CONSTITUTION_REQUIRED_SECTIONS),
            ("specification", (artifacts or {}).get("specification"),
             SPECIFICATION_REQUIRED_SECTIONS)):
        sections = _section_bodies(text)
        for name in required:
            found, chars = _section_present(sections, name)
            ok = found and chars >= MIN_SECTION_CONTENT_CHARS
            checks[f"{label}:{name}"] = {
                "present": found, "content_chars": chars, "ok": ok}
            if not ok:
                missing.append(f"{label}:{name}")
    for phase in ("constitution", "specify"):
        ended = (termination or {}).get(phase)
        ok = ended == "done"
        checks[f"self_termination:{phase}"] = {"ended_via": ended, "ok": ok}
        if not ok:
            missing.append(f"self_termination:{phase}")
    return {"completed": not missing, "checks": checks, "missing": missing}


# --- Probe configs -------------------------------------------------------------

def probe_configs(task_ids):
    """The two frozen probe configs over ``task_ids``.

    Both configs refuse campaign task ids (see
    ``validate_probe_task_ids`` — the caller validates before
    freezing); this builder only shapes the configs.
    """
    shared = {
        "model": PROBE_MODEL,
        "provider_backend": PROBE_PROVIDER_BACKEND,
        "context_tokens": PROBE_CONTEXT_TOKENS,
        "max_input_tokens": PROBE_MAX_INPUT_TOKENS,
        "max_output_tokens": PROBE_MAX_OUTPUT_TOKENS,
        "per_attempt_cap_tokens": PROBE_PER_ATTEMPT_CAP_TOKENS,
        "tasks": list(task_ids),
    }
    return {
        "probe_i_direct_implementation": {
            **shared,
            "probe": "direct_implementation",
            "arm": "baseline",
            "phases": ["solve"],
            "loop": "plain",
            "test_feedback": True,
            "measures": ["completion_rate", "time_to_first_edit",
                         "tokens_per_completion"],
        },
        "probe_ii_standalone_specification": {
            **shared,
            "probe": "standalone_specification",
            "arm": "spec_kit",
            "phases": ["constitution", "specify"],
            "loop": "constitution+specify only",
            "test_feedback": False,
            "completion_judge": "mechanical_specification_checklist",
            "checklist": {
                "constitution_required_sections":
                    list(CONSTITUTION_REQUIRED_SECTIONS),
                "specification_required_sections":
                    list(SPECIFICATION_REQUIRED_SECTIONS),
                "min_section_content_chars": MIN_SECTION_CONTENT_CHARS,
                "self_termination": "each phase ended by the model's own "
                                    "done action",
                "judge": "benchmark_runner.probe.judge_specification_completion",
            },
            "measures": ["completion_rate", "cost_distribution_censoring_aware"],
        },
    }


def validate_probe_task_ids(task_ids, campaign_task_ids):
    """Refuse to freeze a probe over a campaign task: the probe set
    is disjoint from the campaign's six BY DESIGN, and any config
    naming a campaign task id — or a duplicate, or the wrong
    count — is rejected before any probe inference can be built
    on it."""
    ids = list(task_ids)
    overlap = sorted(set(ids) & set(campaign_task_ids))
    if overlap:
        raise ValueError(
            "probe tasks overlap the campaign set (forbidden — the "
            "probe is disjoint by design): %s" % overlap)
    if len(ids) != PROBE_TASK_COUNT or len(set(ids)) != len(ids):
        raise ValueError(
            "probe task list must hold exactly %d distinct ids, got %d"
            % (PROBE_TASK_COUNT, len(ids)))
    return ids


def build_probe_registration(registration):
    """Assemble the probe registration dict from a campaign
    registration dict: derivation record, task list with digests,
    both configs, and the budget accounting. Pure and
    deterministic — the committed probe registration file must
    equal this function's output on the campaign registration."""
    campaign_ids = [t["instance_id"] for t in registration["tasks"]]
    records = derive_probe_tasks(registration)
    task_ids = validate_probe_task_ids(
        [r["instance_id"] for r in records], campaign_ids)
    skipped = []
    campaign = set(campaign_ids)
    excluded = {e["instance_id"] for e in registration.get("exclusions", [])}
    for record in sorted(registration["evaluated_instances"],
                         key=lambda r: r["selection_hash_sha256"]):
        if record["instance_id"] in task_ids:
            continue
        if record["instance_id"] in excluded:
            reason = "pre-named exclusion (plan B1)"
        elif (record.get("feasibility") or {}).get("feasible") is not True:
            reason = "recorded feasibility check did not pass"
        elif record["instance_id"] in campaign:
            reason = "campaign task (probe set is disjoint)"
        else:
            reason = "past the probe set in hash order"
        skipped.append({"hash_rank": record["hash_rank"],
                        "instance_id": record["instance_id"],
                        "reason": reason})
    worst_case = 2 * PROBE_TASK_COUNT * PROBE_PER_ATTEMPT_CAP_TOKENS
    return {
        "schema": "needle-cycle2-probe-registration-v1",
        "status": "DESIGN FROZEN (Cycle 2 offline phase; no probe "
                  "inference has run or is authorized by this file — "
                  "the coordinator runs the probe under its own freeze)",
        "probe": "Cycle 2 capability probe (discriminator D3): "
                 "direct implementation vs standalone specification, "
                 "same frozen model, same tasks",
        "derivation": {
            "rule": "Order the Fast v1.1 level-1 instances by the "
                    "SHA-256 of \"needle-01:\" + instance_id (UTF-8, "
                    "ascending hex), after the pre-named exclusions; "
                    "take the first instances passing the recorded "
                    "resource-feasibility check; the campaign took the "
                    "first six — the probe takes the NEXT six in the "
                    "same order (extended past the campaign set), "
                    "disjoint from the campaign's six.",
            "source_registration": CAMPAIGN_REGISTRATION,
            "campaign_hash_ranks": [t["hash_rank"] for t in registration["tasks"]],
            "probe_hash_ranks": [r["hash_rank"] for r in records],
            "selection_hashes_reverified": True,
            "skipped_in_hash_order": skipped,
            "note": "Instances whose feasibility was never evaluated "
                    "(feasible is not True in the records) are not "
                    "eligible: the probe freezes only on instances "
                    "the records prove feasible. Problem statements "
                    "and prepared solver images for the probe tasks "
                    "are produced at the coordinator's probe freeze "
                    "from the pinned dataset, exactly as the campaign "
                    "freeze produced them for the campaign six; they "
                    "are not part of the campaign registration's "
                    "evaluated records and are not invented here.",
        },
        "tasks": [probe_task_entry(r) for r in records],
        "configs": probe_configs(task_ids),
        "budget": {
            "per_attempt_cap_tokens": PROBE_PER_ATTEMPT_CAP_TOKENS,
            "probe_attempts": 2 * PROBE_TASK_COUNT,
            "worst_case_probe_tokens": worst_case,
            "probe_sub_bound_tokens": PROBE_SUB_BOUND_TOKENS,
            "worst_case_within_sub_bound": worst_case <= PROBE_SUB_BOUND_TOKENS,
            "program_cap_tokens": PROGRAM_CAP_TOKENS,
            "accounting": "Probe spend is charged through "
                          "benchmark_runner.budget_guard.BudgetGuard "
                          "with the probe store as the stage store "
                          "(stage cap = the probe sub-bound) and all "
                          "prior program stores as prior stores "
                          "(program cap = 48,000,000): probe tokens "
                          "count against BOTH caps. See "
                          "benchmark_runner.probe.probe_budget_verdict.",
        },
        "does_not_establish": "Anything about the campaign arms' "
                              "relative merit — the probe locates the "
                              "model's ceiling so Cycle 3 spends on "
                              "the binding constraint.",
    }


def probe_budget_verdict(probe_store, prior_stores=()):
    """Probe budget accounting wired into the program-cap guard:
    the probe store is charged as the guard's stage store under
    the probe sub-bound, and every prior program store counts
    toward the 48,000,000 program cap. Returns the guard's verdict
    with the probe-named keys added."""
    guard = BudgetGuard(probe_store, prior_stores=prior_stores,
                        stage_cap=PROBE_SUB_BOUND_TOKENS,
                        program_cap=PROGRAM_CAP_TOKENS)
    verdict = guard.verdict()
    verdict["probe_tokens"] = verdict["stage_tokens"]
    verdict["probe_sub_bound_tokens"] = PROBE_SUB_BOUND_TOKENS
    verdict["probe_sub_bound_reached"] = verdict["stage_cap_reached"]
    return verdict


def load_campaign_registration(root):
    """Read the campaign registration the probe derivation extends."""
    path = Path(root) / "benchmarks" / "upstream-coding" / CAMPAIGN_REGISTRATION
    return json.loads(path.read_text(encoding="utf-8"))
