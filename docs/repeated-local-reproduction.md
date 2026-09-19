# Reproduce the repeated local comparison

Read `benchmarks/repeated_local/PROTOCOL.md` and `ADJUDICATION.md` first. This is
separate from the earlier run03 and from the original unrun SWE-bench pilot.
Do not update the email/article based on preparation or preliminary results.
The requirement tests are published in this repository. They were withheld from
these isolated solvers, but future replication is not a fresh secret-test study.

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

For a fresh checkout, create the upstream directories and image with:

```powershell
git clone https://github.com/msiemens/tinydb.git artifacts/tinydb-upstream
git -C artifacts/tinydb-upstream checkout 19066e03139e904c24410e23901e4b069d715a2e
git clone https://github.com/tkem/cachetools.git artifacts/cachetools-upstream
git -C artifacts/cachetools-upstream checkout c403f9f4185e58090b904c1915345b9ba46d5a08
docker build -t spec-kit-aee-long:replication benchmarks/long_horizon
docker image inspect spec-kit-aee-long:replication --format '{{.Id}}'
```

The measured image is not distributed through a registry. Set `IMAGE` in your
replication copy of `scripts/repeated_local.py` to the ID you actually built,
then recalibrate and create a new freeze. Do not change historical frozen inputs.
The [previous environment guide](long-horizon-reproduction.md#environment) links
the pinned llama.cpp release and model revision. Verify the weight checksum in
the protocol before loading it; shared system RAM is not dedicated GPU VRAM.

On this Windows host, commands use `.venv-gpu/Scripts/python.exe`. A fresh
`uv sync` normally creates `.venv`; substitute its Python executable throughout.
Create a writable temporary directory before the calibration commands:

```powershell
New-Item -ItemType Directory -Force artifacts/tmp-gpu | Out-Null
$env:TEMP="$PWD/artifacts/tmp-gpu"
$env:TMP=$env:TEMP
$env:PYTHONUTF8='1'
```

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

The wrapper includes this host's service-restoration script under ignored
`artifacts/repeated-assets`. A new host must supply its own ownership-checked
restoration script, hardware/package records, and installed-engine source snapshot
before using the wrapper. This is a research runner with explicit host setup,
not a one-command portable benchmark service. Never copy a historical process ID
and use it to stop a process on another machine.

## Reporting

Study01 was interrupted before hidden grading; its evidence is retained in
`reports/local/repeated-study-01-interrupted`. The replacement uses the same
model, tasks, budgets and grading with a calibrated equivalent context search.
On the measured host, `scripts/run_repeated_revision.py` waits for matched-repair01
and restoration, then starts study02 and restores the service again afterward.
It requires `artifacts/context-selection-01/result.json` from
`scripts/calibrate_context_selection.py`. That calibration uses long saved local
request traces; public exports retain their hashes rather than full requests.
A replication must supply its own saved long histories, verify equivalent
selection under its pinned template, and record a fresh calibration/freeze.

After all generation and hidden grading complete:

```powershell
.venv-gpu/Scripts/python.exe scripts/audit_repeated.py study artifacts/repeated-study-02
.venv-gpu/Scripts/python.exe scripts/audit_repeated.py repair artifacts/matched-repair-01
.venv-gpu/Scripts/python.exe scripts/report_repeated.py study artifacts/repeated-study-02 reports/local/repeated-study-02
.venv-gpu/Scripts/python.exe scripts/report_repeated.py repair artifacts/matched-repair-01 reports/local/matched-repair-01
.venv-gpu/Scripts/python.exe scripts/report_repeated_setup.py reports/local/repeated-setup-01
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
