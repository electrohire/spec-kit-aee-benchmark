#!/usr/bin/env bash
# Host script for the Claim A campaign (v9 measurement design, sections 1/3/4):
# a smaller local model with the Spec-Kit/AEE workflow vs an expensive
# frontier model on ordinary repair, over a shared calibrated task bank.
#
# Runs on Linux or WSL2 with Docker. The campaign has two phases, each with
# its own typed RUN gate; nothing is spent before you type RUN at that gate:
#
#   Phase A (calibration, PAID): ~24 candidate variants, frontier ordinary
#     repair only (1 shared diagnostic + 2 repairs per task). Keeps the
#     0.2-0.8 ordinary pass band as the shared task bank.
#   Phase B (main, mixed): the kept tasks, two matched manifests sharing the
#     task bank and seed 20260921 --
#       local arm:   Qwen-class 8B via the local llama.cpp backend, full
#                    Spec-Kit/AEE guided workflow (FREE, zero marginal dollars)
#       frontier arm: gpt-6-astra ordinary repair via the OpenAI backend (PAID)
#
# Expected paid spend: calibration ~72 attempts + frontier main ~3/kept-task,
# projected at the v8.1 measured rate (~$0.27/attempt); both phases settle to
# measured usage under the standing $25/attempt and $100 global caps. The
# local arm (including its single-task pilot) costs $0 in API spend.
#
# Prerequisites on this host:
#   - the local model server running (scripts/local-model-setup.sh), with
#     LOCAL_MODEL_BASE_URL and LOCAL_MODEL_NAME exported in this session
#   - OPENAI_API_KEY exported (session only, never written to disk) for the
#     two paid phases
#
# Log watch: run the whole script under tee and tail the log from another
# shell:
#   bash scripts/host-setup-claim-a.sh 2>&1 | tee ~/claim-a/claim-a.log
#   tail -f ~/claim-a/claim-a.log
# Per-phase run logs also live under $WORK/logs/. To stop between phases,
# Ctrl-C at any prompt; every phase resumes cleanly on re-run (run
# directories whose freeze.json matches the current manifest resume where
# they left off; mismatched ones are archived, never deleted).
set -euo pipefail

WORK="${1:-$HOME/claim-a}"
REPO_URL="https://github.com/electrohire/spec-kit-aee-benchmark.git"
BRANCH="feat/local-provider"
UPSTREAMS="/tmp/upstreams"
TINYDB_URL="https://github.com/msiemens/tinydb.git"
TINYDB_REV="19066e03139e904c24410e23901e4b069d715a2e"
CACHETOOLS_URL="https://github.com/tkem/cachetools.git"
CACHETOOLS_REV="c403f9f4185e58090b904c1915345b9ba46d5a08"
# v8.1 measured $3.1833 over 12 attempts; used only for the pre-gate estimate.
MEASURED_PER_ATTEMPT_USD="0.2653"

step() { echo; echo "=== $1 ==="; }
die() { echo "ERROR: $1" >&2; exit 1; }

# Docker credential-helper workaround (WSL2): docker-credential-desktop.exe
# cannot execute here ("exec format error"), and the failed helper lookup
# aborts even credential-free pushes to the local registry. Run every docker
# operation in this script under a copy of the user's docker config with the
# credential store stripped; ~/.docker/config.json itself is left untouched.
export DOCKER_CONFIG="$WORK/docker-config"
mkdir -p "$DOCKER_CONFIG" "$WORK" "$WORK/logs"
python3 - "$HOME/.docker/config.json" "$DOCKER_CONFIG/config.json" <<'EOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    cfg = {}
cfg.pop("credsStore", None)
cfg.pop("credHelpers", None)
json.dump(cfg, open(sys.argv[2], "w"), indent=2)
EOF
echo "docker operations will use DOCKER_CONFIG=$DOCKER_CONFIG (credential store stripped)"

