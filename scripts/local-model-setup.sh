#!/usr/bin/env bash
# Serve an 8B-class model on the RTX 5060 Ti for the Claim A local-parity campaign.
#
# Runs on Tristen's WSL2 host (NOT the managed VM). Steps:
#   1. Finds llama-server (uses LLAMA_CPP_DIR or PATH; downloads the latest
#      CUDA release from GitHub if missing).
#   2. Downloads the GGUF checkpoint (default: Qwen3-8B Q4_K_M; override with
#      MODEL_URL).
#   3. Pins the server to the RTX 5060 Ti via CUDA_VISIBLE_DEVICES, leaving
#      the 4070 SUPER free.
#   4. Smoke-tests the OpenAI-compatible endpoint.
#
# After this script prints the export lines, paste them into the shell that
# will run scripts/host-setup.sh for the Claim A campaign.
set -euo pipefail

PORT="${PORT:-8080}"
CTX="${CTX:-32768}"
MODEL_DIR="${MODEL_DIR:-$HOME/models}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/bartowski/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf}"
LOCAL_MODEL_NAME="${LOCAL_MODEL_NAME:-qwen3-8b-local}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-}"

echo "== GPUs =="
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
# Pick the 5060 Ti: the 16GB card. Fall back to the highest-memory GPU.
GPU_INDEX="$(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits \
  | awk -F', ' '{print $1, $3, $2}' | sort -k2 -nr | head -1 | awk '{print $1}')"
GPU_NAME="$(nvidia-smi --query-gpu=index,name --format=csv,noheader,nounits | awk -F', ' -v i="$GPU_INDEX" '$1==i{print $2}')"
echo "Selected GPU index $GPU_INDEX ($GPU_NAME)"

echo "== llama-server =="
if [ -n "$LLAMA_CPP_DIR" ] && [ -x "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
  SERVER="$LLAMA_CPP_DIR/build/bin/llama-server"
elif command -v llama-server >/dev/null 2>&1; then
  SERVER="$(command -v llama-server)"
else
  echo "llama-server not found; downloading latest CUDA release..."
  # NOTE: never pipe curl directly into grep -m1/head under `set -o pipefail`:
  # when the reader exits early, curl dies with error 23 (SIGPIPE) and the
  # script aborts even though the tag was already captured. Download to a
  # temp file first instead.
  TAG_JSON="$(mktemp)"
  curl -fsSL -o "$TAG_JSON" https://api.github.com/repos/ggml-org/llama.cpp/releases/latest
  TAG="$(grep -m1 '"tag_name"' "$TAG_JSON" | cut -d'"' -f4)"
  rm -f "$TAG_JSON"
  [ -n "$TAG" ] || { echo "could not resolve latest llama.cpp release"; exit 1; }
  mkdir -p "$HOME/llama.cpp-release"
  cd "$HOME/llama.cpp-release"
  curl -fSL -o llama.zip "https://github.com/ggml-org/llama.cpp/releases/download/${TAG}/llama-${TAG}-bin-ubuntu-x64.zip"
  unzip -o -q llama.zip
  SERVER="$HOME/llama.cpp-release/build/bin/llama-server"
  [ -x "$SERVER" ] || { echo "downloaded release has no build/bin/llama-server"; exit 1; }
fi
echo "Using: $SERVER"
"$SERVER" --version 2>&1 | head -2 || echo "WARNING: could not query server version"

echo "== model =="
mkdir -p "$MODEL_DIR"
MODEL_FILE="$MODEL_DIR/$(basename "$MODEL_URL")"
if [ ! -f "$MODEL_FILE" ]; then
  echo "Downloading $(basename "$MODEL_URL") ..."
  curl -fSL --retry 3 -o "$MODEL_FILE" "$MODEL_URL"
else
  echo "Already present: $MODEL_FILE"
fi
ls -lh "$MODEL_FILE"

# If a healthy server is already on the port serving the expected model, reuse it.
# Capture to a variable first: piping curl straight into grep -q can SIGPIPE
# (curl error 23) when grep exits on first match, which would wrongly report
# the server as not running and launch a duplicate.
MODELS_JSON="$(curl -fsS "http://localhost:${PORT}/v1/models" 2>/dev/null || true)"
if printf '%s' "$MODELS_JSON" | grep -q "\"id\":\"${LOCAL_MODEL_NAME}\""; then
  echo "Server already running on port $PORT serving ${LOCAL_MODEL_NAME}; reusing it."
else
  echo "== launching server on GPU $GPU_INDEX =="
  LOG="$MODEL_DIR/llama-server-${PORT}.log"
  CUDA_VISIBLE_DEVICES="$GPU_INDEX" nohup "$SERVER" \
    -m "$MODEL_FILE" \
    --port "$PORT" \
    --ctx-size "$CTX" \
    -ngl 99 \
    --alias "$LOCAL_MODEL_NAME" \
    >"$LOG" 2>&1 &
  echo "Log: $LOG (tail it if the smoke test fails)"
  for i in $(seq 1 60); do
    if curl -fsS "http://localhost:${PORT}/v1/models" >/dev/null 2>&1; then break; fi
    sleep 2
  done
fi

echo "== smoke test =="
curl -fsS "http://localhost:${PORT}/v1/models"
echo
RESP="$(curl -fsS "http://localhost:${PORT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${LOCAL_MODEL_NAME}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: ok\"}],\"max_completion_tokens\":16}")"
echo "$RESP" | head -c 400; echo
echo "$RESP" | grep -q '"id":"'"$LOCAL_MODEL_NAME"'"' || echo "WARNING: server reports a different model id than LOCAL_MODEL_NAME"

echo
echo "== done. Export these in the campaign shell: =="
echo "export LOCAL_MODEL_BASE_URL=\"http://localhost:${PORT}/v1\""
echo "export LOCAL_MODEL_NAME=\"${LOCAL_MODEL_NAME}\""
