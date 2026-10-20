"""Conserve frozen electrical totals as fixed-share allocation candidates.

This never creates a valid operating input while PV eligibility is unresolved.
No AC method or solver is imported or executed.
"""
import json
import math
from pathlib import Path
import numpy as np
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record


def conserve(total,weights):
    w=np.asarray(weights,float);v=w/w.sum()*total
    k=int(w.argmax());others=math.fsum(float(x) for i,x in enumerate(v) if i!=k)
    v[k]=total-others
    for _ in range(4):
        value=math.fsum(map(float,v))
        if value==total:break
        v[k]=np.nextafter(v[k],np.inf if value<total else -np.inf)
    assert math.fsum(map(float,v))==total and min(v)>=0
    return v


def main():
    audit=read(DOC/'IEEE123_INPUT_AUTHORITY_AUDIT.json')
    if audit['actual_archived_setpoint_matches']!=120:raise RuntimeError('ORIGINAL_APPLIED_INPUT_NOT_VERIFIED')
    inv=read(DOC/'NETWORK_INVENTORY.json');loads=inv['load_rows']
    wp=np.array([r['kw'] for r in loads]);wq=np.array([r['kvar'] for r in loads])
    csvout('GREENSBORO_FIXED_LOAD_SHARE_CANDIDATES.csv',[dict(load=r['load'],bus=r['bus'],phases=r['phases'],
        kv=r['kv'],P_weight=float(wp[j]/wp.sum()),Q_weight=float(wq[j]/wq.sum()),
        nominal_P_is_operating_input=False,add_original_nominal_load=False) for j,r in enumerate(loads)])
    z=np.load(RUN/'IEEE123_FROZEN_BACKGROUND.npz');reports=[];arrays={}
    for role in ('actual','planning'):
        pp=[];qq=[]
        for t in range(len(z[role+'_P'])):
            pt=math.fsum(map(float,z[role+'_P'][t]));qt=math.fsum(map(float,z[role+'_Q'][t]));vt=math.fsum(map(float,z[role+'_PV'][t]))
            p=conserve(pt,wp);q=conserve(qt,wq);pp.append(p);qq.append(q)
            reports.append(dict(role=role,execution_slot=t if role=='actual' else '',
                evaluation_slot=t-24 if role=='actual' else t,
                IEEE123_P_kw=pt,Greensboro_candidate_P_kw=math.fsum(map(float,p)),P_error_kw=0.,
                IEEE123_Q_kvar=qt,Greensboro_candidate_Q_kvar=math.fsum(map(float,q)),Q_error_kvar=0.,
                IEEE123_PV_kw=vt,Greensboro_PV_kw='',PV_error_kw='',
                P_Q_arithmetic_status='EXACT_FLOAT_FSUM_MATCH',
                complete_input_mapping='INPUT_MAPPING_NOT_VERIFIED',
                reason='PV interconnection eligibility and inherited generator model not verified; no valid operating input or AC'))
        arrays[role+'_P_candidate']=np.array(pp);arrays[role+'_Q_candidate']=np.array(qq)
    np.savez_compressed(RUN/'GREENSBORO_PQ_ALLOCATION_CANDIDATE.npz',**arrays)
    csvout('INPUT_TOTAL_CONSERVATION_216.csv',reports)
    save('INPUT_MAPPING_GATE.json',dict(status='INPUT_MAPPING_NOT_VERIFIED',AC_ALLOWED=False,
        original_actual_setpoint_sha_matches=120,actual_prefix_slots=24,actual_evaluation_slots=96,
        planning_slots=96,planning_and_actual_separate=True,
        P_conservation='EXACT_FLOAT_FSUM_MATCH_ALL_216_ROWS',Q_conservation='EXACT_FLOAT_FSUM_MATCH_ALL_216_ROWS',
        PV_conservation='NOT_VERIFIED',spatial_weights_time_invariant=True,
        weights='Original base_peak nominal P/Q used only as spatial weights, not operating magnitudes',
        original_GSO_nominal_load_added=False,new_scaling_operations=0,
        total_native_load_receivers=len(loads),original_GSO_PVSystems=inv['pv'],
        original_IEEE123_actual_PV_peak_kw=audit['maximum_actual_PV_kw'],
        reason='No verified PV interconnection roster, inverter/transformer/phase/rating binding for transferred original PV model',
        PV_zeroing_or_netting_into_load_forbidden=True,synthetic_PV_receivers_created=0,
        actual_model_input=record(RUN/'IEEE123_FROZEN_BACKGROUND.npz'),
        candidate_PQ_allocation=record(RUN/'GREENSBORO_PQ_ALLOCATION_CANDIDATE.npz')))
    native=read('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1/2025-05-01/NATIVE_INPUT.json')
    p=np.load(RUN/'jobs/ACTUAL_PHYSICAL.npz');P=p['PCC_P_kw'][24:];Q=p['PCC_Q_kvar'][24:];it=p['IT_kw'][24:]
    aidc=[];sta=[];candidates=[];buses={r['bus']:r for r in inv['bus_rows']}
    for tx in inv['transformer_rows']:
        w=tx['windings'][-1];bus=w['bus'].split('.')[0]
        if tx['phases']==3 and w['kv']<1:
            b=buses[bus]
            candidates.append(dict(bus=bus,transformer=tx['transformer'],feeder=tx['feeder'],
                phases=3,kv_ll=w['kv'],transformer_nameplate_kva=w['kva'],x=b['x'],y=b['y'],
                local_existing_customer_load='Retained in PQ weights; remaining margin NOT_VERIFIED',
                port_or_switchgear='NOT_VERIFIED',AC_headroom='NOT_VERIFIED_INPUT_MAPPING_BLOCKED'))
    for j in range(12):
        required=float(np.hypot(P[:,j],Q[:,j]).max())
        for c in candidates:
            aidc.append(dict(site=f'AIDC{j+1:02d}',actual_max_required_kva=required,
                nameplate_necessary_condition=c['transformer_nameplate_kva']>=required,
                spatial_order='NOT_VERIFIED',final_PCC='NOT_SELECTED',**c))
            sta.append(dict(site=f'STA{j+1:02d}',P_limit_kw=300,Q_limit_kvar=250,PCS_kva=400,
                unit_full_PQ_point_kva=math.hypot(300,250),
                nameplate_necessary_condition=c['transformer_nameplate_kva']>=400,
                operational_acceptance='NOT_VERIFIED',final_PCC='NOT_SELECTED',**c))
    csvout('AIDC12_PCC_CANDIDATES.csv',aidc);csvout('STA12_PCC_CANDIDATES.csv',sta)
    csvout('AIDC_LOCATION_SCALE_AUDIT.csv',[dict(site=str(s),installed_GPU=native['capacities'][str(s)],
        IT_peak_kw=float(it[:,j].max()),cooling_aux_peak_kw=float((P[:,j]-it[:,j]).max()),
        actual_P_min_kw=float(P[:,j].min()),actual_P_max_kw=float(P[:,j].max()),actual_Q_max_kvar=float(Q[:,j].max()),
        scale=1.,ratio_to_original_actual_background_peak_percent=100*float(P.sum(1).max())/audit['maximum_actual_background_kw'],
        new_grid_burden_ratio='NOT_VERIFIED_INPUT_MAPPING',PCC='',status='FCFS_POWER_VERIFIED_PCC_NOT_VERIFIED')
        for j,s in enumerate(p['sites'])])
    save('PCC_STATIC_SUMMARY.json',dict(three_phase_LV_candidates=len(candidates),
        LV_transformers_nameplate_at_least_400kVA=sum(c['transformer_nameplate_kva']>=400 for c in candidates),
        certified_AIDC_PCC=0,certified_STA_PCC=0,certified_multi_vehicle_ports=0,
        candidate_type='Electrical nodes with transformer nameplate only; not certified physical sites',
        eight_initial_locations='NOT_VERIFIED; original first four retained as data, no new four invented'))
    csvout('AIDC_JOB_FLEXIBILITY_AUDIT.csv',[dict(job_uid=r['job_uid'],GPU_gang=r['GPU_gang'],
        state=r['state'],planning_site=r['planning_site'],can_timeshift=r['can_timeshift'],
        can_prestart_place=r['can_prestart_place'],can_checkpoint_migrate=r['can_checkpoint_migrate'],
        exact_compute_GPUh=r['exact_compute_GPUh'],feasible_control='NOT_VERIFIED',
        real_delta_kw='',global_delta_pp='',reason='No admitted PCC mapping/B0; permissions not a schedule witness')
        for r in native['known_population']])
    print('P/Q arithmetic exact in',len(reports),'rows; PV mapping blocked; AC remains disabled.')


if __name__=='__main__':main()
