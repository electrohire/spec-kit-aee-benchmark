# Matched detector attempt 01 stopped at its first output-limit failure

This attempt is **incomplete**, not a paired efficacy or savings result.
It ended 2026-10-19 at 19:28:55UTC after 72 of 720 scheduled final judgments.
One further judgment was attempted but ungraded; 647 were unattempted.
All 720 rows and 185 native calls are retained. No later case, retry or resumed
generation ran after the failure.

| Retained observation | Value |
| --- | ---: |
| Independently joined final judgments | 72 |
| Attempted/ungraded judgments | 1 |
| Unattempted judgments | 647 |
| Physical generation calls, including setup and failed output | 185 |
| Native prompt tokens | 665,575 |
| Native completion tokens | 47,344 |
| Known native total | 712,919 |
| Stored generation usage unknowns | 0 |
| Actual setup plus scored AEE assessments with verified local ledgers | 54 |

The last call was the Spec Kit+AEE review of RAGTruth case index 48. Its response
model correctly identified `qwen3.8-27b`; `finish_reason` was `length` and native
completion usage exactly 1,024 tokens. It generated extended reasoning inside a
rationale string before completing the required verdict. The failure is a model
output-limit outcome, not evidence of a model identity change or transport outage.
The harness immediately halted rather than accepting truncated JSON or guessing
the final label. The failed draft/review pair is retained and remains ungraded.

The v1 harness requested brief rationales but its JSON schema bounded list sizes
only, leaving individual strings unbounded. Four new negative regression cases
exposed that contract gap. Prospective v2 applies finite native string bounds
equally across all arms: policy document 3,000 characters, rationale 320, each
source quote 120 and uncertainty 80. Both draft and review repeat the concise
contract. Case output 1,024, policy output 1,536, context 32,768, model, sampling,
seed, author labels, task selection, independent grading and call budgets remain
unchanged. No stored response is rewritten or reclassified into a completed
delivery. Any new attempt needs its own source freeze and paths.

These are public, previously exposed cases. Partial outputs were observed during
failure diagnosis; the amendment changes delivery bounds, not semantic decision
criteria, labels, thresholds or task selection. Do not pool attempt 01 with a new
attempt as if they were independent untouched replications. Preserve its costs
as a distinct failed cohort in all-call accounting. Native tokens are not a bill;
local API spend 0 excludes hardware, energy and labor.

The prefix is small, unbalanced and outcome-conditioned by its stopping event.
It cannot establish whether Spec Kit or AEE materially improves detection, coding
quality, accepted delivery, natural hallucination prevalence or long-term token
economics. Generic errors and AEE findings are not author hallucination labels.
The [completed model-only external results](../external-01-20261019/README.md)
remain separate and unchanged. Synthetic factbooks are another separate diagnostic.

[Every scheduled row](scheduled-rows.json), [all sanitized native receipts](call-receipts.json),
[summary](summary.json), [local AEE ledger commitments](aee-ledger-commitments.json),
[frozen v1 registration](frozen-registration-v1.json), and
[byte-hash manifest](files-sha256.json) are retained. Original full model/context
artifacts and 335 frozen source inputs remain local under
`artifacts/matched-hallucinations-01`. Source text and model rationale are omitted
from public receipts; original dataset IDs and hashes support auditing. Local
hash chains establish retained integrity, not external identity, human acceptance
or semantic truth. All proposed judgments remain unaccepted drafts.
