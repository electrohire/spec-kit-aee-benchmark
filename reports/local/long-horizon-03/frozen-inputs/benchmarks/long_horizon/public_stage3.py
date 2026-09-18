def test_R14_R15_detached_backup():
    db = new_db(storage=MemoryStorage)
    db.insert({'values': [1]})
    snapshot = db.backup()
    assert snapshot == {'_default': {'1': {'values': [1]}}}
    snapshot['_default']['1']['values'].append(2)
    assert db.all()[0]['values'] == [1]

def test_R16_R17_R19_restore_validation():
    db = new_db(storage=CountingStorage)
    db.insert({'old': True})
    backend = CountingStorage.last
    backend.writes.clear()
    with pytest.raises(ValueError):
        db.restore({'ok': {'1': {}}, 'bad': {'01': {}}})
    assert db.all() == [{'old': True}]
    assert backend.writes == []
    db.restore({'new': {'7': {'v': 3}}})
    assert db.tables() == {'new'}
    assert db.table('new').all() == [{'v': 3}]
    assert len(backend.writes) == 1

def test_R18_restore_in_transaction():
    db = new_db(storage=MemoryStorage)
    db.insert({'old': True})
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.restore({'new': {'1': {'x': 2}}})
            assert db.backup() == {'new': {'1': {'x': 2}}}
            raise RuntimeError('abort')
    assert db.all() == [{'old': True}]
