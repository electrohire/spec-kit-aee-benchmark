"""Public telemetry contract, independent from provider response schema."""
import jsonschema

CALL_SCHEMA = {
    "type": "object",
    "required": ["experiment_id", "run_id", "arm", "task_id", "repeat", "attempt_id", "phase",
                 "call_id", "request_id", "provider", "model", "response_model", "started_at", "ended_at",
                 "duration_seconds", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                 "unknown_reason", "price_snapshot_id", "cost_basis", "currency", "cost", "retry", "error", "artifacts"],
    "properties": {
        "arm": {"enum": ["baseline", "spec_kit", "spec_kit_aee"]},
        "repeat": {"type": "integer", "minimum": 1},
        "duration_seconds": {"type": "number", "minimum": 0},
        "retry": {"type": "integer", "minimum": 0},
        "currency": {"const": "USD"},
        "cost_basis": {"const": "list_price_estimate"},
        "cost": {"type": ["string", "null"]},
        **{k: {"type": ["integer", "null"], "minimum": 0} for k in
           ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")},
    },
}


def validate_call(call):
    jsonschema.validate(call, CALL_SCHEMA)
    from .accounting import validate_usage
    validate_usage(call)
