# Resume on the GPU machine

## User request and intended outcome

Stop work on this laptop, save the session and plan, and push to Git. Continue
later on the user's machine with RTX 4070 SUPER, 12 GB VRAM, and RTX 5060 Ti
(VRAM not yet confirmed). Do not start more experiments until that continuation.

Deliver both local application/AEE runtime measurements and a three-arm coding
comparison, with zero paid API calls or credit spending. Then write an honest,
persuasive LinkedIn article encouraging readers to try Spec Kit + AEE, ready to
copy/paste, including URLs for every relevant repository and source. Do not post
it. The original ZIP is explicitly excluded. Do not merge the draft PR.

Repository: https://github.com/electrohire/spec-kit-aee-benchmark
Branch: feat/benchmark-harness
Draft PR: https://github.com/electrohire/spec-kit-aee-benchmark/pull/1

## Start here on the other machine

Choose a parent directory for development, open PowerShell there, and run:

```powershell
git clone --branch feat/benchmark-harness --single-branch https://github.com/electrohire/spec-kit-aee-benchmark.git
Set-Location spec-kit-aee-benchmark
git status --short --branch
```

Open that folder in the coding agent and paste this instruction:

```text
Continue the free local Spec Kit + AEE benchmark and LinkedIn article project.
Read AGENTS.md, START_HERE.md, docs/gpu-machine-handoff.md and the constitution
before making changes. Follow the resume sequence in the GPU handoff.

This machine has an RTX 4070 SUPER with 12 GB VRAM and an RTX 5060 Ti; inspect
the actual GPUs, VRAM and drivers before selecting a model/runtime. Use free
local inference only. Do not use paid APIs or paid Codex credits. Do not use
the previously mentioned ZIP. Keep work on feat/benchmark-harness and the
existing draft PR; do not merge or post to LinkedIn.

Run both deterministic application/AEE overhead benchmarks and a fair coding
comparison of baseline, Spec Kit, and Spec Kit + Evaluator + AEE. The previous
laptop run stopped during warmups: it produced no publishable timing series
and no model-generated coding results. Review the draft runner before use,
prefer faithful workflow execution, freeze a feasible protocol before scored
results, and grade independently. Preserve all failures and token overhead.

After measuring, write a compelling copy/paste LinkedIn article encouraging
people to try Spec Kit + AEE. Ground every numerical claim in actual results,
disclose limitations and ElectroHire's maintenance role, and include URLs for
all relevant repositories, model/runtime sources and versioned results.
Save Markdown and plain-text versions, verify the evidence, and push all work
to the existing branch/draft PR. Proceed without unnecessary confirmation
within this free-local scope; never invent benchmark wins or token savings.
```

## What is actually done

- Original controller, tutorial, accounting and offline integration: 41 tests
  previously passed; Linux CI passed. Frozen 180-attempt SWE-bench schedule is a
  dry run only. No scored SWE-bench results, paid calls or real Docker gold smoke.
- Actual deterministic AEE and Evaluator execution exists under reports/offline.
- Current laptop Docker daemon was unavailable. Codex subscription allowance was
  exhausted; available paid credits were deliberately not used.
- Started the separate runtime script, then interrupted it on the user's stop
  instruction. reports/local/runtime-20260917 contains seven warmups and evidence
  objects only. No measured repetitions or publishable runtime summary.
- Downloaded llama.cpp b11026 CPU binaries and official Qwen2.5-Coder-1.5B-Instruct
  Q4_K_M weights outside the repository. No model server or inference was started.
- scripts/local_experiment.py and docs/local-benchmark-protocol.md are UNVALIDATED
  DRAFTS. They are saved work, not a ready-to-run GPU campaign. No coding freeze,
  smoke, generation, grading or comparative results exist.
- docs/linkedin-article.md is the prior unrun-results draft. Do not present it as
  a completed benchmark article. New article drafting waits for actual results.

## Resume sequence

1. Clone the repo and check out feat/benchmark-harness. Read AGENTS.md,
   constitution, this handoff, protocol, reproduction and relevant project skills.
   Install pinned Python 3.12.6/uv dependencies; run the existing offline checks.
2. Inventory actual hardware with nvidia-smi: both GPU names, VRAM, drivers,
   available RAM/disk and OS. Confirm whether both GPUs are in the same host.
   Do not assume the 5060 Ti has 16 GB or that GPU memory automatically pools.
3. Select a free open-weight coding model and GPU runtime using current official
   documentation. Prefer the strongest practical model fitting verified hardware
   with adequate context. Consider a 7B-class quantized coder as a candidate,
   rather than committing to the laptop's 1.5B model. Verify license, exact model
   revision, weight checksum and runtime version. Download from official sources.
   Bind inference to localhost; disable external-provider fallback. No paid keys.
