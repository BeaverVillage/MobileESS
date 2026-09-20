"""Publish only new export deliverables; never touch campaign source files."""
from pathlib import Path
import json,hashlib,shutil,os,time
OUT=Path(__file__).parent;DEL=OUT/'deliverables'
TARGET=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
archive=read(DEL/'IEEE123_B3_2ROUND_MAY2025_ARCHIVE_MANIFEST.json');assert archive['integrity_test']['status']=='PASS'
csvcheck=read(OUT/'CSV_VERIFIED.json');assert csvcheck['status']=='PASS'
name=archive['archive_filename'];assert sha(DEL/name)==archive['sha256']
folder='IEEE123_2ROUND_PAPER_CSV';csvmanifest=read(DEL/folder/'PAPER_CSV_SOURCE_MANIFEST.json')
assert csvmanifest['source_authority_consistency']=='PASS'
for r in csvcheck['files']:assert sha(DEL/folder/r['filename'])==r['sha256']
assert TARGET.is_dir()
targets=[TARGET/name,TARGET/'IEEE123_B3_2ROUND_MAY2025_ARCHIVE_MANIFEST.json',TARGET/folder]
assert all(not p.exists() for p in targets),'REFUSE_TO_OVERWRITE_EXISTING_OUTPUTS'
assert shutil.disk_usage(TARGET).free>archive['total_size_bytes']+100_000_000
(TARGET/folder).mkdir()
receipts=[]
def copy(src,dst,expected):
 assert dst.parent==TARGET or dst.parent==TARGET/folder
 with src.open('rb') as source,dst.open('xb') as target:
  shutil.copyfileobj(source,target,16*1024*1024);target.flush();os.fsync(target.fileno())
 assert sha(dst)==expected,(str(dst),'PUBLISHED_HASH_MISMATCH')
 receipts.append(dict(path=str(dst),bytes=dst.stat().st_size,sha256=expected))
 print('COPIED_VERIFIED',dst.name,flush=True)
for r in csvcheck['files']:copy(DEL/folder/r['filename'],TARGET/folder/r['filename'],r['sha256'])
copy(DEL/folder/'PAPER_CSV_SOURCE_MANIFEST.json',TARGET/folder/'PAPER_CSV_SOURCE_MANIFEST.json',sha(DEL/folder/'PAPER_CSV_SOURCE_MANIFEST.json'))
copy(DEL/name,TARGET/name,archive['sha256'])
plan=read(OUT/'ARCHIVE_PLAN.json')
for anchor in sorted({Path(r['source_path']).anchor for r in plan['files']}):
 paths=[str(Path(r['source_path']).parent) for r in plan['files'] if Path(r['source_path']).anchor==anchor]
 if anchor!='D:\\':archive['source_root_paths'].append(os.path.commonpath(paths))
archive['source_root_paths'].append(str(OUT.parent/'april_regeneration'))
archive['stage_file_coverage']=read(OUT/'PACKAGING_COVERAGE.json')
archive.update(archive_path=str(TARGET/name),paper_csv_folder=str(TARGET/folder),published_at=time.time(),destination_copy_SHA256_verified=True,
 calibration_state_note='FROZEN_CALIBRATION_STATES.parquet is included only because its SHA exactly matches the original; regenerated historical sensitivity tables are excluded.')
dst=TARGET/'IEEE123_B3_2ROUND_MAY2025_ARCHIVE_MANIFEST.json'
with dst.open('x',encoding='utf-8') as f:json.dump(archive,f,ensure_ascii=False,indent=2)
receipts.append(dict(path=str(dst),bytes=dst.stat().st_size,sha256=sha(dst)))
assert len(list((TARGET/folder).iterdir()))==9
result=dict(status='PASS',archive_integrity='PASS',source_authority_consistency='PASS',published_files=receipts,csv_dimensions=csvcheck['files'],missing=csvmanifest['missing_or_unsupported'],original_campaign_files_modified=0)
(OUT/'PUBLISHED_VERIFICATION.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print('PUBLISH_PASS',str(TARGET),flush=True)
