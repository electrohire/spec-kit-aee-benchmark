# Staged TinyDB study, revision 3 — frozen before its scored generation

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
Workflow artifacts and code both live in /testbed, matching the native skill root.
Only implementation source transfers to grading. Actual compliance is audited
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
Both verified GPUs, layer split 9:14, 131072 context, q8 KV, one slot, 8 CPU threads,
temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence_penalty 0,
repeat_penalty 1.0, seed 20260917, thinking enabled with a server reasoning budget of 2048, prompt caching after the first call of each arm, max output 6144.
This differs from the earlier 14B small-task campaign; do not compare their numbers
as a controlled model or workflow effect. Native usage counts every phase and failure.

Each arm: 3 x 2400-second stages, at most 100 calls/stage, 300 calls/project,
30,000,000 total logical input+output tokens/project. Next-call output reservation enforced.
HTTP generation timeout at most 120 seconds; shell at most 60 seconds.
Full conversation history and this local model's native reasoning fields are retained.
Current active requirements and phase instructions remain in a fixed prefix. Oldest
history pairs are removed only if the rendered prompt plus output reservation exceeds
131072 tokens; removals are logged. There is no rolling 16-message window or action
ledger. The first request of each arm disables prompt caching to avoid cross-arm reuse;
subsequent requests enable it. Native cached tokens are part of logical input tokens,
not an additional token charge; report cached/uncached input separately. No semantic summary model or paid fallback.
Unknown usage stops further inference for that arm. All arms run sequentially in
seed-shuffled order, within the same budgets. Timing includes host phase work and
public grading; final grading/snapshot infrastructure may extend stage wall time.

## Repair and grading

Freeze primary source before feedback. Up to two common repair rounds per failed
public milestone, using reserved stage resources: primary work has 1800 seconds/80 calls;
repairs have at most 10 calls each within the whole-stage 2400-second deadline
and remaining whole-project token budget. Each round
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

## Revision disclosure

Run 01 was stopped after the Spec Kit arm repeatedly inspected files under a
recent-history-only policy: 50 calls at stage 1 (public failure) and one stage-2
call. No hidden results or other-arm results were observed. All 51 calls and
888,819 tokens are preserved separately and count as development/aborted-study
overhead. This revision adds the action ledger, puts phase instructions last,
and clarifies phase deliverables. Task descriptions, tests, weight and budgets
are unchanged. The first revised workflow smoke still looped and failed after
25 calls, showing that context loss alone is not an established cause. Adopt the
model publisher's non-thinking sampling settings (listed above) instead of greedy
decoding, and validate another unrelated workflow smoke before scoring. Source:
https://huggingface.co/Qwen/Qwen3.6-35B-A3B#best-practices. All failed smoke costs
remain separate and included in overall study overhead; no hidden results guided
these changes.

A second revised smoke using the publisher settings also failed after 25 calls
while looking for workflow files under /testbed. The next smoke places pristine
Spec Kit files in the same repository as code and maps the adapter root to
/testbed. This avoids a non-native split-root requirement. It changes no task or
hidden test and applies identically to both Spec Kit treatments. The failed smokes
remain preserved. Causal attribution among prompt, sampling, root placement and
model behavior is not established by these sequential integration checks.

The same-root smoke completed tool-based arithmetic implementation but left the
constitution scaffold unchanged despite a done action. Add a mechanical completion
check for constitution/spec/plan/tasks: required file exists, length >100, and no
PROJECT_NAME scaffold. At most two correction opportunities within the same budget;
checks are logged shell calls. This is artifact presence, not semantic certification.
Final revised smoke must pass both actual document creation and unrelated code tests.

The artifact-gated non-thinking smoke also exhausted its 25-call cap. Final
integration revision resolves the literal skill $ARGUMENTS placeholder with the
actual phase deliverable and task, and uses the publisher's precise-coding thinking
sampling settings with a 2048 reasoning-token budget. Native completion usage
includes reasoning and it is not added twice. All six smoke directories, including
failures, are exported. Full request hashes remain; native reasoning fields are
retained in local traces but not published as an explanatory rationale.

