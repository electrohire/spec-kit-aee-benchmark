# Limitations and open gates
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
