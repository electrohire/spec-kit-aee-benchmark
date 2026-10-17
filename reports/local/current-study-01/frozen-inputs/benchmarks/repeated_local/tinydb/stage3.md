# tinydb milestone 3

Resume after a context-free handoff with repository files and notes preserved. R01-R06 remain active.
R07: apply(operations, token=None) now supports an optional nonempty string idempotency token. Repeating an already successful identical batch/token returns a detached copy of the original inserted IDs without rerunning mutations, even if other direct database writes occurred. Reusing a token with different operations raises ValueError without changing data. Failed batches do not consume a token. None means normal operation; invalid tokens raise ValueError.
R08: Token bookkeeping belongs to this BatchWriter instance, never in user documents. A preview never records/consumes a token and keeps its original signature. Return lists must not expose internal token bookkeeping through mutation.

Implementation source: tinydb/journal.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.
