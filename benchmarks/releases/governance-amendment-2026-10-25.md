# Governance amendment — relocated record (2026-10-25)

**Relocated under the decision of:** Tristen Pierson, repository owner, 2026-10-25 11:31 EDT — "Restore the anchored record byte-identical and move the amendment to its own new file, then re-dispatch."

The amendment below was first recorded on 2026-10-24 as a section appended to the governance decision record, `benchmarks/releases/governance-2026-10-24.md` (PR #60). That record's exact bytes are anchored in the registered release evidence (SHA-256 `60706e73ec0f63ecfc2570748c85fc83c913e3de4791f7ff2d2833c10ee515e6`), and the release gate fetches the record live from this repository's protected main and hash-checks it at verification time. The appended section changed the record's hash (to `b3baac0d4b741178ad3920c8127629dfb4ebe312463c2bc26324bf838554f440`), and the publish run that followed (engine publish run 40206913942, 2026-10-25) was blocked at the gate: "governance decision record changed". The decision record has therefore been restored to its anchored bytes exactly, and the amendment text is moved here verbatim.

**Standing rule: anchored records are frozen at anchoring; amendments are new files.** A record whose hash is anchored in registered evidence is never edited after anchoring; amendments and corrections are recorded as new dated files, as this one now is.

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
