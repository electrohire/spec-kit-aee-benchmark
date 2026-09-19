import copy
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage

def new_db(*args, **kwargs):
    from tinydb import TransactionalTinyDB
    return TransactionalTinyDB(*args, **kwargs)

class Counter(MemoryStorage):
    last = None
    def __init__(self):
        super().__init__()
        self.writes = []
        Counter.last = self
    def write(self, value):
        self.writes.append(copy.deepcopy(value))
        super().write(value)

def test_R01_R02_R03_multitable_retained_handle():
    db = new_db(storage=Counter)
    old = db.table('sensor-east')
    old.insert({'n': 11})
    other = db.table('sensor-west')
    other.insert({'n': 22})
    backend = Counter.last
    backend.writes.clear()
    with db.transaction() as value:
        assert value is db
        old.update({'n': 33})
        other.remove(Query().n == 22)
        db.insert({'n': 44})
        assert backend.writes == []
        assert old.get(Query().n == 33)
    assert len(backend.writes) == 1
    assert old.all() == [{'n': 33}] and other.all() == []

def test_R04_baseexception_and_reuse():
    class Abort(BaseException): pass
    db = new_db(storage=Counter)
    backend = Counter.last
    with pytest.raises(Abort):
        with db.transaction():
            db.insert({'discard': 99})
            raise Abort()
    assert backend.writes == [] and db.all() == []
    with db.transaction():
        db.insert({'keep': 91})
    assert len(backend.writes) == 1 and db.all() == [{'keep': 91}]

def test_R05_aliases_tables_and_caches():
    db = new_db(storage=Counter)
    table = db.table('retained')
    table.insert({'tag': 'old', 'nested': {'items': [8, 9]}})
    assert table.search(Query().tag == 'old')
    backend = Counter.last
    previous = copy.deepcopy(backend.memory)
    backend.writes.clear()
    with pytest.raises(LookupError):
        with db.transaction():
            table.update(lambda doc: doc['nested']['items'].append(10))
            table.update({'tag': 'new'})
            assert table.search(Query().tag == 'new')
            db.drop_table('retained')
            db.table('temporary').insert({'t': 1})
            raise LookupError()
    assert backend.memory == previous
    assert backend.writes == []
    assert db.tables() == {'retained'}
    assert table.search(Query().tag == 'old')[0]['nested']['items'] == [8, 9]
    assert not table.search(Query().tag == 'new')

def test_R06_id_allocation_after_rollback():
    db = new_db(storage=MemoryStorage)
    table = db.table('ids')
    table.insert_multiple([{'n': 1}, {'n': 2}])
    with pytest.raises(ValueError):
        with db.transaction():
            table.truncate()
            table.insert({'n': 8})
            raise ValueError()
    table.insert({'n': 3})
    assert sorted(d['n'] for d in table.all()) == [1, 2, 3]
    assert len({d.doc_id for d in table.all()}) == 3

def test_R08_reopen_multiple_tables(tmp_path):
    path = tmp_path/'holdout.json'
    with new_db(path) as db:
        db.table('prior').insert({'a': [3]})
        with db.transaction():
            db.table('prior').update({'a': [4]})
            db.table('next').insert({'b': 9})
        stable = path.read_bytes()
        with pytest.raises(ValueError):
            with db.transaction():
                db.drop_tables()
                raise ValueError()
        assert path.read_bytes() == stable
    with TinyDB(path) as db:
        assert db.table('prior').all() == [{'a': [4]}]
        assert db.table('next').all() == [{'b': 9}]
