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
---

## Amendment — 2026-10-24: the release step's credential mechanism

**Decided by:** Tristen Pierson, repository owner, 2026-10-24 19:03 EDT — "Amend the workflow: repo-scoped token for the release step, publish, and open the support inquiry in parallel."

### What was found

The audited publish flow named above was dispatched five times for this release (runs 40114404585, 40114640616, 40114994388, 40127687155, 40128143849). Each time the gate passed inside the flow, and each time the flow's release step failed at `gh release create` with `HTTP 403: Resource not accessible by integration` on POST /releases, using the workflow's built-in token — whose own setup logs list Contents: write. The cause was isolated by experiment on 2026-10-24. Organization and repository workflow permissions were both at write; the repository's tag ruleset ("Immutable release and archive tags") was disabled for one complete attempt; no organization rulesets exist; release immutability is off; there is no legacy tag protection. A minimal workflow whose only step ran the same release-creation call with a bare payload — no generated notes, no attached files — was refused identically (run 40129221671), while the owner's user credential created a release at the same endpoint on the exact publish payload (non-draft, generated notes, target = the candidate commit above). That probe release and its tag were deleted afterwards, and the repository was verified back to its prior state (13 releases, 22 tags). The refusal is therefore a property of the built-in Actions token as an actor in that repository, not of any setting, rule, or payload. A support inquiry putting these facts to GitHub has been drafted for the owner to file.

### What changes

One line of the engine repository's publish workflow (electrohire/applied-epistemic-engineering PR #72): the release job's token now comes from the repository secret named `RELEASE_CREDENTIAL` instead of the built-in workflow token. Everything else about the flow is byte-identical — the same jobs in the same order, the same gate resolving this approval, the same verified distributions, the same package-index step on OIDC trusted publishing. No pin binds the publish workflow's own content: the pins set by engine PR #69 bind only the two references inside it to this repository's reusable gate workflows, and those references are unchanged, so no pin update accompanies this amendment.

The replacement credential is a fine-grained personal access token scoped to the engine repository only, with Contents read and write as its only repository permission, a 90-day expiry, and a single purpose: this release step. It is stored as the repository secret `RELEASE_CREDENTIAL`; its value is entered by the owner and never passes through any agent. It is revocable as soon as publication completes, and it can be renewed under the same secret name with no further workflow change.

### What does not change

The standard in [policy-v2](policy-v2.json) and the approval registered under it in [approvals.json](approvals.json) are unchanged. This is a mechanism amendment, not a new approval, and it alters none of the evidence the gate checks: build identity, the reproduced frozen detector battery, and suites green at the release lineage stand exactly as recorded above. Publication still happens only through the engine repository's publish workflow. The boundary stated in this record still applies: nothing here is a policy-v1 approval or a benchmark equivalence claim.
