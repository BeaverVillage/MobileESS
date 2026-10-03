"""Exact hashed Planning read allowlist with before/after audits.

Trusted stage adapters use this broker and audit hook. Opaque native file I/O is
not a permitted adapter capability; subprocess/native external readers are never
approved by this contract. This is a dependency firewall, not an OS sandbox.
"""
import os,sys,json,hashlib,threading,re,gc,io
from pathlib import Path
from datetime import datetime
from .authority import INPUT_KINDS,FORBIDDEN_KINDS,file_sha
_active=None
_installed=False
def active():return _active is not None
def forbidden_path(path):
    text=str(path).replace('\\','/').lower()
    # Phase directory/file components; an unrelated ancestor containing a word
    # such as test_raw_actual_reads is not itself an Actual artifact.
    return any(re.match(r'^(actual|fresh[_-](ac|opendss)|realized[_-]d_?day)($|[_. -])',part) for part in text.split('/'))
def _hook(event,args):
    guard=_active
    if guard is None:return
    if event=='open':
        path,mode,flags=args
        if isinstance(path,int):raise PermissionError('PLANNING_FD_READ_BYPASS_FORBIDDEN')
        try:resolved=Path(os.fsdecode(path)).resolve()
        except Exception:raise PermissionError('UNRESOLVABLE_PLANNING_READ')
        writing=(mode is not None and any(c in mode for c in 'wax+')) or bool(flags and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        row=dict(event=event,path=str(resolved),writing=writing,allowed=not writing and resolved in guard.allowed)
        guard.attempts.append(row)
        if not row['allowed']:raise PermissionError('PLANNING_DEPENDENCY_NOT_WHITELISTED:'+str(resolved))
    elif event in ('subprocess.Popen','os.system','os.posix_spawn','ctypes.dlopen','ctypes.dlsym','mmap.__new__'):
        guard.attempts.append(dict(event=event,allowed=False));raise PermissionError('PLANNING_OPAQUE_IO_BYPASS_FORBIDDEN')

class PlanningReads:
    def __init__(self,entries,*,issue_time):
        self.entries=entries;self.issue_time=datetime.fromisoformat(issue_time);self.allowed=set();self.attempts=[];self.loaded={};self.before={};self.after={};self.receipt=None
        for entry in entries:
            if entry['kind'] not in INPUT_KINDS or entry.get('producer_phase') not in ('D1','PLANNING'):raise PermissionError('ACTUAL_TO_PLANNING_PROVENANCE')
            if entry.get('kind') in ('D1_SOURCE','FORECAST','RUNTIME_CC4'):
                if not entry.get('known_at_issue') or datetime.fromisoformat(entry['available_at'])>self.issue_time:raise PermissionError('FUTURE_DDAY_INFORMATION')
            if forbidden_path(entry['path']):raise PermissionError('ACTUAL_TO_PLANNING_PATH')
            resolved=Path(entry['path']).resolve(strict=True)
            if forbidden_path(resolved):raise PermissionError('ACTUAL_TO_PLANNING_RESOLVED_PATH')
            if resolved in self.allowed:raise ValueError('DUPLICATE_PLANNING_DEPENDENCY')
            self.allowed.add(resolved)
    def __enter__(self):
        global _active,_installed
        if _active is not None:raise RuntimeError('PLANNING_READ_SCOPE_OVERLAP')
        for handle in gc.get_objects():
            if isinstance(handle,io.IOBase) and not handle.closed and isinstance(getattr(handle,'name',None),(str,bytes)) and forbidden_path(os.fsdecode(handle.name)):
                raise PermissionError('PREOPENED_ACTUAL_STREAM_FORBIDDEN')
        # All source hashes and resolved identities are checked before stage entry.
        for entry in self.entries:
            p=Path(entry['path']).resolve(strict=True);digest=file_sha(p)
            if digest!=entry['sha256']:raise PermissionError('PLANNING_SOURCE_SHA_MISMATCH')
            self.before[str(p)]=digest
        if not _installed:sys.addaudithook(_hook);_installed=True
        self.original_thread_start=threading.Thread.start
        self.original_fd_readers={name:getattr(os,name) for name in ('read','pread','readv') if hasattr(os,name)}
        def no_fd(*args,**kwargs):
            self.attempts.append(dict(event='os.fd_read',allowed=False));raise PermissionError('PLANNING_PREOPENED_FD_READ_FORBIDDEN')
        def no_thread(*args,**kwargs):
            self.attempts.append(dict(event='threading.Thread.start',allowed=False));raise PermissionError('PLANNING_BACKGROUND_READER_FORBIDDEN')
        threading.Thread.start=no_thread
        for name in self.original_fd_readers:setattr(os,name,no_fd)
        _active=self
        try:
            for entry in self.entries:
                p=Path(entry['path']).resolve(strict=True);self.loaded[entry['key']]=json.loads(p.read_text(encoding='utf8'))
        except BaseException:
            _active=None;threading.Thread.start=self.original_thread_start
            for name,value in self.original_fd_readers.items():setattr(os,name,value)
            raise
        return self
    def __exit__(self,typ,value,tb):
        global _active
        _active=None;threading.Thread.start=self.original_thread_start
        for name,reader in self.original_fd_readers.items():setattr(os,name,reader)
        for entry in self.entries:
            p=Path(entry['path']).resolve(strict=True);self.after[str(p)]=file_sha(p)
        unchanged=self.before==self.after
        denied=[r for r in self.attempts if not r['allowed']]
        self.receipt=dict(PASS=typ is None and unchanged and not denied,source_before=self.before,source_after=self.after,read_attempts=self.attempts,Actual_reads=0,Fresh_AC_reads=0,source_bytes_unchanged=unchanged,opaque_native_IO_permitted=False,adapter_capability='Broker JSON read API and Python audited opens only; preopened/native/subprocess readers are forbidden.',Planning_inputs_only=True)
        if not unchanged:raise PermissionError('PLANNING_SOURCE_CHANGED_DURING_STAGE')
        if denied and typ is None:raise PermissionError('PLANNING_DENIED_READ_ATTEMPT_CAUGHT_BY_ADAPTER')
        return False
