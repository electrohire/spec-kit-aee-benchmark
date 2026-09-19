def test_R07_reject_nested_initial_release():
    db = new_db(storage=MemoryStorage)
    with db.transaction():
        db.insert({'a': 1})
        with pytest.raises(RuntimeError):
            with db.transaction():
                pass
        db.insert({'b': 2})
    assert len(db) == 2
