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


# CLAIM-A CANDIDATES (feat/claim-a-candidates): hidden tests for new calibration variants.
import pytest

# New hidden tests for Claim A tinydb calibration candidates.
# Concatenated after benchmarks/repeated_local/tinydb/tests.py to form tests_all.py;
# the `pair` fixture is defined there and resolves within the single module.


def test_R07_stored_ops_detached(pair):
    # R07+R03: the writer must not alias the caller's operations list in the
    # token store. Mutating the caller's list after a tokenized apply must not
    # cause a spurious token conflict when replaying the identical batch.
    db, w = pair
    ops = [{'op': 'insert', 'document': {'x': 1}}]
    assert w.apply(ops, token='a') == [1]
    ops[0]['document']['x'] = 2
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [1]
    assert len(db) == 1


def test_R07_empty_batch_token(pair):
    # R01+R07: an empty batch is a successful batch returning []. With a token
    # it must be recorded and replayed like any other batch, not rejected.
    db, w = pair
    assert w.apply([], token='b') == []
    assert w.apply([], token='b') == []
    assert len(db) == 0


def test_R07_conflict_same_length(pair):
    # R07: reusing a token with *different* operations raises ValueError, even
    # when the two operation lists have the same length.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [1]
    with pytest.raises(ValueError):
        w.apply([{'op': 'insert', 'document': {'x': 9}}], token='a')
    assert len(db) == 1


def test_R05_preview_result_detached(pair):
    # R05+R03: every preview call returns a fresh list. Mutating one preview
    # result must not corrupt later preview calls or internal state.
    db, w = pair
    ops = [{'op': 'insert', 'document': {}}]
    first = w.preview(ops)
    first.append(999)
    assert w.preview(ops) == [1]


def test_R07_token_identical_means_equal(pair):
    # R07: "identical batch" means *equal* operations. Dict key order must not
    # matter for the token-conflict comparison.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {}}], token='a') == [1]
    assert w.apply([{'document': {}, 'op': 'insert'}], token='a') == [1]
    assert len(db) == 1


def test_R06_no_stale_snapshot(pair):
    # R06: a direct db.insert between calls must be seen. The wrapper must not
    # reuse a stale snapshot of the data across calls.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}]) == [1]
    db.insert({'x': 2})
    assert w.apply([{'op': 'remove', 'doc_id': 2}]) == []
    assert [d['x'] for d in db.all()] == [1]


def test_R05_compact_no_reuse(pair):
    # R05+R03: inserted IDs are never reused. The next insertion ID keeps
    # advancing even when lower IDs were freed by a remove.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {'a': 1}},
                    {'op': 'insert', 'document': {'b': 2}}]) == [1, 2]
    assert w.apply([{'op': 'remove', 'doc_id': 1}]) == []
    assert w.apply([{'op': 'insert', 'document': {}}]) == [3]


def test_R05_next_id_monotonic(pair):
    # R05: the wrapper threads TinyDB's next-insertion-ID forward across calls.
    # Removing the only document must not rewind it.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {}}]) == [1]
    assert w.apply([{'op': 'remove', 'doc_id': 1}]) == []
    assert w.apply([{'op': 'insert', 'document': {}}]) == [2]


def test_R07_invalid_token_no_side_effects(pair):
    # R07+R02: an invalid token raises ValueError, and a failed apply changes
    # nothing: no documents written, no IDs consumed.
    db, w = pair
    with pytest.raises(ValueError):
        w.apply([{'op': 'insert', 'document': {'x': 1}}], token='')
    assert len(db) == 0
    assert db.insert({}) == 1


# CLAIM-A CANDIDATES, round 2 (2026-09-22): hidden tests for harder variants.

def test_R07_conflict_leaves_data_unchanged(pair):
    # R07: reusing a token with different operations raises ValueError WITHOUT
    # changing data -- the conflict check must run before the batch is written.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [1]
    with pytest.raises(ValueError):
        w.apply([{'op': 'insert', 'document': {'x': 2}}], token='a')
    assert [d['x'] for d in db.all()] == [1]
    assert len(db) == 1
    # The original token still replays its original result afterwards.
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [1]
    assert len(db) == 1


def test_R02_retained_handle_sees_apply(pair):
    # R02: a previously acquired table handle must reflect a successful apply.
    # Without the post-write clear_cache(), the handle serves stale results.
    db, w = pair
    db.insert({'x': 1})
    table = db.table('_default')
    query = Query().x == 1
    assert len(table.search(query)) == 1
    assert w.apply([{'op': 'remove', 'doc_id': 1}]) == []
    assert table.search(query) == []
    assert len(db) == 0


def test_R08_tokens_belong_to_instance(pair):
    # R08: token bookkeeping belongs to the BatchWriter instance -- a fresh
    # writer must not replay another writer's tokens.
    db, w = pair
    assert w.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [1]
    w2 = BatchWriter(db)
    assert w2.apply([{'op': 'insert', 'document': {'x': 1}}], token='a') == [2]
    assert len(db) == 2
