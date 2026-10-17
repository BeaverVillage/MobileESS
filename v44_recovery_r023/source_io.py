"""Rehash every pinned source read, using OS protected handles and mappings.

No digest memo: every known record hashes the whole current mapped content.
File write/delete sharing is denied; parent delete sharing is denied so a
canonical path cannot be rebound. Unknown/mutable paths use original IO.
"""
from contextlib import contextmanager
from types import FunctionType
from pathlib import Path
import os,sys,hashlib,mmap,time,ctypes
from ctypes import wintypes as w

class FileInformation(ctypes.Structure):
    _fields_=[('attributes',w.DWORD),('creation',w.FILETIME),('access',w.FILETIME),('write',w.FILETIME),
        ('volume',w.DWORD),('size_high',w.DWORD),('size_low',w.DWORD),('links',w.DWORD),('index_high',w.DWORD),('index_low',w.DWORD)]

def api():
    if sys.platform!='win32':raise PermissionError('R023_WINDOWS_OS_SOURCE_LEASE_REQUIRED')
    lib=ctypes.WinDLL('kernel32',use_last_error=True)
    lib.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];lib.CreateFileW.restype=w.HANDLE
    lib.CloseHandle.argtypes=[w.HANDLE];lib.CloseHandle.restype=w.BOOL
    lib.GetFileInformationByHandle.argtypes=[w.HANDLE,ctypes.POINTER(FileInformation)];lib.GetFileInformationByHandle.restype=w.BOOL
    return lib

def open_handle(lib,path,*,directory=False):
    handle=lib.CreateFileW(str(path),0x80 if directory else 0x80000000,3 if directory else 1,None,3,0x02000000 if directory else 0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    return handle

def information(lib,handle):
    value=FileInformation()
    if not lib.GetFileInformationByHandle(handle,ctypes.byref(value)):raise ctypes.WinError(ctypes.get_last_error())
    return value

def dispatch(path):
    return _r023_source_record_dispatch(path)

class SourceIO:
    def __init__(self,rows):
        self.lib=api();self.rows=rows;self.files={};self.directories=[]
        self.lookups=0;self.hashed_bytes=0;self.fallbacks=0
        self.elapsed_seconds=0.;self.closed=False

    def open(self):
        import msvcrt
        parents=set()
        for row in self.rows:
            p=Path(row['path'])
            if not p.is_absolute() or str(p.resolve()).casefold()!=str(p).casefold():
                raise PermissionError('R023_CANONICAL_SOURCE_PATH_REQUIRED')
            parents.update(parent for parent in p.parents if parent!=Path(parent.anchor))
        try:
            for directory in sorted(parents,key=lambda p:(len(p.parts),str(p))):
                self.directories.append(open_handle(self.lib,directory,directory=True))
            for row in self.rows:
                p=Path(row['path']);key=os.path.normcase(str(p))
                if key in self.files:
                    if self.files[key]['row']!=row:raise PermissionError('R023_DUPLICATE_SOURCE_IDENTITY_CONFLICT')
                    continue
                handle=open_handle(self.lib,p)
                try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
                except BaseException:self.lib.CloseHandle(handle);raise
                stream=os.fdopen(fd,'rb');mapping=None
                try:
                    meta=information(self.lib,handle);size=(meta.size_high<<32)|meta.size_low
                    mapping=mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) if size else None
                    sha=hashlib.sha256(mapping if mapping is not None else b'').hexdigest()
                    if size!=row['bytes'] or sha!=row['sha256']:raise ValueError('SOURCE_SHA_DRIFT:'+str(p))
                    self.files[key]=dict(stream=stream,mapping=mapping,handle=handle,row=dict(row),
                        identity=(meta.volume,meta.index_high,meta.index_low))
                except BaseException:
                    if mapping is not None:mapping.close()
                    stream.close();raise
        except BaseException:self.close();raise
        return self

    def record(self,path):
        began=time.perf_counter();key=os.path.normcase(os.fspath(path));entry=self.files.get(key)
        if entry is None:
            self.fallbacks+=1
            return self.original(path)
        if self.closed:raise PermissionError('R023_CLOSED_SOURCE_LEASE')
        try:
            meta=information(self.lib,entry['handle']);size=(meta.size_high<<32)|meta.size_low
            if (meta.volume,meta.index_high,meta.index_low)!=entry['identity'] or size!=entry['row']['bytes']:
                raise ValueError('SOURCE_SHA_DRIFT:'+str(path))
            # Always recompute current bytes. A pre-existing writable mapping
            # (despite its file handle being closed) therefore cannot hide a
            # change from source verification.
            sha=hashlib.sha256(entry['mapping'] if entry['mapping'] is not None else b'').hexdigest()
            self.lookups+=1;self.hashed_bytes+=size
            return dict(path=entry['row']['path'],bytes=size,sha256=sha)
        finally:self.elapsed_seconds+=time.perf_counter()-began

    def report(self):
        return dict(source_count=len(self.files),record_lookups=self.lookups,full_content_hashes=self.lookups,
            bytes_hashed=self.hashed_bytes,unknown_path_original_IO_calls=self.fallbacks,
            mapped_record_seconds=self.elapsed_seconds,digest_memoization=False,
            original_Source_SHA_validation_not_skipped=True,write_delete_sharing_denied=True,parent_delete_sharing_denied=True)

    def close(self):
        for entry in reversed(list(self.files.values())):
            if entry['mapping'] is not None:entry['mapping'].close()
            entry['stream'].close()
        self.files.clear()
        for handle in reversed(self.directories):self.lib.CloseHandle(handle)
        self.directories.clear();self.closed=True

@contextmanager
def install(rows,receipt=None):
    import v44.common as common
    function=common.record;old=function.__code__
    original=FunctionType(old,function.__globals__,function.__name__,function.__defaults__,function.__closure__)
    key='_r023_source_record_dispatch'
    if key in function.__globals__:raise PermissionError('R023_DUPLICATE_SOURCE_IO_SCOPE')
    pool=SourceIO(rows).open();pool.original=original
    function.__globals__[key]=pool.record;function.__code__=dispatch.__code__
    try:yield pool
    finally:
        report=pool.report();function.__code__=old;function.__globals__.pop(key,None);pool.close()
        if receipt is not None and Path(receipt).parent.exists():
            from v44.common import atomic,now
            atomic(Path(receipt),dict(UTC=now(),**report,all_source_handles_closed=True))
