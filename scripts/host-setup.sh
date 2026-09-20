#!/usr/bin/env bash
# Host setup for the matched-repair development smoke (freeze v4).
#
# Runs on Linux or WSL2 with Docker. Everything before the final confirmation
# is offline (fixture builds, calibration, grader smoke, audit, freeze);
# paid inference is exactly 3 attempts within the frozen caps
# ($25/attempt, $100 global) and only starts after you type RUN.
#
# The OpenAI key is read once, kept in the shell session only, and never
# written to disk, logs, or the repo.
set -euo pipefail

WORK="${1:-$HOME/mr-smoke}"
REPO_URL="https://github.com/electrohire/spec-kit-aee-benchmark.git"
BRANCH="feat/cloud-matched-repair"
UPSTREAMS="/tmp/upstreams"
TINYDB_URL="https://github.com/msiemens/tinydb.git"
TINYDB_REV="19066e03139e904c24410e23901e4b069d715a2e"
CACHETOOLS_URL="https://github.com/tkem/cachetools.git"
CACHETOOLS_REV="c403f9f4185e58090b904c1915345b9ba46d5a08"

step() { echo; echo "=== $1 ==="; }
die() { echo "ERROR: $1" >&2; exit 1; }

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

step "API key (session only, never written to disk)"
if [ -z "${OPENAI_API_KEY:-}" ]; then
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

step "Fixture images (offline)"
"$VPY" -m benchmark_runner.matched_repair build-images

step "Calibration (offline)"
"$VPY" -m benchmark_runner.matched_repair calibrate "$WORK/calibration"
test -f "$WORK/calibration/calibration.json" || die "calibration.json missing"

step "Freeze v4 (runs reservation, audit, and grader-smoke gates)"
mkdir -p "$WORK/freeze-v4"
"$VPY" -m benchmark_runner.matched_repair freeze "$WORK/freeze-v4" \
  --calibration "$WORK/calibration/calibration.json"
MANIFEST="$WORK/freeze-v4/freeze-v4-smoke.json"
test -f "$MANIFEST" || die "freeze manifest missing"

step "Verify freeze integrity (offline)"
"$VBIN/aee-bench" dry-run "$MANIFEST" >/dev/null || die "freeze verification failed"
python3 - "$MANIFEST" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
c = m["config"]
print("freeze_id:", m["freeze_id"])
print("model:", c["model"], "| reasoning_effort:", c["reasoning_effort"])
print("attempt_cap_usd:", c["attempt_cap_usd"], "| global_cap_usd:", c["global_cap_usd"])
print("gates:", c["reservation_bound_verified"], c["grader_smoke_verified"], c["solver_image_audit_verified"])
print("worst-case reservation:", json.dumps(m["reservation_verification"]))
print("schedule:", [s["attempt_id"] for s in m["schedule"]])
assert len(m["schedule"]) == 3, "smoke must schedule exactly 3 attempts"
assert all(c[k] for k in ("reservation_bound_verified", "grader_smoke_verified", "solver_image_audit_verified"))
EOF

echo
echo "All offline gates passed. The next step spends real money:"
echo "  3 attempts on gpt-6-astra, attempt_cap_usd=25, global_cap_usd=100."
echo "  Worst-case reservation per repair attempt is under the attempt cap."
echo "  Spend settles to measured usage; unknown usage is never released."
printf 'Type RUN to execute the 3-attempt development smoke: '
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "RUN" ] || { echo "Aborted before any paid call. Zero spend."; exit 0; }

step "Running 3-attempt development smoke"
"$VBIN/aee-bench" run "$MANIFEST" "$WORK/runs/smoke-v4" --smoke

step "Spend and outcome summary"
python3 - "$WORK/runs/smoke-v4" <<'EOF'
import json, sys
from pathlib import Path
from decimal import Decimal
root = Path(sys.argv[1])
def events(name):
    p = root / f"{name}.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
attempts = events("attempts")
calls = events("calls")
# Keep the final event per attempt (each attempt logs "started" then its outcome).
final = {}
for a in attempts:
    final[a["attempt_id"]] = a
spend = sum((Decimal(c["cost"]) for c in calls if c.get("cost")), Decimal(0))
per_attempt = {}
for c in calls:
    if c.get("cost"):
        per_attempt[c["attempt_id"]] = per_attempt.get(c["attempt_id"], Decimal(0)) + Decimal(c["cost"])
print(f"attempts: {len(final)}")
for aid, a in final.items():
    spent = per_attempt.get(aid, Decimal(0))
    print(f"  {aid}: {a['status']}" + (f" ({a.get('reason')})" if a.get("reason") else "")
          + f"  measured spend ${spent:.4f}")
print(f"model calls: {len(calls)}")
print(f"total measured spend: ${spend:.4f} USD (caps: $25/attempt, $100 global)")
EOF

echo
echo "Done. Full evidence is in $WORK/runs/smoke-v4 (append-only event streams)."
echo "The API key was never written to disk; unset it with: unset OPENAI_API_KEY"
