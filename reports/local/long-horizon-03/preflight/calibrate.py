from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('scripts').resolve()))
from long_horizon import Sandbox,grade
from benchmark_runner.store import write_json
root=Path('artifacts/long-assets'); image=(root/'image-id.txt').read_text().strip(); upstream=Path('artifacts/tinydb-upstream')
reference='''
from copy import deepcopy
from contextlib import contextmanager
import math
from .database import TinyDB
class Proxy:
    def __init__(self, backend): self.backend=backend; self.frames=[]
    def read(self): return deepcopy(self.frames[-1] if self.frames else self.backend.read())
    def write(self, data):
        if self.frames: self.frames[-1]=deepcopy(data)
        else: self.backend.write(deepcopy(data))
    def close(self): self.backend.close()
class TransactionalTinyDB(TinyDB):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._storage=Proxy(self._storage); self._retained=[]
    def table(self,name,**kwargs):
        table=super().table(name,**kwargs)
        if not any(t is table for t in self._retained): self._retained.append(table)
        return table
    def _invalidate(self):
        for t in self._retained: t.clear_cache(); t._next_id=None
    @contextmanager
    def transaction(self):
        REJECT_NESTED
        self.storage.frames.append(deepcopy(self.storage.read() or {}))
        try: yield self
        except BaseException:
            self.storage.frames.pop(); self._invalidate(); raise
        else:
            data=self.storage.frames.pop(); self.storage.write(data); self._invalidate()
    def backup(self):
        return {name:{str(key):deepcopy(doc) for key,doc in table.items()} for name,table in (self.storage.read() or {}).items()}
    def restore(self,data):
        def valid(v):
            if v is None or type(v) in (bool,int,str): return
            if type(v) is float and math.isfinite(v): return
            if type(v) is list:
                for x in v: valid(x)
                return
            if type(v) is dict and all(type(k) is str for k in v):
                for x in v.values(): valid(x)
                return
            raise ValueError('not finite JSON')
        if type(data) is not dict: raise ValueError('mapping required')
        for name,table in data.items():
            if type(name) is not str or type(table) is not dict: raise ValueError('table')
            for key,doc in table.items():
                if type(key) is not str or not key.isascii() or not key.isdecimal() or int(key)<=0 or str(int(key))!=key or type(doc) is not dict: raise ValueError('document')
                valid(doc)
        self.storage.write(deepcopy(data)); self._invalidate()
'''
results=[]
with Sandbox(image,upstream) as s:
    s.snapshot(root/'untouched.tar')
    init=(upstream/'tinydb/__init__.py').read_bytes()+b'\nfrom .transactions import TransactionalTinyDB\n'
    for stage in (1,2,3):
        code=reference.replace('REJECT_NESTED',"if self.storage.frames: raise RuntimeError('nested')" if stage==1 else 'pass')
        s.put({'tinydb/transactions.py':code.encode(),'tinydb/__init__.py':init})
        snap=root/f'calibration-stage{stage}.tar'; s.snapshot(snap)
        for kind in ('public','holdout'):
            g=grade(snap,stage,kind,image,upstream)
            results.append(dict(stage=stage,kind=kind,**g)); print(stage,kind,g['passed'],g['test_count'],flush=True)
            if not g['passed']: print(g['output'],flush=True)
negative=grade(root/'untouched.tar',1,'holdout',image,upstream)
write_json(root/'calibration.json',dict(positive=results,negative=negative))
assert all(r['passed'] for r in results) and not negative['passed']
