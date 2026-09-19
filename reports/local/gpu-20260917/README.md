# Measured GPU exploration and repair supplement — 2026-09-17

**Observed result:** the document-adapted workflows used substantially more tokens
and had fewer passing primary solutions in this six-task sample. After a shared
repair policy all arms passed 5/6 of the now feedback-exposed upstream test suites.
No superiority, token saving, or full Spec Kit integration claim is supported.

Six public Exercism tasks, one attempt/task/arm: 18 primary attempts, not 18 tasks.
Qwen2.5-Coder-14B-Instruct Q4_K_M, llama.cpp b11026, both NVIDIA GPUs, zero paid model
API calls. The planned 20 x 3 x 3 SWE-bench pilot remains unrun.

## Primary token economics

Correct answer means a final submitted module passing every unchanged upstream test
with expected test discovery and no skips. Tokens include every phase and failed
attempt. Tokens per correct answer = all-attempt input + output / passing solutions
(with parentheses around the summed numerator). Input and output are also shown
separately; they have different computational costs and are not dollar-equivalent.

| Arm | Passes / attempts | Calls | Input tokens | Output tokens | Total tokens | Tokens / correct |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 5/6 | 6 | 1,844 | 495 | 2,339 | 467.80 |
| Spec Kit (adapted) | 2/6 | 29 | 107,882 | 6,273 | 114,155 | 57,077.50 |
| Spec Kit + AEE (adapted) | 1/6 | 25 | 125,705 | 5,653 | 131,358 | 131,358.00 |

All native usage was known; cached input tokens were zero. No failed work is excluded.

| Arm | Workflow seconds | HTTP seconds | Median attempt seconds | Workflow seconds / correct | Tokens on failed attempts | Truncated calls |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 13.22 | 13.11 | 1.84 | 2.64 | 394 | 0 |
| Spec Kit (adapted) | 193.30 | 192.75 | 32.31 | 96.65 | 58,887 | 3 |
| Spec Kit + AEE (adapted) | 193.47 | 185.84 | 31.47 | 193.47 | 86,936 | 4 |

Workflow time includes model HTTP calls, assessments and bookkeeping; it excludes
model startup, development smoke, primary grading and setup. HTTP time is not GPU
kernel time. The seven truncations happened at the frozen 512-token document cap;
they are workflow/cap failures, not seven demonstrated coding-ability failures.
The 11 normally generated final modules had three failing test suites: Hamming
in baseline and combined arms (missing error-message period), and resistor-color
in the adapted Spec Kit arm (colors() referred to a function-local color_map).
No successful final module contains grader-output spoofing or process manipulation.

## Supplemental actual repair loops

The user requested this study after primary results existed. Its own policy was
frozen before repair generation: same model, up to two ordinary repair calls per
failed case, same failure-feedback prompt for all arms, no reruns of passing cases.
These are **same-test feedback outcomes**, not independent held-out repair scores.

| Arm | Eligible failures | Repair calls | Newly fixed (round 1 / 2) | Final passes | Repair input / output | Cumulative tokens | Cumulative tokens / correct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 1 | 2 | 0 / 0 | 5/6 | 2,320 / 126 | 4,785 | 957.00 |
| Spec Kit (adapted) | 4 | 5 | 3 / 0 | 5/6 | 2,846 / 618 | 117,619 | 23,523.80 |
| Spec Kit + AEE (adapted) | 5 | 6 | 4 / 0 | 5/6 | 3,675 / 547 | 135,580 | 27,116.00 |

| Arm | Repair seconds including grading | Repair HTTP seconds | Repair grading seconds | Repair tokens / newly fixed case | Changed code submissions |
| --- | --- | --- | --- | --- | --- |
| Baseline | 6.33 | 4.53 | 1.75 | undefined | 0 |
| Spec Kit (adapted) | 20.03 | 15.52 | 4.38 | 1,154.67 | 4 |
| Spec Kit + AEE (adapted) | 20.16 | 14.62 | 5.38 | 1,055.50 | 4 |

Seven cases were fixed on their first repair; no second-round repair fixed another
case. All three remaining failures were Hamming. The model kept producing the error
message without the final period despite explicit test diffs. Six unsuccessful
Hamming repair calls remain counted. Generation-cap failures received an ordinary
implementation request with empty submitted code; that is recovery from a failed
workflow, not evidence that AEE repaired code. Repair stages did not rerun AEE or
Spec Kit documents. Their results cannot establish an AEE-specific repair advantage.

## Scheduled revision versus actual rework

The original adapted workflows include a convergence review and final implementation
pass. Secondary grading of normally completed initial implementations occurred after
all primary generation; it supplied no feedback to the primary model calls.

| Arm | Initial/solve + final implementation calls | Completed convergence reviews | Scheduled final passes | Comparable initial/final code pairs | Text / AST changes | Primary initial-to-final grades |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 6 | 0 | 0 | 0 | 0 / 0 | {} |
| Spec Kit (adapted) | 6 | 3 | 3 | 3 | 0 / 0 | {"fail -> fail": 1, "pass -> pass": 2} |
| Spec Kit + AEE (adapted) | 4 | 2 | 2 | 2 | 0 / 0 | {"fail -> fail": 1, "pass -> pass": 1} |

