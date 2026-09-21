#!/usr/bin/env bash
# Host setup for the matched-repair scored campaign (freeze v8.1: phase-2 cross-file pairs, R03 spec fix).
#
# Runs on Linux or WSL2 with Docker. Everything before the final confirmation
# is offline (fixture builds, calibration, grader smoke, audits, freeze);
# paid inference is 12 attempts (4 pairs x 3 arms) within the frozen caps
# ($25/attempt, $100 global) and only starts after you type RUN. After the
# run, hidden acceptance grading runs offline (Docker only, no model calls)
# over every completed repair snapshot; hidden outcomes are never fed back.
#
# The OpenAI key is read once, kept in the shell session only, and never
# written to disk, logs, or the repo.
set -euo pipefail

WORK="${1:-$HOME/mr-smoke}"
REPO_URL="https://github.com/electrohire/spec-kit-aee-benchmark.git"
BRANCH="main"
UPSTREAMS="/tmp/upstreams"
TINYDB_URL="https://github.com/msiemens/tinydb.git"
TINYDB_REV="19066e03139e904c24410e23901e4b069d715a2e"
CACHETOOLS_URL="https://github.com/tkem/cachetools.git"
CACHETOOLS_REV="c403f9f4185e58090b904c1915345b9ba46d5a08"

step() { echo; echo "=== $1 ==="; }
die() { echo "ERROR: $1" >&2; exit 1; }

# Docker credential-helper workaround (WSL2): docker-credential-desktop.exe
# cannot execute here ("exec format error"), and the failed helper lookup
# aborts even credential-free pushes to the local registry. Run every docker
# operation in this script under a copy of the user's docker config with the
# credential store stripped; ~/.docker/config.json itself is left untouched.
# (Public base-image pulls still work anonymously; localhost:5000 needs no auth.)
export DOCKER_CONFIG="$WORK/docker-config"
mkdir -p "$DOCKER_CONFIG" "$WORK"
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

step "API key (session only, never written to disk)"
if [ -z "${OPENAI_API_KEY:-}" ]; then
  # With piped stdin (e.g. `echo RUN | ...`) there is no one to paste the key,
  # and the hidden read below would silently swallow the piped line as the key.
  # Fail fast instead of probing with garbage.
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

step "Fixture images (offline)"
"$VPY" -m benchmark_runner.matched_repair build-images

step "Calibration (offline)"
# Archive any previous calibration so the exclusive write below stays fail-closed
# while the script remains re-runnable after an interrupted run.
if [ -d "$WORK/calibration" ]; then
  mv "$WORK/calibration" "$WORK/calibration-prev-$(date +%Y%m%d-%H%M%S)"
fi
"$VPY" -m benchmark_runner.matched_repair calibrate "$WORK/calibration"
test -f "$WORK/calibration/calibration.json" || die "calibration.json missing"

step "Freeze v8.1 (phase-2 cross-file rerun with R03 spec fix: runs reservation, audits, and grader-smoke gates)"
if [ -d "$WORK/freeze-v8-1" ]; then
  mv "$WORK/freeze-v8-1" "$WORK/freeze-v8-1-prev-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$WORK/freeze-v8-1"
"$VPY" -m benchmark_runner.matched_repair freeze-scored-v8-1 "$WORK/freeze-v8-1" \
  --calibration "$WORK/calibration/calibration.json"
MANIFEST="$WORK/freeze-v8-1/freeze-v8-1-scored.json"
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
print("pairs:", len(m["pairs"]), "| schedule:", len(m["schedule"]), "attempts")
assert len(m["schedule"]) == 12, "v8.1 must schedule exactly 12 attempts (4 pairs x 3 arms)"
assert all(c[k] for k in ("reservation_bound_verified", "grader_smoke_verified", "solver_image_audit_verified"))
EOF

echo
echo "All offline gates passed. The next step spends real money:"
echo "  12 attempts on gpt-6-astra (phase-2 cross-file scored campaign, freeze v8.1: 4 pairs x diagnose/ordinary/guided, seed 20260918),"
echo "  attempt_cap_usd=25, global_cap_usd=100."
echo "  Expected spend ~\$4 at ~\$0.32/attempt (v8 measured \$3.8762 over 12 attempts)."
echo "  Spend settles to measured usage; unknown usage is never released."
echo "  Expect up to ~30 minutes per attempt (timeouts are enforced per attempt); the full campaign may take several hours."
printf 'Type RUN to execute the 12-attempt scored campaign: '
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "RUN" ] || { echo "Aborted before any paid call. Zero spend."; exit 0; }

step "Running 12-attempt scored campaign"
"$VBIN/aee-bench" run "$MANIFEST" "$WORK/runs/scored-v8-1"

step "Hidden acceptance grading (offline: Docker only, no model calls)"
"$VPY" -m benchmark_runner.matched_repair grade-run --run "$WORK/runs/scored-v8-1"

step "Spend and graded outcome summary"
python3 - "$WORK/runs/scored-v8-1" <<'EOF'
import json, sys
from pathlib import Path
from decimal import Decimal
root = Path(sys.argv[1])
def events(name):
    p = root / f"{name}.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
attempts = events("attempts")
calls = events("calls")
grades = {g["attempt_id"]: g for g in events("hidden_grades")}
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
    g = grades.get(aid)
    if g and g.get("graded"):
        grade_txt = f"  hidden={'PASS' if g['hidden_passed'] else 'FAIL'} ({g['test_count']} tests" + \
                    (f", failed: {', '.join(g['failed_cases'])}" if g["failed_cases"] else "") + ")"
    elif g:
        grade_txt = f"  hidden=ungraded ({g.get('reason')})"
    else:
        grade_txt = ""
    print(f"  {aid}: {a['status']}" + (f" ({a.get('reason')})" if a.get("reason") else "")
          + f"  measured spend ${spent:.4f}" + grade_txt)
print(f"model calls: {len(calls)}")
print(f"total measured spend: ${spend:.4f} USD (caps: $25/attempt, $100 global)")
print()
print("Graded comparison (ordinary vs guided, hidden pass-rate):")
print(f"{'pair':45} {'ordinary':22} {'guided':22}")
def rate(g):
    return (g["test_count"] - len(g["failed_cases"] or [])) / g["test_count"]
pairs = {}
for aid, g in grades.items():
    if g.get("graded"):
        pairs.setdefault(g["task_id"], {})[g["arm"]] = g
for pair in sorted(pairs):
    def cell(g):
        if not g:
            return "n/a"
        passed = g["test_count"] - len(g["failed_cases"] or [])
        return f"{'PASS' if g['hidden_passed'] else 'FAIL'} ({passed}/{g['test_count']})"
    o, gd = pairs[pair].get("repair_ordinary"), pairs[pair].get("repair_guided")
    mark = ""
    if o and gd and rate(o) != rate(gd):
        mark = "  <-- arms differ"
    print(f"{pair:45} {cell(o):22} {cell(gd):22}{mark}")
EOF

echo
echo "Done. Full evidence is in $WORK/runs/scored-v8-1 (append-only event streams)."
echo "The API key was never written to disk; unset it with: unset OPENAI_API_KEY"
