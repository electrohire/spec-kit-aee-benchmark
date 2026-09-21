#!/usr/bin/env bash
# Serve an 8B-class model on the RTX 5060 Ti for the Claim A local-parity campaign.
#
# Runs on Tristen's WSL2 host (NOT the managed VM). Steps:
#   1. Finds llama-server (uses LLAMA_CPP_DIR or PATH; otherwise downloads the
#      newest bNNNNN pre-release CUDA bundle from ggml-org/llama.cpp plus the
#      matching cudart bundle when the system lacks libcublas, e.g. on WSL2).
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
MODEL_URL="${MODEL_URL:-https://huggingface.co/unsloth/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf}"
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
# Pin the resolved server + CUDA runtime lib path across runs so a re-run
# never re-downloads ~700 MB. Delete this file to force a fresh resolve.
REL_ENV="$HOME/llama.cpp-release/env.sh"
if [ -n "$LLAMA_CPP_DIR" ] && [ -x "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
  SERVER="$LLAMA_CPP_DIR/build/bin/llama-server"
elif command -v llama-server >/dev/null 2>&1; then
  SERVER="$(command -v llama-server)"
elif [ -f "$REL_ENV" ]; then
  # shellcheck disable=SC1090
  . "$REL_ENV" # sets SERVER and LD_LIBRARY_PATH from a previous download
  echo "Reusing: $SERVER"
else
  echo "llama-server not found; downloading a CUDA prebuilt release..."
  # Binaries ship as bNNNNN pre-releases; the "latest" stable (currently
  # v0.4.1) carries no binaries. Take the newest build tag with a CUDA
  # ubuntu-x64 asset. (Never pipe curl into an early-exiting reader under
  # `set -o pipefail`: curl dies with error 23/SIGPIPE and kills the script.)
  LLAMA_TAG="${LLAMA_TAG:-}"
  CUDA_VER="${CUDA_VER:-12.8}"
  if [ -z "$LLAMA_TAG" ]; then
    REL_JSON="$(mktemp)"
    curl -fsSL -o "$REL_JSON" "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=25"
    LLAMA_TAG="$(python3 - "$REL_JSON" "$CUDA_VER" <<'PYEOF'
import json, re, sys
rels = json.load(open(sys.argv[1]))
cuda_ver = sys.argv[2]
for r in rels:
    t = r.get('tag_name', '')
    want = 'llama-%s-bin-ubuntu-cuda-%s-x64.tar.gz' % (t, cuda_ver)
    if re.fullmatch(r'b\d+', t) and any(a.get('name') == want for a in r.get('assets', [])):
        print(t)
        break
PYEOF
)"
    rm -f "$REL_JSON"
  fi
  [ -n "$LLAMA_TAG" ] || { echo "could not resolve a llama.cpp build tag with CUDA binaries"; exit 1; }
  echo "Build tag: $LLAMA_TAG (CUDA $CUDA_VER)"
  BUNDLE_DIR="$HOME/llama.cpp-release"
  mkdir -p "$BUNDLE_DIR"
  cd "$BUNDLE_DIR"
  BASE_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_TAG}"
  SRV_TGZ="llama-${LLAMA_TAG}-bin-ubuntu-cuda-${CUDA_VER}-x64.tar.gz"
  [ -f "$SRV_TGZ" ] || curl -fSL -o "$SRV_TGZ" "${BASE_URL}/${SRV_TGZ}"
  SERVER="$(find "$BUNDLE_DIR" -maxdepth 2 -name llama-server -type f 2>/dev/null | head -1 || true)"
  if [ -z "$SERVER" ]; then
    tar xzf "$SRV_TGZ"
    SERVER="$(find "$BUNDLE_DIR" -maxdepth 2 -name llama-server -type f 2>/dev/null | head -1 || true)"
  fi
  [ -n "$SERVER" ] && [ -x "$SERVER" ] || { echo "downloaded release has no llama-server binary"; exit 1; }
  # WSL2 ships the NVIDIA driver but not the CUDA runtime (no libcublas in
  # ldconfig), so pull the matching cudart bundle unless the system has it.
  CUDART_DIR=""
  if ! ldconfig -p 2>/dev/null | grep -q libcublas; then
    CU_TGZ="cudart-llama-${LLAMA_TAG}-bin-ubuntu-cuda-${CUDA_VER}-x64.tar.gz"
    [ -f "$CU_TGZ" ] || curl -fSL -o "$CU_TGZ" "${BASE_URL}/${CU_TGZ}"
    if ! find "$BUNDLE_DIR" -name 'libcudart.so*' 2>/dev/null | grep -q .; then
      tar xzf "$CU_TGZ"
    fi
    CUDART_DIR="$(find "$BUNDLE_DIR" -name 'libcudart.so*' 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)"
    [ -n "$CUDART_DIR" ] || { echo "cudart bundle has no libcudart"; exit 1; }
    echo "CUDA runtime: $CUDART_DIR"
  fi
  printf 'export LLAMA_SERVER="%s"\n' "$SERVER" > "$REL_ENV"
  if [ -n "$CUDART_DIR" ]; then
    printf 'export LD_LIBRARY_PATH="%s${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"\n' "$CUDART_DIR" >> "$REL_ENV"
  fi
  # shellcheck disable=SC1090
  . "$REL_ENV"
  SERVER="$LLAMA_SERVER"
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
