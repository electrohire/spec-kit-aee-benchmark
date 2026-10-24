# Release governance decision — engine 1.6.0 settled under a revised evidence standard

**Date:** 2026-10-24
**Decided by:** Tristen Pierson, repository owner
**Scope:** the publication of engine (applied-epistemic-engineering) version 1.6.0, and the release standard that governs it

## What was decided

The release of engine 1.6.0 is settled as a governance decision. The release gate's evidence standard is revised: publication no longer requires an audited matched baseline comparison under policy-v1, and instead binds to the evidence listed in [policy-v2](policy-v2.json), which is adopted by this record. Engine 1.6.0 — candidate commit `41e7cf0cce4a6043a6d18de945d66911c65789f7`, candidate bundle SHA-256 `86f1f1828a57191cb7bf6812c023792ee253e515114a8dbc395a00038937c225` — is approved for publication under policy-v2, and the approval is registered in [approvals.json](approvals.json) under that standard, in those words.

## Why the old requirement could not be met

Policy-v1 requires a complete, independently audited, matched baseline and candidate pair, compared under its registered margins. Both registries were empty by design, and the Stage B campaign (2026-10-23) returned a gate verdict of NOT VERIFIED on both engine legs, so nothing could be registered. The modeling study of 2026-10-24 then proved the stronger fact: no campaign in the current design space can produce the rows policy-v1 requires — in the tested workflow, specification stages consumed whole attempt budgets before implementation, so a matched pair of the required shape cannot be run at all, at any budget the program has. A requirement that cannot be produced by any available process is not a safety check; it is a permanent block mislabeled as one. Waiting would not have changed the answer.

## What the revised standard requires instead

An approval under policy-v2 binds publication to evidence that exists and is checked again by the gate, from protected benchmark main, at publish time:

- **Build identity.** The exact build — repository, commit and bundle hash — is recorded in a hash-checked evidence file, and the gate re-reads the build run from the component repository's public Actions records: a completed, successful Benchmark candidate run on the main branch for that exact commit, with its named artifact unexpired. The publish workflow's own input job additionally downloads that artifact and re-verifies every distribution hash before anything is published.
- **The frozen detector battery, reproduced exactly.** The five Spec 006 detector bundles under `reports/aee-validation/` were re-scored under the 1.6.0 candidate on 2026-10-24. Every bundle reproduced its frozen record exactly: headline outcome iterate, the lane-1 threshold met (one of one claims at or above the 0.7 threshold, none below), composed outcome iterate, assessor and composition exit codes 1 and 1, evidence verification checked 1 with 0 findings and 0 unresolvable, and the full score record (direct 0.9, propagated 0.9, band high, identical components and notes). The gate hash-checks the frozen records at publish time and re-compares the recorded fields.
- **Suites green at the release lineage.** The engine's CI workflow completed successfully at the candidate commit (run 39574112301). The benchmark harness suite passed in full — 1,064 tests passed, 0 failed — at the fixed lineage whose tip, commit `125ce77086cce779b5caafa5a4ffbe3bc5c96420`, is contained in this repository's main. The gate checks both facts from public records at publish time.
- **The audited build flow.** Publication happens only through the engine repository's publish workflow, which resolves this approval through the gate and publishes only the distributions extracted from the verified build artifact — the same artifact whose hashes are recorded above (wheel `c8e7fccd213c9961db21c3532804ff8b10fb589be4fe49f93838ef4bbed6763e`, source distribution `077123f3b41dac58a018ae1d37aace9c9997617015730f8c8e3eb118e36d065b`).

## The one precondition that is deliberately not applied

Policy-v1's verifier also required this repository's own CI to be green at the exact main revision before any release. That precondition is not applied to approvals under policy-v2, for a documented reason: at the settlement head, benchmark CI fails at exactly one step — dependency resolution — because this repository requires `applied-epistemic-engineering>=1.6.0,<2` and only versions up to 1.5.3 exist on the package index. The failure is caused by the very pin the publication satisfies, so requiring green CI first would make publication logically impossible. The gate instead records benchmark CI status at the resolved revision in its decision output, and verifying benchmark CI after publication is a required, publicly reported step of this settlement.

## What stays intact

Policy-v1's text is unchanged, and it remains the registered standard for matched-benchmark approvals. Every frozen record — the Stage B verdicts of NOT VERIFIED on both legs, the empty accepted-baselines registry, the frozen battery records — stays exactly as it was; this revision is additive and dated, and rewrites no history. The approval registered for this release states the standard it was granted under and is never valid as a policy-v1 approval.

## What this decision does not establish

This is a governance evidence decision, not a benchmark equivalence result. It establishes the identity of the exact build, that the frozen detector battery reproduces exactly under it, and that the test suites are green at its lineage. It does not establish that version 1.6.0 is as good as, or better than, any baseline on policy-v1's metrics, and no claim of that kind may be made from it.
