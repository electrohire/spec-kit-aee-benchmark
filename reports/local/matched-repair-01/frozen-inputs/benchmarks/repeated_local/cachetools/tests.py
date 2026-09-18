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
