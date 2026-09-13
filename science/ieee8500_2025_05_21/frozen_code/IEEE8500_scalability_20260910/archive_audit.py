import csv, hashlib, io, json, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ZIP = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\EPRI IEEE 123-bus canonical OpenDSS case\electricdss-code-r4173-trunk.zip')
PREFIX = 'electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/'
OUT = ROOT / 'audit'
OUT.mkdir(exist_ok=True)
sha = lambda b: hashlib.sha256(b).hexdigest()
before = hashlib.file_digest(ZIP.open('rb'), 'sha256').hexdigest()
hits, scans, other_archives, manifests = [], [], [], []

def scan(z, outer=''):
    infos = z.infolist()
    scans.append({'archive': outer or str(ZIP), 'entries': len(infos)})
    for i in infos:
        n = i.filename
        full = outer + '!/' + n if outer else n
        relevant = '8500' in n.lower() or Path(n).name.lower() in ('master-unbal.dss', 'unbalancedloads.dss')
        if relevant and not i.is_dir():
            hits.append({'internal_path': full, 'bytes': i.file_size, 'sha256': sha(z.read(i))})
        if n.lower().endswith('.zip') and not i.is_dir():
            try:
                with zipfile.ZipFile(io.BytesIO(z.read(i))) as sub:
                    scan(sub, full)
            except Exception as e:
                scans.append({'archive': full, 'error': repr(e)})
        elif n.lower().endswith(('.7z', '.tar', '.gz', '.rar')):
            other_archives.append(full)

with zipfile.ZipFile(ZIP, 'r') as z:
    scan(z)
    files = [i for i in z.infolist() if i.filename.startswith(PREFIX) and not i.is_dir()]
    if not any(i.filename == PREFIX + 'Master-unbal.dss' for i in files):
        raise SystemExit('IEEE8500_SOURCE_NOT_FOUND_IN_LOCAL_ARCHIVE')
    for i in files:
        rel = Path(i.filename[len(PREFIX):])
        dest = (ROOT / 'source' / rel).resolve()
        assert dest.is_relative_to((ROOT / 'source').resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = z.read(i)
        if dest.exists():
            assert dest.read_bytes() == data
        else:
            dest.write_bytes(data)
        manifests.append({'internal_path': i.filename, 'relative_path': rel.as_posix(), 'bytes':len(data), 'sha256':sha(data)})
for name, rows in [('archive_ieee8500_matches', hits), ('source_manifest', manifests)]:
    (OUT / (name+'.json')).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    with (OUT / (name+'.csv')).open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
after = hashlib.file_digest(ZIP.open('rb'), 'sha256').hexdigest()
summary = {'status':'IEEE8500_SOURCE_FOUND_IN_LOCAL_ARCHIVE', 'zip':str(ZIP), 'zip_sha256_before':before, 'zip_sha256_after':after, 'zip_unchanged':before==after, 'selected_prefix':PREFIX, 'extracted_files':len(manifests), 'matching_files':len(hits), 'zip_scans':scans, 'non_zip_embedded_archives_not_opened':other_archives, 'selection_reason':'Top-level Distrib/IEEETestCases canonical distribution, not Version7/Version8 or training variants.'}
(OUT/'archive_audit.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('zip_scans','non_zip_embedded_archives_not_opened')},ensure_ascii=True,indent=2))
print('ZIP containers scanned:', len(scans), 'non-ZIP embedded containers:',len(other_archives))
