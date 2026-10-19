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

