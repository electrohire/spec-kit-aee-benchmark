# Resume the ElectroHire benchmark

## Active expanded comparison — 2026-09-17

The user authorized all five follow-up improvements: calibrated runtime limits,
full workflow/repair calibration, longer staged work, identical-start repair
diagnostics, and multiple projects/seeds. See
[the frozen protocol](benchmarks/repeated_local/PROTOCOL.md) and
[reproduction instructions](docs/repeated-local-reproduction.md).

The full workflow calibration passed after three retained failed preparations:
95 local model calls, all seven phases, five actual AEE/Evaluator assessments,
and a repaired injected regression checked independently. The scored suite started
at 22:51 America/New_York on September 17. Results are not yet available.
The dedicated benchmark service currently uses both GPUs; the wrapper restores
the original service after execution. Do not start a duplicate run.

Both repository PRs are ready for review, not drafts. No merge or publication is
authorized. Leave the email and existing article unchanged. Prior measurements
below remain historical evidence and are not replaced by this new campaign.

## Completed GPU continuation — 2026-09-17 local date

Workspace: `spec-kit-aee-benchmark` under AXIOVEX. Branch `feat/benchmark-harness`;
existing draft PR https://github.com/electrohire/spec-kit-aee-benchmark/pull/1.
Do not merge or publish to LinkedIn. No paid inference or credits are authorized.

Both GPUs verified: RTX 4070 SUPER 12282 MiB and RTX 5060 Ti 16311 MiB. Host:
i9-14900F, 64 GB RAM, Windows 11, NVIDIA driver 610.88. Measurements and the
[complete token ledger](reports/local/README.md) are now saved. The original local
Qwen service on port 8081 is restored and loaded; the benchmark server is stopped.

- [Runtime and six-task study](reports/local/gpu-20260917/README.md): primary
  baseline 5/6, document-adapted Spec Kit 2/6, combined 1/6; actual shared repairs
  bring every arm to 5/6. These are feedback-exposed tests, not held-out repair grades.
- [Staged TinyDB study](reports/local/long-horizon-03/README.md): transactions,
  nested savepoints, backup/restore. All nine hidden milestones fail strict acceptance;
  final feature coverage is 21/24, 5/24, 3/24 respectively. All arms hit a request
  timeout; exact usage is unknown for one call per arm. Six common repair attempts
  were blocked before inference. Three actual planning AEE assessments returned
  iterate; implementation assessment and evidence rework were not reached.
- Earlier interrupted pilots and all 11 development smokes remain in the ledger.
  No favorable reruns or model changes were made after the run03 freeze.
- The original 180-attempt SWE-bench pilot remains unrun. These studies establish
  no general correctness, reliability or token-saving advantage.

Reproduction: [long study](docs/long-horizon-reproduction.md),
[small study](docs/gpu-reproduction.md). Exact measured source bytes are preserved
in the long report's frozen-inputs directory and map. Full request/native reasoning
traces remain local with hashes; public traces do not support exact prompt replay.

Use `.venv-gpu` (Python 3.12.6, locked packages) and project-local `artifacts/tmp-gpu`
for TEMP/TMP on this host. 54 regression tests passed during this continuation;
final validation is recorded with the result publication. The copy/paste article is ready in [plain text](docs/linkedin-article.txt) and
[Markdown](docs/linkedin-article.md), citing results commit
835573aff15520a580c7c3862b3534b347101e18. No LinkedIn posting.

The older laptop handoff below is historical and does not describe current GPU results.

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
