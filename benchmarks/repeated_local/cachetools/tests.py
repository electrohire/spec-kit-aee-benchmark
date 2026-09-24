import pytest
from cachetools.tagged import TaggedCache

def test_public_basic():
    c=TaggedCache(2); c.put('a',1,['x']); assert c.get('a')==1
    assert c.invalidate('x')==1 and len(c)==0

def test_public_replacement():
    c=TaggedCache(2); c.put('a',1,['old']); c.put('a',2,['new'])
    assert c.invalidate('old')==0 and c.get('a')==2

def test_R01_detached():
    c=TaggedCache(2); v={'x':[1]}; c.put('a',v,['x']); v['x'].append(2)
    out=c.get('a');out['x'].append(3)
    assert c.get('a')=={'x':[1]}

def test_R02_eviction_reuse():
    c=TaggedCache(2);c.put('a',1,['old']);c.put('b',2);c.put('c',3);c.put('a',4,['new'])
    assert c.invalidate('old')==0 and c.get('a')==4

def test_R03_invalid_replacement():
    c=TaggedCache(2);c.put('a',1,['old']);c.put('b',2)
    with pytest.raises(ValueError):c.put('a',99,['ok',3])
    c.put('c',3)
    with pytest.raises(KeyError):c.get('a')
    assert c.get('b')==2

# STAGE2

def test_public_union_resize():
    c=TaggedCache(3);c.put('a',1,['x']);c.put('b',2,['x','y']);c.put('c',3,['y'])
    assert c.invalidate_many(['x','y'])==3
    c.resize(1);assert c.maxsize==1

def test_R04_intersection_empty():
    c=TaggedCache(3);c.put('a',1,['x']);c.put('b',2,['x','y'])
    assert c.invalidate_many([],mode='all')==0 and len(c)==2
    assert c.invalidate_many(['x','y'],mode='all')==1 and c.get('a')==1

def test_R05_resize_lru():
    c=TaggedCache(3)
    for k in 'abc':c.put(k,k)
    c.get('a');c.resize(2)
    with pytest.raises(KeyError):c.get('b')
    assert c.get('a')=='a' and c.get('c')=='c'

def test_R05_invalid_size():
    c=TaggedCache(2);c.put('a',1)
    for size in [True,0,-1,2.5]:
        with pytest.raises(ValueError):c.resize(size)
    assert c.maxsize==2 and c.get('a')==1

def test_R06_generator():
    c=TaggedCache(3);c.put('a',1,(x for x in ['a','a','b']))
    assert c.invalidate_many((x for x in ['a','b']),mode='all')==1

# STAGE3

def test_public_ttl():
    now=[0];c=TaggedCache(2,timer=lambda:now[0]);c.put('a',1,ttl=2)
    now[0]=3
    with pytest.raises(KeyError):c.get('a')

def test_R07_exact_boundary():
    now=[0];c=TaggedCache(2,timer=lambda:now[0]);c.put('a',1,ttl=2);now[0]=2
    assert len(c)==0

def test_R07_zero_ttl():
    c=TaggedCache(2,timer=lambda:0);c.put('a',1,ttl=0)
    with pytest.raises(KeyError):c.get('a')

def test_R07_invalid_ttl():
    c=TaggedCache(2);c.put('a',1,['x'])
    for ttl in [True,-1,float('nan'),float('inf'),'1']:
        with pytest.raises(ValueError):c.put('a',99,['y'],ttl=ttl)
    assert c.get('a')==1 and c.invalidate('x')==1

def test_R08_expiry_invalidation():
    now=[0];c=TaggedCache(3,timer=lambda:now[0]);c.put('a',1,['x'],ttl=1);c.put('b',2,['x'])
    now[0]=1
    assert c.invalidate('x')==1 and len(c)==0

def test_R08_overwrite_expiry():
    now=[0];c=TaggedCache(2,timer=lambda:now[0]);c.put('a',1,ttl=1);c.put('a',2)
    now[0]=10
    assert c.get('a')==2


# CLAIM-A CANDIDATES (feat/claim-a-candidates): hidden tests for new calibration variants.
import pytest
from cachetools.tagged import TaggedCache


def test_R05_resize_recency_grow():
    # R05: resize preserves surviving entries AND their LRU order
    # (growing must not evict, and must not reset recency).
    c = TaggedCache(2)
    c.put('a', 1); c.put('b', 2)
    c.get('a')            # 'a' is now most-recently-used; 'b' is LRU
    c.resize(4)
    c.put('c', 3); c.put('d', 4); c.put('e', 5)   # over capacity: evict LRU
    with pytest.raises(KeyError):
        c.get('b')        # 'b' was LRU after resize
    assert c.get('a') == 1 and c.get('e') == 5


def test_R02_put_overwrite_recency():
    # R02 extension (stage1.md): overwriting an existing key via put refreshes
    # its LRU recency, making it the most-recently-used entry.
    c = TaggedCache(2)
    c.put('a', 1); c.put('b', 2)
    c.put('a', 10)        # overwrite: 'a' becomes most-recently-used
    c.put('c', 3)         # evicts LRU
    with pytest.raises(KeyError):
        c.get('b')
    assert c.get('a') == 10 and c.get('c') == 3


