# Staged TinyDB study — frozen before scored generation

User-requested addition to the completed small-task exploration. Hypothesis:
explicit requirements and evidence tracking may help preserve behavior through
later changes. No positive effect is assumed. This is one controller-authored
three-stage project, one trajectory per arm, not nine independent problems and
not a statistically powered general benchmark. It does not replace the unrun
180-attempt SWE-bench pilot. Selection was informed by the earlier exploration;
no TinyDB scored output was available when these tasks/tests were written.

## Work and treatment

TinyDB v4.9.0, commit 19066e03139e904c24410e23901e4b069d715a2e, MIT.
Three cumulative milestones: opt-in transactions; nested savepoints replacing
the initial nested-transaction rejection; detached backup and validated restore.
Each stage gets only its currently active requirements. Same persistent source
and agent history across stages; separate clean repository per arm. Baseline may
plan, keep notes, write tests, and use all repository tools. No deliberately weak
single-prompt baseline. All arms see upstream tests and current public acceptance.

Spec Kit uses the frozen full skills and pristine setup scripts/templates, through
the existing mini-SWE-agent shell/JSON adapter: constitution (stage 1 only), specify,
plan, tasks, implement, converge, final implementation. Skills requiring interactive
human clarification or subagents are adapted to autonomous single-agent execution.
Artifacts live in /workflow and code in /testbed. Actual compliance is audited
from tool logs and saved workflow files; phase labels alone do not prove fidelity.

Combined treatment adds actual installed AEE/Evaluator assessments after specify,
plan, tasks, implement using model-extracted requirement claims. Observed references
must match recorded shell artifacts. Planning gaps are advisory and passed forward;
one implementation evidence-rework opportunity follows a non-pass/non-warn outcome.
Unresolved outcomes and adapter errors are retained; they are not hidden-test grades.
This advisory routing is an explicit adaptation, not full strict-gate validation.

## Fixed inference and budgets

Free loopback-only llama.cpp b11026; Qwen3.6-35B-A3B, Unsloth UD-Q4_K_M,
publisher revision a483e9e6cbd595906af30beda3187c2663a1118c.
Weight SHA256 ac0e2c1189e055faa36eff361580e79c5bd6f8e76bffb4ce547f167d53e31a61.
Both verified GPUs, layer split 9:14, 32768 context, q8 KV, one slot, 8 CPU threads,
temperature 0, seed 20260917, thinking disabled, cache_prompt false, max output 6144.
This differs from the earlier 14B small-task campaign; do not compare their numbers
as a controlled model or workflow effect. Native usage counts every phase and failure.

Each arm: 3 x 900-second stages, at most 50 calls/stage, 150 calls/project,
2,000,000 total input+output tokens/project. Next-call output reservation enforced.
HTTP generation timeout at most 120 seconds; shell at most 60 seconds.
Last 16 history messages plus full current instructions; remove oldest pairs until
context fits. Compactions are logged. No semantic summary model or paid fallback.
Unknown usage stops further inference for that arm. All arms run sequentially in
seed-shuffled order, within the same budgets. Timing includes host phase work and
public grading; final grading/snapshot infrastructure may extend stage wall time.

## Repair and grading

Freeze primary source before feedback. Up to two common repair rounds per failed
public milestone, sharing that stage's remaining time/call/token budget. Each round
may use multiple tool/model calls. Primary remains separately scored; repaired
source carries into the next stage. Count stage limits, failed repairs, and unfinished
workflow phases. Functional snapshot score and workflow completion are distinct.

Fresh isolated Docker grader: unchanged 223 upstream tests plus acceptance tests.
Public expected totals 227/228/231; hidden totals 229/231/247. Zero failures, errors,
skips and exact expected count required for a full milestone pass. Only tinydb/*.py
source modules transfer, never solver tests or config. No host mounts/network,
nonroot, dropped capabilities, resource limits. Hidden cases run only after all
generation and never supply feedback. They are controller-authored and withheld,
not independently authored; upstream regression tests are independently authored.
Reference calibration must pass all six combinations, untouched TinyDB must fail,
and an unrelated real model/tool smoke must pass before campaign start.

## Prespecified reporting

For each arm/stage/phase report native input/output/total/cached tokens, model calls,
tool calls, HTTP and stage wall time, errors, history compactions, assessment outcomes,
public and hidden primary/final test counts. Report full milestones passed out of 3,
final-project pass, and individual feature-case coverage separately. Total tokens per
fully accepted hidden milestone = all arm tokens / hidden-final full passes; undefined
if zero. Also report primary tokens per primary accepted milestone, repair tokens,
rounds attempted, failed-to-passed transitions and remaining failures. Repeated
regression checks and parameterized validation cases are not independent answers.
Compare cases shared between successive stages for regressions; R07 is intentionally
retired. No selective task/model reruns. Preserve all traces, source snapshots, workflow
artifacts, hashes, infrastructure failures, and unresolved limitations.

API expenditure is zero; electricity, hardware, setup and human/controller labor are
unpriced, not free. ElectroHire maintains AEE/Evaluator and this study: disclose this.
