# Reproduce the staged-project supplement

This is a separately frozen local study, not the original SWE-bench campaign.
Read `benchmarks/long_horizon/PROTOCOL.md` and all three milestone descriptions.
Requirements, visible tests and withheld tests were written before scored output.
The hidden cases become public with this report, so future runs are no longer
secret-test replications. The original small-task results remain available.

The author selected a combination of real-repository maintenance and a staged
feature build in response to the user's request for a more representative long
horizon. TinyDB keeps execution local and inexpensive while exposing requirements
that interact across stages: nested mutation, retained handles, caches, IDs,
rollback, validation and persistence. It is still a small project exercise, not
days of production engineering or a representative repository sample.

## Environment

Use Python 3.12.6 and this repository's locked dependencies. On the measured
Windows host `.venv-gpu` and project-local TEMP/TMP avoid intermittent global
cache/temp ACL failures. The installed uv was 0.9.28 rather than the documented
0.11.32; packages were installed from the lock. Docker runs Linux containers.

Clone https://github.com/msiemens/tinydb and check out
`19066e03139e904c24410e23901e4b069d715a2e`. Build:

```powershell
docker build -t spec-kit-aee-long:20260917 benchmarks/long_horizon
docker image inspect spec-kit-aee-long:20260917 --format '{{.Id}}'
```

The measured immutable image ID is in the campaign freeze. Rebuilding apt/pip
layers can produce a different image even with the same base digest and package
versions; record that difference rather than claiming bitwise reproduction.

Use llama.cpp b11026 from https://github.com/ggml-org/llama.cpp/releases/tag/b11026
and the frozen quantization from
https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/a483e9e6cbd595906af30beda3187c2663a1118c
based on https://huggingface.co/Qwen/Qwen3.6-35B-A3B.
Verify the SHA256 in the protocol. Bind the server to 127.0.0.1:8091 using the
saved launch arguments. No API key, proxy, external fallback or provider SDK is
used by this adapter. Do not start the repository's paid provider.

The existing 8081 router was left alive and its loaded model temporarily unloaded
to reserve the GPUs. The dedicated 8091 server uses that same local weight with
a fixed 131072-token context. Restore the router's model when finished. Shared system
RAM is not dedicated VRAM; the measured devices have 12282 and 16311 MiB.

## Preflight, generation and reporting

The archived `preflight/calibrate.py` builds a reference source only inside a
calibration container. It passes all public/hidden combinations and verifies
that unchanged TinyDB fails new-feature tests. Its source is never supplied to
solvers. `preflight/smoke-v11.py` validates all seven workflow phases, four actual
AEE/Evaluator assessments, and unrelated arithmetic code with independent checks.
All earlier smoke failures and both interrupted campaigns are retained.
Calibration is a test-harness check, not scored model work.

Create metadata with successful smoke/calibration records and verified file
hashes, following the archived metadata schema. Use a fresh output directory:

```powershell
$env:TEMP="$PWD\artifacts\tmp-gpu"
$env:TMP=$env:TEMP
$env:PYTHONUTF8='1'
.\.venv-gpu\Scripts\python.exe scripts/long_horizon.py artifacts/long-horizon-new --upstream artifacts/tinydb-upstream --image IMAGE_SHA256 --metadata artifacts/long-assets/metadata.json
.\.venv-gpu\Scripts\python.exe scripts/report_long_horizon.py artifacts/long-horizon-new reports/local/long-horizon-new
.\.venv-gpu\Scripts\python.exe scripts/check_evidence.py
```

No resume/overwrite is supported: retain interrupted directories and start a new
frozen campaign for protocol changes. A `CANCEL` file in the campaign root stops
at the next model step. A request already in flight can finish; pending request
records preserve uncertain usage if interrupted. Full requests remain local,
with response records and request hashes exported. Source/workflow snapshots,
shell evidence and all grading failures are exported with file checksums.

## Controller workflow and limitations

Controller work used the installed Spec Kit planning workflow and real AEE
assessments during the earlier campaign. This supplement implements the user's
changed workload request using that existing infrastructure. It was not a fresh,
fully sequential controller Spec Kit project cycle; do not claim otherwise.
The benchmark-run skill's original SWE-bench-only commands are superseded here
by the user's explicit free-local experiment change. The separate adapter/grader
and their calibration are exposed for review. The original paid gates remain.

Run 03 uses thinking with a 2048-token reasoning budget, resolved skill arguments,
full conversation history with native reasoning retention, same-repository workflow
files, and within-arm prompt caching. Source snapshots transfer only TinyDB Python
modules. Primary work receives 120 calls/2400 seconds per stage; two repair rounds
reserve 20 calls each within 160 calls/3000 seconds total. Each project is capped at
480 calls and 60M logical input plus output tokens. Cached input is part of logical
input, not an additional charge or a reason to erase context cost. See the frozen
protocol for the complete revision history and assessment-scope limitations.

Additional environment failures retained in this task: the first calibration
container could not archive the upstream clone because Git detected differing
Windows ownership. The runner now uses a per-command safe.directory exception
for the exact upstream path, without changing global Git configuration. That
unused, unmounted temporary container was inspected and removed. Intermittent
sandbox denial of the Docker pipe also occurred during cleanup; it did not
interrupt the already-running scored process.
