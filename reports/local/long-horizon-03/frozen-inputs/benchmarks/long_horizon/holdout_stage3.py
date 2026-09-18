def test_R14_R15_backup_active_and_both_directions():
    db = new_db(storage=MemoryStorage)
    assert db.backup() == {}
    db.table('nested').insert({'box': {'items': [4]}})
    before = db.backup()
    before['nested']['1']['box']['items'].append(5)
    assert db.table('nested').all()[0]['box']['items'] == [4]
    snapshot = db.backup()
    with db.transaction():
        db.table('nested').update(lambda doc: doc['box']['items'].append(6))
        assert db.backup()['nested']['1']['box']['items'] == [4, 6]
    assert snapshot['nested']['1']['box']['items'] == [4]

def test_R16_restore_retained_handles_cache_and_ids():
    db = new_db(storage=MemoryStorage)
    table = db.table('same')
    table.insert_multiple([{'tag': 'old'}, {'tag': 'old2'}])
    assert table.search(Query().tag == 'old')
    source = {'same': {'17': {'tag': 'restored', 'a': [1]}}}
    db.restore(source)
    source['same']['17']['a'].append(9)
    assert not table.search(Query().tag == 'old')
    assert table.search(Query().tag == 'restored')[0]['a'] == [1]
    table.insert({'tag': 'later'})
    assert len({d.doc_id for d in table.all()}) == 2
    assert sorted(d['tag'] for d in table.all()) == ['later', 'restored']

@pytest.mark.parametrize('bad', [[], {'x': []}, {'x': {'1': []}}, {1: {}},
    {'x': {'0': {}}}, {'x': {'-2': {}}}, {'x': {'02': {}}}, {'x': {2: {}}},
    {'x': {'1': {'v': float('nan')}}}, {'x': {'1': {'v': float('inf')}}},
    {'x': {'1': {'v': {1, 2}}}}, {'x': {'1': {'v': {1: 'bad-key'}}}}])
def test_R17_reject_before_mutation(bad):
    db = new_db(storage=Counter)
    db.insert({'prior': [3]})
    backend = Counter.last
    previous = copy.deepcopy(backend.memory)
    backend.writes.clear()
    if isinstance(bad, dict):
        bad = {'valid-first': {'1': {'valid': True}}, **bad}
    with pytest.raises(ValueError):
        db.restore(bad)
    assert backend.memory == previous and backend.writes == []

def test_R18_inner_restore_rollback_then_outer_commit():
    db = new_db(storage=Counter)
    db.insert({'old': 1})
    backend = Counter.last
    backend.writes.clear()
    with db.transaction():
        db.insert({'outer': 2})
        parent = db.backup()
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.restore({})
                assert db.backup() == {}
                raise RuntimeError()
        assert db.backup() == parent
    assert len(backend.writes) == 1 and len(db) == 2

def test_R19_json_restore_reopen(tmp_path):
    path = tmp_path/'restored.json'
    with new_db(path) as db:
        db.insert({'remove': 1})
        db.restore({'archive': {'12': {'value': [5, 6]}}})
    with new_db(path) as db:
        assert db.backup() == {'archive': {'12': {'value': [5, 6]}}}
        db.restore({})
    with TinyDB(path) as db:
        assert db.tables() == set()
