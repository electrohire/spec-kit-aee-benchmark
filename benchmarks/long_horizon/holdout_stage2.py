def test_R09_R10_R11_three_levels():
    db = new_db(storage=Counter)
    backend = Counter.last
    with db.transaction():
        db.insert({'keep': 'outer'})
        with pytest.raises(ValueError):
            with db.transaction():
                db.insert({'discard': 'middle'})
                with db.transaction():
                    db.insert({'discard': 'inner-success'})
                raise ValueError()
        db.insert({'keep': 'after'})
        assert backend.writes == []
    assert db.all() == [{'keep': 'outer'}, {'keep': 'after'}]
    assert len(backend.writes) == 1

def test_R12_inner_success_outer_failure():
    db = new_db(storage=Counter)
    table = db.table('retain')
    table.insert({'nested': [6]})
    backend = Counter.last
    backend.writes.clear()
    with pytest.raises(ArithmeticError):
        with db.transaction():
            with db.transaction():
                table.update(lambda doc: doc['nested'].append(7))
                db.drop_table('retain')
                db.table('new').insert({'x': 1})
            raise ArithmeticError()
    assert table.all() == [{'nested': [6]}]
    assert db.tables() == {'retain'} and backend.writes == []

def test_R13_cached_inner_query_and_ids():
    db = new_db(storage=MemoryStorage)
    table = db.table('q')
    table.insert({'kind': 'original'})
    with db.transaction():
        with pytest.raises(ValueError):
            with db.transaction():
                table.update({'kind': 'discarded'})
                assert table.search(Query().kind == 'discarded')
                table.insert({'kind': 'also-discarded'})
                raise ValueError()
        assert not table.search(Query().kind == 'discarded')
        assert table.search(Query().kind == 'original')
        table.insert({'kind': 'new'})
    assert len({d.doc_id for d in table.all()}) == 2
    assert sorted(d['kind'] for d in table.all()) == ['new', 'original']