All five completed initial/final pairs were unchanged. Scheduled reviews therefore
produced zero observed code fixes in this sample. They must not be described as
successful repair loops. Actual test-feedback loops are the separately counted
13 supplemental calls above. Primary infrastructure retries and AEE recovery loops
were zero. Eleven installed AEE/Evaluator assessments returned gather_evidence;
each examined a controller-written generic unverified claim, not extracted code
claims. This demonstrates evidence-gap processing, not defect detection.

## Per-task paired outcomes

| Task | Arm | Primary | Primary tokens | Primary tests run | Repair calls | After repair |
| --- | --- | --- | --- | --- | --- | --- |
| hamming | Baseline | test failure | 394 | 9 | 2 | fail |
| hamming | Spec Kit (adapted) | truncated | 10501 | not run | 2 | fail |
| hamming | Spec Kit + AEE (adapted) | test failure | 43604 | 9 | 2 | fail |
| isogram | Baseline | pass | 303 | 14 | 0 | pass |
| isogram | Spec Kit (adapted) | truncated | 7132 | not run | 1 | pass |
| isogram | Spec Kit + AEE (adapted) | truncated | 7132 | not run | 1 | pass |
| leap | Baseline | pass | 311 | 9 | 0 | pass |
| leap | Spec Kit (adapted) | truncated | 10572 | not run | 1 | pass |
| leap | Spec Kit + AEE (adapted) | truncated | 11774 | not run | 1 | pass |
| pangram | Baseline | pass | 337 | 12 | 0 | pass |
| pangram | Spec Kit (adapted) | pass | 27721 | 12 | 0 | pass |
| pangram | Spec Kit + AEE (adapted) | pass | 44422 | 12 | 0 | pass |
| raindrops | Baseline | pass | 450 | 18 | 0 | pass |
| raindrops | Spec Kit (adapted) | pass | 27547 | 18 | 0 | pass |
| raindrops | Spec Kit + AEE (adapted) | truncated | 11810 | not run | 1 | pass |
| resistor-color | Baseline | pass | 544 | 4 | 0 | pass |
| resistor-color | Spec Kit (adapted) | test failure | 30682 | 4 | 1 | pass |
| resistor-color | Spec Kit + AEE (adapted) | truncated | 12616 | not run | 1 | pass |

## Phase token and latency accounting

| Arm | Phase | Calls | Input | Output | HTTP seconds | Truncations |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | solve | 6 | 1844 | 495 | 13.11 | 0 |
| Spec Kit (adapted) | constitution | 6 | 14786 | 1455 | 40.55 | 0 |
| Spec Kit (adapted) | converge | 3 | 13320 | 512 | 17.66 | 0 |
| Spec Kit (adapted) | final_implement | 3 | 14291 | 298 | 13.02 | 0 |
| Spec Kit (adapted) | implement | 3 | 13460 | 298 | 12.58 | 0 |
| Spec Kit (adapted) | plan | 5 | 13046 | 2048 | 53.56 | 2 |
| Spec Kit (adapted) | specify | 6 | 27652 | 1398 | 44.64 | 1 |
| Spec Kit (adapted) | tasks | 3 | 11327 | 264 | 10.75 | 0 |
| Spec Kit + AEE (adapted) | constitution | 6 | 14786 | 1455 | 40.55 | 0 |
| Spec Kit + AEE (adapted) | converge | 2 | 17932 | 332 | 15.41 | 0 |
| Spec Kit + AEE (adapted) | final_implement | 2 | 18570 | 109 | 9.86 | 0 |
| Spec Kit + AEE (adapted) | implement | 2 | 15712 | 109 | 8.55 | 0 |
| Spec Kit + AEE (adapted) | plan | 5 | 19055 | 2179 | 60.25 | 3 |
| Spec Kit + AEE (adapted) | specify | 6 | 27652 | 1398 | 44.62 | 1 |
| Spec Kit + AEE (adapted) | tasks | 2 | 11998 | 71 | 6.61 | 0 |

## Native runtime throughput

Weighted rates sum native tokens and divide by summed native phase time.

| Arm | Prompt tokens/s | Decode tokens/s |
| --- | --- | --- |
| Baseline | 1,824.72 | 45.40 |
| Spec Kit (adapted) | 2,874.69 | 42.46 |
| Spec Kit + AEE (adapted) | 2,739.47 | 41.75 |

Process launch to health-ready was 3.695 seconds, including runtime initialization.
This is not a measured cold disk/cache load. The excluded hello development call
used 44 input + 13 output tokens and 0.860 seconds HTTP time; its one Docker test
passed. Deliberately wrong-code and zero-test grading checks both failed as required.

## Deterministic application and AEE runtime

One warmup and seven measured repetitions per case; seed-shuffled measured order.
No concurrent model inference. Input construction excluded. Pipeline includes
subprocess startup, Evaluator composition and evidence I/O. CLI includes startup,
file I/O and atomic output. All substantive output hashes matched within each case.

