"""Exact-byte audit storage: original receipt paths, one physical copy per value.

Only finalized raw candidate records enter this store. Replacements always use
new temporary files/links and os.replace; a shared inode is never overwritten.
"""
from contextlib import contextmanager
import hashlib,inspect,json,linecache,os,re,sqlite3,textwrap,uuid
from pathlib import Path
from unittest.mock import patch


RAW_NAMES={'VOLTAGE_CONTROL_ACTUAL_SLOTS.json','VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json'}


class ExactContentStore:
    def __init__(self,root,index=None):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.index=Path(index) if index else self.root/'EXACT_RAW_CONTENT.sqlite3'
        self.db=sqlite3.connect(self.index,timeout=30)
        self.db.execute('CREATE TABLE IF NOT EXISTS raw (sha TEXT,size INTEGER,path TEXT,PRIMARY KEY(sha,size))')
        self.db.commit()
        self.counts=dict(new_files=0,shared_files=0,already_shared=0,logical_duplicate_bytes=0,
            existing_allocated_bytes_released=0,fallback_files=0,collision_or_stale_entries=0)

    def close(self):self.db.close()

    def _path(self,path):
        if Path(path).is_symlink():raise ValueError('R035_RAW_AUDIT_SYMLINK_FORBIDDEN')
        p=Path(path).resolve()
        p.relative_to(self.root)
        if p.name not in RAW_NAMES:raise ValueError('R035_RAW_AUDIT_PATH_REQUIRED')
        if p.is_symlink():raise ValueError('R035_RAW_AUDIT_SYMLINK_FORBIDDEN')
        return p

    def write(self,path,data,*,adopt_existing=False):
        p=self._path(path)
        sha=hashlib.sha256(data).hexdigest();size=len(data)
        p.parent.mkdir(parents=True,exist_ok=True)
        temporary=p.with_name(p.name+'.'+uuid.uuid4().hex+'.store.tmp')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute('SELECT path FROM raw WHERE sha=? AND size=?',(sha,size)).fetchone()
            canonical=None
            if row:
                try:
                    candidate=self._path(row[0])
                    # Hash is an index, never the final equality test.
                    if candidate.stat().st_size==size and candidate.read_bytes()==data:canonical=candidate
                except (OSError,ValueError):pass
                if canonical is None:self.counts['collision_or_stale_entries']+=1
            if canonical is not None:
                if p.exists() and os.path.samefile(p,canonical):
                    self.counts['already_shared']+=1
                else:
                    try:
                        released=0
                        if adopt_existing and p.exists() and p.stat().st_nlink==1:
                            if os.name=='nt':
                                import ctypes
                                api=ctypes.windll.kernel32.GetCompressedFileSizeW
                                api.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
                                api.restype=ctypes.c_ulong
                                high=ctypes.c_ulong(0);low=api(str(p),ctypes.byref(high))
                                if low!=0xffffffff:released=(high.value<<32)+low
                            else:released=getattr(p.stat(),'st_blocks',0)*512
                        os.link(canonical,temporary)
                        os.replace(temporary,p)
                        self.counts['shared_files']+=1
                        self.counts['logical_duplicate_bytes']+=size
                        self.counts['existing_allocated_bytes_released']+=released
                    except OSError:
                        # Unsupported links keep the exact complete raw file.
                        temporary.unlink(missing_ok=True)
                        if not adopt_existing:
                            temporary.write_bytes(data);os.replace(temporary,p)
                        self.db.execute('INSERT OR REPLACE INTO raw VALUES(?,?,?)',(sha,size,str(p)))
                        self.counts['fallback_files']+=1
            else:
                if adopt_existing:
                    if not p.exists() or p.read_bytes()!=data:raise ValueError('R035_EXISTING_RAW_CHANGED')
                else:
                    temporary.write_bytes(data);os.replace(temporary,p)
                self.db.execute('INSERT OR REPLACE INTO raw VALUES(?,?,?)',(sha,size,str(p)))
                self.counts['new_files']+=1
            self.db.commit()
        except BaseException:
            self.db.rollback();raise
        finally:temporary.unlink(missing_ok=True)
        return len(data)

    def write_text(self,path,text,encoding='utf8'):
        # Match Path.write_text's Windows newline translation and character count.
        data=text.replace('\n',os.linesep).encode(encoding)
        self.write(path,data)
        return len(text)


def writer(function,encoding,store,original):
    adapted=original(function,encoding)
    source=textwrap.dedent(inspect.getsource(adapted))
    for name in ('path','events'):
        source,count=re.subn(r'(?m)^(\s*)'+name+r'\.write_text\(',
            lambda m:m[1]+'_r035_write('+name+',',source)
        if count!=1:raise ValueError('R035_RAW_PERSIST_SOURCE_DRIFT')
    filename=__file__+'.persist.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(adapted.__globals__,_r035_write=store.write_text)
    exec(compile(source,filename,'exec'),ns)
    return ns[adapted.__name__]


@contextmanager
def install(root):
    from v44_recovery_r029 import current_ac_performance as performance
    active=[None]
    original=performance.audit_writer
    scope=performance.current_probe_scope
    def factory(function,encoding):
        if active[0] is None:active[0]=ExactContentStore(root)
        return writer(function,encoding,active[0],original)
    @contextmanager
    def measured(oracle,rows,encoding):
        with scope(oracle,rows,encoding) as stats:yield stats
        request=performance._actual_request.get()
        if request:
            from v44.common import atomic,now
            atomic(Path(request['case_root'])/'R035_EXACT_RAW_STORAGE.json',dict(UTC=now(),
                counts=active[0].counts if active[0] else {},raw_paths_and_bytes_unchanged=True,independent_Fresh_changed=False))
    # The yielded accessor is also useful to isolated validation callers.
    with patch.object(performance,'audit_writer',factory),patch.object(performance,'current_probe_scope',measured):
        try:yield active
        finally:
            if active[0] is not None:active[0].close()


def cleanup(root,*,progress=None):
    """Caller must prove the requested case and its coordinator have exited."""
    store=ExactContentStore(root)
    checked=0;preserved=[]
    try:
        for directory,dirs,files in os.walk(store.root):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
            if 'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json' not in files:continue
            manifest=Path(directory)/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json'
            try:
                audit=json.loads(manifest.read_text(encoding='utf-8-sig'))
                for key in ('slots_receipt','physical_solve_events_receipt'):
                    receipt=audit[key];path=store._path(receipt['path'])
                    data=path.read_bytes()
                    if len(data)!=receipt['bytes'] or hashlib.sha256(data).hexdigest()!=receipt['sha256']:
                        raise ValueError('R035_EXISTING_AUDIT_RECEIPT_DRIFT:'+str(path))
                    store.write(path,data,adopt_existing=True);checked+=1
                if progress and checked%100==0:progress(dict(checked_files=checked,**store.counts))
            except (KeyError,json.JSONDecodeError,OSError,ValueError) as error:
                # Partial, unavailable or inconsistent records are kept in place.
                preserved.append(dict(manifest=str(manifest),error=repr(error)))
                continue
        result=dict(PASS=True,checked_files=checked,preserved_unverified=preserved,**store.counts)
        if progress:progress(result)
        return result
    finally:store.close()
