"""Transparent B0-peak completeness supplement before final score selection."""
import time
import numpy as np
from .controllability import *


def run():
    axes,base,li,weights,folder=prepare();candidates=rows(REPORT/'STA_MV_LV_CANDIDATES.csv')
    receipt0=read(folder/'RECEIPT.json');t=int(receipt0['peak_slot'])
    assert t not in SLOTS
    prereg=dict(schema='BASELINE_PEAK_COMPLETENESS_SUPPLEMENT_V1',baseline=receipt(folder/'RECEIPT.json'),extra_slot=t,
        original_six_sample_preregistration=receipt(REPORT/'CONTROLLABILITY_PREREGISTRATION.json'),
        reason='BG0.85 baseline global peak slot74 was absent from six explicit samples; add exact peak before score selection',
        candidate_scores_or_policy_results_inspected=False,original_six_samples_preserved=True,
        merge_rule='all seven derivative samples equally weighted with original frozen corridor weights and power/ETA bounds',
        candidate_or_hardware_or_jobs_or_geometry_rule_changed=False,Native_calls=0)
    path=REPORT/'BASELINE_PEAK_SUPPLEMENT_PREREGISTRATION.json'
    if path.exists():assert read(path)==prereg
    else:write(path,prereg)
    states=read(folder/'CONTROL_STATES.json');data=dict(np.load(ROOT/'ieee8500_v42_high/data/facility/recomputed/C0_PLANNING_INPUTS.npz'))
    e=HighEngine('CANDIDATE_PEAK_EXTRA',.85,report_dir=REPORT)
    mv=next(r for r in candidates if r['candidate_id'].startswith('MV:'));lv=next(r for r in candidates if r['candidate_id'].startswith('LV:'))
    e.add_pcc('PROBE_MV',mv['candidate_bus']);e.add_pcc('PROBE_LV',lv['candidate_bus'],'LV_SPLIT_240')
    e.apply_inputs(t,data);a=e.settle('fixed',states[t]);error=float(np.abs(a['line_rho']-base['line_rho'][t]).max());assert error<1e-7
    derivative=np.zeros((1,len(candidates),2,len(li)))
    for k,r in enumerate(candidates):
        mode='MV' if r['candidate_id'].startswith('MV:') else 'LV';load=e.pccs['PROBE_'+mode]['element'];bus=r['candidate_bus']
        e.d.Text.Command(f'edit {load} bus1={bus}.1.2.3' if mode=='MV' else f'edit {load} bus1={bus}.1.2')
        for dim in (0,1):
            samples=[]
            for sign in (-1.,1.):
                e.d.Loads.Name(load.split('.',1)[1]);e.d.Loads.kW(sign if dim==0 else 0.);e.d.Loads.kvar(sign if dim==1 else 0.)
                a=e.settle('fixed');samples.append(a['line_rho'][li].copy())
            derivative[0,k,dim]=(samples[1]-samples[0])/2
        e.d.Loads.Name(load.split('.',1)[1]);e.d.Loads.kW(0.);e.d.Loads.kvar(0.)
        if (k+1)%300==0:print('Peak supplement',t,k+1,'/',len(candidates),flush=True)
    np.savez_compressed(REPORT/'CANDIDATE_PEAK_SUPPLEMENT_DERIVATIVES.npz',slots=np.array([t]),candidate_ids=np.array([r['candidate_id'] for r in candidates]),
        line_indices=np.array(li),weights=weights,d_rho_d_consumption=derivative)
    write(REPORT/'BASELINE_PEAK_SUPPLEMENT_RECEIPT.json',dict(PASS=True,baseline_rho_error=error,slot=t,candidates=len(candidates),
        AC_calls=1+4*len(candidates),archive=receipt(REPORT/'CANDIDATE_PEAK_SUPPLEMENT_DERIVATIVES.npz'),Native_calls=0))