4. Use a development task excluded from scored tasks to establish stable GPU
   inference, native token accounting, deterministic settings and grading. Record
   both cold model loading and steady-state work separately. Choose one model and
   fixed hardware configuration for all arms. Do not change them based on scores.
5. Decide the coding campaign before outcomes. Prefer the existing mini-SWE-agent
   runner plus a separately implemented localhost provider and working Docker
   isolation/grading, preserving full Spec Kit skill execution. The current
   provider is for paid OpenAI calls: do not bypass its gates or mislabel local
   inference as that provider. Real gold smoke precedes SWE-bench generation.
   Estimate duration from the unscored smoke; freeze a feasible local pilot size.
   The original 20 × 3 × 3 pilot remains unrun unless actually executed.
6. If using the smaller Exercism exploration instead, explicitly retain its
   limitations: three convenience tasks, public-test contamination, small sample,
   document-only Spec Kit adaptation, no repository scripts/tools and a
   controller-created assertion rather than model-extracted claim coverage. It
   cannot establish full Spec Kit effectiveness or AEE correctness improvements.
   Use unchanged upstream tests, held out until final grading. Never improvise
   passing criteria or tune on scored output. Consider more tasks/repetitions
   before freezing, based on smoke feasibility, not favorable outcomes.
7. Review and harden the draft script before running it. Replace hard-coded D:
   paths with CLI options; record GPU runtime/settings and all dependencies;
   enforce whole-attempt limits, interrupted-call usage uncertainty and failures;
   freeze installed AEE/Evaluator/adapter sources as well as prompts/tests;
   verify no task answer/reference solutions enter prompts. Its AST filter is
   not a security sandbox: execute generated code in proper OS isolation.
   Ensure final-phase failure cannot silently grade earlier implementation code.
   Ensure grading actually discovers tests and checks nonzero test count.
8. Freeze the new protocol, selection, settings, runner, source hashes, grading
   inputs and shuffled schedule before scored generation. Use a fresh run ID.
   Preserve original interrupted warmups; do not resume them as a complete run.
9. Run deterministic performance measurements with no concurrent model workload:
   AEE engine scaling, installed AEE+Evaluator pipeline, and triage CLI workloads.
   Retain warmups separately and all measured samples; validate output hashes.
   Record CPU/GPU utilization/context so comparison is interpretable. Then run
   all coding arms sequentially/interleaved with identical tools and budgets.
10. Grade independently after generation. Count failures and limits. Report
    successes/attempts, total input/output tokens for every phase, latency,
    overhead, and zero API expenditure separately from unpriced compute/setup.
    AEE outcomes are evidence-gap decisions, not independent success grades.
11. Audit cited artifacts, run tests/CI, and write the article plus a plain-text
    copy/paste version. Lead with a concrete reason to try Spec Kit+AEE; use
    measured findings without implying superiority or savings if unsupported.
    Disclose ElectroHire's maintenance role, sample limits and model constraints.
    Link public versioned results and all relevant repositories. Push to the
    existing draft PR, leaving merge and LinkedIn publication to the user.

## Local assets on the old laptop (not pushed)

- Workspace: D:/Development/spec-kit-aee-benchmark; environment .venv312.
- D:/Development/benchmark-tools/llama-b11026.zip and llama-b11026/.
- D:/Development/benchmark-tools/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf.
  SHA-256: cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046.
  HF revision: f86cb2c1fa58255f8052cc32aeede1b7482d4361.
- D:/Development/benchmark-upstreams/exercism-python at
  1f6aab8667bf653b10cc3799f94352fcdb749db6; upstream clones listed in START_HERE.
- Weights, binaries, environments and upstream clones are intentionally not Git
  artifacts. Recreate them on the destination; GPU runtime/model may differ.

## Source URLs for the eventual article

- https://github.com/github/spec-kit
- https://github.com/electrohire/spec-kit-aee
- https://github.com/electrohire/spec-kit-evaluator
- https://github.com/electrohire/applied-epistemic-engineering
- https://github.com/electrohire/spec-kit-aee-benchmark
- https://github.com/SWE-bench/SWE-bench
- https://github.com/SWE-bench/swe-bench-tasks
- https://github.com/SWE-agent/mini-swe-agent
- https://github.com/Aider-AI/aider/blob/main/benchmark/README.md
- https://github.com/exercism/python
- https://github.com/exercism/problem-specifications
- https://github.com/ggml-org/llama.cpp
- https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF

Only cite tools actually relevant to the final experiment, add the selected GPU
model's official source, and verify URLs/revisions before publication.
