"""Package the completed May campaign without modifying scientific results."""
from pathlib import Path
import datetime, hashlib, io, json, os, tarfile, time

ROOT = Path(r'\\?\C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
DEST = Path(r'\\?\C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터')
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
NAME = 'V41R4_May2025_31days_124policies_raw_' + STAMP
BASE = 'V41R4_May2025_raw'
SOURCES = [
    'frozen_artifacts/v41r4_may/loop_wall_v4',
    'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1',
    'frozen_artifacts/v41r4_restoration_revision_v1',
    'frozen_artifacts/v41r4_selective_actual_revision_v1',
    'frozen_artifacts/v41r4',
]
CODE = ['restoration_revision_v1.py', 'restoration_revision_reader_r1.py',
        'selective_actual_revision_v1.py', 'restoration_revision_final_audit.py',
        'restoration_revision_background.py', 'restoration_revision_resume_env_r1.py']

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

class HashReader:
    def __init__(self, stream):
        self.stream, self.hash = stream, hashlib.sha256()
    def read(self, size=-1):
        data = self.stream.read(size)
        self.hash.update(data)
        return data

def main():
    revision = ROOT / SOURCES[2]
    audit = read(revision / 'FINAL_AUDIT.json')
    finished = read(revision / 'background/CAMPAIGN_FINISHED.json')
    assert audit['status'] == finished['status'] == 'COMPLETE'
    assert audit['counts']['total_accepted'] == 124 and not audit['pending']
    assert sha(revision / 'FINAL_AUDIT.json') == finished['final_audit']['sha256']
    index = []
    for day in range(1,32):
        date = f'2025-05-{day:02d}'
        for policy in ('B0','B1','B2','B3'):
            accept = read(revision / date / policy / 'ACCEPTANCE.json')
            assert accept['status'] == 'PASS'
            actual_root = SOURCES[3] if date == '2025-05-31' and policy in ('B2','B3') else SOURCES[1]
            actual = f'{actual_root}/replays/{date}/{policy}'
            receipt = read(ROOT / actual / 'CANDIDATE_RECEIPT.json')
            assert receipt['status'] == 'COMPLETE'
            index.append(dict(day=date, policy=policy, final_actual=actual,
                acceptance=f'{SOURCES[2]}/{date}/{policy}/ACCEPTANCE.json',
                accepted_joint_original_path=accept['new_joint']['path'],
                accepted_joint_sha256=accept['new_joint']['sha256']))
    DEST.mkdir(parents=True, exist_ok=True)
    final = DEST / (NAME + '.tar.gz')
    partial = DEST / (NAME + '.tar.gz.partial')
    assert not final.exists() and not partial.exists()
    paths, excluded = [], []
    for relative in SOURCES:
        for folder, dirs, files in os.walk(ROOT / relative, followlinks=True):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            for name in sorted(files):
                path = Path(folder)/name
                rel = path.relative_to(ROOT).as_posix()
                if name.endswith(('.tmp','.lock','.pyc')) or name.startswith('MONITOR_'):
                    excluded.append(rel)
                else:
                    paths.append((path, rel, path.stat().st_size))
    for name in CODE:
        path = ROOT/name
        paths.append((path, name, path.stat().st_size))
    total = sum(s for _,_,s in paths)
    print(json.dumps(dict(stage='PACKING', files=len(paths), raw_bytes=total, output=str(final)), ensure_ascii=False), flush=True)
    manifest = []
    last = time.monotonic()
    packed = 0
    with tarfile.open(partial, 'w:gz', compresslevel=1, dereference=True) as archive:
        def metadata(name, data):
            content = data.encode('utf-8')
            info = tarfile.TarInfo(BASE + '/' + name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for i,(path,rel,size) in enumerate(paths,1):
            before = path.stat()
            info = archive.gettarinfo(str(path), BASE+'/'+rel)
            assert info.isfile(), rel
            with path.open('rb') as f:
                reader = HashReader(f)
                archive.addfile(info, reader)
            after = path.stat()
            assert (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns), ('SOURCE_CHANGED',rel)
            manifest.append(dict(path=rel, bytes=size, sha256=reader.hash.hexdigest()))
            packed += size
            if time.monotonic()-last > 20:
                print(json.dumps(dict(stage='PACKING', files=i, total_files=len(paths), percent=round(100*packed/total,1))),flush=True)
                last=time.monotonic()
        metadata('FINAL_RESULT_INDEX.json',json.dumps(index,indent=2))
        metadata('FILE_MANIFEST.json',json.dumps(manifest,indent=2))
        metadata('PACKAGE_INFO.json',json.dumps(dict(campaign='May 2025',days=31,policy_days=124,
            counts=audit['counts'], source_root=str(ROOT),sources=SOURCES,created_at=STAMP,
            regular_files=len(paths),raw_bytes=total,excluded_operational_files=excluded,
            junctions='Directory junctions materialized as regular files; no external link dependency.',
            note='Original absolute provenance paths are preserved inside raw receipts. Use FINAL_RESULT_INDEX.json for final accepted results. Historical FAIL and older Actual artifacts are diagnostic evidence, not final results.'),indent=2))
        metadata('README.txt','May 2025 V41R4 complete raw results: 31 days x B0/B1/B2/B3 = 124.\n'
            'FINAL_RESULT_INDEX.json identifies the final Actual result for every policy-day.\n'
            'May31 B2/B3 use v41r4_selective_actual_revision_v1; the other 122 use v41r4_actual_eta95_qsafe_robust_v2_perf1.\n'
            'DA/Fresh source artifacts, restoration evidence, Actual inputs/trajectories/OpenDSS arrays, and final audit are included.\n'
            'Historical failure artifacts remain unchanged and must not be confused with final accepted outcomes.\n'
            'Directory junctions have been replaced with their actual file contents. Original provenance paths in JSON are retained.\n'
            'FILE_MANIFEST.json records SHA-256 for all source files. Archive verification hashes every archived source file.\n')
    print(json.dumps(dict(stage='VERIFYING', compressed_bytes=partial.stat().st_size)),flush=True)
    expected = {BASE+'/'+m['path']:m for m in manifest}
    verified=0
    with tarfile.open(partial,'r|gz') as archive:
        for member in archive:
            assert member.isfile(), member.name
            if member.name in expected:
                h=hashlib.sha256()
                with archive.extractfile(member) as f:
                    for block in iter(lambda:f.read(4*1024*1024),b''):
                        h.update(block)
                m=expected.pop(member.name)
                assert member.size==m['bytes'] and h.hexdigest()==m['sha256'], member.name
                verified+=1
            if time.monotonic()-last>20:
                print(json.dumps(dict(stage='VERIFYING',files=verified,total_files=len(manifest))),flush=True)
                last=time.monotonic()
    assert not expected
    archive_hash=sha(partial)
    partial.rename(final)
    (DEST/(NAME+'.tar.gz.sha256')).write_text(archive_hash+'  '+final.name+'\n',encoding='utf-8')
    verification=dict(status='VERIFIED',archive=str(final),sha256=archive_hash,compressed_bytes=final.stat().st_size,
        source_files=len(manifest),verified_files=verified,policy_days=124,raw_bytes=total)
    (DEST/(NAME+'.verification.json')).write_text(json.dumps(verification,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(verification,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
