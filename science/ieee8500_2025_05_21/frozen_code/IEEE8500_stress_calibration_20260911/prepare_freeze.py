import sys,ast,os,platform
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
import stress_common as s
H=s.H
def main():
    mf=H/'PRE_EXECUTION_FREEZE_MANIFEST.json';assert not mf.exists();prior=s.PREV/'SOURCE_GRID_EVIDENCE_FREEZE_MANIFEST.json';assert s.sha(prior)=='aa070828da04a7cb8914ec7699006cdd9c56f48e330004a409b0d6ea005b214e'
    for r in s.read(s.PREV/'PROTECTED_AUTHORITIES_BEFORE.json'):assert s.record(Path(r['path']))==r,r['path']
    for r in s.read(prior)['files']:
        p=s.PREV/r['path'];assert s.sha(p)==r['sha256'] and p.stat().st_size==r['bytes'],str(p)
    authority=s.read(s.PREV/'FINAL_OPERATING_POINT_AUTHORITY.json');assert authority['final_authority_valid'] and authority['source_pu']==1.045 and authority['alpha8500']==.25
    protected=[]
    for name in ['IEEE8500_scalability_20260910','IEEE8500_pcc_overlay_20260911','IEEE8500_operating_point_20260911','IEEE8500_voltage_control_forensic_20260911','IEEE8500_production_compatibility_20260911','IEEE8500_source_grid_compatibility_20260911']:
        protected.extend(s.record(p) for p in sorted((s.ROOT/name).rglob('*')) if p.is_file())
    assert len(protected)==3315,len(protected);s.save(H/'PROTECTED_AUTHORITIES_BEFORE.json',protected)
    s.save(H/'PRESERVED_VOLTAGE_FEASIBLE_AUTHORITY.json',dict(role='Immutable voltage-feasible compatibility authority',source_pu=1.045,alpha8500=.25,authority=s.record(s.PREV/'FINAL_OPERATING_POINT_AUTHORITY.json'),evidence_manifest=s.record(prior),replacement_or_modification=False))
    s.save(H/'ENGINE_ENVIRONMENT.json',dict(python=sys.version,platform=platform.platform(),opendss=s.frozen.odd.Basic.Version(),cpu_count=os.cpu_count(),worker_processes=5,OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS'),OPENBLAS_NUM_THREADS=os.environ.get('OPENBLAS_NUM_THREADS'),bytecode_writes_disabled=True))
    for p in H.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    local=[s.record(p) for p in sorted(H.rglob('*')) if p.is_file()]
    s.save(mf,dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),execution_started=False,scope='Fixed 100-case stress calibration grid, target 0.85, lexicographic selection, hard constraints, executable code and all immutable source/PCC/topology/input/previous evidence hashes',protected_original_files=len(protected),prior_voltage_feasible_authority_preserved=True,B1_B2_B3_data_reads=0,bound_files=protected+local))
    (H/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').write_text(s.sha(mf)+'  '+mf.name+'\n',encoding='ascii');print('PRE_EXECUTION_FREEZE_COMPLETE',s.sha(mf),'protected',len(protected),'bound',len(protected+local),flush=True)
if __name__=='__main__':main()
