# Governance amendment — scope correction (2026-10-25)

**Decided by:** Tristen Pierson, repository owner, 2026-10-25 12:12 EDT — "Add the workflow scope to the classic token in place, record the correction, and re-dispatch."

This amendment is a new file, recorded under the standing rule: **anchored records are frozen at anchoring; amendments are new files.** It touches nothing that is anchored: the governance decision record ([governance-2026-10-24.md](governance-2026-10-24.md), SHA-256 `60706e73ec0f63ecfc2570748c85fc83c913e3de4791f7ff2d2833c10ee515e6`), [policy-v2.json](policy-v2.json), [approvals.json](approvals.json), and the registered evidence all stand exactly as they were. It succeeds the credential-swap amendment ([governance-amendment-2026-10-25-credential-swap.md](governance-amendment-2026-10-25-credential-swap.md)), whose credential terms it corrects in the single respect stated below.

## What was found

The publish flow was dispatched under the classic token (engine publish run 40209847265, 2026-10-25). The preparation job and the release gate both passed — the gate's seventh in-flow pass — and the release step then failed at the same creation call, at 2026-10-25T16:04:02Z. This run's log carries no literal `HTTP 403` line; the `gh` CLI rendered the refusal in its scope-hint form, verbatim:

```
! Failed to create release, "workflow" scope may be required.
  To request it, run:
    gh auth refresh -h github.com -s workflow
```

Nothing was published or created by that run; the repository was verified back to its prior state (13 releases, 22 tags; package index untouched).

That hint is the first scope-specific evidence the refusals have produced, and it states a hypothesis, which this record adopts **as a hypothesis, not a finding**: creating the release — and with it the tag, on a commit whose tree contains `.github/workflows` — requires the `workflow` grant. The hypothesis is consistent with every refusal on record. The built-in integration token holds no workflow grant. The fine-grained token was specified with Contents read/write only. The classic token was specified with the `repo` scope only. And the one credential that has ever succeeded at the identical call — the owner's OAuth user credential, in the Phase 1 premise probe on the exact publish payload — carries the `repo` **and** `workflow` scopes. Whether adding `workflow` clears the refusal is not established by anything so far; the correction below is the test.

One process admission belongs in this record, stated plainly. The two prior credential specifications both omitted the `workflow` scope — the fine-grained specification granted Contents only, and the classic specification granted `repo` only with the scope expressly recorded as not needed — although the succeeding credential's scope list (`gist`, `read:org`, `repo`, `workflow`) had been in the diagnostic record since 2026-10-24. The refusal messages until this run never named a scope, and the discrepancy in the scope list was not weighed. The correction is recorded here so the record of how this release was unblocked — if it is unblocked by it — is complete about the omission as well.

## What changes

Only the classic token's scopes. The token behind the repository secret `RELEASE_CREDENTIAL` (`aee-release-credential-classic`) gains the `workflow` scope **in place**: editing a classic token's scopes does not change its value, so the secret itself is not changed, the secret's name is unchanged, and the publish workflow is not edited. The scope is added by the owner; its value never passes through any agent, exactly as before.

Every other recorded term stands unchanged: the token is single-purpose; its 7-day expiry lapses around 2026-11-01; the fine-grained token stands revoked; and **the classic token is revoked immediately after publication verifies**. Once the owner has added the scope, the publish flow is re-dispatched once, through its gate as always; a further refusal at the release step would close the token family entirely and leave the routes already on record (the updated support inquiry, or a human-credential publication recorded as a departure).

## What does not change

The standard in [policy-v2](policy-v2.json) and the approval registered under it in [approvals.json](approvals.json) are unchanged. This is a third mechanism amendment, not a new approval, and it alters none of the evidence the gate checks: build identity, the reproduced frozen detector battery, and suites green at the release lineage stand exactly as recorded. Publication still happens only through the engine repository's publish workflow. The boundary stated in the decision record still applies: nothing here is a policy-v1 approval or a benchmark equivalence claim.