step "Host checks"
[ "$(uname -s)" = "Linux" ] || die "live runs require Linux/WSL2 (this is $(uname -s))"
grep -qi microsoft /proc/version 2>/dev/null && echo "WSL2 detected" || echo "native Linux detected"
command -v docker >/dev/null || die "docker not found; install Docker Desktop (WSL2 backend) or Docker Engine"
docker info >/dev/null 2>&1 || die "'docker info' failed; is the Docker daemon running?"
command -v git >/dev/null || die "git not found"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" \
  || die "python3.12+ required (found $(python3 --version 2>&1))"

step "Repository"
mkdir -p "$WORK"
if [ ! -d "$WORK/repo/.git" ]; then
  git clone -q "$REPO_URL" "$WORK/repo" || die "clone failed"
fi
cd "$WORK/repo"
git fetch -q origin || die "git fetch failed"
git checkout -q -B "$BRANCH" "origin/$BRANCH" || die "checkout $BRANCH failed"
echo "checked out $(git rev-parse --short HEAD) on $BRANCH (tracking origin/$BRANCH)"

step "Python dependencies (isolated venv)"
if [ ! -d "$WORK/venv" ]; then
  python3 -m venv "$WORK/venv" \
    || die "could not create a venv; on Ubuntu run: sudo apt install python3-venv python3-pip"
fi
VPY="$WORK/venv/bin/python"
VBIN="$WORK/venv/bin"
if ! "$VPY" -c "import benchmark_runner, aee, minisweagent" 2>/dev/null; then
  "$VPY" -m pip install -q -e "$WORK/repo" || die "pip install failed"
  "$VPY" -m pip install -q pytest || die "pip install pytest failed"
fi
"$VPY" -m pytest -q tests 2>&1 | tail -2 || die "test suite failed"

step "Candidate build guard"
"$VPY" -c "
from benchmark_runner.claim_a import CLAIM_A_CANDIDATES
assert CLAIM_A_CANDIDATES, 'CLAIM_A_CANDIDATES is empty: the candidate task build has not been merged into $BRANCH yet'
print(f'{len(CLAIM_A_CANDIDATES)} candidate variants frozen for calibration')" \
  || die "candidate guard failed"

step "Local model server (fail closed)"
[ -n "${LOCAL_MODEL_BASE_URL:-}" ] || die "LOCAL_MODEL_BASE_URL is not set; start the server with scripts/local-model-setup.sh and export it in this session"
[ -n "${LOCAL_MODEL_NAME:-}" ] || die "LOCAL_MODEL_NAME is not set; export it in this session (e.g. qwen3-8b-local)"
"$VPY" -c "
from benchmark_runner.local_provider import check_local_server
print('local server OK, serving model:', check_local_server())" \
  || die "local model server probe failed"

step "API key (session only, never written to disk)"
if [ -z "${OPENAI_API_KEY:-}" ]; then
  [ -t 0 ] || die "OPENAI_API_KEY is not set and stdin is not a terminal, so the key cannot be pasted. Export it first (session only): export OPENAI_API_KEY='sk-...' — then re-run."
  printf 'Paste your OpenAI API key (input hidden): '
  IFS= read -rs OPENAI_API_KEY || true
  echo
  export OPENAI_API_KEY
fi
[ -n "${OPENAI_API_KEY:-}" ] || die "no API key provided"

step "Preflight"
PREFLIGHT="$("$VBIN/aee-bench" preflight)"
echo "$PREFLIGHT" | python3 -c "
import json, sys
p = json.load(sys.stdin)
assert p['docker_ready'], 'docker not ready'
assert p['api_credential_present'], 'API credential probe failed; check the key'
print('docker_ready=True api_credential_present=True')"
echo "$PREFLIGHT" | python3 -c "import json,sys; p=json.load(sys.stdin); print('docker CPUs:', p['docker_cpu'])"