| Workload | Size | Median ms | Min ms | Max ms | Measured repetitions |
| --- | --- | --- | --- | --- | --- |
| engine | 10 | 0.59 | 0.51 | 1.03 | 7 |
| engine | 100 | 26.28 | 25.72 | 28.56 | 7 |
| engine | 1000 | 2,453.51 | 2,400.39 | 2,472.26 | 7 |
| pipeline | 10 | 661.50 | 646.48 | 680.83 | 7 |
| pipeline | 100 | 800.02 | 785.54 | 813.36 | 7 |
| triage | 1000 | 186.99 | 182.29 | 227.83 | 7 |
| triage | 10000 | 431.79 | 373.65 | 465.80 | 7 |
| triage | 100000 | 1,383.32 | 1,300.67 | 2,123.81 | 7 |

The earlier local `runtime/` series is preliminary and excluded; the interrupted
laptop warmups are also not results. Desktop background apps remained running;
a short controller AEE assessment operation overlapped part of the runtime series.
This host-load interference and wide CLI range limit precision. The data is not an
isolated performance laboratory result or a CPU/GPU speedup comparison. AEE/triage
workloads are CPU/Python measurements; the GPUs accelerate the coding model.

## Hardware, spending and scope

Observed i9-14900F (24 cores / 32 threads), 64 GB RAM, Windows 11 Pro for Workstations,
driver 610.88. nvidia-smi: 4070 SUPER 12282 MiB; 5060 Ti 16311 MiB. User's hardware
report: Gen4 x16 and x4 respectively. Explicit 10:14 layer split; 16384 context,
one slot, temperature zero, seed 20260917. Shared system memory is not counted as
VRAM. Post-smoke usage was about 6523/6927 MiB; sampled load is retained in CSV.
Server properties matched before primary generation and after repairs. The original
Qwen3.6 service was restored and its model reported loaded after the experiment.

Benchmark model API expenditure: **USD 0**. Local electricity, hardware depreciation,
downloads, controller development and human/setup time are unpriced, not zero.
There were 60 primary + 13 repair + 1 development model calls, all to the dedicated
localhost server. Primary + repair tokens total 257984; excluded development adds
57 tokens. No paid OpenAI provider or credit-consuming benchmark endpoint was used.

Limitations: six convenience tasks; public contamination; one quantized model;
no repeats; document-only Spec Kit; no solver shell/repository tools; unequal
phase counts; restrictive document caps; generic AEE claims; no component-isolated
AEE effect; test-feedback exposure in repairs; controller-authored harness; and
no external replication. AST filtering can reject valid programs, although no
observed final grade here failed that filter. Timeout checks are between operations
and HTTP timeouts are socket timeouts; no independent whole-operation watchdog.
No observed request/attempt exceeded its limit. Grader output parsing is not
hardened against adversarial spoofing; reviewed submitted modules did not do so.

Expanded economics/revision analysis was requested during generation, but its
written-plan hash was captured after primary results existed. The initial text
and corrected plan remain on record. Repair policy was separately frozen before
repair outputs. Controller development did not strictly follow every Spec Kit
setup command in sequence; this deviation is explicit in the protocol.

ElectroHire maintains the evaluated AEE/Evaluator projects. This is a conflict of
interest. Treat these artifacts as inspectable local evidence, not a marketing
proof or a claim that full Spec Kit worsens coding.

## Evidence and reproduction

- [Primary summary](coding/coding-summary.json), [per-attempt grades and rework](coding/results.json), [sanitized freeze](coding/freeze-sanitized.json), [audit](coding/audit.json).
- [Repair summary](repair/summary.json), [all repair rounds](repair/results.json), [repair freeze](repair/freeze.json), [audit](repair/audit.json).
- [Runtime samples](runtime-final/runtime.json), [summary](runtime-final/runtime-summary.json), [runtime freeze](runtime-final/freeze.json).
- [Primary protocol](../../../docs/gpu-experiment-protocol.md), [repair protocol](../../../docs/gpu-repair-protocol.md), [reproduction](../../../docs/gpu-reproduction.md).
- [Regression test output](tests-final.txt): 49 passed; original 41-test checks are retained under reports/offline.
- [Spec Kit](https://github.com/github/spec-kit), [AEE extension](https://github.com/electrohire/spec-kit-aee), [Evaluator](https://github.com/electrohire/spec-kit-evaluator), [AEE engine](https://github.com/electrohire/applied-epistemic-engineering).
- [Model revision](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF/tree/d0a692ef765eefbf2fabb130b3cb2e8917e3d225), [runtime release](https://github.com/ggml-org/llama.cpp/releases/tag/b11026), [Exercism source](https://github.com/exercism/python/tree/1f6aab8667bf653b10cc3799f94352fcdb749db6), [canonical problem specifications](https://github.com/exercism/problem-specifications).

Operational failures preserved: original laptop interruption; initial GPU-host
uv/shared-temp permission errors (a test invocation had 19 passes/29 setup errors);
successful retry used a project-local environment/temp directory. No model attempt
was rerun to hide these setup issues. Seven primary truncations, three primary test
failures and six failed repair calls are all visible in the evidence.
