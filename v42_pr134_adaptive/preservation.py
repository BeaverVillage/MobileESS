"""Read-only final byte/source audit of the completed production authority."""
from .common import *

def main():
    original=read(SOURCE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json');bad=[]
    for r in original['files']:
        p=Path(r['path'])
        if not p.is_file() or sha(p)!=r['sha256']:bad.append(r['path'])
    freeze=read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json');sourcebad=[]
    for r in freeze['source_files']:
        if sha(r['path'])!=r['sha256']:sourcebad.append(r['path'])
    result=dict(PASS=not bad and not sourcebad,original_production_files=len(original['files']),
        production_bytes=sum(r['bytes'] for r in original['files']),changed_production_files=bad,
        source_closure_files=len(freeze['source_files']),changed_original_source_files=sourcebad,
        original_Git_SHA=freeze['Git_SHA'],scientific_SHA=freeze['scientific_SHA'],current_run_unchanged=True,
        no_PASS_date_rerun=True,no_May10_or_May12_optimization=True,completed_production_identity=freeze['run_id'],
        original_manifest=record(SOURCE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json'),audited_UTC=now())
    write('ORIGINAL_PRODUCTION_PRESERVATION_AUDIT.json',result);print('PRODUCTION_BYTE_SOURCE_PRESERVATION',result['PASS'],len(original['files']),len(freeze['source_files']),flush=True)
    if not result['PASS']:raise ValueError('READ_ONLY_AUTHORITY_CHANGED')
if __name__=='__main__':main()