step "Upstream checkouts (pinned revisions)"
mkdir -p "$UPSTREAMS"
clone_at() { # url dir rev
  if [ ! -d "$UPSTREAMS/$2/.git" ]; then
    git clone -q "$1" "$UPSTREAMS/$2" || die "clone $2 failed"
  fi
  git -C "$UPSTREAMS/$2" fetch -q origin || die "fetch $2 failed"
  git -C "$UPSTREAMS/$2" checkout -q "$3" || die "checkout $3 failed"
  actual="$(git -C "$UPSTREAMS/$2" rev-parse HEAD)"
  [ "$actual" = "$3" ] || die "$2 at $actual, expected $3"
  [ -z "$(git -C "$UPSTREAMS/$2" status --porcelain)" ] || die "$2 checkout is dirty"
  echo "$2 at ${actual:0:12}"
}
clone_at "$TINYDB_URL" tinydb "$TINYDB_REV"
clone_at "$CACHETOOLS_URL" cachetools "$CACHETOOLS_REV"
echo "minisched is fully synthetic (ships in the repo); no checkout needed"

# Archive-then-build helper: keeps the script re-runnable after an
# interrupted run while exclusive writes stay fail-closed.
fresh_dir() { # dir
  if [ -d "$1" ]; then
    mv "$1" "$1-prev-$(date +%Y%m%d-%H%M%S)"
  fi
  mkdir -p "$1"
}

# Resume-safety for offline build steps (constitution IV: resumption MUST
# reject changed configurations). Every freeze manifest is a pure function of
# its inputs (repo HEAD, candidate list, calibration record, kept set), so a
# recorded fingerprint match means the existing outputs are exactly what a
# rebuild would produce -- rebuilding would only churn docker image digests
# and break resumption of a paid run. A mismatch dies loudly instead of
# silently rebuilding; set CLAIM_A_REBUILD=1 to archive and rebuild after an
# intentional change.
inputs_fingerprint() { # [extra files...] -> sha on stdout
  { git -C "$WORK/repo" rev-parse HEAD
    "$VPY" -c "from benchmark_runner.claim_a import CLAIM_A_CANDIDATES
for t in CLAIM_A_CANDIDATES: print(t)"
    for f in "$@"; do sha256sum "$f" | cut -d' ' -f1; done
  } | sha256sum | cut -d' ' -f1
}

# offline_build dir fpfile keyfile [extra inputs...]
# Returns 0 when the caller should build into dir, 1 when existing outputs
# are current and the build must be skipped.
offline_build() { # dir fpfile keyfile [extra...]
  local dir="$1" fpfile="$2" keyfile="$3"; shift 3
  local want cur
  want="$(inputs_fingerprint "$@")"
  if [ -f "$dir/$fpfile" ]; then
    cur="$(cat "$dir/$fpfile")"
    if [ "$cur" = "$want" ]; then
      echo "Offline outputs in $dir are current (inputs unchanged); skipping rebuild." >&2
      return 1
    fi
    if [ "${CLAIM_A_REBUILD:-0}" = "1" ]; then
      echo "Inputs changed and CLAIM_A_REBUILD=1; archiving $dir and rebuilding." >&2
      fresh_dir "$dir"
    else
      die "changed configuration: $dir was built from different inputs (repo HEAD, candidate list, calibration, or kept set changed). Rerun with CLAIM_A_REBUILD=1 to archive and rebuild, or investigate before spending."
    fi
  elif [ -f "$dir/$keyfile" ]; then
    die "unrecognized outputs in $dir (no inputs fingerprint; not built by this script version). Archive $dir manually, or rerun with CLAIM_A_REBUILD=1."
  else
    mkdir -p "$dir"
  fi
  echo "$want" > "$dir/$fpfile"
  return 0
}

