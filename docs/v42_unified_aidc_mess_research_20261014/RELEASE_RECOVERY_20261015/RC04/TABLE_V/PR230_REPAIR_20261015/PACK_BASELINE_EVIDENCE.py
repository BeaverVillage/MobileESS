"""Lossless byte-only backup of completed historical B0 and Native evidence."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration').is_dir())
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record

fix=Path(__file__).resolve().parent;base=fix.parent
destination=fix/'PRESERVED_BASELINE_EVIDENCE_01'
destination.mkdir(exist_ok=False)
paths=list((base/'EXECUTION02/B0').rglob('*'))
paths=[p for p in paths if p.is_file()]
for run in ('EXECUTION01','EXECUTION02'):
    for name in ('PLANNING_AUTHORIZATION.json','K48_AUTHORIZATION.json','PLANNING_NATIVE_LEDGER.json',
            'K48_NATIVE_LEDGER.json','EXECUTION_SOURCE_FREEZE.json'):
        path=base/run/name
        if path.is_file():paths.append(path)
for path in (base/'EXECUTION02/B1').rglob('*'):
    if path.is_file() and path.suffix.lower() in ('.json','.log') and path.stat().st_size<2000000:
        paths.append(path)
paths+=list((fix/'STOP_AUDIT01/SOURCES').rglob('*.py'))
paths=sorted(set(paths));records=[file_record(p) for p in paths]
archive=destination/'HISTORICAL_B0_NATIVE_RAW.zip'
entries=[]
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
    for path,record in zip(paths,records):
        name=path.relative_to(ROOT).as_posix()
        package.write(path,name);entries.append(dict(archive_path=name,original=record))
with zipfile.ZipFile(archive) as package:
    assert sorted(package.namelist())==sorted(e['archive_path'] for e in entries)
    for entry in entries:
        content=package.read(entry['archive_path']);original=entry['original']
        assert len(content)==original['bytes'] and hashlib.sha256(content).hexdigest()==original['sha256']
assert records==[file_record(p) for p in paths]
report=dict(schema='PR230_HISTORICAL_B0_NATIVE_LOSSLESS_ARCHIVE_V1',status='PASS',archive=file_record(archive),
    entries=entries,source_raw_unchanged=True,readback_bytes_and_SHA_verified=True,
    original_B0_FULL_PASS_preserved=True,current_release_B0_recertified=False,
    historical_native_seconds=1965.3929998874664,fresh_B1_cycle_starts_at_zero=True,
    previous_solution_bound_or_DW_certificate_for_new_B1=False,Native_calls=0)
with (destination/'ARCHIVE_MANIFEST.json').open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2)
print(json.dumps(dict(status='PASS',archive=report['archive'],entries=len(entries))),flush=True)
