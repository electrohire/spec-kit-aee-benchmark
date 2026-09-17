# Resume the ElectroHire benchmark
## GPU continuation — 2026-09-17

Current workspace is the `spec-kit-aee-benchmark` subdirectory of AXIOVEX.
Both GPUs verified: RTX 4070 SUPER 12282 MiB and RTX 5060 Ti 16311 MiB.
The free-local six-task/three-arm exploration and separately frozen repair loops
are complete. Read [measured results](reports/local/gpu-20260917/README.md),
[GPU protocol](docs/gpu-experiment-protocol.md),
[repair protocol](docs/gpu-repair-protocol.md) and
[reproduction](docs/gpu-reproduction.md). All failures and token overhead remain.
Primary passes: 5/6 baseline, 2/6 adapted Spec Kit, 1/6 adapted combined arm.
After shared same-test-feedback repairs: 5/6 each. This is not full Spec Kit validation.

**Latest user direction:** add a better long-horizon benchmark, with real repository
tools and requirements carried through implementation/change/repair. Preserve the
small-task results; do not promote them as the final project study. Long-horizon
task/model/protocol must be frozen before its generation. Include token economics,
tokens per correct result, and actual repair loops. Article and final PR update wait
for this additional work. No paid inference/credits, merge or LinkedIn posting.

Host dependencies: `.venv-gpu`, Python 3.12.6, locked packages; use project-local
`artifacts/tmp-gpu` as TEMP/TMP due intermittent shared-cache/temp ACL errors.
49 regression tests pass. Existing Qwen3.6 router at localhost:8081 was restored
with its original preset and model loaded after the first campaign; the user has
authorized temporarily pausing/restoring it or using it if suitable.

The older notes below describe the pre-GPU laptop state and are historical.

## Latest handoff — paused at user request, 2026-09-17
Read [docs/gpu-machine-handoff.md](docs/gpu-machine-handoff.md) first. The user
stopped this laptop experiment and requested saving/pushing the session for a
machine with an RTX 4070 SUPER (12 GB) and RTX 5060 Ti (VRAM unconfirmed).
No coding-model inference has run. Partial runtime warmups are incomplete and
must not be used as benchmark results. No further execution on this laptop.
Free local inference is authorized; paid calls/credits remain unauthorized.

Goal: compare ordinary coding, Spec Kit and Spec Kit+Evaluator+AEE on 20 Verified
tasks × three repeats × three arms, with honest token economics and an article.
User excluded the ZIP entirely. Follow docs/implementation-brief.md.

## Current state
Public repository: https://github.com/electrohire/spec-kit-aee-benchmark
Branch: feat/benchmark-harness (draft PR; do not merge automatically).
Offline implementation and tutorial are present. reports/latest-offline.json
records actual checks and extension execution. No scored or real model smoke runs.
AEE outcomes: iterate, because independent/live evidence is missing.

## Local environment
Directory: D:/Development/spec-kit-aee-benchmark
Python 3.12.6; Specify 1.0.0; AEE engine 1.0.2; extensions 1.0.0;
mini-SWE-agent 2.4.6; SWE-bench 5.0.2. Exact dependencies: uv.lock.
On this Windows checkout, use $env:UV_PROJECT_ENVIRONMENT = '.venv312'
before uv commands. The old .venv is Python 3.11 and is ignored; do not use it.
Fresh clones use ordinary .venv with .python-version.
Upstream clones: D:/Development/benchmark-upstreams/{SWE-bench,swe-bench-tasks,mini-swe-agent}.
Pinned commits/checksums: manifests/versions.json.

## Commands
```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv312'
$env:PYTHONUTF8 = '1'
uv sync --locked --group dev --extra grading
uv run --extra grading pytest -q
uv run --extra grading python scripts/verify_offline.py
uv run --extra grading aee-bench preflight
uv run --extra grading aee-bench dry-run manifests/offline-freeze.json
```
The offline freeze is prepared after final source verification; see its file hashes.
If source changed, create a fresh manifest rather than overwriting prior evidence.
Full run/grade/aggregation instructions: docs/reproduction.md.
Artifact store: reports/offline/<timestamp>/ for shareable checks; artifacts/ for
local experiments, excluded from Git. reports/verification.md maps requirements.

## Decisions and next action
No model credentials were detected. Docker engine remained unreachable in Windows
and WSL after a launch attempt. No spending cap was supplied. Model/prices/budgets
remain unset in the executable pilot config. Do not bypass these gates.
Proposed next action: obtain USD 30 smoke authorization (USD 10 each for three
development attempts), configure credentials locally, restore Docker and run the
independent gold smoke. See docs/smoke-proposal.md. Pilot cap follows measured smoke.
License selection pending. No prior shared skills.md recovered. No article posting
or leaderboard submission. Preserve upstream notices and private logs.

Draft PR: https://github.com/electrohire/spec-kit-aee-benchmark/pull/1
Implementation commit: 9f2257dd6138a738b6b63960d4bb8447219d866e
Offline tests: 41 passed; initial GitHub Actions Linux test and sample checks passed.

User decision (2026-09-17): **Keep work offline.** Paid smoke and pilot are not authorized. Continue only offline verification and review until this changes.
