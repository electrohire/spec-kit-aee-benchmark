# tinydb milestone 1

Build tinydb.journal.BatchWriter(db), wrapping a supplied TinyDB instance without changing its ordinary APIs. Use the default table only.
R01: apply(operations) accepts a list of operation dictionaries. Each operation is either {'op':'insert','document':dict} or {'op':'remove','doc_id':positive integer}. Return a list of inserted document IDs (removes add no result). Empty input returns []. Unknown/malformed operations raise ValueError.
R02: Batch application is atomic: validate and apply sequentially, but on any error restore the complete pre-batch default-table data. A remove targeting a missing ID is an error. Previously acquired db.table('_default') handles must reflect both success and rollback.
R03: Ordinary TinyDB reads/writes and preexisting documents continue to work. Inserted and returned nested data must not alias the caller's input. Mutating an operation after apply cannot mutate the database.

Implementation source: tinydb/journal.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.
