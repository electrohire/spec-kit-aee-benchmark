from copy import deepcopy

class BatchWriter:
    def __init__(self, db):
        self.db = db
        self.tokens = {}

    def _simulate(self, operations):
        if not isinstance(operations, list):
            raise ValueError('operations must be a list')
        storage = deepcopy(self.db.storage.read() or {})
        docs = {int(k): deepcopy(v) for k, v in storage.get('_default', {}).items()}
        table = self.db.table('_default')
        next_id = table._next_id if table._next_id is not None else max(docs, default=0) + 1
        inserted = []
        for op in operations:
            if not isinstance(op, dict):
                raise ValueError('operation must be a dict')
            if op.get('op') == 'insert' and set(op) == {'op', 'document'} and isinstance(op['document'], dict):
                docs[next_id] = deepcopy(op['document'])
                inserted.append(next_id)
                next_id += 1
            elif op.get('op') == 'remove' and set(op) == {'op', 'doc_id'}:
                ident = op['doc_id']
                if type(ident) is not int or ident <= 0 or ident not in docs:
                    raise ValueError('invalid or missing document id')
                del docs[ident]
            else:
                raise ValueError('invalid operation')
        storage['_default'] = docs
        return storage, next_id, inserted

    def preview(self, operations):
        return self._simulate(operations)[2]

    def apply(self, operations, token=None):
        if token is not None and (not isinstance(token, str) or not token):
            raise ValueError('invalid token')
        if token is not None and token in self.tokens:
            previous, result = self.tokens[token]
            if previous != operations:
                raise ValueError('token conflict')
            return deepcopy(result)
        storage, next_id, inserted = self._simulate(operations)
        self.db.storage.write(storage)
        for table in self.db._tables.values():
            table.clear_cache()
        self.db.table('_default')._next_id = next_id
        if token is not None:
            self.tokens[token] = (deepcopy(operations), deepcopy(inserted))
        return inserted
