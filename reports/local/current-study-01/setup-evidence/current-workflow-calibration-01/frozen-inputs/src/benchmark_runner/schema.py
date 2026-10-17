"""Public telemetry contract, independent from provider response schema."""
import jsonschema

# Every arm the provider can log. The enum must cover every arm, otherwise paid
# calls fail telemetry validation AFTER the HTTP request (money spent, call
# never logged, budget never settled). provider.query() additionally validates
# the identity up front so such a mismatch fails fast before any spend.
ARM_ENUM = ["baseline", "spec_kit", "spec_kit_aee",
            "diagnose", "repair_ordinary", "repair_guided", "repair_workflow"]

CALL_SCHEMA = {
    "type": "object",
    "required": ["experiment_id", "run_id", "arm", "task_id", "repeat", "attempt_id", "phase",
                 "call_id", "request_id", "provider", "model", "response_model", "started_at", "ended_at",
                 "duration_seconds", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                 "unknown_reason", "price_snapshot_id", "cost_basis", "currency", "cost", "retry", "error", "artifacts"],
    "properties": {
        # Main-experiment arms plus the matched-repair cloud-port arms.
        "arm": {"enum": ARM_ENUM},
        "repeat": {"type": "integer", "minimum": 1},
        "duration_seconds": {"type": "number", "minimum": 0},
        "retry": {"type": "integer", "minimum": 0},
        "currency": {"const": "USD"},
        "cost_basis": {"enum": ["list_price_estimate", "local_inference"]},
        "cost": {"type": ["string", "null"]},
        **{k: {"type": ["integer", "null"], "minimum": 0} for k in
           ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")},
    },
}


def validate_call(call):
    jsonschema.validate(call, CALL_SCHEMA)
    from .accounting import validate_usage
    validate_usage(call)


# The telemetry fields known before any HTTP request. provider.query()
# validates these up front so a schema/arm mismatch raises before money is
# spent, rather than after the request when the call can no longer be logged.
IDENTITY_SCHEMA = {
    "type": "object",
    "required": ["experiment_id", "run_id", "arm", "task_id", "repeat", "attempt_id", "phase"],
    "properties": {
        "arm": {"enum": ARM_ENUM},
        "repeat": {"type": "integer", "minimum": 1},
        "phase": {"type": "string"},
    },
}


def validate_identity(identity):
    jsonschema.validate(identity, IDENTITY_SCHEMA)
