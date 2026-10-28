# Governance amendment — credential swap (2026-10-25)

**Decided by:** Tristen Pierson, repository owner, 2026-10-25 11:50 EDT — "Swap the secret to a classic token (repo scope, short expiry, revoked after release), update the ticket, and re-dispatch."

This amendment is a new file, recorded under the standing rule: **anchored records are frozen at anchoring; amendments are new files.** It touches nothing that is anchored: the governance decision record ([governance-2026-10-24.md](governance-2026-10-24.md), SHA-256 `60706e73ec0f63ecfc2570748c85fc83c913e3de4791f7ff2d2833c10ee515e6`), [policy-v2.json](policy-v2.json), [approvals.json](approvals.json), and the registered evidence all stand exactly as they were. It succeeds the first mechanism amendment ([governance-amendment-2026-10-25.md](governance-amendment-2026-10-25.md)), whose credential terms it replaces as stated below.

## What was found

The first mechanism amendment put a fine-grained personal access token behind the publish workflow's release step (repository secret `RELEASE_CREDENTIAL`). After the decision record was restored to its anchored bytes and the amendment relocated to its own file, the publish flow was re-dispatched (engine publish run 40207970185, 2026-10-25). The release gate passed inside the flow — the sixth in-flow pass, and the first since the amendment — and the release step then failed at the same creation call, this time under the fine-grained token, at 2026-10-25T15:40:07Z, verbatim:

```
HTTP 403: Resource not accessible by personal access token (https://api.github.com/repos/electrohire/applied-epistemic-engineering/releases)
```

Nothing was published or created by that run; the repository was verified back to its prior state (13 releases, 22 tags; package index untouched).

The one explanation left open at that point — that the token might stand unapproved under the electrohire organization's fine-grained-token policy, a surface only the owner can read — has since been checked by the owner and is excluded. The token (`aee-release-credential`, Token ID 21766074) stands **active** in the organization's token list; the organization's pending-requests list is empty, although the org policy does require administrator approval. Its recorded configuration matches the first amendment's terms in every particular: owner tbitcs, resource owner electrohire, repository access `electrohire/applied-epistemic-engineering` only, repository permissions Metadata read and Contents (code) read and write, no organization permissions, and expiry Sat, Jan 23 2027 — exactly the specified 90 days from its creation. The publish run presented the token and GitHub registered its use; the creation call was still refused.

The position is therefore sharp. Both credential mechanisms GitHub offers a workflow — its built-in integration token and a fine-grained personal access token — are refused on the same POST /releases in the engine repository, while the owner's OAuth user credential performed the identical call successfully on the exact publish payload (the Phase 1 premise probe: non-draft, generated notes, target = the candidate commit; probe release created and deleted, repository verified unchanged). The support inquiry drafted under the first amendment has been updated with these runs and the token-state verification, for the owner to file in parallel.

## What changes

Only the credential behind the existing secret. The repository secret `RELEASE_CREDENTIAL` in the engine repository now holds a **classic personal access token**, with the single scope `repo`. The secret's name is unchanged and the publish workflow is not edited — the release step reads whichever token the secret holds.

Stated plainly, as the record requires: a classic token's `repo` scope **cannot be narrowed to a single repository**. It reaches every repository the owner's account can access, and in that respect it is broader than the fine-grained token it replaces. The swap is accepted on those terms, bounded by these mitigations:

- **7-day expiry** — the token is created with an expiration seven days out, the shortest practical window for this release.
- **Single purpose** — it exists only to authenticate the publish workflow's release step for this release.
- **The fine-grained token is revoked** (Token ID 21766074) once the classic token is stored in the secret.
- **The classic token is revoked immediately after publication verifies** — as soon as the release is live and the verification checklist has read it back, the credential's work is done and it is destroyed.
- Its value is entered by the owner and never passes through any agent, exactly as with the credential it replaces.

## What does not change

The standard in [policy-v2](policy-v2.json) and the approval registered under it in [approvals.json](approvals.json) are unchanged. This is a second mechanism amendment, not a new approval, and it alters none of the evidence the gate checks: build identity, the reproduced frozen detector battery, and suites green at the release lineage stand exactly as recorded. Publication still happens only through the engine repository's publish workflow. The boundary stated in the decision record still applies: nothing here is a policy-v1 approval or a benchmark equivalence claim.
