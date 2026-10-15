"""Lossless packaging and verification; original raw files stay in place."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
MANIFEST=OUT/'COMPRESSED_EVIDENCE_MANIFEST.json'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.verify:
        m=json.loads(MANIFEST.read_text(encoding='utf8'))
        for row in m['files']:
            p=ROOT/row['compressed_relative'];assert file_record(p)['sha256']==row['compressed']['sha256']
            data=gzip.decompress(p.read_bytes())
            assert len(data)==row['original']['bytes'] and hashlib.sha256(data).hexdigest()==row['original']['sha256']
            original=ROOT/row['original_relative']
            if original.exists():assert file_record(original)==row['original']
        print(json.dumps(dict(status='PASS_LOSSLESS_RECOVERY',files=len(m['files']),originals_deleted=False)));return
    if MANIFEST.exists():raise FileExistsError('RELEASE_PACKAGING_MUST_NOT_OVERWRITE')
    rows=[]
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or p.suffix=='.gz' or p.stat().st_size<=1_000_000:continue
        rel=p.relative_to(OUT);dest=OUT/'compressed_evidence'/Path(str(rel)+'.gz')
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise FileExistsError(dest)
        raw=p.read_bytes();original=file_record(p)
        dest.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
        recovered=gzip.decompress(dest.read_bytes());assert recovered==raw
        rows.append(dict(original_relative=p.relative_to(ROOT).as_posix(),original=original,
            compressed_relative=dest.relative_to(ROOT).as_posix(),compressed=file_record(dest),
            roundtrip_SHA256_PASS=True,original_file_preserved_on_disk=True))
    _write(MANIFEST,dict(status='PASS_LOSSLESS_PACKAGING',originals_deleted=False,threshold_bytes=1_000_000,
        files=rows,git_plain_large_raw_excluded=[r['original_relative'] for r in rows],
        restore='gzip.decompress(compressed_file.read_bytes()); verify original SHA256 and bytes before use; never overwrite different existing evidence',
        verify_command='python tools/package_v42_release_evidence.py --verify'))
    print(json.dumps(dict(status='PASS',files=len(rows),raw_bytes=sum(r['original']['bytes'] for r in rows),
        compressed_bytes=sum(r['compressed']['bytes'] for r in rows))))

if __name__=='__main__':main()