# Resume-aware run directory: a directory whose freeze.json matches the
# current manifest resumes where it left off; a mismatched one is archived
# (never deleted) so a rerun starts clean while its evidence stays
# inspectable.
run_dir_for() { # run_subdir manifest
  local dir="$WORK/runs/$1" manifest="$2"
  if [ -f "$dir/freeze.json" ]; then
    if python3 - "$dir/freeze.json" "$manifest" <<'EOF'
import json, sys
try:
    a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
except Exception:
    sys.exit(1)
sys.exit(0 if a == b else 1)
EOF
    then
      echo "Existing run directory $dir matches this freeze; resuming." >&2
    else
      local arch="$dir-prev-$(date +%Y%m%d-%H%M%S)"
      echo "Previous run directory holds a different frozen manifest; archiving to $arch" >&2
      mv "$dir" "$arch"
    fi
  fi
  echo "$dir"
}

verify_manifest() { # manifest expected_schedule_len label
  "$VBIN/aee-bench" dry-run "$1" >/dev/null || die "freeze verification failed ($3)"
  python3 - "$1" "$2" "$3" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
c = m["config"]
print("freeze_id:", m["freeze_id"])
print("backend:", c["provider_backend"], "| model:", c["model"])
print("attempt_cap_usd:", c["attempt_cap_usd"], "| global_cap_usd:", c["global_cap_usd"])
print("gates:", c["reservation_bound_verified"], c["grader_smoke_verified"], c["solver_image_audit_verified"])
print("worst-case reservation:", json.dumps(m["reservation_verification"]))
print("tasks:", len(m["pairs"]), "| schedule:", len(m["schedule"]), "attempts")
assert len(m["schedule"]) == int(sys.argv[2]), f"expected {sys.argv[2]} scheduled attempts"
assert all(c[k] for k in ("reservation_bound_verified", "grader_smoke_verified", "solver_image_audit_verified"))
EOF
}

project_spend() { # scheduled_attempts label
  python3 -c "
attempts = $1
rate = float('$MEASURED_PER_ATTEMPT_USD')
print(f'$2: {attempts} attempts, projected ~\${attempts * rate:.2f} at the v8.1 measured rate; settles to measured usage (caps \$25/attempt, \$100 global)')"
}

# ---------------------------------------------------------------------------
# Phase A: calibration (PAID, frontier ordinary repair only)
# ---------------------------------------------------------------------------
step "Phase A: fixture calibration (offline: builds candidate + clean images)"
if offline_build "$WORK/calibration" "inputs.sha256" "calibration.json"; then
  "$VPY" -m benchmark_runner.claim_a calibrate "$WORK/calibration"
fi
test -f "$WORK/calibration/calibration.json" || die "calibration.json missing"

step "Phase A: build calibration freeze (offline gates)"
if offline_build "$WORK/freeze-calibration" "inputs.sha256" "freeze-claim-a-calibration.json" "$WORK/calibration/inputs.sha256"; then
  "$VPY" -m benchmark_runner.claim_a freeze-calibration "$WORK/freeze-calibration" \
    --calibration "$WORK/calibration/calibration.json"
fi
CAL_MANIFEST="$WORK/freeze-calibration/freeze-claim-a-calibration.json"
test -f "$CAL_MANIFEST" || die "calibration freeze manifest missing"
N_CAL_ATTEMPTS="$("$VPY" -c "
import json; print(len(json.load(open('$CAL_MANIFEST'))['schedule']))")"
verify_manifest "$CAL_MANIFEST" "$N_CAL_ATTEMPTS" "claim-a calibration"

echo
echo "All offline gates passed. The next step spends real money:"
project_spend "$N_CAL_ATTEMPTS" "Phase A calibration (frontier ordinary repair, 1 diagnostic + 2 repairs per candidate)"
echo "  Unknown usage is never released against the caps; spend settles to measured usage."
echo "  Expect up to ~30 minutes per attempt (timeouts enforced); the phase may take several hours."
printf 'Type RUN to execute Phase A calibration: '
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "RUN" ] || { echo "Aborted before any paid call. Zero spend."; exit 0; }

