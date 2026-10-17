# Repeated two-project local comparison

**Audit qualification:** [Read the interpretation and exposure limits](analysis.md). All 36 checkpoints were attempted, but the 24 structured checkpoints are ungraded collection errors (22 missing modules, two import-time NameErrors). Only six specification AEE assessments occurred; all 52 public-repair records made zero inference calls. Zero accepted deliveries is not a complete AEE workflow efficacy test.

12 project trajectories; 36 dependent checkpoints, not independent tasks. All inference is local. API expenditure $0; hardware, energy and controller work unpriced.

| Arm | Primary /12 | Final /12 | Entire trajectories /4 | Known tokens | Unknown calls | Tokens/accepted | Repair rounds | Completed milestone workflows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 9 | 9 | 2 | 7,748,458 | 0 | 860939.7777777778 | 4 | 9 |
| spec_kit | 0 | 0 | 0 | 8,511,570 | 1 | undefined | 24 | 0 |
| spec_kit_aee | 0 | 0 | 0 | 7,827,107 | 0 | undefined | 24 | 0 |

## Paired project/seed outcomes

| Project | Seed | Arm | Stage | Public final | Hidden primary → final | Completed phases | Repair rounds |
|---|---|---|---:|---|---|---:|---:|
| cachetools | 20261016 | baseline | 1 | True | True → True | 1/1 | 0 |
| cachetools | 20261016 | baseline | 2 | True | True → True | 1/1 | 0 |
| cachetools | 20261016 | baseline | 3 | True | True → True | 0/1 | 0 |
| cachetools | 20261016 | spec_kit | 1 | False | False → False | 3/7 | 2 |
| cachetools | 20261016 | spec_kit | 2 | False | False → False | 2/6 | 2 |
| cachetools | 20261016 | spec_kit | 3 | False | False → False | 0/6 | 2 |
| cachetools | 20261016 | spec_kit_aee | 1 | False | False → False | 2/7 | 2 |
| cachetools | 20261016 | spec_kit_aee | 2 | False | False → False | 1/6 | 2 |
| cachetools | 20261016 | spec_kit_aee | 3 | False | False → False | 0/6 | 2 |
| cachetools | 20261017 | baseline | 1 | True | True → True | 1/1 | 0 |
| cachetools | 20261017 | baseline | 2 | True | True → True | 1/1 | 0 |
| cachetools | 20261017 | baseline | 3 | True | True → True | 1/1 | 0 |
| cachetools | 20261017 | spec_kit | 1 | False | False → False | 3/7 | 2 |
| cachetools | 20261017 | spec_kit | 2 | False | False → False | 0/6 | 2 |
| cachetools | 20261017 | spec_kit | 3 | False | False → False | 0/6 | 2 |
| cachetools | 20261017 | spec_kit_aee | 1 | False | False → False | 2/7 | 2 |
| cachetools | 20261017 | spec_kit_aee | 2 | False | False → False | 0/6 | 2 |
| cachetools | 20261017 | spec_kit_aee | 3 | False | False → False | 0/6 | 2 |
| tinydb | 20261016 | baseline | 1 | True | True → True | 1/1 | 0 |
| tinydb | 20261016 | baseline | 2 | True | True → True | 1/1 | 0 |
| tinydb | 20261016 | baseline | 3 | False | False → False | 0/1 | 2 |
| tinydb | 20261016 | spec_kit | 1 | False | False → False | 3/7 | 2 |
| tinydb | 20261016 | spec_kit | 2 | False | False → False | 1/6 | 2 |
| tinydb | 20261016 | spec_kit | 3 | False | False → False | 1/6 | 2 |
| tinydb | 20261016 | spec_kit_aee | 1 | False | False → False | 2/7 | 2 |
| tinydb | 20261016 | spec_kit_aee | 2 | False | False → False | 0/6 | 2 |
| tinydb | 20261016 | spec_kit_aee | 3 | False | False → False | 1/6 | 2 |
| tinydb | 20261017 | baseline | 1 | True | True → True | 1/1 | 0 |
| tinydb | 20261017 | baseline | 2 | True | False → False | 1/1 | 0 |
| tinydb | 20261017 | baseline | 3 | False | False → False | 0/1 | 2 |
| tinydb | 20261017 | spec_kit | 1 | False | False → False | 2/7 | 2 |
| tinydb | 20261017 | spec_kit | 2 | False | False → False | 0/6 | 2 |
| tinydb | 20261017 | spec_kit | 3 | False | False → False | 1/6 | 2 |
| tinydb | 20261017 | spec_kit_aee | 1 | False | False → False | 2/7 | 2 |
| tinydb | 20261017 | spec_kit_aee | 2 | False | False → False | 0/6 | 2 |
| tinydb | 20261017 | spec_kit_aee | 3 | False | False → False | 0/6 | 2 |

