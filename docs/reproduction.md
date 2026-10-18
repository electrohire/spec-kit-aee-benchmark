# Reproduction

## Prospective scored admission: model failures are outcomes

The user directed scoring to start after readiness08 completed the full TinyDB
combined workflow and an independently rechecked injected repair (225 public/upstream
tests passed), then stopped on repeated incomplete grep actions. Original08 remains
interrupted and unchanged. Requiring every arm/project to succeed before comparison
is retired: model loops, incomplete phases and ordinary phase/call exhaustion stop
that trajectory and count as measured failures. Dependent later checkpoints are
explicitly not attempted, with zero new model calls, retained source, independent
grades and unknown completion declarations. Other scheduled trajectories continue.
Infrastructure, model-identity, snapshot/integrity and unknown interventions still
stop the campaign. No loop threshold, timeout, token/call cap, grader, task, seed,
model, provider, solver prompt or native action grammar changes.

Fresh preflight09 binds original interrupted evidence, independently verified exact
repair source, four real AEE semantic replays, existing gold/untouched grader controls,
image isolation, native transport, context and latency proofs. No claim that all six
readiness cases passed. All failed setup costs remain. Study02 gets a fresh immutable
freeze before scored generation; historical study01/preparations stay unchanged.
The amendment is prospective: no scored02 outcomes existed when it was chosen.
Runtime-interrupted work cannot count as completed workflow even if its code passes
some tests. Preserve positive/unknown/ungraded claim denominators. Results need not
favor any arm; no savings conclusion is assumed. Shared before/after measurement
must retain this same failure policy.


## Current free local study

**Stop before reproducing scored inference:** the current-study-01 budget design
failed readiness. See the [investigation](../reports/investigation/current-study-01-20261018/README.md).
The live controller now rejects that configuration before model calls. A future
run requires a new prospective budget, representative unscored calibration and a
new freeze; the commands below do not authorize automatic reruns of the old study.
Runtime interventions save `runtime-alert.json` and attempt a source snapshot;
inspect those and the retained calls, then stop for review. Never resume a scored
attempt with adjusted limits/prompts or reinterpret skipped phases as completed.

The [current protocol](../benchmarks/current_local/PROTOCOL.md) is separate from
the historical SWE-bench pilot below. Its host-specific model ID, weights path,
loopback service and immutable Docker image are recorded by `current_local.py`.
Do not substitute another model and reuse an existing freeze or claim the Ubuntu
offline CI executed GPU inference. No provider credentials or paid endpoint is used.

Using new output directories, run `scripts/current_local.py grade-calibration`,
`context-calibration`, and `latency`, then `workflow-calibration` with
`--latency LATENCY/calibration.json`. Run `scripts/audit_current_image.py` to
record the image isolation check. All seven workflow phases, four real AEE/
Evaluator invocations and independently checked injected-regression repair must
pass before scoring. Keep failed preparations and every native call.

`scripts/complete_current_study.py --help` lists the explicit workflow, grade,
context, latency, image-audit, preflight, raw, report and status paths. It waits
for that workflow, stops on failure, copies successful evidence, replays the four
actual AEE checkpoints under the final dependencies, and runs the frozen twelve
trajectories/thirty-six dependent checkpoints. Supply every earlier readiness and
failed/successful calibration folder with repeated `--setup` arguments. It never
retries a failed campaign, resumes incomplete trajectories, merges or publishes.
The status and per-command logs remain under the chosen status directory.

After complete export, run `scripts/readme_results.py` to regenerate the prominent
README table from measured JSON, review the paired outcomes and unknowns, and run
the offline checks before committing. Public exports omit raw prompts/native
reasoning while retaining hashes, so exact public prompt replay is unavailable.
Raw artifacts stay local; independent grade sources and bound snapshots are
exported. A failed preflight is not a scored treatment result.

See [current tooling](current-tooling.md) for installed versions and immutable
archive reproduction, and the [lifecycle protocol](lifecycle-protocol.md) for
hallucination/cost reporting. Historical freezes retain their original versions.

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
