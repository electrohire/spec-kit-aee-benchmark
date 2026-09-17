# Reproduce the free GPU exploration

Use [the frozen protocol](gpu-experiment-protocol.md), not the legacy CPU coding
draft. `scripts/local_experiment.py coding` remains historical, unvalidated code;
the GPU campaign uses `scripts/gpu_experiment.py`. No paid-provider configuration
is needed or changed. The SWE-bench pilot remains a different, unrun campaign.

## Dependencies and assets

The host used Python 3.12.6, uv 0.9.28 and locked dependencies. A local environment
and cache avoid this machine's intermittent access errors in shared temp/cache paths:

```powershell
$env:UV_CACHE_DIR = "$PWD/artifacts/uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD/artifacts/python"
$env:UV_PROJECT_ENVIRONMENT = '.venv-gpu'
uv sync --locked --group dev --extra grading
New-Item -ItemType Directory -Force artifacts/tmp-gpu | Out-Null
$env:TEMP = "$PWD/artifacts/tmp-gpu"
$env:TMP = $env:TEMP
$env:PYTHONUTF8 = '1'
.venv-gpu/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=artifacts/pytest-NEW-ID
```

Use a fresh pytest basetemp for each run. The grading container is Python 3.12.14,
identified by `python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
Docker Desktop engine was 29.8.0. Generated code never executes in the host Python.

Download official assets, retaining notices and checking their SHA-256 values:

- [Model repository at the frozen revision](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF/tree/d0a692ef765eefbf2fabb130b3cb2e8917e3d225): `qwen2.5-coder-14b-instruct-q4_k_m.gguf`.
- [llama.cpp b11026 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11026): `llama-b11026-bin-win-cuda-13.4-x64.zip` and `cudart-llama-bin-win-cuda-13.4-x64.zip`, extracted together.
- [Exercism Python revision](https://github.com/exercism/python/tree/1f6aab8667bf653b10cc3799f94352fcdb749db6), checked out under `artifacts/exercism-python`.

Model SHA-256: `c1e659736d89ac1065fb495330fb824d94001974a4bfa78e7270e43476a8d940`.
Binary archive SHA-256: `6799f0962d066c54aee3773f0e5efa0076e46418695c0f4f6d24a38e7007dfb1`.
CUDA runtime archive SHA-256: `738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668`.
The measured downloads matched official Hugging Face/GitHub metadata.

## Runtime before inference

Stop or pause competing inference with the owner's permission. Capture GPU memory,
utilization, CPU/OS/RAM/disk and source hashes before starting. Use a new directory:

```powershell
.venv-gpu/Scripts/python.exe scripts/local_experiment.py runtime reports/local/NEW-ID/runtime
```

The measured run is `reports/local/gpu-20260917/runtime-final`; the earlier
`runtime` directory is preliminary and excluded from final claims. Preserve both.
The measured series has eight warmups and 56 measured samples. Source/initial GPU
metadata is in `runtime-final/freeze.json`. Outputs are checked for stable hashes.

## Start the model

Run from the repository, with assets stored as above. In a separate terminal:

```powershell
artifacts/gpu-assets/llama/llama-server.exe `
  -m artifacts/gpu-assets/qwen2.5-coder-14b-instruct-q4_k_m.gguf `
  --host 127.0.0.1 --port 8091 --alias local-coder `
  --ctx-size 16384 --parallel 1 --n-gpu-layers 999 `
  --split-mode layer --tensor-split 10,14 --flash-attn on --fit off --threads 8
```

Record the command, executable/DLL hashes, model hash/revision, and elapsed process
launch to `/health` reporting `ok`. This is not a claim of cold disk/cache loading.
Use nvidia-smi to verify both GPUs actually hold model data. Do not alter settings
between arms. The original service must be restored after this temporary experiment.

## Smoke, freeze, generate, grade

```powershell
$image = 'python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'
.venv-gpu/Scripts/python.exe scripts/gpu_experiment.py smoke artifacts/NEW-smoke `
  --upstream artifacts/exercism-python --image $image
.venv-gpu/Scripts/python.exe scripts/gpu_experiment.py freeze artifacts/NEW-coding `
  --upstream artifacts/exercism-python --image $image `
  --metadata artifacts/NEW-machine-metadata.json --smoke artifacts/NEW-smoke
.venv-gpu/Scripts/python.exe scripts/gpu_experiment.py coding artifacts/NEW-coding `
  --upstream artifacts/exercism-python --image $image
```

Create machine metadata from the observed machine, following the published
`coding/machine-metadata.json` structure; do not copy measurements and present
them as observations of another host. Smoke estimates request latency; it does
not establish treatment-phase adequacy. The original caps were frozen before
scored output, and their observed truncation failures must remain counted.

`coding` grades only after all generations complete. It refuses implicit reruns.
For cancellation create `artifacts/NEW-coding/CANCEL`; pending requests finish or
hit their socket timeout before the next boundary. Unknown interrupted usage is
retained. Whole-attempt limits are checked between operations, not enforced by an
independent watchdog; the HTTP timeout is a socket timeout. Record any overrun.

## Export and audit

```powershell
.venv-gpu/Scripts/python.exe scripts/export_gpu_results.py artifacts/NEW-coding `
  reports/local/NEW-ID/coding --smoke artifacts/NEW-smoke --assets artifacts/gpu-assets `
  --upstream artifacts/exercism-python
```

The export verifies source hashes, request usage, counts, grades and AEE evidence
objects. It includes model responses but omits raw task prompts, retaining hashes
and upstream pins. Review generated modules and successful grader logs for spoofed
test output; this grader is not designed for adversarial evaluation attacks.
Keep original local records. A sanitized freeze is explicitly labeled and retains
the original freeze hash; it is not byte-identical to the original local freeze.

Review source paths when sharing on another machine. The frozen local sources use
literal file hashes; cross-platform line-ending conversions can change these even
when Python semantics are unchanged. A replication requires its own fresh freeze.

The complete report distinguishes workflow wall time from model HTTP time,
grading/setup time, native input/output tokens, cached tokens and API expenditure.
Token usage in controller development and human/setup effort is outside this coding
comparison; no claim of a zero-cost development process is made.

## Separately frozen repair supplement

After preserving the primary results, and only under the separately authorized
[repair protocol](gpu-repair-protocol.md), run against the same unchanged server:

```powershell
.venv-gpu/Scripts/python.exe scripts/gpu_repair.py artifacts/NEW-coding `
  artifacts/NEW-repairs --upstream artifacts/exercism-python
.venv-gpu/Scripts/python.exe scripts/export_gpu_repairs.py artifacts/NEW-repairs `
  reports/local/NEW-ID/repair --primary artifacts/NEW-coding
```

Do this before stopping the dedicated model server. The repair script freezes its
policy and refuses an existing output directory. Its outcomes use test feedback;
keep them separate from the primary held-out generation outcomes.
