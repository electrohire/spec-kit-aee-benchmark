# Study 02 infrastructure stop — incomplete

**2026-10-19 follow-up:* * the [audited stopped-study export](../../local/current-study-02-stopped-postmortem/README.md)
now includes all 36 rows and independent grades of two retained final snapshots.
TinyDB's public pass did not survive its hidden grade; Cachetools collection was
incomplete. Proxy categories are positive 0/negative 0/unknown 1/ungraded 35. This
postmortem used no inference or campaign retry and is not a completed comparison.

## Original incident note

Pipeline 09 halted at 2026-10-18T22:21:19Z. A context-preflight `/apply-template` request returned HTTP 500; retaining that error then raised `OSError: [Errno28] No space left on device`. The host currently reports roughly 420 GB free. The underlying cause is unresolved; do not claim persistent disk exhaustion or a workflow failure.

All 348 frozen input hashes and all 7 existing event streams verify. Retained generation: 192 calls, 4,089,695 prompt tokens +82,529 completion tokens =4,172,224 native tokens; no stored generation call lacks native usage. The failed context preflight made 9HTTP requests and never created a new generation call. Historical setup/failed preparations remain retained but are not included in this subtotal or finally aggregated.

Of 12 scheduled trajectories/36 checkpoints, only 5 attempt rows exist. Cachetools+AEE stage 1 stopped on a repeated action after 22 calls; stages 2/3 are recorded unattempted with 0 calls. TinyDB+SpecKit stage 1 completed public verification after 114 calls; stage 2 stopped during tasks after 56 additional generation calls. No final independent campaign grading or export exists. Public verification does not establish accepted delivery. Completion-proxy positive/negative/unknown/ungraded categories and paired rework/regression economics remain uncomputed. No efficacy, hallucination-reduction, savings or detector precision/recall conclusion is justified.

Preserve the campaign and every historical preparation. Do not resume/retry implicitly. Diagnose the service/storage failure, retain integrity/accounting evidence, and establish a fresh prospective campaign before new scored generation. Do not weaken guards or budgets. Local API spend $0 excludes hardware, energy and labor. Convenience samples, readiness exposure, host/controller adaptation and concurrent authorized CPU-only product validation limit interpretation.

[Admission amendment PR26](https://github.com/electrohire/spec-kit-aee-benchmark/pull/26). [Frozen source](https://github.com/electrohire/spec-kit-aee-benchmark/tree/0fb1098106ddc0867778911e76b5df629caae7f9). Subsequent recovery must be recorded separately from this stopped campaign.

[Fresh diagnostic results](diagnostics-01/summary.json): a 64 KiB flushed write and small/last-completed-request template checks passed, with zero generation calls. The exact failed context-selection request and its HTTP error response body were not retained; these probes do not establish the original cause.
