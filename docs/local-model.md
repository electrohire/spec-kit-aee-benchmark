# Local inference backend (Claim A)

The benchmark harness can run a campaign against a local OpenAI-compatible
server (llama.cpp) instead of the OpenAI API. Local calls cost zero marginal
dollars; the budget ledger records a zero reservation per call so every call
is still tracked, and evidence events carry `cost_basis: "local_inference"`.

## Operator setup (WSL2 host)

```bash
bash scripts/local-model-setup.sh
```

The script serves an 8B-class checkpoint on the RTX 5060 Ti (leaving the 4070
SUPER free), smoke-tests the endpoint, and prints the exports the campaign
shell needs:

```bash
export LOCAL_MODEL_BASE_URL="http://localhost:8080/v1"
export LOCAL_MODEL_NAME="qwen3-8b-local"
```

Overrides: `MODEL_URL` (different checkpoint), `PORT`, `CTX`,
`LLAMA_CPP_DIR` (existing llama.cpp build), `CUDA_VISIBLE_DEVICES` selection
is automatic (highest-VRAM GPU).

To fall back to the 32B split model across both GPUs, serve it with llama.cpp
normally and point `LOCAL_MODEL_BASE_URL` at it; nothing in the harness
changes.

## Campaign wiring

The frozen `configs/experiment.yaml` selects the backend:

```yaml
provider_backend: "local"   # or "openai" (default)
```

Fail-closed behavior, all preserved for local runs:

- `validate_live()` probes the server and requires the reported model id to
  match `LOCAL_MODEL_NAME`; a wrong checkpoint or a down server aborts before
  any attempt.
- `verify_reservation_bounds()` returns zero bounds for local configs.
- `LocalProvider` sends no OpenAI-only parameters (`reasoning_effort`,
  `service_tier`) and records `response_model` as observed.
- Telemetry identity is validated before the HTTP request, exactly as with
  the OpenAI provider.

## What the setup script does not do

It does not pick the checkpoint for you beyond the default (Qwen3-8B Q4_K_M).
If the 8B model floors on the shared task bank, the 32B split fallback is a
campaign decision recorded in the v9 design doc, not a script change.