A further 25-call thinking smoke still failed. The final handoff keeps phase
instructions in the system message rather than repeating the entire skill as
a new last user request, so the most recent user observation remains the tool
result. Both Spec Kit arms receive the same explicit constitution principles:
backward compatibility, testable requirements, evidence provenance, scoped simplicity
and honest uncertainty. These are stakeholder-style inputs, not a supplied solution.
This change is smoke-validated before the new three-arm freeze.

The system-instruction smoke created the constitution but failed the coding
transition. The adapter had filtered CONTROL_PHASE messages out of history; the
revised provider retains a concise phase-transition user turn. Actual tool results
remain the latest observations thereafter. This is a harness correction, not a
model/workflow result. The eighth development smoke validates both phases before
scored run 02. Seven earlier smokes, including the first passing code-only smoke,
remain in preflight accounting.

Budget revision before run 02: reserve resources for actual repair rather than
letting document work consume the entire stage. Primary gets 80 calls/1200 seconds,
each of two public repair rounds gets up to 10 calls, all within 1800 seconds/stage
and 6M tokens/300 calls/project. Same allocation for all arms. This is based on
workflow smoke overhead, not hidden results; run 01 retains its original caps.

## Run 03: full-context integration revision

Run 02 was stopped after 234 calls / 4,377,753 tokens: two Spec Kit public milestones
failed after primary and repair caps without implementation source changes, and the
third was interrupted. Baseline/combined did not run; no hidden results were observed.
This is retained as an incomplete integration pilot, not a comparative outcome.
The 16-message adapter dominated behavior with repeated reads. The existing host
configuration demonstrated room for 131072 context; this was reverified at startup
with 11208/13589 MiB occupied on the two GPUs. Use batch512/ubatch256, full history,
native reasoning retention and within-arm prompt caching. Weight/sampling settings
and task/grader definitions remain the same. These simultaneous changes are not an
isolated causal test of context or caching. A new full-workflow arithmetic smoke must
complete all seven phases, four actual AEE/Evaluator assessments and independent code
checks before scored run03. Primary allocation becomes 1800 seconds/80 calls, with
10 calls per repair and 2400 seconds total/stage; cap300 calls/30M logical tokens per
arm allows retained/cached history without pretending cached input is free logical
context. All setup and interrupted costs remain visible. This iterative design is
exploratory, not an untouched preregistration or evidence of general superiority.

The first full-context smoke completed constitution/specification but omitted
required AEE claims. Add at most two model format-repair opportunities when a
required claims object is missing, charged to the same phase/stage budget. The
next full-workflow smoke must validate actual assessment execution as well as
code. Run03 also freezes every workflow script/template and adapter hash before
generation, closing the supplemental-provenance limitation in the earlier pilot.

Final run03 resource allocation supersedes the historical caps above: primary
120 calls/2400 seconds; at most two 20-call public repair rounds; total160 calls
and3000 seconds per stage,480 calls/60M logical tokens per arm. This provides
headroom relative to the full-workflow smoke and reserves useful inspection/edit/
retest capacity. Caching does not remove logical tokens from the numerator.
The same allocation applies to baseline and both workflow arms.

Final preflight: smoke10 failed when model claims used kind=observed, an invalid
claim type. Smoke11 used explicit claim/evidence type guidance and the installed
Claim.from_dict validation, with at most two charged model format corrections.
It completed all seven phases, four actual AEE/Evaluator assessments and independent
arithmetic checks in 64 model calls. Run03 then froze the final configuration.
Failed AEE subprocess diagnostics now remain in the evidence store; a separate
pinned-CLI synthetic diagnostic fixture proves error retention and is not presented
as the lost original smoke10 stderr.