def test_R06_generator_tags_stored():
    # R06: generator tags must be consumed exactly once AND still be stored
    # on the entry (a double-consumed generator silently stores empty tags).
    c = TaggedCache(3)
    c.put('a', 1, (t for t in ['x', 'y']))
    assert c.get('a') == 1
    assert c.invalidate('x') == 1
    assert len(c) == 0


def test_R04_invalid_mode():
    # R04: reject an invalid mode with ValueError before any mutation.
    c = TaggedCache(3)
    c.put('a', 1, ['x']); c.put('b', 2, ['y'])
    with pytest.raises(ValueError):
        c.invalidate_many(['x'], mode='bogus')
    assert c.get('a') == 1 and c.get('b') == 2 and len(c) == 2


def test_R08_resize_purges_expired():
    # R08 x R05: expired entries are removed before resize, so an expired entry
    # can never win a shrink-survivor slot over a live entry.
    now = [0]
    c = TaggedCache(3, timer=lambda: now[0])
    c.put('a', 1, ttl=1); c.put('b', 2)
    c.get('a')            # 'a' most-recently-used, but it expires at now == 1
    now[0] = 1
    c.resize(1)
    assert c.get('b') == 2
    assert len(c) == 1


def test_R08_put_evicts_after_expiry():
    # R08 x R02: expired entries are removed before put, so capacity eviction
    # only ever discards live entries (upstream cachetools TTLCache documents
    # the same ordering: expired entries removed first, LRU only if none expired).
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1, ttl=1); c.put('b', 2)
    c.get('a')            # order: b (LRU), a (MRU, expires at now == 1)
    now[0] = 1
    c.put('c', 3)         # 'a' expires first; no live entry is evicted
    assert c.get('b') == 2 and c.get('c') == 3
    with pytest.raises(KeyError):
        c.get('a')


def test_R04_all_requires_every_tag():
    # R04: mode='all' removes entries containing EVERY supplied tag, i.e. the
    # entry's tag set must be a superset of the requested tags (not the reverse).
    c = TaggedCache(3)
    c.put('a', 1, ['x']); c.put('b', 2, ['x', 'y'])
    assert c.invalidate_many(['x', 'y'], mode='all') == 1
    assert c.get('a') == 1
    with pytest.raises(KeyError):
        c.get('b')


def test_R08_expire_preserves_recency():
    # R08: removing expired entries must not touch the recency of survivors --
    # a purge pass that reads through the recency-touching LRUCache.__getitem__
    # instead of the passive Cache.__getitem__ silently resets survivor order.
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1); c.put('b', 2)
    c.get('a')            # 'a' is now most-recently-used
    now[0] = 5
    assert len(c) == 2    # triggers _expire with nothing expired
    c.put('c', 3)         # evicts LRU
    with pytest.raises(KeyError):
        c.get('b')        # 'b' was LRU; 'a' had been refreshed by get
    assert c.get('a') == 1 and c.get('c') == 3


# CLAIM-A CANDIDATES, round 2 (2026-09-22): hidden tests for harder variants.

def test_R05_resize_preserves_expiry():
    # R05 clarification: preserving a surviving entry preserves its absolute
    # expiry; resize must not drop expiries (immortal entries) or recompute them.
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1, ttl=100)
    c.resize(4)
    now[0] = 50
    assert c.get('a') == 1       # still live: expiry survived the resize
    now[0] = 150
    with pytest.raises(KeyError):
        c.get('a')               # expired on its original schedule


def test_R05_resize_preserves_expiry_shrink():
    # Same through a shrink: the MRU survivor keeps its original expiry.
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1, ttl=100); c.put('b', 2)
    c.get('a')                   # 'a' is MRU; survives a shrink to 1
    c.resize(1)
    now[0] = 50
    assert c.get('a') == 1
    now[0] = 150
    with pytest.raises(KeyError):
        c.get('a')


def test_R08_len_counts_live():
    # R08: expired entries are removed before len; len counts live entries.
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1, ttl=1); c.put('b', 2)
    now[0] = 5
    assert len(c) == 1
    assert c.get('b') == 2


def test_R02_get_refreshes_recency():
    # R02: get refreshes LRU recency -- it must read through the
    # recency-touching LRUCache __getitem__, not the passive Cache.__getitem__.
    c = TaggedCache(2)
    c.put('a', 1); c.put('b', 2)
    c.get('a')          # 'a' is now MRU; 'b' is LRU
    c.put('c', 3)       # evicts LRU
    with pytest.raises(KeyError):
        c.get('b')
    assert c.get('a') == 1 and c.get('c') == 3


def test_R08_overwrite_replaces_expiry():
    # R08: overwriting with a new ttl REPLACES the prior expiry (it does not
    # extend it, and a naive always-clear repair would fail this direction).
    now = [0]
    c = TaggedCache(2, timer=lambda: now[0])
    c.put('a', 1, ttl=100)
    now[0] = 50
    c.put('a', 2, ttl=100)      # new expiry: 150, not 100
    now[0] = 120
    assert c.get('a') == 2
    now[0] = 200
    with pytest.raises(KeyError):
        c.get('a')
