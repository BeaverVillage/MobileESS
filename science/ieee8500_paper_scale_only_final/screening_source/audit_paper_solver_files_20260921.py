"""Read-only archive versus disk audit; never imports production modules."""
import collections, hashlib, json, tarfile, time
from pathlib import Path

ROOT = Path(r'D:\ChatGPT\Mobile ESS 2')
HERE = Path(__file__).resolve().parent
PAPER = ROOT/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
CURRENT = HERE/'full_production_paper_BG055200_AIDC240_MESS200'
OUT = CURRENT/'diagnostic_attempts'/('PAPER_FILE_AND_MILP_AUDIT_'+time.strftime('%Y%m%d_%H%M%S'))
OUT.mkdir(parents=True, exist_ok=False)
ARCHIVE = Path(json.loads((HERE/'RAW_ARCHIVE_AUDIT.json').read_text(encoding='utf-8'))['archive'])
PREFIX = PAPER.relative_to(ROOT).as_posix()+'/'
def sha(p):
    return hashlib.file_digest(Path(p).open('rb'), 'sha256').hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(name, data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('OUTPUT',OUT,flush=True)
records=[]
start=time.perf_counter()
with tarfile.open(ARCHIVE,'r|gz') as tf:
    for m in tf:
        if not m.isfile() or not m.name.startswith(PREFIX): continue
        rel=m.name[len(PREFIX):]
        # Hash source code, B2 solve receipts/cache, and input identity manifests.
        take=(rel.endswith('.py') or (rel.startswith('B2/') and rel.endswith('.json'))
              or ('/' not in rel and rel.endswith('.json')))
        if not take: continue
        blob=tf.extractfile(m).read()
        h=hashlib.sha256(blob).hexdigest(); disk=ROOT/m.name
        dh=sha(disk) if disk.is_file() else None
        records.append(dict(member=m.name,bytes=m.size,archive_sha256=h,disk_sha256=dh,
                            status='MATCH' if dh==h else 'MISSING' if dh is None else 'DIFFERENT'))
        if rel in ('mess_runtime.py','mess_grid8500.py','B2/ORIGINAL_SELECTED_BEFORE_EXACT.json'):
            (OUT/('ARCHIVE_'+rel.replace('/','_'))).write_bytes(blob)
write('ARCHIVE_FILE_AUDIT.json',dict(archive=str(ARCHIVE),archive_bytes=ARCHIVE.stat().st_size,
      seconds=time.perf_counter()-start,counts=dict(collections.Counter(r['status'] for r in records)),files=records))
print('ARCHIVE_COUNTS',dict(collections.Counter(r['status'] for r in records)),flush=True)
receipts=read(OUT/'ARCHIVE_B2_ORIGINAL_SELECTED_BEFORE_EXACT.json')
keys=('mess_id','solver_status','full_gap','full_MILP_wallclock_seconds','full_planning_objective','full_best_bound','move_binary_count','preferred_MIPStart_loaded')
vehicles=[{k:v[k] for k in keys if k in v} for v in receipts['selected_state']['vehicles']]
write('PAPER_SELECTED_SOLVES.json',vehicles)
checks=[]
for entry in read(PAPER/'INHERITED_SOURCE_FREEZE.json')['files']:
    p=Path(entry['path']); observed=sha(p) if p.is_file() else None
    checks.append(dict(path=str(p),expected=entry['sha256'],observed=observed,status='MATCH' if observed==entry['sha256'] else 'MISSING' if observed is None else 'DIFFERENT'))
for entry in read(CURRENT/'CODE_DIFF.json'):
    for key in ('source','override'):
        p=Path(entry[key]); observed=sha(p) if p.is_file() else None
        checks.append(dict(module=entry['module'],role=key,path=str(p),expected=entry[key+'_sha256'],observed=observed,status='MATCH' if observed==entry[key+'_sha256'] else 'MISSING' if observed is None else 'DIFFERENT'))
write('SOURCE_MANIFEST_AUDIT.json',checks)
print('MANIFEST_COUNTS',dict(collections.Counter(r['status'] for r in checks)),flush=True)
print('EXCEPTIONS',json.dumps([r for r in checks if r['status']!='MATCH'],ensure_ascii=False),flush=True)
sources=[]
for p in PAPER.glob('*.py'):
    q=CURRENT/p.name
    sources.append(dict(file=p.name,paper_sha256=sha(p),current_sha256=sha(q) if q.is_file() else None,
                        status='MATCH' if q.is_file() and sha(p)==sha(q) else 'MISSING' if not q.is_file() else 'CHANGED'))
write('CURRENT_SOURCE_PRESENCE.json',sources)
print('CURRENT_SOURCE_COUNTS',dict(collections.Counter(r['status'] for r in sources)),flush=True)
for root,label in ((PAPER,'paper'),(CURRENT,'current')):
    cache=root/'B2/candidate_cache';fs=list(cache.rglob('*'))
    print('CACHE',label,sum(p.is_file() for p in fs),sum(p.stat().st_size for p in fs if p.is_file()),flush=True)
print('DONE',OUT,flush=True)
