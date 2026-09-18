# Limitations and open gates
## GPU continuation update

The [six-task local exploration and repair results](../reports/local/gpu-20260917/README.md)
are now actual measured evidence. They use a document-only adaptation, not the
full repository-tool Spec Kit workflow. Seven primary document truncations and
three failing generated solutions remain counted. Supplemental repairs use the
same exposed tests and are not held-out evaluation. All arms end at 5/6, with
much higher cumulative token use in the adapted workflows. These results cannot
establish how the full workflow performs on longer-horizon engineering work.
That longer-horizon campaign was requested afterward and is now complete under
a separate freeze after two interrupted integration pilots. None of its nine hidden
milestones passed all acceptance cases. All arms timed out, with one unknown native
usage each; six attempted common repairs were blocked before inference. See
[the complete results](../reports/local/long-horizon-03/README.md).

## Staged-project scope

The TinyDB supplement is one real repository and three dependent milestones, with
one trajectory per arm. It is not nine independent tasks, a statistically powered
study, or days of production maintenance. The task and acceptance tests are
controller-authored; upstream regression tests have independent authorship.
Hidden cases are withheld from solvers until all generation ends. Once published,
those cases are no longer secret for future replications.

Both Spec Kit treatments use frozen full skills/scripts/templates through an
autonomous mini-SWE-agent adapter. Human clarification and delegated work are
adapted to a single agent. Phase labels and document-presence checks do not prove
semantic compliance; actual tool records and workflow artifacts require review.
The combined treatment uses actual installed AEE/Evaluator assessments on
model-extracted claims. The adapter forwards complete composed assessment JSON,
including nested metadata, rather than a compact findings-only summary. Its token
cost is therefore specific to this implementation, not a minimum cost inherent
to AEE. Planning outcomes are advisory, with one bounded
implementation evidence-rework opportunity. Later convergence, final implementation
and common repairs are not reassessed; AEE outcomes do not certify final source.

The first two staged pilots were interrupted before other arms or hidden grading.
Their 285 calls and 5,266,572 tokens remain development overhead. Eleven separate
smokes led to a passing full-workflow preflight. Directory layout, phase handoff,
claim-format validation, context, sampling and caching changed during integration;
these changes are not isolated causal experiments. Final scored settings were
frozen before run 03 generation and remain unchanged across its arms.

The 120-second request timeout can interrupt a valid but slow response. Missing
native usage then stops further inference for that arm, even though API spending
is zero. End-to-end results include this harness policy. The passing arithmetic
smoke exercises the workflow but is not a worst-case long-context latency test.

Logical input includes cached tokens. Native completion includes reasoning; neither
is counted twice. Tokens per fully accepted milestone are undefined if no milestone
passes. A snapshot may pass tests despite an incomplete workflow, and the report
keeps those two facts separate. Explicit repair rounds and evidence rework are
counted; internal debugging is retained in tokens/tool traces but is not automatically
converted into a semantic number of fixes. API expenditure is zero; electricity,
hardware, model downloads, setup and controller labor are unpriced.

The following is the historical pre-GPU status of the unrun SWE-bench pilot.

No scored generation or real model smoke has run. All model-response tests are
synthetic fixtures. Actual deterministic AEE/Evaluator execution is separate
evidence; it does not establish end-to-end provider/Docker integration.

Docker engine was unavailable during initial preflight even after a launch attempt.
No OPENAI_API_KEY was detected in the controller environment. No dollar budget,
model snapshot or price snapshot was supplied. Image digests/audit and independent
gold smoke are therefore unverified. Live runner fails closed on these gates.

The three-arm comparison estimates the combined Evaluator+AEE effect. It cannot
isolate AEE. Twenty task clusters with three repetitions are a pilot; public
benchmark contamination and repository imbalance restrict generalization.
No model-generated evidence is independent proof. AEE scores are not probabilities.

Phase adapter uses frozen core Spec Kit skills through mini-SWE-agent, not the
Codex UI's slash-command runtime. Host runs extensions and forwards routing while
holding model constant. Real smoke must verify workflow artifacts, skill fidelity,
image cleanliness, provider usage semantics and cancellation before scored runs.
Conservative full-context reservations may end runs earlier than actual caps.
No automatic retries or infrastructure reruns; changed protocols require new runs.

Raw dataset contents and issue text are not republished here. Task IDs, revisions,
selection rules and issue hashes permit regeneration through upstream loaders.
Runtime logs remain local until reviewed for secrets and redistribution rights.
License selection remains pending.
