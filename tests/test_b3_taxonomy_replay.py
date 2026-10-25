"""B-3 taxonomy replay: recorded terminal shapes + totality.

The stop policy's worth is that classification is mechanical:
the recorded (status, reason) pair alone decides the class, and
the class alone decides whether the study scores-and-continues
or halts. This suite replays the terminal shapes the program has
actually recorded — at the granularity the campaign records
preserve — and pins two structural properties the historical
suites did not: the classifier is TOTAL (every input, however
garbled, lands in exactly one class and never raises), and the
branch order is specific-before-generic when a reason matches
markers of two classes.

Shapes already pinned elsewhere are not duplicated here: the
wall-expiry protocol variants and the no-drift table live in
tests/test_tripwire_taxonomy.py; the transport deadline shapes
live in tests/test_amendment1_transport.py and
tests/test_cycle1.py.
"""
import pytest

from benchmark_runner.store import Store
from benchmark_runner.tripwires import (
    HALT_STUDY, INTEGRITY, MODEL_OUTCOME, PREMISE_EQUIPMENT,
    SCORE_AND_CONTINUE, SKIP_AND_CONTINUE, UNKNOWN, behavior_for,
    classify_halt, record_tripwire)

CLASSES = {MODEL_OUTCOME, PREMISE_EQUIPMENT, INTEGRITY, UNKNOWN}


# --- Recorded shapes -----------------------------------------------------

def test_stage_b_equipment_stall_replays_to_the_recorded_tripwire():
    # Stage B, baseline leg, attempt 7 (2026-10-23 19:29 EDT,
    # STAGEB-RECORD.md): status "error", TransportStallError /
    # TransportStallSuspected. The recorded tripwire was
    # premise_equipment / infrastructure_error / halt_study, and
    # attempts 8-12 never started.
    assert classify_halt(
        "error", "TransportStallError: TransportStallSuspected") == (
        PREMISE_EQUIPMENT, "infrastructure_error")


def test_stage_b_stall_tripwire_record_halts_the_study(tmp_path):
    store = Store(tmp_path)
    event = record_tripwire(
        store, {"task": "pytest-dev__pytest-5809", "arm": "spec_kit"},
        "error", "TransportStallError: TransportStallSuspected")
    assert event["halt_class"] == PREMISE_EQUIPMENT
    assert event["halt_kind"] == "infrastructure_error"
    assert event["behavior"] == HALT_STUDY


def test_stage_b_phase_terminals_replay_as_model_outcomes():
    # Stage B candidate leg (STAGEB-RECORD.md): terminals all
    # status "limit" — phase_budget_exhausted:<phase> on specify
    # and plan, and the AEE recovery bound. All score; none halts.
    for reason, kind in [
            ("phase_budget_exhausted:specify", "phase_budget_exhausted"),
            ("phase_budget_exhausted:plan", "phase_budget_exhausted"),
            ("AEE recovery bound", "aee_gate_recovery_exhausted")]:
        halt_class, halt_kind = classify_halt("limit", reason)
        assert halt_class == MODEL_OUTCOME
        assert halt_kind == kind
        assert behavior_for("limit", halt_class) == SCORE_AND_CONTINUE


def test_two_consecutive_equipment_terminals_each_halt():
    # The stop policy's leg-level rule is applied by the
    # supervisor over per-attempt behaviors: an equipment terminal
    # halts; a second one after a resume halts again. The
    # classifier owes the supervisor the same answer both times.
    for _ in range(2):
        halt_class, _ = classify_halt(
            "error", "TransportStallError: TransportStallSuspected")
        assert behavior_for("error", halt_class) == HALT_STUDY


# --- Totality --------------------------------------------------------------

STATUSES = ["limit", "error", "cancelled", "skipped",
            "infrastructure_failure", "completed", "", "weird",
            None, 0]
REASONS = ["", None, "attempt_wall_expired", "attempt wall expired",
           "phase_budget_exhausted:specify", "AEE recovery bound",
           "call_outer_bound", "TransportStallError",
           "clean base checkout mismatch", "freeze violated",
           "docker image missing", "no usable temporary directory",
           "🔥" * 50, "x" * 100_000,
           "budget reservation would exceed cap"]


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("reason", REASONS)
def test_classifier_is_total(status, reason):
    halt_class, halt_kind = classify_halt(status, reason)
    assert halt_class in CLASSES
    assert isinstance(halt_kind, str) and halt_kind
    behavior = behavior_for(status, halt_class)
    assert behavior in {SCORE_AND_CONTINUE, HALT_STUDY,
                        SKIP_AND_CONTINUE}


# --- Branch order: specific before generic --------------------------------

def test_wall_token_beats_transport_wording_under_limit():
    # The Cycle 1 failure mode: a wall expiry whose reason also
    # carries transport wording must classify as the model's own
    # disclosed limit, not equipment.
    halt_class, halt_kind = classify_halt(
        "limit", "attempt_wall_expired: provider stream closed")
    assert (halt_class, halt_kind) == (MODEL_OUTCOME,
                                       "attempt_wall_expired")


def test_integrity_marker_beats_premise_marker_under_error():
    halt_class, halt_kind = classify_halt(
        "error", "transport failed: freeze mismatch on resume")
    assert (halt_class, halt_kind) == (
        INTEGRITY, "identity_or_freeze_mismatch")


def test_wall_token_under_error_status_is_not_promoted():
    # The protocol token promotes only under status "limit"; the
    # same words as an error stay an error (here: unclassified,
    # which halts — the safe direction).
    halt_class, _ = classify_halt("error", "attempt_wall_expired")
    assert halt_class != MODEL_OUTCOME
    assert behavior_for("error", halt_class) == HALT_STUDY
