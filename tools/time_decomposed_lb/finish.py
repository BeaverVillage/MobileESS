"""Aggregate certified lower bounds by max, never snapshot incumbents."""
from pathlib import Path
import math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.time_decomposed_lb.grid import read,write,sha,require
DOCS=ROOT/'docs/v42_b2_time_decomposed_global_lb'

def main():
    contract=read(DOCS/'TASK_CONTRACT.json');old=contract['existing_Global_LB'];ub=contract['validated_original_U4_UB']
    ledger=read(DOCS/'NATIVE_LEDGER.json');stages=[];bounds=[]
    for slot in contract['snapshot_slots_0_based']:
        out=DOCS/f'slot{slot:02d}';z=read(out/'NATIVE0.json');r=read(out/'RESULT.json');c=read(out/'INDEPENDENT_CERTIFICATE.json')
        valid=bool(c['PASS']) and c.get('Certified_LB') is not None
        lb=c.get('Certified_LB') if valid else None
        require(lb is None or math.isfinite(lb) and 0<=lb<=ub+1e-8,'CERTIFIED_BOUND_INVALID')
        if lb is not None:bounds.append(lb)
        stages.append(dict(slot=slot,dimensions=z['dimensions'],certificate_PASS=c['PASS'],Certified_LB=lb,
            certified_gain_over_existing=None if lb is None else lb-old,ObjBound=r.get('ObjBound'),ObjVal=r.get('ObjVal'),
            MIPGap=r.get('MIPGap'),LP_relaxation_log_objective=r.get('LP_relaxation_log_objective'),
            root_complete=r.get('root_complete'),NodeCount=r.get('NodeCount'),Runtime=r.get('Runtime'),
            model_build_seconds=r['model_build_seconds'],model_extraction_seconds=z['model_extraction_seconds'],
            optimize_wall_seconds=r['optimize_wall_seconds'],peak_process_RSS_bytes=r['peak_process_RSS_bytes'],
            peak_private_commit_bytes=r['peak_private_commit_bytes'],certificate_sha256=sha(out/'INDEPENDENT_CERTIFICATE.json')))
    snapshot_calls=[c for c in ledger['calls'] if c['kind']=='SNAPSHOT'];window_calls=[c for c in ledger['calls'] if c['kind']=='WINDOW']
    require(len(snapshot_calls)==3 and len(window_calls)==1 and [c['slot'] for c in snapshot_calls]==[75,82,94], 'UNEXPECTED_CALLS')
    override=read(DOCS/'USER_WINDOW_360_OVERRIDE.json');frozen=read(DOCS/'SNAPSHOT_NATIVE_LEDGER.json')
    require(override['binary_cap_override_authorized'] and override['Window_TimeLimit_seconds']==360 and ledger['calls'][:3]==frozen['calls'], 'WINDOW_AUTHORITY_OR_SNAPSHOT_PREFIX')
    require(window_calls[0]['TimeLimit']==360 and sum(c['TimeLimit'] for c in snapshot_calls)==90 and sum(c['TimeLimit'] for c in ledger['calls'])==450,'UNEXPECTED_BUDGET')
    wout=DOCS/'window360';wz=read(wout/'NATIVE0.json');wr=read(wout/'RESULT.json');wc=read(wout/'INDEPENDENT_CERTIFICATE.json')
    wlb=wc.get('Certified_LB') if wc['PASS'] else None
    require(wlb is None or math.isfinite(wlb) and 0<=wlb<=ub+1e-8,'WINDOW_CERTIFIED_BOUND_INVALID')
    if wlb is not None:bounds.append(wlb)
    wstage=dict(window=[88,96],physical_representation=wz['physical_representation'],dimensions=wz['dimensions'],certificate_PASS=wc['PASS'],Certified_LB=wlb,
        certified_gain_over_existing=None if wlb is None else wlb-old,ObjBound=wr.get('ObjBound'),ObjVal=wr.get('ObjVal'),MIPGap=wr.get('MIPGap'),
        LP_relaxation_log_objective=wr.get('LP_relaxation_log_objective'),root_complete=wr.get('root_complete'),NodeCount=wr.get('NodeCount'),Runtime=wr.get('Runtime'),
        model_build_seconds=wr['model_build_seconds'],model_extraction_seconds=wz['model_extraction_seconds'],optimize_wall_seconds=wr['optimize_wall_seconds'],
        peak_process_RSS_bytes=wr['peak_process_RSS_bytes'],peak_private_commit_bytes=wr['peak_private_commit_bytes'],certificate_sha256=sha(wout/'INDEPENDENT_CERTIFICATE.json'))
    new=max([old]+bounds);gain=new-old;material=gain>=.001
    classification='TIME_DECOMPOSITION_MATERIAL' if material else 'TIME_DECOMPOSITION_NONMATERIAL' if bounds else 'TIME_DECOMPOSITION_NOT_CERTIFIED'
    window=read(DOCS/'window_native0/WINDOW_NATIVE0_DESIGN.json')
    require(window['PASS'] and window['Native_optimize_calls']==0,'WINDOW_PROJECTION_AUDIT')
    value=dict(PASS=bool(bounds),classification=classification,parent_PR214=contract['parent_PR214'],source18r=contract['source18r_PR207'],case_sha=contract['case_sha'],
        Global_LB_old=old,Global_LB_new=new,Global_LB=new,validated_U4_UB=ub,UB=ub,improvement=gain,material=material,
        Global_Gap=(ub-new)/ub,Global_Gap_percent=100*(ub-new)/ub,global_gap_3pct=(ub-new)/ub<=.03,
        global_gap_3pct_classification='GLOBAL_GAP_3PCT_PASS' if (ub-new)/ub<=.03 else 'GLOBAL_GAP_3PCT_NOT_REACHED',
        stages=stages,window_stage=wstage,snapshot_material_trigger=any(s['Certified_LB'] is not None and s['Certified_LB']-old>=.001 for s in stages),Window_execute=True,Window_Native_calls=1,
        Window_stage_classification='TIME_DECOMPOSITION_MATERIAL' if wlb is not None and wlb-old>=.001 else 'TIME_DECOMPOSITION_NONMATERIAL' if wlb is not None else 'TIME_DECOMPOSITION_RESOURCE_STOP' if wr['resource_stops'] or wr['memory_stops'] else 'TIME_DECOMPOSITION_NOT_CERTIFIED',
        Window_why='User explicitly requested one360-second Window. Compact896Binary integer-physical-projection equivalence certified and preferred; all original arcs/physics/grid and boundary/Native0/readback/resource gates preserved. No literal16236-Binary Optimize.',
        snapshot_calls=len(snapshot_calls),Native_calls=len(ledger['calls']),requested_Native_seconds=sum(c['TimeLimit'] for c in ledger['calls']),
        actual_Native_Runtime=sum(s['Runtime'] for s in stages)+wr['Runtime'],optimize_wall_seconds=sum(s['optimize_wall_seconds'] for s in stages)+wr['optimize_wall_seconds'],
        peak_process_RSS_bytes=max([s['peak_process_RSS_bytes'] for s in stages]+[wr['peak_process_RSS_bytes']]),peak_private_commit_bytes=max([s['peak_private_commit_bytes'] for s in stages]+[wr['peak_private_commit_bytes']]),
        B1_launches=0,full_MILP_calls=0,campaign_calls=0,selective_integrality_Native_calls=0,repeated_or_extra_calls=0,
        bound_combination='max(existing same-Source/Case Global LB, independently certified snapshot and Window lower bounds); no addition',
        snapshot_or_window_incumbent_is_FULL_UB=False,Actual_AC_PASS=False,original_source_U4_protected=True,
        adopted_formulation='Certified Snapshot/Window lower-bound research only' if material else 'No material lower-bound formulation adopted',
        production_integration=False,ledger_sha256=sha(DOCS/'NATIVE_LEDGER.json'))
    write(DOCS/'FINAL_RESULT.json',value);print({k:value[k] for k in ('PASS','classification','Global_LB_new','Global_Gap_percent','Native_calls','actual_Native_Runtime')})

if __name__=='__main__':main()
