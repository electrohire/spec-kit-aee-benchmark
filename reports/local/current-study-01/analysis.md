# Interpretation and audit of the completed attempt

All 12 scheduled trajectories and 36 cumulative checkpoints were attempted.
Generation, independent grading attempts and export ended on 2026-10-17. The
snapshot-bound audit is in `post-run-audit.json`; original observations, model
configuration, budgets and acceptance tests were not changed after scoring.

The ordinary agent produced 9 accepted hidden checkpoints out of 12 and delivered
2 of 4 final-stage projects. Each structured arm produced zero accepted
checkpoints and delivered no final-stage project. **The structured arms did not
complete the prescribed workflows. This is not evidence that a fully executed
AEE workflow is ineffective, nor evidence of a benefit.**

## What was and was not graded

The 144 primary/final × public/hidden grade records bind to the exact source
snapshots and frozen grader hashes. Forty-eight have the complete expected case
inventory: all four grades for each of the 12 baseline checkpoints. The other 96
records describe collection failures. Public final records can reuse an earlier
grading result for identical source bytes; these are not 144 distinct processes. For the 24 structured final hidden snapshots,
22 lack the required implementation module and two contain a module that raises
`NameError` during import. The source archives and original pytest diagnostics
independently establish those conditions. These checkpoints remain **ungraded**
in the strict case-inventory analysis, not silently converted to complete failing
test suites. Zero accepted checkpoints still means zero observed deliveries.

## Workflow exposure and budgets

Neither structured arm completed a milestone workflow. Only 6 of 48 intended AEE
assessments occurred, all after specification; none reached plan, tasks or
implementation assessment. All six actual assessments composed exactly one AEE
result; four anchored project ledgers verify with entry counts 2, 1, 2 and 1.
Their findings concern evidence/claim quality and missing human acceptance; they
are not independently adjudicated hallucinations or behavioral defects.

The shared 40-minute milestone ceiling included planning and implementation.
The successful arithmetic calibration established that the integration could
execute all phases; it did not establish that these project workflows would fit
that ceiling. Longer planning, repeated actions and output truncation consumed
budgets before implementation. This is a major treatment-exposure limitation.
The caps and prompts were not adjusted after scored outcomes became available.

There are 52 public-feedback repair records (4 baseline, 24 Spec Kit, 24 combined).
Every record made zero inference calls after the stage budget was exhausted.
Zero source-changing repairs therefore does not establish repair ineffectiveness.
Any future treatment change needs a separately preregistered campaign; this
attempt must remain visible in its own denominator.

## Hallucination proxy

Baseline: 9 explicit positive final completion declarations, one contradicted by
complete independent hidden grading (1/9, 11.1%), and 3 unknown declarations.
Both structured arms: 12 unknown declarations, no positive declarations, and an
undefined false-completion rate (0/0). **Undefined is not zero hallucinations.**
There were no independently verified recoveries of false completion. Generic
repair was never exercised with inference. Matching AEE detector decisions for
these final claims were not measured, so precision/recall remains unmeasured.

## Tokens, costs and adoption claim

All 1,131 scored generation calls are allocated exactly once. Known input plus
output tokens: baseline 7,748,458; Spec Kit at least 8,511,570; combined 7,827,107.
The Spec Kit HTTP500 call has unknown native usage and remains in the accounting;
its total and exact per-delivery/scenario costs are not imputed. Native cached
input and reasoning categories are subsets, not extra tokens.

The separate setup inventory retains 174 physical calls, including failed
candidate calibrations, with 3 unknown native usages. Setup models have different
tokenizers and are not pooled into an efficacy estimate. Actual API spend was $0;
electricity, equipment and human work were not priced. Illustrative hosted token
rates are sensitivity scenarios, not measured savings or provider quotations.

The study supplies no proof that Spec Kit+AEE saves money, reduces rework, or
reduces hallucinations. Its practical lesson is to measure actual execution and
assessment coverage before interpreting scores or adoption claims. The requested
execution controls—scoped preflight, fresh trusted evidence, enforceable test
links, and status-aware handoff—are future design proposals, not mechanisms this
study proves would fix the observed limitations.

The workload consists of two convenience-selected libraries and two seeds with
dependent milestones and a simulated handoff, not months of production history.
The local runner adapts installed Spec Kit skills and executes AEE explicitly;
it is not an unmodified native hook-installation or DefaultAgent benchmark.
Public exports omit raw requests/native reasoning while retaining hashes, so
exact public prompt replay is unavailable. The original SWE-bench pilot is unrun.
