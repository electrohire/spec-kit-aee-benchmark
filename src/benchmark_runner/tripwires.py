"""Tripwire records: every halt classified under the shared taxonomy.

Protocol amendment 2026-10-20, PC-4. A halt is classified as exactly
one of:

- ``model_outcome`` — the measured result of the model's own work:
  the AEE gate's recovery bound was exhausted, or a disclosed limit
  (wall time, call count, attempt token reservation) was reached.
- ``premise_equipment`` — the run's premises or equipment failed, or
  the operator stopped it: campaign budget, an operator interrupt, a
  missing prerequisite, an infrastructure or transport error.
- ``integrity`` — an identity or freeze fact did not check out: the
  solver image is not the clean base checkout, a freeze or resume
  configuration mismatch.
- ``unknown`` — anything else, including interrupted attempts whose
  cause was never established. Unknown is an honest class, not a
  rounding bucket: a halt whose cause is not established is never
  promoted into a model outcome.

Recording only. Classification never changes when the workflow
stops, what it stops, or any status a run reports; whether a known
model outcome may end only its own trajectory is the owner's pending
stop-policy decision and is not pre-empted here.
"""
from .store import utc

MODEL_OUTCOME = "model_outcome"
PREMISE_EQUIPMENT = "premise_equipment"
INTEGRITY = "integrity"
UNKNOWN = "unknown"

_INTEGRITY_MARKERS = ("clean base checkout", "freeze", "resume configuration mismatch")
_PREMISE_MARKERS = ("docker", "image", "provider", "transport", "connection",
                    "sandbox", "patch extraction", "credential", "no usable temporary")


def classify_halt(status, reason):
    """Classify one attempt halt as (halt_class, halt_kind).

    ``status`` and ``reason`` are the run record's own values; the
    classification derives from them alone, so any recorded halt —
    including one written before this module existed — classifies
    the same way.
    """
    text = " ".join(str(reason or "").split())
    low = text.lower()
    if status == "limit":
        if text == "AEE recovery bound":
            return MODEL_OUTCOME, "aee_gate_recovery_exhausted"
        if "budget" in low or "reservation would exceed cap" in low:
            return PREMISE_EQUIPMENT, "campaign_budget_exceeded"
        return MODEL_OUTCOME, "disclosed_limit_reached"
    if status == "cancelled":
        return PREMISE_EQUIPMENT, "operator_interrupt"
    if status == "infrastructure_failure":
        return UNKNOWN, "interrupted_attempt"
    if status == "skipped":
        return PREMISE_EQUIPMENT, "prerequisite_evidence_missing"
    if status == "error":
        if any(marker in low for marker in _INTEGRITY_MARKERS):
            return INTEGRITY, "identity_or_freeze_mismatch"
        if any(marker in low for marker in _PREMISE_MARKERS):
            return PREMISE_EQUIPMENT, "infrastructure_error"
        return UNKNOWN, "unclassified_error"
    return UNKNOWN, "unclassified_status"


def record_tripwire(store, identity, status, reason):
    """Append the tripwire event for an attempt that ended other
    than completed. Returns the event, or None for a completion."""
    if status == "completed":
        return None
    halt_class, halt_kind = classify_halt(status, reason)
    event = {**identity, "status": status, "reason": reason,
             "halt_class": halt_class, "halt_kind": halt_kind,
             "behavior_changed": False, "timestamp": utc()}
    store.append("tripwires", event)
    return event
