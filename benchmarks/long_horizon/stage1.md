# Stage 1: opt-in transactions for TinyDB

Extend this existing TinyDB repository with `from tinydb import TransactionalTinyDB`.
Keep ordinary TinyDB behavior unchanged. This is a single-instance, single-thread
feature for JSON-compatible document data, using MemoryStorage or JSONStorage.
Do not promise concurrent-writer safety, power-loss durability, or rollback after
arbitrary partial backend write failure. Do not change the upstream tests.

- R01: TransactionalTinyDB accepts the same constructor arguments as TinyDB;
  existing nontransactional operations and named/default tables work normally.
- R02: `with db.transaction() as current:` yields the same db. Mutations through
  the db or table handles obtained before entry are visible within the transaction.
- R03: No backend storage.write call occurs during a transaction. Successful outer
  exit writes the complete logical database exactly once, even for multiple tables.
- R04: Any exception, including BaseException subclasses, propagates out and rolls
  back the entire scope with zero backend writes. A later transaction still works.
- R05: Rollback restores nested mutable values changed through supported callable
  updates, table creation/deletion, and preexisting table-handle query results.
  Query caches must not return data from discarded work.
- R06: After commit/rollback, existing handles can insert without ID collisions.
  Exact reuse of IDs consumed by rolled-back work is not required.
- R07: For this initial release, nesting transaction() raises RuntimeError before
  changing the parent transaction. A caught nesting error leaves the parent usable.
- R08: A committed JSONStorage database survives close/reopen; rollback leaves its
  persisted state unchanged. The existing upstream test suite continues to pass.

Add focused tests and usage documentation. You may inspect, edit and test the real
repository. Public milestone examples are at `/testbed/acceptance_public.py`;
additional acceptance cases are withheld. Run tests with `python -m pytest -c
/dev/null tests acceptance_public.py` so optional upstream coverage plugins are
not required. All model calls, tools and rework count against your shared budget.
