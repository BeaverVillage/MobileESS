"""Keep large audit JSON byte-identical without filling the source diff."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration').is_dir())
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
fix=Path(__file__).resolve().parent
names=('DOMAIN_AUDIT01/UID_DOMAIN_AUDIT.json',
    'FOUR_DEFECT_AUDIT04/RELEASE_SOURCE_PINS_BEFORE.json','FOUR_DEFECT_AUDIT04/RELEASE_SOURCE_PINS_AFTER.json',
    'DW_NATIVE0_EVIDENCE_01/LOCAL_ONLY_LARGE_ARTIFACTS_SHA256_MANIFEST.json')
records=[file_record(fix/name) for name in names]
archive=fix/'COMPACT_REVIEW_RAW_EVIDENCE.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
    for name in names:package.write(fix/name,name)
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    for name,record in zip(names,records):
        value=package.read(name)
        assert len(value)==record['bytes'] and hashlib.sha256(value).hexdigest()==record['sha256']
assert records==[file_record(fix/name) for name in names]
report=dict(status='PASS',archive=file_record(archive),raw_files=records,
    byte_identical_readback=True,original_raw_unchanged=True,
    other_large_raw_locations=dict(full_pricing_roster='DW_NATIVE0_EVIDENCE_01/BLOCK_PRICING_ORACLE_VERIFICATION.json.gz',
        final_124_case_rebind='FINAL_EXECUTOR_EVIDENCE_01/TABLE_V_FINAL_EXECUTOR_NATIVE0_EVIDENCE.zip'))
with (fix/'COMPACT_REVIEW_RAW_MANIFEST.json').open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2)
print(json.dumps(report['archive']),flush=True)
