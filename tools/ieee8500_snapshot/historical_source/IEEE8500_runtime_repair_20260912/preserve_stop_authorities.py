import json, hashlib, time
from pathlib import Path

H=Path(__file__).absolute().parent
R=H.parent/'IEEE8500_v41r4_production_20260911_r2'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(p):return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def write(name,data):
    p=H/name
    assert not p.exists()
    p.write_text(json.dumps(data,indent=2),encoding='utf-8')
def main():
    b1=R/'B1/ACCEPTED_AIDC.json'
    assert sha(b1)=='3dee86735dbf4ebd5200fce575cba6691fb2381f0d4d55ccc4cafc9c82c83ddf'
    primary=R/'B2/final_exact/AC_VALIDATION.json'
    report=json.loads(primary.read_text())
    assert report['status']=='FAIL' and abs(report['metrics']['Vmax_pu']-1.0585440631902354)<1e-12
    diag=H/'pruned_0_exact/AC_VALIDATION.json'
    witness=json.loads(diag.read_text())
    assert witness['status']=='PASS' and abs(witness['metrics']['Vmax_pu']-1.0499207243101567)<1e-12
    write('DIAGNOSTIC_AC_FEASIBLE_EXISTENCE_WITNESS.json',dict(
        classification='DIAGNOSTIC_AC_FEASIBLE_EXISTENCE_WITNESS',state_id='B2-S4-e0d2bbcf68b5d690',
        report=record(diag),metrics=witness['metrics'],production_authority=False,
        forbidden_uses=['final decision','fallback seed','restoration seed','target','selection anchor','beam/final selection modification']))
    write('FROZEN_PRIMARY_FAILURE.json',dict(status='PRIMARY_FRESH_FAIL',state_id='B2-S4-b55b48c9f33cb380',
        original_selection=record(R/'B2/beam/2025-05-21/B2/B2/FINAL_RESULT.json'),primary_exact=record(primary),
        metrics=report['metrics'],B1_preserved=record(b1),B1_rerun_authorized=False,beam_selection_changes_authorized=False))
    roots=[R/'B1',R/'B2',H/'DEVELOPMENT_ONLY_REJECTED_SELECTION_ORDER']
    files=[record(p) for root in roots for p in sorted(root.rglob('*')) if p.is_file()]
    files += [record(p) for p in sorted(R.glob('*.py'))]
    files += [record(p) for p in sorted(H.rglob('*')) if p.is_file() and 'DEVELOPMENT_ONLY_REJECTED_SELECTION_ORDER' not in p.parts]
    write('STOP_PRESERVATION_SHA256_MANIFEST.json',dict(created_unix=time.time(),files=files,
        quarantine_classification='DEVELOPMENT_ONLY_REJECTED_SELECTION_ORDER',production_from_quarantine=False))
    print('PRESERVED',len(files),'files',flush=True)
if __name__=='__main__':main()