def merge_scores():
    import shutil
    first=dict(np.load(REPORT/'CANDIDATE_CRITICAL_LINE_PQ_DERIVATIVES.npz'));extra=dict(np.load(REPORT/'CANDIDATE_PEAK_SUPPLEMENT_DERIVATIVES.npz'))
    assert int(first['completed_slots'])==6 and np.array_equal(first['candidate_ids'],extra['candidate_ids'])
    slots=np.r_[first['slots'],extra['slots']].astype(int);derivative=np.concatenate((first['d_rho_d_consumption'],extra['d_rho_d_consumption']))
    weights=first['weights'];candidates=rows(REPORT/'STA_MV_LV_CANDIDATES.csv');data=dict(np.load(ROOT/'ieee8500_v42_high/data/facility/recomputed/C0_PLANNING_INPUTS.npz'))
    ready={}
    for r in rows(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv'):
        if int(r['departure_slot'])==0:ready.setdefault(r['destination_STA'],[]).append(900*int(r['earliest_day0_ready_slot']))
    sites=list(map(str,data['sites']));qf=np.tan(np.arccos(.95));combined=[];aidc=[];mess=[]
    for site in [f'AIDC{i:02d}' for i in range(1,13)]+[f'STA{i:02d}' for i in range(1,13)]:
        for k,r in enumerate(candidates):
            mv=r['candidate_id'].startswith('MV:')
            if site.startswith('AIDC') and not mv:continue
            dp=derivative[:,k,0];dq=derivative[:,k,1]
            if site.startswith('AIDC'):
                j=sites.index(site);bound=data['source_mask_P_upper_bound_kw'][slots,j];power=data['PCC_P_kw'][slots,j]
                relief=(dp+qf*dq)*bound[:,None];value=float((relief@weights).mean());bad=float((np.maximum(-relief,0)@weights).mean())
                out=dict(location_id=site,candidate_id=r['candidate_id'],candidate_bus=r['candidate_bus'],electrical_region=r['electrical_region'],
                    score=value-bad,source_mask_relaxation_P_max_kw=float(bound.max()),certified_flexible_P_kw=0.,certified_nonzero_dispatch='NOT_CERTIFIED',
                    mean_total_AIDC_load_effect_rho=float((((dp+qf*dq)*power[:,None])@weights).mean()),
                    mean_relaxation_relief_rho=value,independent_Q=False,flexible_workload_multiplier=1,score_slots=slots.tolist())
                aidc.append(out)
            else:
                p=450. if mv else 5.;q=300. if mv else 3.;reach=np.array([sum(x<=900*t for x in ready.get(site,[]))/6 for t in slots])
                relief=dp*p;value=float(((np.maximum(relief,0)+.25*np.abs(dq*q)-np.maximum(-relief,0))@weights*reach).mean())
                out=dict(location_id=site,candidate_id=r['candidate_id'],candidate_bus=r['candidate_bus'],electrical_region=r['electrical_region'],score=value,
                    P_screening_kw=p,Q_screening_kvar=q,mean_reachable_vehicle_fraction=float(reach.mean()),mean_signed_P_relief_rho=float((relief@weights).mean()),
                    mean_Q_response_rho=float((np.abs(dq*q)@weights).mean()),hardware_actual_current_gate='FINAL_NONLINEAR_REQUIRED',
                    field_ETA_access='UNVERIFIED',schedule_certificate=False,score_slots=slots.tolist())
                mess.append(out)
            combined.append(dict(location_id=site,candidate_id=r['candidate_id'],score=out['score']))
    for name in ('AIDC_CONTROLLABILITY_SCORES.csv','MESS_CONTROLLABILITY_SCORES.csv','JOINT_CANDIDATE_SCORES.csv'):
        target=REPORT/'six_time_score_preserved'/name;target.parent.mkdir(exist_ok=True)
        if not target.exists():shutil.copyfile(REPORT/name,target)
    table(REPORT/'AIDC_CONTROLLABILITY_SCORES.csv',aidc);table(REPORT/'MESS_CONTROLLABILITY_SCORES.csv',mess)
    table(REPORT/'FINAL_JOINT_CANDIDATE_SCORES.csv',combined)
    np.savez_compressed(REPORT/'FINAL_SEVEN_TIME_DERIVATIVES.npz',slots=slots,candidate_ids=first['candidate_ids'],line_indices=first['line_indices'],weights=weights,d_rho_d_consumption=derivative)
    write(REPORT/'FINAL_CANDIDATE_SCORE_FREEZE.json',dict(PASS=True,seven_slots=slots.tolist(),
        input_archives=[receipt(REPORT/'CANDIDATE_CRITICAL_LINE_PQ_DERIVATIVES.npz'),receipt(REPORT/'CANDIDATE_PEAK_SUPPLEMENT_DERIVATIVES.npz')],
        score=receipt(REPORT/'FINAL_JOINT_CANDIDATE_SCORES.csv'),all_original_sites_jobs_and_PF=True,Native_calls=0,no_Actual_or_policy_outcome_used=True))


if __name__=='__main__':
    import sys
    merge_scores() if 'merge' in sys.argv else run()
