# Matched source-grounding treatments, prospective v1

This new experiment compares baseline, Spec Kit, and Spec Kit plus AEE on the
same fixed HaluEval/RAGTruth cases as external-01. It is a **workflow adaptation
to response classification**, not the original coding workflow, an official
dataset leaderboard submission, or an efficacy result already obtained.

The machine-readable preregistration is [matched-v1.json](matched-v1.json).
Upstream sources, author labels and public selection remain unchanged. Original
model-only predictions and earlier synthetic diagnostics remain immutable. Prior
case exposure and development on public data are disclosed; this is not a fresh
unseen-test replication. Never select a treatment or alter prompts from partial
matched outputs.

## Treatment execution

All arms receive the same bounded task, source payloads, label definitions, local
model, sampling, seed, context cap, native JSON contract and two-call draft/review
budget per case. Gold, benchmark IDs, annotations and sibling outputs are never
projected into classification prompts. The baseline writes an ordinary reusable
policy brief; no sham framework calls are added to match higher setup overhead.

Spec Kit arms execute the installed Python create-feature, setup-plan and
prerequisite helpers in real isolated projects. The model receives the shipped
constitution/specify/plan/tasks commands and templates, generates four draft
policy documents per dataset/arm, and implements their checklist on each case.
The host supplies tools and persists files rather than asking the model to emit
shell syntax. Artifact statuses stay draft and human acceptance unrecorded.

The AEE arm additionally executes the released AEE extension/engine and actual
single-result strict Evaluator composition after specify/plan/tasks, and before
and after each case's review. Context captures are evidence that input bytes
were supplied, not proof of the proposed verdict. Actual findings and next
actions enter later prompts; valid iterate/gather_evidence outcomes remain
nonpassing. No agent-generated identity, approval or oracle is synthesized.

The released AEE engine's structural/evidence assessment is not itself an
independent semantic hallucination detector. This tests the behavior of its
actual feedback within this declared adapter. A null effect or higher cost is
an acceptable finding. Additional adapters would require new registrations.

## Counts and failure policy

There are 720 final judgments: 240 cases times three arms, each with one draft
and one review (1,440 scored generation calls). Closed-world technical smoke
uses two synthetic cases per arm; their correctness is recorded, not an
all-correctness admission selection. Nine smoke policy calls plus twelve smoke
case calls plus eighteen dataset policy calls give 39 expected setup calls.
Total expected generation calls: 1,479; absolute reservation: 1,488 calls times
32,768 tokens. Case output is capped at 1,024, policy output at 1,536; timeout
600 seconds. These are this separate experiment's registered caps, not changed
caps for an old coding campaign.

First protocol, infrastructure, identity, source, context, response-limit or
hard-block failure halts immediately. No retries, automatic run resumption,
source mutation, case replacement or guard weakening. Failed calls retain their
native usage or explicit unknown reason. Incorrect classifications are measured
outcomes, not transport faults. A stopped study has attempted/ungraded and
unattempted rows; it is not a complete treatment comparison.

Before any generation: committed clean exact-green source, stopped prior
supervisors, idle approved worker, immutable copied inputs, source archive,
worker binding and model-weight identity. Only the existing authorized free
local worker may be used. Tests and real helper/evaluator integration use no
model calls. The technical model smoke runs once and is retained in setup cost.

## Grading, uncertainty and economics

Grade proposed final verdicts using the unchanged original author labels only
after generation. Report each dataset/arm separately: full-denominator accuracy,
precision, recall, false acceptances, false alarms, abstentions, invalid and
ungraded counts. Report AEE composition outcomes and a distinct gate-eligible
view that abstains unless the final actual composition passes or warns. Gate
abstention is not a correct factual judgment.

Join both physical receipts to each case, verify schema/model/seed/caps and exact
input/draft/policy bytes, generated files, helper exits, AEE artifact hashes,
retained ledger snapshots and current local anchors. These checks establish
retained integrity, not external identity or complete execution-environment
immutability. Raw calls and independent grade rows remain available for audit.

Pair differences by source cluster; bootstrap the matched cluster differences.
One policy per dataset/arm and one seed mean intervals are conditional on those
policies, not independent policy replications. Preserve HaluEval question pairs
and RAGTruth source strata and the original implicit_true label convention.

Report native prompt/completion/cache fields, setup/scored/failed counts and
unknowns by arm. Cached tokens are subsets, never extra charges. Include policy
and AEE-review overhead rather than reporting only final verdict tokens. CPU
assessment time is distinct from model tokens. Local API spend zero excludes
hardware, energy and labor. No claimed monetary saving or coding hallucination
prevalence follows from these detector results.

Long-horizon economic adoption is separately planned in
[the prospective measurement design](../../docs/long-horizon-economics-plan.md).
Detector data and independent coding/regression outcomes remain separate panels;
no blended score or generic-test-failure-as-hallucination conversion.
