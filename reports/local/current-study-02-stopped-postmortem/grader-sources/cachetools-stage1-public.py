import pytest
from cachetools.tagged import TaggedCache

def test_public_basic():
    c = TaggedCache(2)
    c.put('a', 1, ['x'])
    assert c.get('a') == 1
    assert c.invalidate('x') == 1 and len(c) == 0

def test_public_replacement():
    c = TaggedCache(2)
    c.put('a', 1, ['old'])
    c.put('a', 2, ['new'])
    assert c.invalidate('old') == 0 and c.get('a') == 2