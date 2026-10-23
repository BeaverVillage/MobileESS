"""One byte-verified preparation shared only by same-case K48 -> Joint."""
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
import hashlib,time
import numpy as np
from .stage_immutable_io import ImmutableRecords

CURRENT=ContextVar('V2_ADD_CASE_PREPARATION_CACHE',default=None)

def fingerprint(case):
    h=hashlib.sha256()
    h.update(repr(case.A.shape).encode())
    for a in (case.A.indptr,case.A.indices,case.A.data,*[case.d[k] for k in ('lower','upper','types','objective','rhs','sense','constant','names','row_names')]):
        a=np.ascontiguousarray(a);h.update(a.dtype.str.encode());h.update(memoryview(a).cast('B'))
    return h.hexdigest()

class Cache:
    def __init__(self):self.entry=None;self.stats=dict(stored=0,reused=0,verified_reuse_seconds=0.)
    def clear(self):
        if self.entry:self.entry['locks'].close()
        self.entry=None
    def remember(self,case,manifest):
        from .stage_common import record
        from v42_native.contracts import digest
        self.clear();locks=ImmutableRecords(r['path'] for r in manifest['files']+manifest['proof_files'])
        try:
            # Every source file must be protected before granting reuse. If
            # sharing permissions prevent that, keep the ordinary reload path.
            for row in manifest['files']+manifest['proof_files']:
                if not locks.locked(row['path']):locks.close();return
                if record(row['path'])!=row:raise ValueError('K48_PREPARATION_FILE_DRIFT')
            self.entry=dict(case=case,manifest_sha=digest(manifest),matrix_sha=fingerprint(case),locks=locks)
            self.stats['stored']+=1
        except BaseException:locks.close();raise
    def take(self,manifest,output):
        from v42_native.contracts import digest
        start=time.perf_counter();entry=self.entry
        if not entry:return None
        if digest(manifest)!=entry['manifest_sha']:self.clear();return None
        case=entry['case']
        if fingerprint(case)!=entry['matrix_sha'] or digest(case.identity)!=case.case_sha:raise ValueError('CACHED_PREPARATION_MUTATED')
        case.output=Path(output);case.output.mkdir(parents=True,exist_ok=True)
        self.stats['reused']+=1;self.stats['verified_reuse_seconds']+=time.perf_counter()-start
        return case

@contextmanager
def scope():
    cache=Cache();token=CURRENT.set(cache)
    try:yield cache
    finally:cache.clear();CURRENT.reset(token)

def remember(case,manifest):
    cache=CURRENT.get()
    if cache:cache.remember(case,manifest)

def take(manifest,output):
    cache=CURRENT.get()
    return cache.take(manifest,output) if cache else None

def clear():
    cache=CURRENT.get()
    if cache:cache.clear()
