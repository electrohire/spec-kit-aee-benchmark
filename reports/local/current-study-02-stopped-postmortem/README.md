# Study 02: audited stopped-study observations

This is a postmortem of the infrastructure-interrupted campaign, not a completed
paired experiment. No inference or campaign retry occurred. All stopped raw
artifacts remained byte-for-byte unchanged. The frozen348-input inventory and
seven existing event streams verified. The original infrastructure cause remains
unresolved; the prospective controller guard fix does not explain it.

## What was actually attempted

The [complete JSON inventory](checkpoint-rows.json) and [CSV](checkpoint-rows.csv)
cover all 12 scheduled trajectories and 36 dependent checkpoints. Only two
trajectories began. Three checkpoints incurred generation calls; 33 were
unattempted. There were no observed accepted final-stage project deliveries.
The infrastructure censoring prevents interpreting these as arm-level efficacy
or completion-rate estimates.

| Project / seed / arm / stage | Generation calls | Observation |
| --- | ---: | --- |
| Cachetools / 20261019 / Spec Kit+AEE / 1 | 22 | Repeated-action intervention during specification; implementation never reached |
| Cachetools / same / 2 and 3 | 0 | Dependent checkpoints withheld |
| TinyDB / 20261019 / Spec Kit / 1 | 114 | All seven workflow phases completed; public 225 tests passed; hidden grade failed |
| TinyDB / same / 2 | 56 | Infrastructure halt during tasks; no submitted final snapshot |
| Remaining scheduled checkpoints | 0 | Campaign stopped before execution |

The raw Cachetools stage 3 row has a bookkeeping `handoff=true` flag despite its
`not_attempted_dependent` status and zero calls. That flag is not an executed
handoff, accepted delivery or completed workflow. It remains visible in the export.

## Independent source grades

The two retained stage 1 primary/final snapshots have identical primary/final
hashes within each checkpoint. Four fresh public/hidden grader invocations used
the original pinned upstream revisions, network-disabled image and unchanged
grader functions/test bytes. [Freeze](freeze.json), [controller](controller.py),
[driver and grader sources](grader-sources/grader-driver.py), and both actual
snapshot archives are retained and hash-bound in [summary.json](summary.json).
The pinned TinyDB and Cachetools source retains its original attribution and
[TinyDB MIT notice](licenses/tinydb-LICENSE) / [Cachetools MIT notice](licenses/cachetools-LICENSE).
No agent test, model assertion or new source change supplies an independent grade.

| Snapshot | Public/upstream | Hidden | Interpretation |
| --- | --- | --- | --- |
| Cachetools stage 1 | Collection error: 1 case vs218 expected | Collection error: 1 case vs221 expected | Incomplete inventory; proxy-ungraded |
| TinyDB stage 1 | 225/225 passed | 227/228 passed | One independently observed hidden failure; no accepted checkpoint |

TinyDB's `test_R02_retained_cache` expected an empty result but received
`[{'x': 1}]`. This shows that the public suite did not establish the retained-cache
requirement. It does not establish a hallucination, false completion or an AEE
detection. The explicit completion declaration was unknown. The model's public
test success and completed phase workflow therefore cannot stand in for accepted
delivery. See the full [hidden grade](grade-tinydb-20261019-spec_kit-stage1-hidden.json).

The interim TinyDB stage 2 source was not promoted to a submitted final checkpoint.
Unattempted Cachetools carry-forward snapshots were not scored as new attempts.
The missing checkpoints remain ungraded, with their zero new-call accounting intact.

## Completion and treatment exposure

The disjoint completion-proxy categories across 36 scheduled checkpoints are:
**positive 0; negative 0; unknown with complete inventory 1; ungraded 35**. The 35
include 33 unattempted checkpoints, one infrastructure-interrupted partial
checkpoint and the Cachetools collection failure. False-completion rate is
undefined because there is no eligible positive declaration. No detector
precision/recall can be estimated without independent joined detection labels.

There were **zero actual scored AEE assessments**. The combined arm stopped in
specification before its first assessment. The four semantic dependency replays
and primary ledger anchors used for admission are setup evidence, not scored
treatment exposure or agent-side execution-ledger events. No matched completed
arm pairs exist. Neither an AEE benefit nor an AEE harm follows from this campaign.

The first postmortem exporter counted any available grade invocation as
proxy-eligible. Applying the existing complete-inventory requirement leaves
Cachetools ungraded. The [initial exporter bytes](initial-export-run.json) and
[correction note](REVIEW.md) are retained. No raw snapshot, test, grade, threshold
or stopped campaign was altered. The offline auditor rejects rebound snapshots,
incomplete-inventory promotion, missing rows and invented performance/exposure.

During pre-publication checks, a targeted regression showed that the new auditor
could ignore a missing hidden-grade binding. Both public and hidden bindings are
now mandatory. The [initial failing case](validation/missing-mode-red.json) is
retained as byte-exact base64 with its hash; this was an auditor implementation
gap, not another model defect. The [interim full suite](validation/full-interim.xml)
passed 510 cases before that final hardening; final focused checks cover 10 cases.
The exact-head Ubuntu CI also runs the full suite and the committed audit command.

## Calls, costs and rework limits

Study 02 retained 192 generation calls: 4,089,695 prompt+82,529 completion=
**4,172,224 known native tokens**, with 0 stored generation-usage unknowns.
Reported cached prompt tokens are 2,147,082, a subset of prompt tokens rather than
additional tokens or a monetary discount. The failed context preflight's nine
HTTP helper requests made zero additional generation calls.

The [bounded retained-cost inventory](bounded-cost-inventory.json) covers 2074
deduplicated receipts, including four with unknown usage. Its cohorts remain
separate:

| Cohort / model | Calls | Known native-token lower bound | Unknown-usage calls |
| --- | ---: | ---: | ---: |
| Setup / gpt-oss-20b | 56 | 542,676 | 1 |
| Setup / qwen3.8-27b | 695 | 14,334,614 | 2 |
| Invalid historical study 01 / qwen3.8-27b | 1131 | 24,087,135 | 1 |
| Stopped study 02 / qwen3.8-27b | 192 | 4,172,224 | 0 |

Older study families outside those explicitly inventoried roots remain excluded;
this is not final all-history economics. Unknown usage stays unknown. Models and
cohorts are not pooled into an efficiency estimate. Local API spend was$0,
excluding hardware, energy and labor. No hypothetical price is presented as a bill.

No repair round was recorded for the two submitted stage 1 snapshots. The partial
later work cannot establish repair efficacy or absence of regressions. Timing is
descriptive: convenience tasks, public stage 1 readiness exposure, controller/host
adaptation, prospective admission amendment and concurrent authorized CPU-only
product validation limit inference. Twelve trajectories are not twelve unrelated
projects, and 36 dependent checkpoints are not 36 independent samples.

## Remaining requirements

The benchmark remains stopped. Recover historical server/router stderr around
2026-10-18T22:21UTC or equivalent concrete diagnostic evidence; establish applicable
prospective admission and a fresh immutable campaign before new scored generation.
Preserve inclusive model-failure outcomes and all prior failed costs. No implicit
retry, cap/guard/grader relaxation, hidden-outcome feature tuning or source change
to the stopped campaign is authorized by this report. A valid before/after study
and coordinated product release validation remain unfinished.

Run `python scripts/audit_stopped_postmortem.py`, `python scripts/check_evidence.py`
and `python scripts/readme_results.py --check` to inspect the committed report.
