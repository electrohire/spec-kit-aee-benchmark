# Reproduce the repeated local comparison

Read `benchmarks/repeated_local/PROTOCOL.md` and `ADJUDICATION.md` first. This is
separate from the earlier run03 and from the original unrun SWE-bench pilot.
Do not update the email/article based on preparation or preliminary results.

## Prerequisites

Use Python3.12 and `uv sync --locked --group dev`. The measured host uses Python3.12.6
in `.venv-gpu`, verified RTX4070SUPER12282MiB plus RTX5060Ti16311MiB, and the same
local quantized Qwen weight/hash as run03. No API keys, paid endpoints or fallback.
The adapter's HTTP helper only addresses127.0.0.1:8091 and disables proxies/redirects.

Clone the pinned TinyDB and cachetools revisions listed in PROJECTS in
`scripts/repeated_local.py` into `artifacts/tinydb-upstream` and
`artifacts/cachetools-upstream`. Use the immutable Linux Docker image from the
previous long study; rebuilding it produces a newly recorded image identity.
The solver/grader containers have no host mounts or network and run nonroot.

Start an owned localhost llama.cpp server using the recorded launch arguments.
On the measured host the existing8081router remains running while its model is
unloaded to free VRAM. A separate8091benchmark server uses both GPUs. Never stop
an unrelated PID. Restore the original model after the suite, including on failure.

## Calibration and freeze

Run in order, using fresh output directories for every failed or changed attempt:

```powershell
.venv-gpu/Scripts/python.exe scripts/repeated_local.py calibrate artifacts/repeated-calibration-01
.venv-gpu/Scripts/python.exe scripts/repeated_local.py latency artifacts/repeated-latency-01
.venv-gpu/Scripts/python.exe scripts/calibrate_repeated_workflow.py artifacts/repeated-workflow-04
.venv-gpu/Scripts/python.exe scripts/matched_repair.py calibrate artifacts/matched-calibration-01 --preflight artifacts/repeated-calibration-01
```

Workflow attempts01–03 are retained development failures; do not overwrite or
exclude their work. The final workflow gate path is explicit in the runner and
must match the completed calibration. Changing paths/protocol requires a new
freeze. Model-free grader references and unrelated model workflow calibration
serve different purposes. Both must pass before scored generation.

The suite wrapper sequentially starts the12 project trajectories and16 matched
repair pairs, then restores the original model in `finally`:

```powershell
.venv-gpu/Scripts/python.exe scripts/run_repeated_suite.py
```

On another host, adapt only preflight paths/server ownership and record a new
freeze. A campaign creates a new directory exclusively; it does not selectively
resume or overwrite partial attempts. Keep interrupted directories and report
all work. Review the full freeze and pinned source hashes before a new run.

## Reporting

After all generation and hidden grading complete:

```powershell
.venv-gpu/Scripts/python.exe scripts/report_repeated.py study artifacts/repeated-study-01 reports/local/repeated-study-01
.venv-gpu/Scripts/python.exe scripts/report_repeated.py repair artifacts/matched-repair-01 reports/local/matched-repair-01
.venv-gpu/Scripts/python.exe scripts/check_evidence.py
```

The export preserves source/workflow snapshots, tool evidence, grades, usage,
request hashes and native-response hashes with reasoning omitted. Exact public
request replay is unavailable. Check generated totals against raw call records.
Manually adjudicate findings under the frozen rubric and publish both judgments
and evidence. Generic epistemic gaps must not be counted as detected coding bugs.

Shared diagnosis in matched repairs is physical work counted once. Comparative
repair economics charge that identical diagnostic to each arm, separately labeled.
Do not sum those attributed arm totals as the physical inventory. Unknown tokens
remain unknown; conservative budget reservations are separately labeled bounds.
Zero accepted/fixed cases yield undefined tokens per acceptance/fix.
