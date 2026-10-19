"""Migrate unreferenced legacy candidate raw into verified lossless row archives.

All externally referenced candidate folders remain ordinary files. Old audit
metadata is retained unchanged; migration maps allow exact original Raw export.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,sqlite3,subprocess,time
import v44_recovery_r029
from v44_recovery_r037 import operations as op
from v44_audit_chunk_store import ChunkStore,SCHEMA,MARKER
from v44.common import read,record,verify,atomic,now
from v44_audit_storage_maintenance import allocated

ROOT=op.RAW_ROOT.resolve()
PLAN=op.OPS/'LEGACY_RAW_ARCHIVE_PLAN.json'
CATALOG=op.OPS/'LEGACY_RAW_ARCHIVE.sqlite3'
PROGRESS=op.OPS/'LEGACY_RAW_ARCHIVE_PROGRESS.json'
AUTH=op.OPS/'LEGACY_RAW_ARCHIVE_AUTHORIZATION.json'
KEY=re.compile(rb'AC_PROBES[/\\]+(20\d\d-\d\d-\d\d)[/\\]+(B[0-3])[/\\]+([a-f0-9]{32})(?:_REFERENCE)?',re.I)
FLAT=re.compile(rb'\{[^{}]{0,8192}\}')
SCIENCE_NAMES={'CURRENT_AC_RECEIPTS.json','PREFIX_CERTIFICATES.json','FRESH_SVR12_TIME_AC.json',
               'SIMULATOR_PRIVATE_CARRYOUT.json','RESULT.json','request.json'}
ROW_START=re.compile(rb'\{(?:"PASS":(?:true|false),"arm":"B[0-3]","capcontrol":|"completed":(?:true|false),"controls":)')
TRAJECTORY=re.compile(rb'"frozen_trajectory_SHA":("(?:[^"\\]|\\.)*")')
_durable_chunks=set()

def durable_archive(manifest,store,mapping):
    value=read(manifest)
    for row in value['rows']:
        key=row['sha256']
        if key in _durable_chunks:continue
        with store.chunk_path(key).open('r+b') as f:os.fsync(f.fileno())
        _durable_chunks.add(key)
    for path in (manifest,mapping):
        with Path(path).open('r+b') as f:os.fsync(f.fileno())

def keys(data):
    return {'/'.join((m[1].decode(),m[2].decode().upper(),m[3].decode().lower())) for m in KEY.finditer(data)}

def references(path):
    path=Path(path);found=set();overlap=b''
    with path.open('rb') as f:
        while block:=f.read(8*1024*1024):
            data=overlap+block
            # Unknown reference styles and plain path lists are protected too.
            found.update(keys(data))
            overlap=data[-16384:]
    return found

def inventory():
    found={}
    base=ROOT/'AC_PROBES'
    for directory,dirs,files in os.walk(base):
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
        if 'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json' not in files:continue
        path=Path(directory);rel=path.relative_to(base)
        if len(rel.parts)!=3 or not re.fullmatch('[a-f0-9]{32}',rel.parts[-1]):continue
        found['/'.join(rel.parts)]=str(path)
    return found

def plan(roots=None):
    roots=roots or [Path('D:/MobileESS_V44'),Path('D:/v44_may01_07_prepare_20261016/docs'),
        Path('D:/v44_r022_rowgen_20261017'),
        Path('C:/Users/kjw39/OneDrive/\ubb38\uc11c/ChatGPT/Mobile ESS 2'),
        Path('C:/Users/kjw39/OneDrive/\ubb38\uc11c/ChatGPT/Mobile ESS')]
    command=['rg','-l','--hidden','--no-ignore','-F','AC_PROBES',
        '-g','*.json','-g','*.jsonl','-g','*.py','-g','*.md','-g','*.txt','-g','*.log',
        '-g','*.html','-g','*.csv','-g','*.tex','-g','*.xml','-g','*.toml','-g','*.yaml','-g','*.ipynb',
        '-g','!**/.git/**','-g','!**/runtime/v43_planning_svr12_actual_v1/AC_AUDIT/**',
        '-g','!**/LEGACY_RAW_ARCHIVE*']+[str(p) for p in roots if p.exists()]
    result=subprocess.run(command,capture_output=True)
    if result.returncode not in (0,1):raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[:1000])
    files=[Path(p) for p in result.stdout.decode('utf-8').splitlines()]
    protected=set();scanned=[]
    for i,path in enumerate(files):
        if path.is_relative_to(ROOT):continue
        # This exact, hash-sealed administrative inventory merely enumerates
        # duplicate candidates; it is not an execution/validation consumer.
        inventory_report=Path('D:/MobileESS_V44/development/EXACT_AUDIT_DUPLICATE_PLAN_20261018.json')
        if path==inventory_report and record(path)==read(op.OPS/'R035_CHANGE_AND_VALIDATION.json')['duplicate_plan']:
            continue
        found=references(path)
        if found:protected.update(found);scanned.append(dict(path=str(path),candidate_references=len(found)))
        if i%100==0:atomic(op.OPS/'LEGACY_RAW_REFERENCE_SCAN_PROGRESS.json',dict(UTC=now(),files_scanned=i,total_matching_files=len(files),protected_candidates=len(protected)))
    candidates=inventory();eligible=[dict(key=k,path=p) for k,p in candidates.items() if k not in protected]
    value=dict(UTC=now(),PASS=True,root=str(ROOT),scan_roots=[str(p) for p in roots],
        total_candidates=len(candidates),protected_candidates=len(set(candidates)&protected),
        eligible_candidates=eligible,reference_sources=scanned,
        rule='Never migrate any candidate referenced by external execution/verification receipts or source/doc text',
        migration_executed=False)
    atomic(PLAN,value)
    print(dict(total_candidates=len(candidates),protected_candidates=value['protected_candidates'],eligible_candidates=len(eligible),matching_external_files=len(files)),flush=True)
    return value

def check_ids():
    """Also protect IDs referenced without a full path or with different casing."""
    value=read(PLAN);by_id={r['key'].rsplit('/',1)[1]:r for r in value['eligible_candidates']}
    pattern=op.OPS/'LEGACY_RAW_UUID_PATTERNS.txt';pattern.write_text('\n'.join(by_id),encoding='ascii')
    command=['rg','-l','-i','--hidden','--no-ignore','-F','-f',str(pattern),
        '-g','*.json','-g','*.jsonl','-g','*.py','-g','*.md','-g','*.txt','-g','*.log',
        '-g','*.html','-g','*.csv','-g','*.tex','-g','*.xml','-g','*.toml','-g','*.yaml','-g','*.ipynb',
        '-g','!**/.git/**','-g','!**/runtime/v43_planning_svr12_actual_v1/AC_AUDIT/**',
        '-g','!**/LEGACY_RAW_*','-g','!**/EXACT_AUDIT_DUPLICATE_PLAN_20261018.json']+value['scan_roots']
    result=subprocess.run(command,capture_output=True)
    if result.returncode not in (0,1):raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[:1000])
    protect=set();sources=[];token=re.compile(rb'(?<![a-f0-9])([a-f0-9]{32})(?![a-f0-9])',re.I)
    for name in result.stdout.decode('utf-8').splitlines():
        path=Path(name)
        if path.is_relative_to(ROOT):continue
        found=set();tail=b''
        with path.open('rb') as f:
            while block:=f.read(8*1024*1024):
                data=tail+block
                for m in token.finditer(data):
                    key=m[1].decode().lower()
                    if key in by_id:found.add(key)
                tail=data[-128:]
        if found:protect.update(found);sources.append(dict(path=name,ids=sorted(found)))
    value['eligible_candidates']=[row for row in value['eligible_candidates'] if row['key'].rsplit('/',1)[1] not in protect]
    value['protected_candidates']+=len(protect);value['additional_id_reference_sources']=sources
    value['second_reference_scan_complete']=True;value['UTC']=now();atomic(PLAN,value)
    atomic(op.OPS/'LEGACY_RAW_UUID_REFERENCE_AUDIT.json',dict(UTC=now(),PASS=True,additional_protected=len(protect),sources=sources))
    print(dict(additional_protected=len(protect),eligible_candidates=len(value['eligible_candidates'])),flush=True)

def guard(require_dedup=True):
    stop=read(op.OPS/'STOP_AUTONOMY.json')
    if stop.get('user_dispatch_pause') is not True or not op.previous.ready():
        raise PermissionError('ARCHIVE_REQUIRES_USER_HOLD_AND_NO_LIVE_CASE_OR_COORDINATOR')
    result=read(op.previous.CLEANUP_CASE/'RESULT.json')
    if type(result.get('PASS')) is not bool:raise PermissionError('ARCHIVE_REQUIRES_TERMINAL_B3')
    if require_dedup and not (op.OPS/'R035_EXISTING_RAW_CLEANUP.json').exists():raise PermissionError('ARCHIVE_WAITS_FOR_EXACT_DUPLICATE_PASS')

def pack_legacy(path,raw,store):
    """Split original canonical bytes directly; never round floating point data."""
    newline=b'\r\n' if raw.endswith(b'\r\n') else b'\n' if raw.endswith(b'\n') else b''
    body=raw[:-len(newline)] if newline else raw
    if not body.startswith(b'[') or not body.endswith(b']'):raise ValueError('ARCHIVE_JSON_ARRAY_REQUIRED')
    starts=[m.start() for m in ROW_START.finditer(body)]
    if not body[1:-1]:parts=[]
    elif starts and starts[0]==1 and all(body[i-1:i]==b',' for i in starts[1:]):
        parts=[body[start:(starts[n+1]-1 if n+1<len(starts) else len(body)-1)] for n,start in enumerate(starts)]
    else:parts=[body[1:-1]] # Unknown older layouts remain losslessly reconstructable.
    if b'['+b','.join(parts)+b']'+newline!=raw:raise ValueError('ARCHIVE_RAW_SPLIT_DRIFT')
    tokens=[];descriptors=[]
    for part in parts:
        matches=list(TRAJECTORY.finditer(part));token=None
        if len(matches)==1 and MARKER not in part:
            token=matches[0][1].decode('utf-8');m=matches[0]
            part=part[:m.start(1)]+b'null'+part[m.end(1):]
        descriptor=store.put(part)
        if token is not None:
            if token not in tokens:tokens.append(token)
            descriptor['trajectory_token']=tokens.index(token)
        descriptors.append(descriptor)
    manifest=dict(schema=SCHEMA,layout='COMPLETE_RAW_RECONSTRUCTABLE_FROM_SHARED_ROWS',
        raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),encoding='utf-8',
        newline=newline.decode('ascii'),trajectory_tokens=tokens,rows=descriptors)
    atomic(path,manifest)
    store.counts['logical_raw_bytes']+=len(raw);store.counts['manifest_bytes']+=Path(path).stat().st_size
    return manifest

def migrate_one(folder,store,db,*,allow_delete=True):
    folder=Path(folder).resolve();folder.relative_to(ROOT/'AC_PROBES')
    if folder.is_symlink():raise ValueError('ARCHIVE_SYMLINK_FORBIDDEN')
    audit=read(folder/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json')
    result=dict(converted_files=0,deleted_legacy_copies=0,allocated_bytes_released=0,logical_bytes_archived=0)
    for key in ('slots_receipt','physical_solve_events_receipt'):
        receipt=audit[key];path=Path(receipt['path']).resolve()
        if path.parent!=folder or path.is_symlink():raise ValueError('ARCHIVE_RECEIPT_PATH_DRIFT')
        if path.name not in ('VOLTAGE_CONTROL_ACTUAL_SLOTS.json','VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json'):
            raise ValueError('ARCHIVE_LEGACY_RAW_FILENAME_REQUIRED')
        row=db.execute('SELECT manifest FROM archived WHERE legacy=?',(str(path),)).fetchone()
        if not path.exists():
            if row:
                raw=store.restore(row[0])
                if hashlib.sha256(raw).hexdigest()==receipt['sha256'] and len(raw)==receipt['bytes']:
                    db.execute("UPDATE archived SET state='ARCHIVED' WHERE legacy=?",(str(path),));db.commit();continue
            raise ValueError('ARCHIVE_MISSING_UNRECOVERABLE_LEGACY_RAW')
        raw=path.read_bytes()
        if len(raw)!=receipt['bytes'] or hashlib.sha256(raw).hexdigest()!=receipt['sha256']:
            raise ValueError('ARCHIVE_ORIGINAL_RECEIPT_DRIFT')
        manifest=path.with_name(path.stem+'_MANIFEST.json')
        if not row or not Path(row[0]).exists():pack_legacy(manifest,raw,store)
        if store.restore(manifest)!=raw:raise ValueError('ARCHIVE_EXACT_ROUNDTRIP_REQUIRED')
        stat=path.stat();before=allocated(path) if stat.st_nlink==1 else 0
        db.execute('INSERT OR REPLACE INTO archived VALUES(?,?,?,?,?,?,?)',
            (str(path),str(manifest),receipt['sha256'],receipt['bytes'],now(),0,'PREPARED'));db.commit()
        mappings=dict(schema='V44_LEGACY_RAW_ARCHIVE_MAP_V1',original_metadata_unchanged=True,
            entries=[dict(legacy=r[0],manifest=r[1],sha256=r[2],bytes=r[3]) for r in db.execute(
                'SELECT legacy,manifest,sha,bytes FROM archived WHERE legacy LIKE ?',(str(folder)+'%',))])
        atomic(folder/'LEGACY_RAW_ARCHIVE_MAP.json',mappings)
        result['converted_files']+=1;result['logical_bytes_archived']+=len(raw)
        if allow_delete:
            guard()
            durable_archive(manifest,store,folder/'LEGACY_RAW_ARCHIVE_MAP.json')
            if (path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)!=(stat.st_ino,stat.st_size,stat.st_mtime_ns):
                raise ValueError('ARCHIVE_LEGACY_CHANGED_BEFORE_DELETE')
            db.execute("UPDATE archived SET released=?,state='VERIFIED_READY_TO_DELETE' WHERE legacy=?",(before,str(path)));db.commit()
            # Checked absolute file stays inside the requested audit root.
            path.resolve().relative_to(ROOT/'AC_PROBES');path.unlink()
            db.execute("UPDATE archived SET state='ARCHIVED' WHERE legacy=?",(str(path),));db.commit()
            result['deleted_legacy_copies']+=1;result['allocated_bytes_released']+=before
    return result

def migrate(prepare=False):
    guard(require_dedup=not prepare);value=read(PLAN)
    authorization=read(AUTH);verify(authorization['sources']+[authorization['plan'],authorization['revision_authorization']])
    if authorization['plan']!=record(PLAN):raise ValueError('ARCHIVE_AUTHORIZED_PLAN_DRIFT')
    if not prepare and not value.get('second_reference_scan_complete'):raise ValueError('ARCHIVE_SECOND_REFERENCE_SCAN_REQUIRED')
    if value['root']!=str(ROOT):raise ValueError('ARCHIVE_PLAN_ROOT_DRIFT')
    store=ChunkStore(ROOT)
    db=sqlite3.connect(CATALOG)
    db.execute('CREATE TABLE IF NOT EXISTS archived (legacy TEXT PRIMARY KEY,manifest TEXT,sha TEXT,bytes INTEGER,UTC TEXT,released INTEGER,state TEXT)');db.commit()
    total=dict(checked_candidates=0,converted_files=0,deleted_legacy_copies=0,allocated_bytes_released=0,logical_bytes_archived=0)
    errors=[];last=0
    try:
        for candidate in value['eligible_candidates']:
            guard(require_dedup=not prepare)
            try:
                row=migrate_one(candidate['path'],store,db,allow_delete=not prepare)
                for k,v in row.items():total[k]+=v
            except (ValueError,OSError) as error:errors.append(dict(path=candidate['path'],error=repr(error)))
            total['checked_candidates']+=1
            if time.monotonic()-last>5:
                atomic(op.OPS/'LEGACY_RAW_ARCHIVE_PREPARATION_PROGRESS.json' if prepare else PROGRESS,dict(UTC=now(),phase='PREPARING_LOSSLESS_SHARED_ROWS_NO_DELETION' if prepare else 'MIGRATING_VERIFIED_UNREFERENCED_LEGACY_RAW',**total,
                    new_storage=store.counts,errors=errors[-20:],next_date_started=False));last=time.monotonic()
        result=dict(UTC=now(),PASS=not errors,phase='COMPLETE',**total,new_storage=store.counts,
            preserved_candidates=value['protected_candidates'],errors=errors,next_date_started=False)
        if not prepare:
            result['catalog_archived_files'],result['catalog_allocated_bytes_released']=db.execute("SELECT COUNT(*),COALESCE(SUM(released),0) FROM archived WHERE state='ARCHIVED'").fetchone()
        atomic(op.OPS/'LEGACY_RAW_ARCHIVE_PREPARATION_PROGRESS.json' if prepare else PROGRESS,result)
        atomic(op.OPS/('LEGACY_RAW_ARCHIVE_PREPARATION_RESULT.json' if prepare else 'LEGACY_RAW_ARCHIVE_RESULT.json'),result)
        print(result,flush=True)
    finally:db.close()

def restore_legacy(legacy,output=None):
    legacy=Path(legacy).resolve();legacy.relative_to(ROOT)
    with sqlite3.connect(CATALOG) as db:
        row=db.execute('SELECT manifest,sha,bytes FROM archived WHERE legacy=?',(str(legacy),)).fetchone()
    if not row:raise KeyError('LEGACY_RAW_NOT_ARCHIVED')
    raw=ChunkStore(ROOT).restore(row[0])
    if len(raw)!=row[2] or hashlib.sha256(raw).hexdigest()!=row[1]:raise ValueError('LEGACY_ARCHIVE_RECEIPT_DRIFT')
    target=Path(output) if output else legacy
    with target.open('xb') as f:f.write(raw)
    return record(target)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','check-ids','prepare','migrate','restore']);p.add_argument('--legacy',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.mode=='plan':plan()
    elif a.mode=='check-ids':check_ids()
    elif a.mode=='migrate':migrate()
    elif a.mode=='prepare':migrate(prepare=True)
    else:print(restore_legacy(a.legacy,a.output))
