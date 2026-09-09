"""Read-only archive intake. Never resolves archived provenance paths on the host."""
import hashlib, json, os, tarfile, time
from pathlib import Path, PurePosixPath

def longpath(p):
    p = str(Path(p).absolute())
    return Path(p if p.startswith('\\\\?\\') else '\\\\?\\' + p) if os.name == 'nt' else Path(p)

class HashReader:
    def __init__(self, f): self.f, self.h = f, hashlib.sha256()
    def read(self, n=-1):
        b=self.f.read(n); self.h.update(b); return b

def intake(archive, cache, report):
    archive=Path(archive); cache=longpath(cache); report=Path(report)
    cache.mkdir(parents=True,exist_ok=False)
    before=archive.stat(); entries=[]; hashes={}; last=time.monotonic(); size=0
    with archive.open('rb') as raw:
        reader=HashReader(raw)
        with tarfile.open(fileobj=reader,mode='r|gz') as tf:
            for member in tf:
                rel=PurePosixPath(member.name)
                if rel.is_absolute() or '..' in rel.parts or any(':' in p for p in rel.parts): raise ValueError('UNSAFE_ARCHIVE_PATH')
                if not member.isfile(): raise ValueError('NONREGULAR_ARCHIVE_MEMBER:'+member.name)
                if member.name in hashes: raise ValueError('DUPLICATE_ARCHIVE_MEMBER:'+member.name)
                dest=cache.joinpath(*rel.parts); dest.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256()
                with tf.extractfile(member) as src, dest.open('xb') as dst:
                    for block in iter(lambda:src.read(4*1024*1024),b''):
                        dst.write(block);h.update(block)
                hashes[member.name]=h.hexdigest();size+=member.size
                entries.append(dict(path=member.name,bytes=member.size,sha256=h.hexdigest()))
                if time.monotonic()-last>20:
                    print(json.dumps(dict(stage='ARCHIVE_INTAKE',files=len(entries),uncompressed_GB=round(size/1e9,2))),flush=True);last=time.monotonic()
        while reader.read(4*1024*1024):pass
        archive_sha=reader.h.hexdigest()
    after=archive.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'ARCHIVE_CHANGED'
    roots={PurePosixPath(e['path']).parts[0] for e in entries};assert len(roots)==1
    prefix=roots.pop();source=cache/prefix
    def read(n):return json.loads((source/n).read_text(encoding='utf-8-sig'))
    fm=read('FILE_MANIFEST.json')
    for row in fm: assert hashes[prefix+'/'+row['path']]==row['sha256'],row['path']
    ix=read('FINAL_RESULT_INDEX.json'); units=[(r['day'],r['policy']) for r in ix]
    expected={(f'2025-05-{d:02d}',p) for d in range(1,32) for p in ('B0','B1','B2','B3')}
    assert len(units)==len(set(units))==124 and set(units)==expected,'INCOMPLETE_FINAL_INDEX'
    availability=[]
    for row in ix:
        day,p=row['day'],row['policy'];a=read(row['acceptance']); ac=row['final_actual']
        receipt=read(ac+'/CANDIDATE_RECEIPT.json');assert a['status']=='PASS' and receipt['status']=='COMPLETE'
        da=f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{p}/dayahead'
        fresh=row['acceptance'].rsplit('/',1)[0]+'/accepted_fresh' if a['old_primary_fresh']=='FAIL' else da+'/fresh'
        post=ac+('/CONTROL_COMMON_BINDING' if p in ('B0','B1') else '/ETA95_QSAFE_ACTUAL')
        fields=dict(day=day,policy=p,Fresh=(source/fresh/'OPENDSS_PHASE_ARRAYS.npz').exists(),
            Actual=(source/post/'OPENDSS_PHASE_ARRAYS.npz').exists(),
            Q_safe_or_control=(source/post/'COMPLETE.json').exists() or (source/ac/'COMPLETE.json').exists(),
            objective=(source/da/'optimization/OBJECTIVE_LEDGER.json').exists(),
            MESS=(source/da/'FROZEN_MESS_COMMANDS.json').exists(), AIDC=(source/da/'FROZEN_JOINT_DECISION.json').exists(),
            ML=(source/da/'ml/ML_SNAPSHOT.json').exists())
        assert all(fields[k] for k in ('Fresh','Actual','Q_safe_or_control','objective','MESS','AIDC')),fields
        availability.append(fields)
    result=dict(status='ARCHIVE_INTAKE_PASS',source_archive=str(archive),source_archive_SHA256=archive_sha,
        source_archive_size_bytes=before.st_size,archive_file_count=len(entries),raw_bytes=size,
        cache=str(cache),source_extracted=str(source),detected_days=31,detected_policy_days=124,
        policy_counts={p:sum(u[1]==p for u in units) for p in ('B0','B1','B2','B3')},
        missing_policy_days=[],duplicate_policy_days=[],verified_source_files=len(fm),availability=availability,
        external_workspace_read_count=0,archive_mtime_ns=before.st_mtime_ns)
    (cache/'INVENTORY.json').write_text(json.dumps(entries),encoding='utf-8')
    report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='availability'}),flush=True)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--cache',required=True);p.add_argument('--report',required=True)
    a=p.parse_args();intake(a.archive,a.cache,a.report)
