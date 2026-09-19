# Local exploratory campaign, 2026-09-17
**PAUSED / DRAFT:** User stopped this CPU plan before coding generation and asked
to continue on a GPU machine. See gpu-machine-handoff.md. Runtime execution was
interrupted during warmups; no completed measurement series exists. Model,
runtime, scope and adapter below are proposals, not a frozen GPU protocol.


User requested both runtime and coding comparisons with no paid inference. This
is a separate campaign, not execution of the frozen SWE-bench pilot. No model
results were inspected before selecting this protocol. API expenditure is zero;
electricity, hardware, setup and human time are not zero and are not priced.

## Runtime
One warmup then seven measured repetitions per case, seeded shuffled case order
(20260917), sequential, perf_counter_ns. Measure AEEEngine.assess on 10, 100 and
1000 synthetic unsupported claims; measure installed AEE plus Evaluator composition
and artifact recording on 10 and 100 claims; measure maintenance-triage CLI on
1000, 10000 and 100000 synthetic rows. Input construction excluded; CLI startup,
I/O and atomic output included. Publish every timing, median/min/max and hashes.
These measure this laptop and synthetic workloads, not production latency.

## Coding
Three deliberately small public Exercism Python exercises: leap, raindrops,
isogram. These are a convenience sample, not a representative random sample.
Upstream revision 1f6aab8667bf653b10cc3799f94352fcdb749db6. Use upstream unittest
files unchanged, withheld from model prompts until final grading. One attempt
per task per arm (nine total), seed-shuffled order, no retries or outcome tuning.
An unscored hello-function smoke checks local generation and grading first.

Model: official Qwen2.5-Coder-1.5B-Instruct GGUF Q4_K_M, Hugging Face revision
f86cb2c1fa58255f8052cc32aeede1b7482d4361, llama.cpp b11026 CPU, 8 threads,
16384 context, temperature 0, seed 20260917, localhost only. Record file hashes.
No model filesystem, shell, network or grader tool access. Every request includes
the same exercise description and starter. Baseline: one ordinary coding request.
Spec Kit adapted arm: constitution/specify/plan/tasks/implement/converge requests
using the frozen upstream skill text. The adapter asks for document contents in
responses instead of executing repository scripts; prior responses are passed
forward, prior skill text is not. This is a constrained workflow experiment,
NOT validation of the full Spec Kit CLI/agent integration. Max 256 output tokens
for document phases, 768 for implementation and convergence, 600 seconds/request.
All calls and input/output tokens count, including failed and truncated outputs.

Combined arm adds actual installed AEE/Evaluator assessments after specify,
plan, tasks and implement. A controller-created claim explicitly represents the
unverified model proposal, with asserted/model evidence; never pretend a model
claim is independently observed. Forward findings to the next phase. No recovery
loop, no independent test feedback and no fabricated observed evidence. This
tests conservative gap feedback, not automatic verification or full claims
extraction. Convergence emits final Python code; missing/invalid code is failure.

Grade only after all attempts finish, using upstream unittest in temporary
directories. Before execution, reject unsafe generated AST (imports except math,
re,string,collections; dunder access; eval/exec/open/compile/input and other OS
access). This is a restricted pure-function experiment, not an OS security
sandbox. Grading timeout 10 seconds. Keep all nine attempts in denominator.
Report passes, native server input/output tokens, wall time and all gaps. Do not
infer population effects, significance, token savings or superiority from this
sample. Public task contamination and a small quantized model limit conclusions.

Freeze script, protocol, skill and upstream input/test hashes before generation.
Any change after the smoke or first scored call requires a separately named run
and recorded deviation. No paid endpoints, no Codex credits, no LinkedIn posting.
