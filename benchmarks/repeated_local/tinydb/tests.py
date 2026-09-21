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

# STAGE2

def test_public_preview(pair):
    db,w=pair; ops=[{'op':'insert','document':{}}]
    assert w.preview(ops)==[1] and len(db)==0
    assert w.apply(ops)==[1]

def test_R04_bool_and_fields(pair):
    db,w=pair; db.insert({})
    for op in [{'op':'remove','doc_id':True},{'op':'insert','document':{},'extra':0}]:
        with pytest.raises(ValueError): w.apply([op])
    assert len(db)==1

def test_R05_preview_cache_and_id(pair):
    db,w=pair; db.insert({'x':1}); table=db.table('_default'); query=Query().x==1
    table.search(query)
    assert w.preview([{'op':'remove','doc_id':1},{'op':'insert','document':{'x':2}}])==[2]
    assert len(table.search(query))==1
    assert db.insert({})==2

def test_R06_external_writes(pair):
    db,w=pair; db.insert({}); w.apply([{'op':'insert','document':{}}]); assert db.insert({})==3
    assert w.preview([{'op':'insert','document':{}}])==[4]

def test_R04_list_and_empty(pair):
    db,w=pair
    for ops in [None,{},'insert',(1,)]:
        with pytest.raises(ValueError): w.apply(ops)
    assert w.apply([])==[]
    assert w.apply([{'op':'insert','document':{}}])==[1]

# STAGE3

def test_public_idempotent(pair):
    db,w=pair; ops=[{'op':'insert','document':{'x':1}}]
    assert w.apply(ops,token='a')==[1]
    assert w.apply(ops,token='a')==[1]
    assert len(db)==1

def test_R07_conflict(pair):
    db,w=pair; w.apply([{'op':'insert','document':{}}],token='a')
    with pytest.raises(ValueError): w.apply([],token='a')
    assert len(db)==1

def test_R07_failed_token(pair):
    db,w=pair
    with pytest.raises(ValueError): w.apply([{'op':'bad'}],token='a')
    assert w.apply([{'op':'insert','document':{}}],token='a')==[1]

def test_R08_detached_token_result(pair):
    db,w=pair; ops=[{'op':'insert','document':{}}]
    result=w.apply(ops,token='a'); result.append(777)
    db.insert({'other':1})
    assert w.apply(ops,token='a')==[1] and len(db)==2

def test_R08_preview_no_token(pair):
    db,w=pair; ops=[{'op':'insert','document':{}}]
    assert w.preview(ops)==[1]
    assert w.apply(ops,token='a')==[1]
    assert '_tokens' not in str(db.all())

def test_R07_bad_tokens(pair):
    db,w=pair
    for token in ['',False,1,[]]:
        with pytest.raises(ValueError): w.apply([{'op':'insert','document':{}}],token=token)
    assert len(db)==0

def test_R08_replay_detached(pair):
    # Freeze v7 trap test: the replay path must return a detached copy, not
    # the stored list itself. A repair that fixes the token store but
    # "simplifies" the replay detach passes every public test yet corrupts
    # bookkeeping as soon as a caller mutates a replayed result.
    db,w=pair; ops=[{'op':'insert','document':{}}]
    r1=w.apply(ops,token='a'); r1.append(1)
    r2=w.apply(ops,token='a'); r2.append(2)
    assert w.apply(ops,token='a')==[1] and len(db)==1
