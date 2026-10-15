"""Losslessly package RC02/RC03 raw evidence without deleting originals.

Independent gzip members contain at most 64 MiB of original bytes. This keeps
each Git object below GitHub's file limit even for incompressible evidence.
Restore by concatenating decompressed members in manifest order and verifying
the original size and SHA256 before use. Never overwrite different evidence.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OUT=BASE/'RC03/EVIDENCE_DELIVERY'
MANIFEST=OUT/'COMPRESSED_EVIDENCE_MANIFEST.json'
CHUNK_BYTES=64*1024*1024


def verify(manifest):
    for row in manifest['files']:
        hasher=hashlib.sha256();size=0
        for part in row['members']:
            path=ROOT/part['compressed_relative']
            assert file_record(path)==part['compressed']
            data=gzip.decompress(path.read_bytes())
            assert len(data)==part['original_bytes']
            assert hashlib.sha256(data).hexdigest()==part['original_sha256']
            assert part['original_offset']==size
            hasher.update(data);size+=len(data)
        assert size==row['original']['bytes'] and hasher.hexdigest()==row['original']['sha256']
        original=ROOT/row['original_relative']
        if original.exists():assert file_record(original)==row['original']
    return dict(status='PASS_LOSSLESS_RECOVERY',files=len(manifest['files']),
        raw_bytes=sum(row['original']['bytes'] for row in manifest['files']),
        originals_deleted=False,Native_calls=0)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.verify:
        print(json.dumps(verify(json.loads(MANIFEST.read_text(encoding='utf8'))),indent=2));return
    if OUT.exists():raise FileExistsError('DELIVERY_MANIFEST_AND_MEMBERS_MUST_NOT_OVERWRITE')
    files=[]
    for location in ('RC02','RC03'):
        for path in sorted((BASE/location).rglob('*')):
            if (not path.is_file() or OUT in path.parents or path.suffix=='.gz'
                    or path.stat().st_size<=1_000_000):continue
            files.append(path)
    OUT.mkdir(parents=True)
    rows=[]
    for path in files:
        original=file_record(path);relative=path.relative_to(BASE)
        members=[];offset=0
        with path.open('rb') as source:
            for index,data in enumerate(iter(lambda:source.read(CHUNK_BYTES),b'')):
                short_name=hashlib.sha256(relative.as_posix().encode('utf8')).hexdigest()[:24]
                dest=OUT/'compressed_evidence'/(short_name+f'.part{index+1:04d}.gz')
                dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open('xb') as stream:stream.write(gzip.compress(data,compresslevel=6,mtime=0))
                assert dest.stat().st_size<100_000_000
                assert gzip.decompress(dest.read_bytes())==data
                members.append(dict(compressed_relative=dest.relative_to(ROOT).as_posix(),compressed=file_record(dest),
                    original_offset=offset,original_bytes=len(data),original_sha256=hashlib.sha256(data).hexdigest()))
                offset+=len(data)
        assert offset==original['bytes'] and file_record(path)==original
        rows.append(dict(original_relative=path.relative_to(ROOT).as_posix(),original=original,
            members=members,roundtrip_SHA256_PASS=True,original_preserved_on_disk=True))
    manifest=dict(schema='V42_RC02_RC03_LOSSLESS_EVIDENCE_PACKAGE_V1',status='PASS_LOSSLESS_PACKAGING',
        originals_deleted=False,threshold_bytes=1_000_000,raw_chunk_bytes=CHUNK_BYTES,gzip_compresslevel=6,files=rows,
        git_plain_large_raw_excluded=[row['original_relative'] for row in rows],
        restore='Concatenate gzip.decompress(member bytes) in manifest order; verify original bytes/SHA256 before use.',
        verify_command='python tools/package_v42_release_rc03_evidence.py --verify')
    _write(MANIFEST,manifest)
    result=verify(manifest)
    result['compressed_bytes']=sum(part['compressed']['bytes'] for row in rows for part in row['members'])
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
