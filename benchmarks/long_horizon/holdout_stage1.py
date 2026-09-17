def test_R07_nested_rejection_keeps_outer():
    db = new_db(storage=Counter)
    backend = Counter.last
    with db.transaction():
        db.table('parent').insert({'n': 7})
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.table('child').insert({'forbidden': 1})
        db.table('parent').insert({'n': 8})
    assert len(backend.writes) == 1
    assert db.tables() == {'parent'}
    assert db.table('parent').all() == [{'n': 7}, {'n': 8}]
