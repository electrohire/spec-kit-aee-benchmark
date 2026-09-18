import copy
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage

def new_db(*args, **kwargs):
    from tinydb import TransactionalTinyDB
    return TransactionalTinyDB(*args, **kwargs)

class CountingStorage(MemoryStorage):
    last = None
    def __init__(self):
        super().__init__()
        self.writes = []
        CountingStorage.last = self
    def write(self, data):
        self.writes.append(copy.deepcopy(data))
        super().write(data)

def test_R01_R02_R03_commit():
    db = new_db(storage=CountingStorage)
    backend = CountingStorage.last
    table = db.table('items')
    with db.transaction() as current:
        assert current is db
        table.insert({'value': 1})
        db.insert({'value': 2})
        assert table.all()[0]['value'] == 1
        assert backend.writes == []
    assert len(backend.writes) == 1
    assert len(db) == 1 and len(table) == 1

def test_R04_R05_R06_rollback():
    db = new_db(storage=CountingStorage)
    db.insert({'value': 1, 'nested': [1]})
    assert db.search(Query().value == 1)
    backend = CountingStorage.last
    backend.writes.clear()
    with pytest.raises(ValueError):
        with db.transaction():
            db.update(lambda doc: doc['nested'].append(2))
            db.update({'value': 3})
            assert db.search(Query().value == 3)
            raise ValueError('rollback')
    assert db.search(Query().value == 1)[0]['nested'] == [1]
    assert not db.search(Query().value == 3)
    assert backend.writes == []
    new_id = db.insert({'value': 4})
    assert len({d.doc_id for d in db.all()}) == 2
    assert new_id != 1

def test_R08_json_persistence(tmp_path):
    path = tmp_path/'data.json'
    with new_db(path) as db:
        with db.transaction():
            db.insert({'kept': True})
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.truncate()
                raise RuntimeError('abort')
    with TinyDB(path) as check:
        assert check.all() == [{'kept': True}]
