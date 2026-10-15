"""Lossless delivery of large new diagnostic evidence; originals stay intact."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    manifest=OUT/'LOSSLESS_EVIDENCE_DELIVERY.json'
    if manifest.exists():raise FileExistsError('DELIVERY_MANIFEST_MUST_NOT_OVERWRITE')
    records=[]
    for source in sorted(OUT.rglob('*')):
        if not source.is_file() or source.suffix=='.gz' or source.stat().st_size<=2_000_000:continue
        # Only new generated receipts are packaged. No historical Source/Raw
        # path is moved, deleted, normalized or replaced.
        if source.suffix not in {'.json','.csv','.xml','.log'}:
            raise ValueError('UNREVIEWED_LARGE_DELIVERY_FILE:'+str(source))
        target=source.with_name(source.name+'.gz')
        if target.exists():raise FileExistsError(target)
        before=sha(source)
        with source.open('rb') as raw,target.open('wb') as packed:
            with gzip.GzipFile(filename='',fileobj=packed,mode='wb',mtime=0,compresslevel=9) as compressed:
                shutil.copyfileobj(raw,compressed)
        with gzip.open(target,'rb') as stream:restored=hashlib.file_digest(stream,'sha256').hexdigest()
        assert before==restored==sha(source)
        assert target.stat().st_size<95_000_000
        records.append(dict(original_path=source.relative_to(ROOT).as_posix(),original_bytes=source.stat().st_size,
            original_sha256=before,delivery_path=target.relative_to(ROOT).as_posix(),
            delivery_bytes=target.stat().st_size,delivery_sha256=sha(target),decompressed_byte_identical=True))
    required_plain={str((OUT/n).relative_to(ROOT).as_posix()) for n in
        ('C0_UNKNOWN_ALLOCATION_EVENTS.csv','C1_UNKNOWN_ALLOCATION_EVENTS.csv')}
    report=dict(status='PASS',scope='NEW_ISOLATED_DIAGNOSTIC_ONLY',compression='DETERMINISTIC_GZIP_MTIME_0',
        local_plain_originals_preserved=True,historical_Source_Raw_Receipt_modified=False,
        all_compressed_records=records,required_named_reports_committed_plain=sorted(required_plain),
        staging_excludes_only_original_path_entries=[r for r in records if r['original_path'] not in required_plain])
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status='PASS',files=len(records),original_bytes=sum(r['original_bytes'] for r in records),
        delivery_bytes=sum(r['delivery_bytes'] for r in records)),indent=2))


if __name__=='__main__':main()
