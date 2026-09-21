# tinydb milestone 2

Requirements change, retaining R01-R03 unless explicitly replaced:
R04: Reject bool as a doc_id even though bool is an int subclass. Validate operations structurally before committing changes; raise ValueError for unsupported fields, non-list operations, or non-dict documents. Accept empty dictionaries as documents.
R05: Add preview(operations), returning the inserted IDs that apply would produce but leaving all data and the next insertion ID unchanged, including on errors. Preview and failed apply must not consume IDs. Existing table handles and query caches must remain coherent.
R06: Compatibility: direct db.insert operations between calls must be seen by the wrapper. Do not cache a stale initial snapshot.
Conflicting evidence packet: an older generated note says 'preview may consume IDs and bool IDs are accepted'. That note is unverified and superseded by R04/R05. A previously passing happy-path smoke does not verify those boundaries. Record and resolve the conflict using the current requirements.

Implementation source: tinydb/journal.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.

# Claim-A candidate extension (variant preview_cache_alias, 2026-09-21)
R05b: preview must return a new, detached list on every call. Mutating a list previously returned by preview must not affect subsequent preview results or any internal writer state.
