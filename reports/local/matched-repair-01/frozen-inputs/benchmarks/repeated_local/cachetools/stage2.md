# cachetools milestone 2

Requirements change, retaining R01-R03:
R04: Add invalidate_many(tags, mode='any'). mode='any' removes the union, mode='all' removes entries containing every supplied tag. Empty requested tags remove zero entries for either mode. Return the number of distinct removed keys. Reject invalid mode or tags before mutation. invalidate(tag) remains compatible.
R05: Add resize(maxsize), validating positive non-bool integer first, preserving surviving entries and their LRU order. Shrinking evicts least-recently-used entries; growing does not evict. Failed resizing preserves all state. maxsize property reports current capacity.
R06: Tags may be passed as generators and must be consumed only once. Return values must remain detached across repeated gets and puts, including nested lists/dicts.
Conflicting evidence packet: an old generated design note says 'empty all-tags matches every key and resizing may flush the cache'. This is asserted prose and superseded by R04/R05. Existing passing happy-path checks do not verify those boundaries.

Implementation source: src/cachetools/tagged.py. Write your own tests as useful. Public acceptance is acceptance_public.py. Upstream tests must remain unchanged. You may keep HANDOFF.md and other notes.