Read the frozen protocol and summary.json for cached/uncached/generated tokens, native timing, stage wall time, regressions and workflow completion. Feature counts are separate from unchanged upstream tests; dependent checkpoints are not pooled as independent tasks. Repeated upstream case names use discovery-order occurrence identifiers because this pytest configuration omits class names. Public repair feedback is not hidden grading. Hidden cases were controller-authored; projects were convenience selected. Two seeds are not statistical proof. Raw requests/native reasoning stay local with hashes; exact public prompt replay is unavailable. Earlier failures and calibration work are reported separately, never erased.

The earlier interrupted pilot used a linear context selector with repeated tokenization overhead. This fresh campaign uses a native-calibrated binary search for the same first-fitting cutoff. Helper requests are reported separately; they are not extra model-generation tokens. Stage wall time includes preflight, tools, grading and container work. Controller audits also ran on the host during generation. Do not attribute all wall-time differences to Spec Kit or the AEE engine alone.

## Explicit completion claims and hallucination proxy

| Arm | Positive / negative / unknown declarations | False completion / graded positive declarations | Rate |
|---|---:|---:|---:|
| baseline | 9 / 0 / 3 | 1/9 | 11.1% |
| spec_kit | 0 / 0 / 12 | 0/0 | undefined |
| spec_kit_aee | 0 / 0 / 12 | 0/0 | undefined |

This is a preregistered false-completion proxy, not a comprehensive hallucination rate. Unknown/missing declarations are not confident assertions. AEE findings are not independent truth labels; matching detector decisions were not collected for these final claims, so detector precision/recall remains unmeasured. See lifecycle-report.json for bound grading, unknowns and denominators.

Primary-to-final recovery counts distinguish independently repaired code from explicit withdrawal of a positive declaration while code still fails. Missing declarations are unknown, not evidence of self-correction. Public-feedback repairs are shared across arms; these counts do not isolate an AEE mechanism.

## Recorded AEE management activity

| Arm | Assessment invocations / errors | Verdict counts | Findings by severity | Evidence rework rounds |
|---|---:|---|---|---:|
| baseline | 0 / 0 | {} | {} | 0 |
| spec_kit | 0 / 0 | {} | {} | 0 |
| spec_kit_aee | 6 / 0 | {'iterate': 2, 'gather_evidence': 4} | {'high': 22, 'medium': 60, 'low': 34} | 0 |

These are recorded management actions, not verified hallucination detections. Claim structure, evidence quality and human-acceptance findings must remain separate from independently graded behavioral defects.

Final-stage project delivery is separate from uninterrupted success at every checkpoint. Per-delivered-project costs include all scored calls on both delivered and failed trajectories. Illustrative USD/million token sensitivity calculation, not a provider quote, bill, GPU/energy/human cost or a claim that hosted inference has the same behavior. Rates are recorded in lifecycle-evidence.json; no actual financial-saving conclusion follows from illustrative rates or unpriced labor/energy. Failing cases are not automatically unique bugs.

## Delivery and token economics

| Arm | Final-stage projects delivered | All scored tokens per delivered project | Illustrative USD per delivered project | Blocked milestones |
|---|---:|---:|---:|---:|
| baseline | 2/4 | 3874229.0 | 1.70368835 | 0 |
| spec_kit | 0/4 | undefined/unknown | undefined/unknown | 0 |
| spec_kit_aee | 0/4 | undefined/unknown | undefined/unknown | 0 |

Zero delivered projects makes cost per delivery undefined, rather than zero. Compare quality and complete accounting before interpreting token differences; cumulative stages and repeated seeds are not independent production projects. No electricity, hardware depreciation or human rework cost was priced.

## Retained setup work

174 unscored physical generation calls are retained in setup-inventory.json, grouped by actual model, with unknown usage explicit. They are not silently assigned to scored treatment denominators or discarded. API spend $0; hardware, energy and human work unpriced.
