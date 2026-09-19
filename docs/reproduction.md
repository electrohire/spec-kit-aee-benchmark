# Reproduction
## Offline checks (PowerShell or Linux)
Install uv 0.11.32 and Python 3.12.6. From repository:
```
uv sync --locked --group dev
uv run pytest -q
uv run maintenance-triage examples/maintenance_triage/sample.csv output.json
uv run aee-bench preflight
uv run aee-bench freeze artifacts/offline-freeze.json
uv run aee-bench dry-run artifacts/offline-freeze.json
uv run aee-bench aggregate artifacts/unrun artifacts/not-run.json
uv run aee-bench article-table artifacts/not-run.json
```
Use a fresh freeze filename; freeze never overwrites evidence. The public task
manifest has issue hashes and placeholders. Dry-run schedules 180 attempts but
does not spend or require Docker. Live generation rejects placeholders.

## Upstream environment (Linux/WSL2)
Clone outside this controller and solver contexts:
```bash
git clone https://github.com/SWE-bench/SWE-bench ../benchmark-upstreams/SWE-bench
git -C ../benchmark-upstreams/SWE-bench checkout 02e7a74ffd0b707aab73d203fe87bdc7c76afc8e
git clone https://github.com/SWE-bench/swe-bench-tasks ../benchmark-upstreams/swe-bench-tasks
git -C ../benchmark-upstreams/swe-bench-tasks checkout 3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d
uv venv ../benchmark-upstreams/harness-venv --python 3.12
uv pip install --python ../benchmark-upstreams/harness-venv/bin/python -e ../benchmark-upstreams/SWE-bench
../benchmark-upstreams/harness-venv/bin/swebench --help
../benchmark-upstreams/harness-venv/bin/swebench dataset check ../benchmark-upstreams/swe-bench-tasks
```
Record resolved harness dependencies before grading; do not upgrade between arms.
Upstream task images are reused, not rebuilt from a homegrown grader.
Run the independent gold smoke outside any solver, with a fresh run ID:
```bash
swebench eval verified --gold -i sympy__sympy-20590 --run-id harness-smoke-gold-UNIQUE --task-repo ../benchmark-upstreams/swe-bench-tasks -j 1
```
Preflight CPU/RAM/disk and Docker before model spending. Gold task is excluded.

## Task manifest and live freeze
```
uv run python -X utf8 scripts/select_upstream.py ../benchmark-upstreams/SWE-bench ../benchmark-upstreams/swe-bench-tasks artifacts/tasks-hydrated.json --include-issues
```
Use the resulting safe hydrated records as local manifests/tasks.json; keep
dataset text out of public commits. Pull upstream image tags outside solvers,
record registry digests and image IDs, replace tags with digests in the live
manifest. Audit images for held-out grader artifacts. Freeze this resolved state.

Select one model snapshot and reasoning configuration for all arms. Pin official
dated prices, context/output limits, approved global/per-attempt dollar caps and
token ceilings in configs/experiment.yaml. Store API credentials via local
environment only. Never paste keys into chat or commit them. Preserve signed-off
budget authorization text as a nonsecret reference. Verify reservation bounds.
First use a separate development_smoke configuration and development task manifest;
never set verification flags based on fixtures. Record actual smoke evidence.

## Run, grade and analyze
```bash
uv run aee-bench freeze artifacts/live-freeze.json
uv run aee-bench run artifacts/live-freeze.json artifacts/pilot
# For individual arms (changes interleaving; record as deviation):
uv run aee-bench run artifacts/live-freeze.json artifacts/pilot --arm baseline
uv run aee-bench run artifacts/live-freeze.json artifacts/pilot --arm spec_kit
uv run aee-bench run artifacts/live-freeze.json artifacts/pilot --arm spec_kit_aee
uv run aee-bench grade artifacts/pilot --task-repo ../benchmark-upstreams/swe-bench-tasks --harness-repo ../benchmark-upstreams/SWE-bench
uv run aee-bench aggregate artifacts/pilot artifacts/pilot-report.json
uv run aee-bench article-table artifacts/pilot-report.json
```
Run all arms together for primary random/interleaved order. Resume by repeating
the same command with identical freeze. Ctrl-C cancels; creating artifacts/pilot/CANCEL
stops at the next safe boundary. Interrupted attempts become infrastructure failures;
no silent rerun. Each grade uses a UUID run ID and explicit task ID.
Put the pinned harness executable on PATH for grade. Reports preserve absent grades.

## Extensions
Installed Codex skill names use hyphens, e.g. $speckit-aee-assess,
$speckit-evaluator-compose and $speckit-evaluator-report.
```
specify extension list
uv run python .specify/extensions/aee/scripts/python/run_aee.py assess --input specs/001-benchmark/claims.json --phase after_specify
uv run python .specify/extensions/evaluator/scripts/python/compose_results.py --results-dir .specify/extensions/evaluator/results --phase after_specify --strategy strict --output artifacts/composed.json
```
Reports/workflow retains actual controller execution. No claim that optional hooks
ran automatically; after_verify is not after_converge.

## Evidence sharing
Artifacts are SHA-256 addressed under artifacts/*/objects. Append-only streams
link attempts, calls, phases, tool observations, assessments and grades. Keep
raw sensitive data local. Review sanitized artifacts and redistribution rights
before attaching versioned release assets; include hashes and retrieval instructions.
Compact offline evidence is committed under reports/. Never publish entire datasets.
