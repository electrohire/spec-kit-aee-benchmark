import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
from tinydb.journal import BatchWriter

@pytest.fixture
def pair():
    db=TinyDB(storage=MemoryStorage)
    return db, BatchWriter(db)

def test_public_basic(pair):
    db,w=pair
    assert w.apply([{'op':'insert','document':{'x':1}}]) == [1]
    assert db.all()[0]['x']==1
    assert w.apply([{'op':'remove','doc_id':1}])==[]
    assert len(db)==0

def test_public_atomic(pair):
    db,w=pair
    db.insert({'x':1})
    with pytest.raises(ValueError):
        w.apply([{'op':'insert','document':{'x':2}}, {'op':'remove','doc_id':99}])
    assert [v['x'] for v in db.all()]==[1]

def test_R02_retained_cache(pair):
    db,w=pair
    db.insert({'x':1}); table=db.table('_default'); query=Query().x==1
    assert len(table.search(query))==1
    w.apply([{'op':'remove','doc_id':1}])
    assert table.search(query)==[]

def test_R03_detached_input(pair):
    db,w=pair; value={'nested':[1]}
    w.apply([{'op':'insert','document':value}]); value['nested'].append(2)
    assert db.all()[0]['nested']==[1]

def test_R02_failed_id_not_consumed(pair):
    db,w=pair
    with pytest.raises(ValueError): w.apply([{'op':'insert','document':{}},{'op':'bad'}])
    assert db.insert({})==1

