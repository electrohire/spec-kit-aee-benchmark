# Reproduce the upstream benchmark adapter

Start with [START_HERE](../START_HERE.md). Inspect current durable supervisor, process and model-qualified worker slots before inference. Do not launch this checkout while another frozen study uses the worker. Only already-authorized free local inference is allowed; never change the shared model/service or baseline env.

```sh
uv sync --locked --group dev
uv run python scripts/check_active_harness.py
uv run python scripts/check_evidence.py
uv run python scripts/check_pins.py
uv run python scripts/readme_results.py --check
```

These are offline thin-adapter/data-integrity checks, not GPU inference, upstream coding grades, efficacy, acceptance or a coverage target. Historical custom-task checks are retained for explicit archival reproduction, not default maintenance.

For an actual experiment, pin upstream revisions, immutable images and grader code; register task selection/treatments/seed/checkpoints/caps before outcomes; validate independent grading/transport; commit clean exact-green source; admit ONE fresh output/freeze through the saved serial controller. Frozen case/source hashes and call inventories must match. New release candidates use isolated dependencies; never replace the current baseline wheel or installed self-copies.

Finish the full schedule, independent author-label/retained-source grades, receipt/ledger/hash/accounting audits, separate result panels and exact-green publication. A raw export/launch flag is not completion. Unknown usage remains a reasoned lower bound; model failures are not fabricated hallucination labels.

See [matched protocol](../benchmarks/hallucinations/MATCHED-PROTOCOL.md), [coding economics design](long-horizon-economics-plan.md) and [release integration](benchmark-release-gates.md). The [earlier reproduction instructions](archive/reproduction-pre-upstream-20261019.md) are historical and do not authorize reruns of retired/stopped studies.


## Completed detector comparison and remaining coding work

The [amended matched detector results](../reports/hallucinations/matched-03-recovered-20261020/README.md) cover all 720 scheduled judgments. Baseline / Spec Kit / Spec Kit + AEE accuracy is 70.0% / 67.5% / 71.7% on HaluEval and 62.5% / 61.7% / 57.5% on RAGTruth. All paired intervals cross zero; the same-original-worker sensitivity also does not establish a consistent benefit. Gate eligibility is separate: all 240 AEE proposals remain ineligible. These detector data do not establish coding delivery, spontaneous workflow hallucination prevalence or long-horizon payback.

Original03 remains stopped after a worker crash with 711 retained judgments; the user authorized restoring only the existing profile and completing the missing 9 cells under a fresh frozen episode. The crash cause remains unresolved. All 1,487 physical requests, including technical readiness and the failed/orphan work, retain at least 5,613,402 native tokens and 1 unknown-usage request. This recovery is disclosed, not treated as an uninterrupted campaign, independent replication or a release-equivalence baseline.
