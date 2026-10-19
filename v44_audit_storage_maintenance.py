"""Low priority, byte-verified transparent compression of closed raw audits.

No paths or file contents are removed. Exact duplicate removal is separately
gated by the requested May02 B3 completion boundary in r035.
"""
from pathlib import Path
from collections import deque
import ctypes,hashlib,json,os,sqlite3,subprocess,time
import psutil
from v44_actual_content_store import RAW_NAMES


def allocated(path):
    if os.name!='nt':return getattr(Path(path).stat(),'st_blocks',0)*512
    api=ctypes.windll.kernel32.GetCompressedFileSizeW
    api.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)];api.restype=ctypes.c_ulong
    high=ctypes.c_ulong(0);low=api(str(path),ctypes.byref(high))
    if low==0xffffffff:raise OSError('R036_ALLOCATION_READ_FAILED')
    return (high.value<<32)+low


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def fingerprint(path):
    s=Path(path).stat()
    return json.dumps([s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns])


def candidates(root,done,*,now=None,min_age=900):
    root=Path(root).resolve();now=time.time() if now is None else now
    found={}
    for directory,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
        if 'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json' not in files:continue
        for name in RAW_NAMES.intersection(files):
            p=Path(directory)/name
            try:
                if p.is_symlink():continue
                s=p.stat();key=fingerprint(p)
                if s.st_size<1024*1024 or now-s.st_mtime<min_age or key in done:continue
                found.setdefault((s.st_dev,s.st_ino),(s.st_size,p,key))
            except OSError:continue
    return sorted(found.values(),key=lambda r:r[0],reverse=True)


def compact(path,root):
    path=Path(path);path.resolve().relative_to(Path(root).resolve())
    if path.is_symlink() or path.name not in RAW_NAMES:raise ValueError('R036_CLOSED_RAW_PATH_REQUIRED')
    before_sha=sha(path);before=allocated(path)
    result=subprocess.run(['compact.exe','/C','/EXE:LZX','/F','/I','/Q',str(path)],
        capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'IDLE_PRIORITY_CLASS',0))
    after_sha=sha(path)
    if before_sha!=after_sha:raise ValueError('R036_TRANSPARENT_COMPRESSION_CONTENT_DRIFT:'+str(path))
    if result.returncode:return dict(PASS=False,bytes_released=0,error=result.stderr.decode('utf-8',errors='replace')[-500:])
    return dict(PASS=True,bytes_released=max(0,before-allocated(path)),sha256=after_sha)


def start(op):
    from v44.common import read,record,atomic,now
    from v44.locks import alive,process_identity
    lease=op.OPS/'R036_STORAGE_MAINTENANCE_LEASE.json'
    if lease.exists() and alive(read(lease)):return read(lease)
    import sys
    process=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-X','utf8','-u','-m',op.ENTRY,
        '--storage-maintenance','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parent,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'IDLE_PRIORITY_CLASS',0))
    return dict(pid=process.pid,starting=True)


def run(op):
    from v44.common import read,atomic,now
    from v44.locks import exclusive_lock,process_identity
    op.authority()
    process=psutil.Process();process.nice(psutil.IDLE_PRIORITY_CLASS)
    process.cpu_affinity([2] if psutil.cpu_count()>2 else [psutil.cpu_count()-1])
    try:process.ionice(psutil.IOPRIO_VERYLOW)
    except (AttributeError,psutil.Error,NotImplementedError):pass
    with exclusive_lock(op.OPS/'R036_STORAGE_MAINTENANCE.lock'):
        atomic(op.OPS/'R036_STORAGE_MAINTENANCE_LEASE.json',dict(UTC=now(),**process_identity()))
        db=sqlite3.connect(op.OPS/'R036_STORAGE_MAINTENANCE.sqlite3')
        db.execute('CREATE TABLE IF NOT EXISTS done (fingerprint TEXT PRIMARY KEY,path TEXT,sha TEXT,released INTEGER)')
        db.commit();last=0;errors=deque(maxlen=10)
        def status(phase):
            rows=db.execute('SELECT COUNT(*),COALESCE(SUM(released),0) FROM done').fetchone()
            atomic(op.OPS/'R036_STORAGE_MAINTENANCE_PROGRESS.json',dict(UTC=now(),**process_identity(),
                phase=phase,compressed_unique_files=rows[0],allocated_bytes_released=rows[1],
                deleted_paths=0,file_bytes_and_sha_preserved=True,errors=list(errors),
                priority='IDLE',CPU_affinity=process.cpu_affinity(),root=str(op.RAW_ROOT)))
        try:
            while True:
                op.authority()
                # Avoid overlapping the post-case duplicate pass or user stop.
                stop=op.OPS/'STOP_AUTONOMY.json'
                if stop.exists() and read(stop).get('user_stop'):
                    status('USER_STOP_PRESERVED');return
                if (op.CLEANUP_CASE/'RESULT.json').exists() and not (op.OPS/'R035_EXISTING_RAW_CLEANUP.json').exists():
                    status('WAITING_FOR_POST_B3_DUPLICATE_PASS');time.sleep(15);continue
                done={r[0] for r in db.execute('SELECT fingerprint FROM done')}
                work=candidates(op.RAW_ROOT,done)
                for size,path,key in work:
                    if stop.exists() and read(stop).get('user_stop'):
                        status('USER_STOP_PRESERVED');return
                    if (op.CLEANUP_CASE/'RESULT.json').exists() and not (op.OPS/'R035_EXISTING_RAW_CLEANUP.json').exists():break
                    try:
                        if fingerprint(path)!=key:continue
                        result=compact(path,op.RAW_ROOT)
                        if result['PASS']:
                            db.execute('INSERT OR REPLACE INTO done VALUES(?,?,?,?)',
                                (fingerprint(path),str(path),result['sha256'],result['bytes_released']));db.commit()
                        else:errors.append(dict(path=str(path),**result))
                    except OSError as error:errors.append(dict(path=str(path),error=repr(error)))
                    if time.monotonic()-last>5:status('COMPRESSING_CLOSED_AUDITS');last=time.monotonic()
                status('WAITING_FOR_NEW_CLOSED_AUDITS');time.sleep(30)
        except BaseException as error:
            errors.append(dict(error=repr(error)));status('ERROR');raise
        finally:db.close()
