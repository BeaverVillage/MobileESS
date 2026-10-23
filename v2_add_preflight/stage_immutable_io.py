"""Same-case hash reuse while Windows denies writes and replacement."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
from unittest.mock import patch
import ctypes,os,time
from ctypes import wintypes
from functools import lru_cache

@lru_cache(maxsize=1)
def file_api():
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    create=k.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    close=k.CloseHandle;close.argtypes=[wintypes.HANDLE]
    return k,create,close

class ImmutableRecords:
    def __init__(self,paths):
        self.allowed={str(Path(p).resolve()).casefold() for p in paths}
        self.values={};self.handles=[];self.hits=0;self.misses=0;self.avoided_bytes=0
    def locked(self,path):
        if os.name!='nt':return False
        k,create,close=file_api()
        handle=create(str(Path(path).resolve()),0x80000000,1,None,3,0x80,None)
        if handle==wintypes.HANDLE(-1).value:return False
        self.handles.append(handle);return True
    def wrap(self,original):
        def record(path):
            key=str(Path(path).resolve()).casefold()
            if key not in self.allowed:return original(path)
            # Include producer identity: original record functions can encode
            # equivalent file paths differently. Never rewrite that schema.
            identity=(key,id(original),str(Path(path)))
            if identity in self.values:
                value=self.values[identity];self.hits+=1;self.avoided_bytes+=value['bytes'];return dict(value)
            self.misses+=1
            if not self.locked(path):return original(path)
            value=original(path);self.values[identity]=dict(value);return value
        return record
    def close(self):
        if self.handles:
            k,create,close=file_api()
            for handle in self.handles:close(handle)
        self.handles.clear();self.values.clear()
    def report(self):
        return dict(hash_reuses=self.hits,initial_hashes=self.misses,avoided_rehashed_bytes=self.avoided_bytes,
            scope='ONE_EXACT_CURRENT_CASE',byte_identity_locked_by_OS=True,arrays_or_solver_results_cached=False)

@contextmanager
def scope(case,modules):
    import sys
    from .stage_common import record as source_record
    from .prestart_execution import atomic
    paths=list(case._immutable_file_stats)
    cache=ImmutableRecords(paths)
    # Patch actual imported aliases, preserving each producer's path schema.
    targets=list(modules.values())+[m for name,m in list(sys.modules.items()) if name.startswith('v2_add_preflight.')]
    seen=set();wrappers={}
    try:
        with ExitStack() as stack:
            for module in targets:
                if id(module) in seen or not hasattr(module,'record'):continue
                seen.add(id(module));original=module.record
                wrappers.setdefault(id(original),cache.wrap(original))
                stack.enter_context(patch.object(module,'record',wrappers[id(original)]))
            yield cache
    finally:
        report=cache.report();cache.close()
        atomic(case.output/'IMMUTABLE_CASE_IO_PROFILE.json',report)
