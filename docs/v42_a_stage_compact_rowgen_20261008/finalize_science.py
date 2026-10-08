"""Read-only scientific consolidation after all authorized native work ends."""
import json,sys,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from v42_pr134_b1.common import read,record,atomic
def run():
    if not (OUT/'DIRECT_RESULT.json').exists():raise RuntimeError('DIRECT_NATIVE_MUST_END_BEFORE_FINAL_CONSOLIDATION')
    for p in (OUT/'CANARIES').glob('*/STARTED.json'):
        if not (p.parent/'RESULT.json').exists():raise RuntimeError('AUTHORIZED_CANARY_MUST_END_BEFORE_FINAL_CONSOLIDATION')
    subprocess.run([sys.executable,str(OUT/'report_progress.py')],cwd=ROOT,check=True)
    phi=read(OUT/'FROZEN64_RESULT.json');p1=read(OUT/'INTEGER_RESULT.json');direct=read(OUT/'DIRECT_RESULT.json');c=read(OUT/'DIRECT_CHECKPOINT.json')
    assert phi['certified_zero'] and p1['P1_accepted'] and p1['global_gap']<=.005
    stages={s['component']:s for s in direct['stages']}
    for s in stages.values():
        assert record(s['certificate']['path'])==s['certificate'] and read(s['certificate']['path'])['PASS']
    canaries={p.parent.name:read(p) for p in sorted((OUT/'CANARIES').glob('*/RESULT.json'))}
    classification=direct['classification'];obstruction='NATIVE_OPTIMAL_CANDIDATE_FAILS_ORIGINAL_PHYSICS' in direct.get('stop_reason','')
    if obstruction:classification='A_NUMERICAL_INCONCLUSIVE'
    result=dict(PASS=True,classification=classification,Phi=0,P1_accepted=True,P1_gap_ratio=p1['global_gap'],
        May19_A1_accepted=direct['A1_accepted'],May19_A1_scientific_status='ACCEPTED' if direct['A1_accepted'] else 'INCONCLUSIVE',
        migration_count=0,certified_P2_stages=stages,final_current_stage_valid_LB=c['valid_global_LB'],
        final_current_stage_valid_UB=None if c['incumbent'] is None else c['incumbent']['value'],
        native_stop_reason=direct.get('stop_reason'),hard_original_physics_obstruction=obstruction,
        canaries=canaries,canary_status='EXECUTED_CONDITIONALLY' if canaries else 'NOT_TRIGGERED',
        canary_not_triggered_reason=None if canaries else 'MAY19_A1_NOT_ACCEPTED' if not direct['A1_accepted'] else '90_MINUTE_REMAINING_GATE_NOT_MET',
        deadline=read(OUT/'OVERNIGHT_START.json'),completed_before_deadline=time.time()<=read(OUT/'OVERNIGHT_START.json')['deadline_unix'],
        evidence={n:record(OUT/n) for n in ('FROZEN64_RESULT.json','P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json','P2_MIGRATION_PROBE_RESULT.json','DIRECT_RESULT.json','DIRECT_CHECKPOINT.json','AGGREGATE_PROGRESS.json')},
        production_Planning_Actual_Fresh_AC_executed=False,M_lane_touched=False)
    atomic(OUT/'FINAL_SCIENTIFIC_RESULT.json',result)
    text=(OUT/'REPORT.md').read_text(encoding='utf8')
    headline=f"Final classification: **{classification}**. May19 four-objective A1 status: **{result['May19_A1_scientific_status']}**.\n\n"
    text=text.replace('Current classification: **'+direct['classification']+'**. This report is refreshed during execution; the final repository handoff records the final HEAD and remote match separately.',headline.strip())
    text+='\nFinal scientific consolidation is in `FINAL_SCIENTIFIC_RESULT.json`; partial P2 bounds are not exact objective locks.\n'
    (OUT/'REPORT.md').write_text(text,encoding='utf8');print(json.dumps({k:result[k] for k in ('classification','May19_A1_accepted','canary_status','completed_before_deadline')}))
if __name__=='__main__':run()