step "Phase A: running calibration (paid)"
CAL_RUN="$(run_dir_for calibration "$CAL_MANIFEST")"
"$VBIN/aee-bench" run "$CAL_MANIFEST" "$CAL_RUN" 2>&1 | tee "$WORK/logs/phase-a-run.log"

step "Phase A: hidden acceptance grading (offline)"
"$VPY" -m benchmark_runner.matched_repair grade-run --run "$CAL_RUN"

step "Phase A: discriminative band selection (offline)"
"$VPY" "$WORK/repo/scripts/analyze_claim_a.py" band --run "$CAL_RUN" --out "$WORK/kept.json"
N_KEPT="$("$VPY" -c "import json; print(len(json.load(open('$WORK/kept.json'))))")"
[ "$N_KEPT" -gt 0 ] || die "calibration kept zero tasks in the 0.2-0.8 band; the task bank needs rework, not more spend"

# ---------------------------------------------------------------------------
# Phase B: local pilot (FREE) -- real-smoke gate for the local backend
# ---------------------------------------------------------------------------
step "Phase B: local pilot freeze (single task, offline gates)"
if offline_build "$WORK/freeze-pilot" "inputs.sha256" "freeze-claim-a-pilot.json" "$WORK/calibration/inputs.sha256" "$WORK/kept.json"; then
  "$VPY" -m benchmark_runner.claim_a freeze-pilot "$WORK/freeze-pilot" \
    --calibration "$WORK/calibration/calibration.json" --kept "$WORK/kept.json"
fi
PILOT_MANIFEST="$WORK/freeze-pilot/freeze-claim-a-pilot.json"
verify_manifest "$PILOT_MANIFEST" 2 "claim-a local pilot"

step "Phase B: local pilot run (FREE: zero marginal dollars)"
PILOT_RUN="$(run_dir_for pilot "$PILOT_MANIFEST")"
"$VBIN/aee-bench" run --smoke "$PILOT_MANIFEST" "$PILOT_RUN" 2>&1 | tee "$WORK/logs/phase-b-pilot.log"
"$VPY" - <<EOF || die "local pilot did not complete cleanly; fix the local backend before the main local run"
import json, sys
from pathlib import Path
root = Path("$PILOT_RUN")
final = {}
for line in (root / "attempts.jsonl").read_text().splitlines():
    a = json.loads(line)
    final[a["attempt_id"]] = a
assert len(final) == 2, f"pilot must finish 2 attempts, saw {len(final)}"
bad = {aid: a["status"] for aid, a in final.items() if a["status"] != "completed"}
assert not bad, f"pilot attempts not completed: {bad}"
print("pilot OK: 2/2 attempts completed on the local backend")
EOF
PILOT_EVIDENCE="Local backend real smoke: freeze-claim-a-pilot ($PILOT_RUN), 2/2 attempts (diagnose + guided repair) completed on $LOCAL_MODEL_NAME via $LOCAL_MODEL_BASE_URL."

# ---------------------------------------------------------------------------
# Phase B: local main run (FREE)
# ---------------------------------------------------------------------------
step "Phase B: local main freeze (offline gates)"
if offline_build "$WORK/freeze-local" "inputs.sha256" "freeze-claim-a-local.json" "$WORK/calibration/inputs.sha256" "$WORK/kept.json"; then
  "$VPY" -m benchmark_runner.claim_a freeze-main "$WORK/freeze-local" \
    --calibration "$WORK/calibration/calibration.json" --kept "$WORK/kept.json" \
    --backend local --pilot-evidence "$PILOT_EVIDENCE"
fi
LOCAL_MANIFEST="$WORK/freeze-local/freeze-claim-a-local.json"
N_LOCAL_ATTEMPTS="$("$VPY" -c "
import json; print(len(json.load(open('$LOCAL_MANIFEST'))['schedule']))")"
verify_manifest "$LOCAL_MANIFEST" "$N_LOCAL_ATTEMPTS" "claim-a local main"

