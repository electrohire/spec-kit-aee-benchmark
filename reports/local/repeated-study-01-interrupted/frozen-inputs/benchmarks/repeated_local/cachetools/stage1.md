# cachetools milestone 1

Build cachetools.tagged.TaggedCache(maxsize), using the existing cachetools.LRUCache for bounded storage and preserving all existing cachetools APIs.
R01: put(key,value,tags=()) inserts/replaces an entry. get(key) returns a detached deep copy or raises KeyError for missing keys. Values are copied on input too. Keys are hashable. Tags must be a finite iterable of strings; deduplicate tags. Reject a bare string as tags and nonstring tag entries with ValueError, before changing existing state.
R02: invalidate(tag) removes exactly currently cached entries carrying that tag and returns the number removed. Replacing a key removes its old tag memberships. LRU eviction must not leave stale memberships affecting later reuse of the same key. get refreshes LRU recency. len(cache) counts live entries.
R03: maxsize must be a positive integer, excluding bool. Invalid replacement input must leave the old value/tags/recency unchanged. Values cost one capacity slot regardless of object size.

Implementation source: src/cachetools/tagged.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.
