# Free GPU exploration protocol, 2026-09-17

This is the smaller exploration expressly permitted in the GPU handoff, not the
20 x 3 x 3 SWE-bench pilot. The existing paid-provider runner remains gated and
unchanged. A new localhost-only runner avoids any paid API path. No coding scores
were inspected in selecting tasks, model, limits or schedule.

## Specification and rationale

GPU-001: retain every attempted call, failure, truncation and unknown token count.
GPU-002: execute generated code only inside isolated Docker, including smoke.
GPU-003: freeze one model/configuration, sources, dependency versions, prompts,
upstream tests and shuffled schedule before scored generation; no silent reruns.
GPU-004: grade only after all generations; use unchanged upstream tests and require
the expected nonzero test count, no skips, normal exit and no errors/failures.
GPU-005: publish all-arm counts, latency and native token totals, with zero API
expenditure separate from unpriced local compute, electricity and setup.
GPU-006: report actual AEE assessments separately from correctness grades.

The independent runner review found host code execution, incomplete failed-call
accounting, no total deadline and document-adaptation limitations in the old draft.
The new runner fixes execution/accounting and documents the remaining scope limits.
The previous runtime series started before this protocol and is preliminary only.
Its original samples remain preserved and are excluded from final runtime claims.

## Model and hardware

Qwen/Qwen2.5-Coder-14B-Instruct-GGUF, Q4_K_M, official model repository revision
d0a692ef765eefbf2fabb130b3cb2e8917e3d225. Apache-2.0 model license. Weight SHA-256
c1e659736d89ac1065fb495330fb824d94001974a4bfa78e7270e43476a8d940.
llama.cpp b11026 (b49650adb), Windows CUDA 13.4 binary, pinned archive hashes in
machine metadata. Server bound to 127.0.0.1:8091, no credentials, proxies, redirects
or external-provider fallback. Temperature 0, seed 20260917, one slot, context
16384, all layers on GPU, layer split 10:14, flash attention on, fit off.
The model is an established coding-specific non-thinking model with official
quantized artifacts, selected for a reproducible bounded pilot, not asserted to
be the strongest available model. Existing Qwen3.6 service is paused and restored.

Both GPUs verified in one host: RTX 4070 SUPER 12282 MiB and RTX 5060 Ti 16311 MiB;
Studio driver 610.88, Intel i9-14900F, 64 GB RAM, Windows 11 Pro for Workstations.
User reports PCIe Gen4 x16 and x4 respectively. Shared system RAM is not VRAM.
This split is explicit; memory does not automatically pool. Record actual offload
and VRAM usage from runtime logs/nvidia-smi. Cold process launch to health-ready
is separate from unscored request and steady-state generation.

## Coding design

Six convenience tasks: leap, raindrops, isogram, pangram, hamming, resistor-color.
One attempt per task per arm, 18 total, shuffled with seed 20260917. More distinct
tasks than the old three-task draft; no repetitions or population inference.
Pinned Exercism Python revision 1f6aab8667bf653b10cc3799f94352fcdb749db6.
Inputs are only introduction.md (if present), instructions.md and the starter;
no reference solutions, tests, controller instructions or sibling output.

One common ceiling for all arms: 900 seconds/attempt, 120 seconds/request,
100000 cumulative input tokens and 8192 output tokens; conservative 16384-input
reservation before each call. Baseline gets one ordinary solve request. Adapted
Spec Kit gets constitution, specify, plan, tasks, implement, converge and final
implement. Documents max 512 output tokens; code max 1024. Truncation is a failure,
not an accepted partial document. Converge proposes tasks; final implement emits
code. This corrects the old draft's instruction to make converge write code.
Every arm uses identical task text/model/settings, fresh histories and no tools.
Different phase counts deliberately incur different actual resource use.

Combined treatment runs installed AEE 1.0.2 and Evaluator adapter/composition after
specify, plan, tasks and implement. It assesses one controller-written unverified
generic requirement, not model-extracted claims. Findings are forwarded, with no
test feedback or recovery loops. This does not measure claim extraction, coverage,
defect detection or full workflow effectiveness. The feedback says it is not a grade.

Unscored hello-function development smoke must pass in Docker before freezing.
No task tests run until all attempts finish. Frozen grading image by digest,
network disabled, non-root, read-only root, no mounts/keys, all capabilities dropped,
no-new-privileges, 1 CPU/256 MiB/64 PIDs, 20-second host timeout and forced cleanup.
Generated module and unchanged tests enter through a tar stream into private tmpfs.
AST checks are additional filtering, not the isolation boundary. Test discovery
counts are frozen from upstream source. Failed final phases never use earlier code.
Unknown usage remains null and known subtotals are reported. All failures remain
in the denominator; any rerun needs a new campaign and published deviation.

## Runtime design

No concurrent model inference. One warmup and seven measured repetitions per case,
seeded shuffled measured order, sequential perf_counter_ns. AEE engine with 10,
100 and 1000 synthetic unsupported claims; installed AEE+Evaluator pipeline with
10 and 100; maintenance-triage CLI with 1000, 10000 and 100000 synthetic rows.
Input construction excluded; pipeline subprocess startup and evidence I/O included;
CLI startup, input/output and atomic replacement included. Preserve all samples,
warmups separately, normalized substantive result hashes and hardware/load context.
Report median/min/max, no laptop comparison or production-performance inference.

## Evidence, limits and publication

Local raw records stay under artifacts; reviewed results, grades, model responses,
request hashes, usage, freeze hashes and source metadata are committed under reports.
Full upstream dataset/task text need not be republished. This is a single-machine,
single-model, small public convenience sample with potential training contamination,
document-only Spec Kit and controller-created claims. Combined Evaluator+AEE cannot
isolate either component. Controller and implementation authors are not independent;
upstream tests supply a separate correctness stream. Host background apps/load remain
a timing limitation. No claim of superiority, token savings or correctness improvement
is justified merely by successful tests or an AEE outcome.

ElectroHire maintains the AEE/Evaluator projects. Article links versioned evidence
and relevant upstream sources. Push to existing branch/draft PR only; no merge or
LinkedIn publication. Constitution 1.1.0 records this authorized separate scope.

## Implementation tasks

- Freeze protocol and sources; retain controller assessment evidence at all phases.
- Harden localhost transport, pending-call ledger, deadlines and terminal-phase rules.
- Validate Docker smoke, failed/zero-test grading, truncation and unknown accounting.
- Run isolated runtime series, smoke, freeze, all-arm generation and final grading.
- Audit artifacts and article numbers; preserve limitations and push draft PR.

Controller development deviation: runner hardening began during specification review
before this consolidated protocol file was written. No scored coding generation had
begun. Controller AEE outcomes must remain evidence-gap decisions, not retroactive
proof of a strictly ordered controller development process.
