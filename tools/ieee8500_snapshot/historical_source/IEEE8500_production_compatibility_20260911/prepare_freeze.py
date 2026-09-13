import sys, json, hashlib, ast
from pathlib import Path
from datetime import datetime, timezone
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def record(p):
    s=p.stat();return dict(path=str(p),sha256=sha(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
def main():
    target=HERE/'PRE_EXECUTION_FREEZE_MANIFEST.json';assert not target.exists()
    forensic=ROOT/'IEEE8500_voltage_control_forensic_20260911'
    fm=forensic/'FORENSIC_EVIDENCE_FREEZE_MANIFEST.json'
    assert sha(fm)=='a9e599f613987d082859b4d3e979806b74d7babbbec3cfc20d596b7126bd59aa'
    before=read(forensic/'PROTECTED_AUTHORITIES_BEFORE.json')
    for r in before:
        p=Path(r['path']);s=p.stat();assert sha(p)==r['sha256'] and s.st_size==r['bytes'] and s.st_mtime_ns==r['mtime_ns'],str(p)
    for r in read(fm)['files']:
        p=forensic/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'],str(p)
    protected=[]
    for name in ['IEEE8500_scalability_20260910','IEEE8500_pcc_overlay_20260911','IEEE8500_operating_point_20260911','IEEE8500_voltage_control_forensic_20260911']:
        protected.extend(record(p) for p in sorted((ROOT/name).rglob('*')) if p.is_file())
    assert len(protected)==2492,len(protected)
    (HERE/'PROTECTED_AUTHORITIES_BEFORE.json').write_text(json.dumps(protected,indent=2,ensure_ascii=False),encoding='utf-8')
    (HERE/'Master_IEEE8500_Compatible_B0.dss').write_text(f'! Adapted reduced-load study model; not canonical IEEE8500 reproduction.\nCompile "{ROOT / "IEEE8500_pcc_overlay_20260911/Master_IEEE8500_PCC.dss"}"\nRedirect "{HERE / "IEEE8500_Compatibility_Adaptation.dss"}"\nRedirect "{ROOT / "IEEE8500_operating_point_20260911/B0_RESOURCE_OBJECTS.dss"}"\n! No Solve: use the frozen chronological screen script for inputs and controls.\n',encoding='utf-8')
    for p in HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    local=[record(p) for p in sorted(HERE.iterdir()) if p.is_file()]
    manifest=dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),execution_started=False,scope='User-fixed compatibility rule, executable code, all original source/PCC/topology/input and forensic evidence',canonical_reproduction=False,original_forensic_manifest_sha256=sha(fm),original_files_verified=2492,B1_B2_B3_data_reads=0,bound_files=protected+local)
    target.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    (HERE/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').write_text(sha(target)+'  '+target.name+'\n',encoding='ascii')
    print('PRE_EXECUTION_FREEZE_COMPLETE',sha(target),'protected=',len(protected),'bound=',len(manifest['bound_files']))
if __name__=='__main__':main()
