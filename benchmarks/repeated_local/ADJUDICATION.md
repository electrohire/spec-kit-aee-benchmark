# Prospective finding-adjudication rules

Judge findings after all model generation and independent grading. Do not tune
solver prompts or reveal grades from adjudication. Retain the full original
finding and shared diagnostic with every judgment.

1. Concrete defect finding: identifies an implemented behavior or code condition
   that violates an active requirement, with enough specificity to reproduce or
   locate it. A claim-ID match alone is insufficient.
2. True concrete finding: that condition is present in the frozen starting source
   and independently confirmed by a failing requirement case or a recorded minimal
   reproduction. Link exact evidence and the seeded mutation when applicable.
3. False concrete alarm: asserts such a violation in the frozen source, but an
   independently checked reproduction and source inspection contradict it. Passing
   existing tests alone does not establish falsity; mark unresolved if insufficient.
4. Evidence/schema gap: requests evidence, narrower claims, provenance, or atomicity
   without establishing a code defect. Report separately, never score it as a true
   defect merely because its subject overlaps the seeded requirement.
5. Unresolved: insufficient specificity/evidence for a defensible judgment.

Precision = true concrete findings/(true concrete findings+false concrete alarms),
undefined if denominator zero. Report counts and unresolved judgments alongside it.
Seeded-defect recall is defects with at least one confirmed concrete finding divided
by seeded defects; report by project/seed, with correlated repeated defects disclosed.
Control findings and source changes are separate: requesting more evidence about
correct code is not automatically a false code-defect alarm, but its work cost counts.

Useful repair: hidden acceptance changes from failing to passing without loss of
previously passing cases. Report first-round and final transitions; final fixes
that also occur under ordinary repair are not an AEE-exclusive benefit. Temporal
association between a finding and repair is not proof of causation. Both treatments
already receive the same raw model diagnostic; this comparison isolates the added
assessment/routing presentation, not an independent new source of facts.

Controller-authored faults/tests and maintainer adjudication are not independent
external validation. Publish judgments, uncertainty, raw evidence and counterexamples
for review. Do not edit the email/article based on preliminary outcomes.
