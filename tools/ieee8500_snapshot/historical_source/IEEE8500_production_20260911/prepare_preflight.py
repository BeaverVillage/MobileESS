import sys,ast
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
import ac8500 as ac
H=ac.H
def main():
    assert not (H/'PREFLIGHT_EXECUTION_FREEZE.json').exists();prior=ac.STRESS/'STRESS_CALIBRATION_EVIDENCE_FREEZE_MANIFEST.json';assert ac.sha(prior)=='c08bb1de9376dc970ecd8ca4e014f84e2af40787ffd0167f98ee95b37eca89fd'
    protected=ac.read(ac.STRESS/'PROTECTED_AUTHORITIES_BEFORE.json')
    for r in protected:assert ac.record(Path(r['path']))==r
    for r in ac.read(prior)['files']:assert ac.sha(ac.STRESS/r['path'])==r['sha256']
    protected+= [ac.record(p) for p in sorted(ac.STRESS.rglob('*')) if p.is_file()];assert len(protected)==3997,len(protected)
    ac.save(H/'PROTECTED_AUTHORITIES_BEFORE.json',protected)
    for p in H.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    ac.save(H/'PREFLIGHT_RULE.json',dict(authority=ac.record(ac.STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json'),selected_date='2025-05-21',source_pu=1.04,Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF',coefficient_control_axes=ac.channels(),finite_difference_step=1.,local_representative_slots=[0,24,48,70,95],local_representative_steps=[[0,10],[1,10],[22,-10],[24,30],[25,40],[48,-30],[71,-40]],local_validation_absolute_error_limits=dict(voltage_pu=.001,loading_pu=.005),B0_reproduction_tolerance_pu=1e-10,final_and_incumbent_AC_gate='Full chronological native-control 96-slot exact AC, unchanged physical limits',B1_search_seconds=14400,B3_A1_search_seconds=14400,checkpoints_seconds=[1800,3600,7200,14400],early_stagnation_stop=False,IEEE123_coefficient_reuse=False,policy_runs_require_preflight_PASS=True))
    files=protected+[ac.record(p) for p in sorted(H.iterdir()) if p.is_file()];ac.save(H/'PREFLIGHT_EXECUTION_FREEZE.json',dict(utc=datetime.now(timezone.utc).isoformat(),files=files,originals_immutable=True,stage='ELECTRICAL_PREFLIGHT_ONLY'))
    (H/'PREFLIGHT_EXECUTION_FREEZE.sha256').write_text(ac.sha(H/'PREFLIGHT_EXECUTION_FREEZE.json')+'\n');print('PREFLIGHT_FROZEN',len(files),flush=True)
if __name__=='__main__':main()
