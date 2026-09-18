# Stage 3: detached backup and transactional restore

Continue the same codebase, preserving R01-R06 and R08-R13. Add `db.backup()` and
`db.restore(snapshot)`. The snapshot is an in-memory JSON-compatible dictionary,
not a filename: `{table_name: {document_id_string: document_dictionary}}`.

- R14: backup() returns all tables, including the default table, from the current
  logical state. During a transaction it includes tentative changes. Empty DB -> {}.
- R15: Backups are deeply detached: changing nested backup values does not change
  the database, and later database changes do not mutate an earlier backup.
- R16: restore(snapshot) replaces the complete logical database, removing tables
  absent from the snapshot. It deeply copies caller input. Existing table handles,
  caches and subsequent ID allocation reflect restored data without collisions.
- R17: Validate the entire snapshot before any mutation/write. Root/table/document
  containers must be dictionaries, table names strings, document IDs canonical
  positive decimal strings (e.g. '1', '23'; not '0', '-1', '01', int, or bool).
  Document values must be JSON-compatible and finite (reject NaN/Infinity, sets,
  non-string nested dictionary keys). Reject invalid snapshots with ValueError;
  preserve the complete prior database and perform zero backend writes.
- R18: restore() inside any transaction is rollbackable and does not write storage
  until successful outer commit. Failed inner restore scopes restore parent state;
  outer rollback discards successful inner restores. backup() observes active state.
- R19: Restoring outside a transaction performs one backend write. JSONStorage
  backup/restore survives close/reopen. {} is a valid replacement database.

These requirements do not add concurrent-writer guarantees, file backup APIs or
crash-safe storage guarantees. Preserve ordinary TinyDB API compatibility and
the unchanged upstream regression suite. Update your feature tests/documentation.
