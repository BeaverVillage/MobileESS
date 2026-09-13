import sys,ast,json,hashlib,platform,os
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
import screen_source_grid as s
H=s.H
def main():
    mf=H/'PRE_EXECUTION_FREEZE_MANIFEST.json';assert not mf.exists()
    prev=s.PREV;old_mf=prev/'COMPATIBILITY_EVIDENCE_FREEZE_MANIFEST.json';assert s.sha(old_mf)=='c800967e9df3aa6fde01b3414db0c0d721d3e081ddd6d33c548928d8bc8a5893'
    for r in s.read(prev/'PROTECTED_AUTHORITIES_BEFORE.json'):assert s.record(Path(r['path']))==r,r['path']
    for r in s.read(old_mf)['files']:
        p=prev/r['path'];assert s.sha(p)==r['sha256'] and p.stat().st_size==r['bytes'],str(p)
    protected=[]
    for name in ['IEEE8500_scalability_20260910','IEEE8500_pcc_overlay_20260911','IEEE8500_operating_point_20260911','IEEE8500_voltage_control_forensic_20260911','IEEE8500_production_compatibility_20260911']:
        protected.extend(s.record(p) for p in sorted((s.ROOT/name).rglob('*')) if p.is_file())
    assert len(protected)==2618,len(protected);s.save(H/'PROTECTED_AUTHORITIES_BEFORE.json',protected)
    s.save(H/'ENGINE_ENVIRONMENT.json',dict(python=sys.version,platform=platform.platform(),opendss=s.frozen.odd.Basic.Version(),cpu_count=os.cpu_count(),worker_processes=5,bytecode_writes_disabled=True))
    for p in H.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    local=[s.record(p) for p in sorted(H.iterdir()) if p.is_file()]
    s.save(mf,dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),execution_started=False,scope='Fixed source grid, alpha grid, lexicographic selection/replay rules, executable code and all immutable source/PCC/topology/input/prior evidence hashes',previous_failure_manifest_sha256=s.sha(old_mf),original_files_verified=len(protected),B1_B2_B3_data_reads=0,bound_files=protected+local))
    (H/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').write_text(s.sha(mf)+'  '+mf.name+'\n',encoding='ascii');print('PRE_EXECUTION_FREEZE_COMPLETE',s.sha(mf),'protected',len(protected),'bound',len(protected+local))
if __name__=='__main__':main()
