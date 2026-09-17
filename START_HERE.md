# Resume the ElectroHire benchmark
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