step "Phase B: local main run (FREE: zero marginal dollars)"
LOCAL_RUN="$(run_dir_for local-main "$LOCAL_MANIFEST")"
"$VBIN/aee-bench" run "$LOCAL_MANIFEST" "$LOCAL_RUN" 2>&1 | tee "$WORK/logs/phase-b-local.log"

step "Phase B: local hidden acceptance grading (offline)"
"$VPY" -m benchmark_runner.matched_repair grade-run --run "$LOCAL_RUN"

# ---------------------------------------------------------------------------
# Phase B: frontier main run (PAID)
# ---------------------------------------------------------------------------
step "Phase B: frontier main freeze (offline gates)"
if offline_build "$WORK/freeze-frontier" "inputs.sha256" "freeze-claim-a-frontier.json" "$WORK/calibration/inputs.sha256" "$WORK/kept.json"; then
  "$VPY" -m benchmark_runner.claim_a freeze-main "$WORK/freeze-frontier" \
    --calibration "$WORK/calibration/calibration.json" --kept "$WORK/kept.json" \
    --backend frontier
fi
FRONTIER_MANIFEST="$WORK/freeze-frontier/freeze-claim-a-frontier.json"
N_FRONTIER_ATTEMPTS="$("$VPY" -c "
import json; print(len(json.load(open('$FRONTIER_MANIFEST'))['schedule']))")"
verify_manifest "$FRONTIER_MANIFEST" "$N_FRONTIER_ATTEMPTS" "claim-a frontier main"

echo
echo "Local arm finished (free). The next step spends real money:"
project_spend "$N_FRONTIER_ATTEMPTS" "Phase B frontier main (gpt-6-astra ordinary repair, 1 diagnostic + 2 repairs per kept task)"
echo "  Unknown usage is never released against the caps; spend settles to measured usage."
printf 'Type RUN to execute the Phase B frontier arm: '
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "RUN" ] || { echo "Aborted before any paid call in Phase B. Local-arm evidence is preserved."; exit 0; }

step "Phase B: frontier main run (paid)"
FRONTIER_RUN="$(run_dir_for frontier-main "$FRONTIER_MANIFEST")"
"$VBIN/aee-bench" run "$FRONTIER_MANIFEST" "$FRONTIER_RUN" 2>&1 | tee "$WORK/logs/phase-b-frontier.log"

step "Phase B: frontier hidden acceptance grading (offline)"
"$VPY" -m benchmark_runner.matched_repair grade-run --run "$FRONTIER_RUN"

# ---------------------------------------------------------------------------
# Analysis + evidence packaging (offline)
# ---------------------------------------------------------------------------
step "Claim A comparison analysis (offline)"
"$VPY" "$WORK/repo/scripts/analyze_claim_a.py" compare \
  --frontier "$FRONTIER_RUN" --local "$LOCAL_RUN" --kept "$WORK/kept.json" \
  2>&1 | tee "$WORK/logs/claim-a-analysis.txt"

step "Evidence packaging"
command -v zip >/dev/null || die "zip not found; install it (e.g. sudo apt install zip) or package the evidence manually"
rm -f "$WORK/claim-a-evidence.zip"
(cd "$WORK" && zip -qr claim-a-evidence.zip \
  runs/calibration runs/local-main runs/frontier-main runs/pilot \
  runs/*-prev-* kept.json logs \
  freeze-calibration freeze-local freeze-frontier freeze-pilot calibration 2>/dev/null) || \
  (cd "$WORK" && zip -qr claim-a-evidence.zip \
    runs/calibration runs/local-main runs/frontier-main runs/pilot kept.json logs)
echo "Evidence packaged: $WORK/claim-a-evidence.zip — attach it in chat for the independent audit."
echo "The API key was never written to disk; unset it with: unset OPENAI_API_KEY"
