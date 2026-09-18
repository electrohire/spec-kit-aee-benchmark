def test_R09_R10_R11_savepoint():
    db = new_db(storage=CountingStorage)
    backend = CountingStorage.last
    with db.transaction():
        db.insert({'a': 1})
        with pytest.raises(ValueError):
            with db.transaction():
                db.insert({'discard': True})
                raise ValueError('inner')
        with db.transaction() as current:
            assert current is db
            db.insert({'b': 2})
        assert backend.writes == []
    assert db.all() == [{'a': 1}, {'b': 2}]
    assert len(backend.writes) == 1

def test_R12_R13_outer_rollback():
    db = new_db(storage=MemoryStorage)
    table = db.table('items')
    table.insert({'value': 1})
    with pytest.raises(RuntimeError):
        with db.transaction():
            with db.transaction():
                table.update({'value': 2})
                assert table.search(Query().value == 2)
            raise RuntimeError('outer')
    assert table.search(Query().value == 1)
    assert not table.search(Query().value == 2)
