"""Tripwire taxonomy: Amendment 1 (2026-10-21) phase-budget guard.

The phase-budget guard ends an attempt with status ``limit`` and
the protocol reason token ``phase_budget_exhausted:<phase>`` when a
phase exhausts its budget envelope. That reason contains the word
"budget", so without an explicit earlier branch in
``classify_halt`` it would fall into the pre-existing
``"budget" in low`` rule and halt the study as a campaign-budget
premise fault instead of scoring as a model outcome.

These tests pin:

- the protocol token (colon form, bare form, and space form) as a
  proven model outcome that scores and continues;
- the trap regression: natural wording such as "phase budget
  exhausted" must NOT classify as phase-budget exhaustion — the
  protocol token is load-bearing, and natural wording still falls
  to the campaign-budget rule and halts the study;
- every pre-existing classification the amendment must not disturb.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest

from benchmark_runner.store import Store
from benchmark_runner.tripwires import (
    ATTEMPT_WALL_EXPIRED,
    HALT_STUDY,
    INTEGRITY,
    MODEL_OUTCOME,
    PHASE_BUDGET_EXHAUSTED,
    PREMISE_EQUIPMENT,
    SCORE_AND_CONTINUE,
    UNKNOWN,
    attempt_wall_expiry_reason,
    behavior_for,
    classify_halt,
    phase_exhaustion_reason,
    record_tripwire,
)


def _classify_and_behavior(status, reason):
    halt_class, halt_kind = classify_halt(status, reason)
    return halt_class, halt_kind, behavior_for(status, halt_class)


# --- Amendment 1: the protocol token -----------------------------------------

def test_phase_budget_exhausted_constant_and_helper():
    assert PHASE_BUDGET_EXHAUSTED == "phase_budget_exhausted"
    assert phase_exhaustion_reason("constitution") == (
        "phase_budget_exhausted:constitution")
    assert phase_exhaustion_reason("repair") == "phase_budget_exhausted:repair"


def test_phase_budget_exhausted_with_phase_is_model_outcome():
    assert _classify_and_behavior(
        "limit", "phase_budget_exhausted:constitution") == (
            MODEL_OUTCOME, "phase_budget_exhausted", SCORE_AND_CONTINUE)


def test_phase_budget_exhausted_bare_is_model_outcome():
    assert _classify_and_behavior("limit", "phase_budget_exhausted") == (
        MODEL_OUTCOME, "phase_budget_exhausted", SCORE_AND_CONTINUE)


@pytest.mark.parametrize("reason", [
    "phase_budget_exhausted constitution",
    "phase_budget_exhausted:repair",
    # Classification derives from the normalized lowercase reason.
    "PHASE_BUDGET_EXHAUSTED:constitution",
    "  phase_budget_exhausted:constitution  ",
])
def test_phase_budget_exhausted_protocol_variants(reason):
    assert _classify_and_behavior("limit", reason) == (
        MODEL_OUTCOME, "phase_budget_exhausted", SCORE_AND_CONTINUE)


def test_phase_exhaustion_reason_round_trips_through_classifier():
    reason = phase_exhaustion_reason("constitution")
    assert classify_halt("limit", reason) == (
        MODEL_OUTCOME, PHASE_BUDGET_EXHAUSTED)


# --- The trap regression: natural wording is not the protocol token ----------

def test_natural_wording_phase_budget_exhausted_is_not_protocol_token():
    """Documented behavior proving the protocol token is load-bearing:
    "phase budget exhausted" (spaces, no underscores) contains
    "budget", so it falls to the pre-existing budget rule —
    premise_equipment / campaign_budget_exceeded / halt_study —
    and must never be promoted to the phase-budget model outcome."""
    halt_class, halt_kind, behavior = _classify_and_behavior(
        "limit", "phase budget exhausted")
    assert (halt_class, halt_kind) != (MODEL_OUTCOME, "phase_budget_exhausted")
    assert (halt_class, halt_kind, behavior) == (
        PREMISE_EQUIPMENT, "campaign_budget_exceeded", HALT_STUDY)


# --- Cycle 2 C2-F1: the attempt-wall-expiry protocol token -------------------
#
# The branch order is pinned here: the wall token classifies as a
# scored model outcome through its explicit branch, placed before
# the generic transport rules — the rules whose markers classified
# Cycle 1's wall-killed flowing call (an "error" record carrying
# provider/transport wording) as an infrastructure halt.

def test_attempt_wall_expired_constant_and_helper():
    assert ATTEMPT_WALL_EXPIRED == "attempt_wall_expired"
    assert attempt_wall_expiry_reason() == "attempt_wall_expired"


def test_attempt_wall_expired_is_model_outcome_and_continues():
    assert _classify_and_behavior("limit", "attempt_wall_expired") == (
        MODEL_OUTCOME, "attempt_wall_expired", SCORE_AND_CONTINUE)


@pytest.mark.parametrize("reason", [
    "attempt_wall_expired: plan",
    "attempt_wall_expired plan",
    "ATTEMPT_WALL_EXPIRED",
    "  attempt_wall_expired  ",
])
def test_attempt_wall_expired_protocol_variants(reason):
    assert _classify_and_behavior("limit", reason) == (
        MODEL_OUTCOME, "attempt_wall_expired", SCORE_AND_CONTINUE)


def test_attempt_wall_token_wins_over_budget_wording():
    # Branch order within "limit": the explicit wall branch fires
    # before the campaign-budget rule even when the reason carries
    # budget wording after the token.
    assert _classify_and_behavior(
        "limit", "attempt_wall_expired: budget of wall time spent") == (
            MODEL_OUTCOME, "attempt_wall_expired", SCORE_AND_CONTINUE)


def test_attempt_wall_natural_wording_is_not_the_protocol_token():
    # "attempt wall expired" (spaces, no underscores) must NOT
    # reach the wall branch: as a limit it falls through to the
    # generic disclosed limit (a different kind), and as an error
    # carrying transport wording it still hits the generic
    # transport rules and halts — the token is load-bearing.
    assert _classify_and_behavior("limit", "attempt wall expired") == (
        MODEL_OUTCOME, "disclosed_limit_reached", SCORE_AND_CONTINUE)
    assert _classify_and_behavior(
        "error", "attempt wall expired: transport timeout from provider") == (
            PREMISE_EQUIPMENT, "infrastructure_error", HALT_STUDY)


def test_attempt_wall_token_under_error_status_is_not_promoted():
    # The branch is scoped to status "limit": the same token on an
    # error record does not become a model outcome.
    halt_class, halt_kind, behavior = _classify_and_behavior(
        "error", "attempt_wall_expired")
    assert (halt_class, halt_kind) != (MODEL_OUTCOME, "attempt_wall_expired")
    assert behavior == HALT_STUDY


def test_record_tripwire_attempt_wall_expired(tmp_path):
    store = Store(tmp_path / "run")
    identity = {"attempt_id": "att-1", "arm": "spec_kit", "task_id": "task-1"}
    event = record_tripwire(store, identity, "limit",
                            attempt_wall_expiry_reason())
    assert event["halt_class"] == MODEL_OUTCOME
    assert event["halt_kind"] == "attempt_wall_expired"
    assert event["behavior"] == SCORE_AND_CONTINUE
    (stored,) = store.events("tripwires")
    assert stored["halt_kind"] == "attempt_wall_expired"


# --- Pre-existing limit classifications, unchanged ---------------------------

def test_disclosed_limit_reached_unchanged():
    assert _classify_and_behavior(
        "limit", "next request token reservation exceeds attempt cap") == (
            MODEL_OUTCOME, "disclosed_limit_reached", SCORE_AND_CONTINUE)


def test_aee_recovery_bound_unchanged():
    assert _classify_and_behavior("limit", "AEE recovery bound") == (
        MODEL_OUTCOME, "aee_gate_recovery_exhausted", SCORE_AND_CONTINUE)


def test_campaign_budget_reason_unchanged():
    assert _classify_and_behavior("limit", "campaign budget exceeded") == (
        PREMISE_EQUIPMENT, "campaign_budget_exceeded", HALT_STUDY)


def test_reservation_would_exceed_cap_unchanged():
    assert _classify_and_behavior(
        "limit", "next request reservation would exceed cap") == (
            PREMISE_EQUIPMENT, "campaign_budget_exceeded", HALT_STUDY)


# --- Representative sweep of the pre-existing taxonomy -----------------------

@pytest.mark.parametrize("status,reason,halt_class,halt_kind,behavior", [
    ("cancelled", "operator interrupt",
     PREMISE_EQUIPMENT, "operator_interrupt", HALT_STUDY),
    ("infrastructure_failure", "interrupted; no automatic rerun",
     UNKNOWN, "interrupted_attempt", HALT_STUDY),
    ("error", "freeze mismatch against the recorded configuration",
     INTEGRITY, "identity_or_freeze_mismatch", HALT_STUDY),
    ("error", "solver image does not contain a clean base checkout",
     INTEGRITY, "identity_or_freeze_mismatch", HALT_STUDY),
    ("error", "transport error contacting the provider",
     PREMISE_EQUIPMENT, "infrastructure_error", HALT_STUDY),
    ("error", "something opaque happened",
     UNKNOWN, "unclassified_error", HALT_STUDY),
    ("skipped", "pre-skipped: diagnostic evidence not recorded",
     PREMISE_EQUIPMENT, "prerequisite_evidence_missing", "skip_and_continue"),
])
def test_pre_existing_taxonomy_no_drift(status, reason, halt_class,
                                         halt_kind, behavior):
    assert _classify_and_behavior(status, reason) == (
        halt_class, halt_kind, behavior)


# --- record_tripwire against a real Store ------------------------------------

def test_record_tripwire_phase_budget_exhausted(tmp_path):
    store = Store(tmp_path / "run")
    identity = {"attempt_id": "att-1", "arm": "baseline", "task_id": "task-1"}
    event = record_tripwire(store, identity, "limit",
                            "phase_budget_exhausted:constitution")
    assert event["halt_class"] == MODEL_OUTCOME
    assert event["halt_kind"] == "phase_budget_exhausted"
    assert event["behavior"] == SCORE_AND_CONTINUE
    assert event["behavior_changed"] is True
    (stored,) = store.events("tripwires")
    assert stored["attempt_id"] == "att-1"
    assert stored["status"] == "limit"
    assert stored["reason"] == "phase_budget_exhausted:constitution"
    assert stored["halt_class"] == MODEL_OUTCOME
    assert stored["halt_kind"] == "phase_budget_exhausted"
    assert stored["behavior"] == SCORE_AND_CONTINUE


def test_record_tripwire_natural_wording_halts(tmp_path):
    store = Store(tmp_path / "run")
    identity = {"attempt_id": "att-1", "arm": "baseline", "task_id": "task-1"}
    event = record_tripwire(store, identity, "limit", "phase budget exhausted")
    assert event["halt_class"] == PREMISE_EQUIPMENT
    assert event["halt_kind"] == "campaign_budget_exceeded"
    assert event["behavior"] == HALT_STUDY
    (stored,) = store.events("tripwires")
    assert stored["halt_kind"] == "campaign_budget_exceeded"
    assert stored["behavior"] == HALT_STUDY


def test_record_tripwire_completed_writes_nothing(tmp_path):
    store = Store(tmp_path / "run")
    identity = {"attempt_id": "att-1", "arm": "baseline", "task_id": "task-1"}
    assert record_tripwire(store, identity, "completed", None) is None
    assert store.events("tripwires") == []
