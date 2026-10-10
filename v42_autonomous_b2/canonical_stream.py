"""Stream the original cleaned JSON bytes without copying the full proof tree.

Only the B2 proof scope installs these adapters on certificate_box's digest
and atomic aliases. Scientific functions, original common helpers, Native
accounting and healthy immutable workers are unchanged.
"""
from pathlib import Path
import hashlib,json,os,uuid,weakref
import numpy as np
from v42_pr134_b1.common import write_lock,replace_file


class _Dict(dict):
    def __init__(self,source,memo):self.source,self.memo=source,memo
    def __len__(self):return len(self.source)
    def items(self):
        # Original clean uses string keys with first insertion order and the
        # last value on a collision. Index only this dictionary, not its tree.
        keys={str(k):k for k in self.source}
        for text,key in keys.items():yield text,_clean(self.source[key],self.memo)


class _List(list):
    def __init__(self,source,memo):self.source,self.memo=source,memo
    def __len__(self):return len(self.source)
    def __iter__(self):
        for value in self.source:yield _clean(value,self.memo)


def _clean(value,memo):
    if isinstance(value,(dict,tuple,list,np.ndarray)):
        prior=memo.get(id(value))
        if prior is not None:return prior
        result=(_Dict if isinstance(value,dict) else _List)(value,memo)
        memo[id(value)]=result
        return result
    if isinstance(value,np.generic):return _clean(value.item(),memo)
    if isinstance(value,Path):return str(value)
    if isinstance(value,float) and not np.isfinite(value):return str(value)
    return value


def chunks(value,*,canonical=False):
    memo=weakref.WeakValueDictionary()
    encoder=(json.JSONEncoder(sort_keys=True,separators=(',',':')) if canonical else
        json.JSONEncoder(ensure_ascii=False,indent=2,allow_nan=False))
    yield from encoder.iterencode(_clean(value,memo),_one_shot=False)


def digest(value):
    h=hashlib.sha256()
    for part in chunks(value,canonical=True):h.update(part.encode())
    return h.hexdigest()


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    with write_lock(path):
        try:
            with temp.open('w',encoding='utf8',newline='\n') as stream:
                pending=[];size=0
                for part in chunks(value):
                    pending.append(part);size+=len(part)
                    if size>=65536:stream.write(''.join(pending));pending=[];size=0
                if pending:stream.write(''.join(pending))
                stream.write('\n')
            replace_file(temp,path)
        finally:temp.unlink(missing_ok=True)
