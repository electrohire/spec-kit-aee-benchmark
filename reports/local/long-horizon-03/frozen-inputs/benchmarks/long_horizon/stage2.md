# Stage 2: nested savepoints

Continue the same repository and implementation. Preserve R01-R06 and R08 from
stage 1. Product requirements now deliberately replace R07: nested transactions
must be supported rather than rejected. Update documentation and your own tests
to reflect this explicit change; do not preserve the obsolete rejection behavior.

- R09 (supersedes R07): Nested transaction() contexts create independent savepoints,
  including at least three levels. Each context yields the same db.
- R10: Successful inner exit merges into its parent without writing the backend.
  Only a successful outermost exit writes storage, exactly once.
- R11: A failed inner scope rolls back only its own changes. If caught inside the
  outer scope, earlier outer work remains and later outer work can still commit.
- R12: An outer failure discards even successfully completed inner scopes, including
  table creation/deletion and nested mutable updates. It writes nothing.
- R13: Preexisting table handles and warmed query caches reflect the current active
  savepoint after inner rollback. Subsequent inserts must not collide with live IDs.

Retain all other stage-1 scope exclusions. `/testbed/acceptance_public.py` now has
cumulative public examples for this release. The old nesting-rejection example
is intentionally removed because its requirement was superseded.
