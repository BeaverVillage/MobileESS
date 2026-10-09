"""Frozen multi-time, multi-corridor AC candidate screen (not dispatch proof)."""
import time
import numpy as np
from ieee8500_v42_high.common import ROOT,REPORT as HIGH,read,write,rows,table,receipt,MAPPING
from ieee8500_v42_high.engine import HighEngine

REPORT=ROOT/'docs/ieee8500_v42_joint_pcc_reselection'
SLOTS=[0,9,48,68,72,75]


def prepare():
    REPORT.mkdir(parents=True,exist_ok=True);folder=HIGH/'ac/E1R_C0_BG0.850'
    axes=read(folder/'AC_AXES.json');base=dict(np.load(folder/'AC_96.npz'));groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    ranked=sorted(groups,key=lambda n:(-float(base['line_rho'][:,groups[n]].max()),n))
    targets=ranked[:20]
    for phase in (1,2,3):
        candidates=[n for n in ranked if any(axes['lines'][i]['group']=='Primary' and axes['lines'][i]['node']==phase for i in groups[n])]
        candidates=sorted(candidates,key=lambda n:(-float(base['line_rho'][:,[i for i in groups[n] if axes['lines'][i]['node']==phase]].max()),n))
        targets.extend(candidates[:3])
    targets.extend([n for n in ranked if axes['lines'][groups[n][0]]['group']=='Triplex'][:10])
    targets.extend(r['binding_line'] for r in rows(folder/'SLOTS.csv'))
    targets=list(dict.fromkeys(targets));li=sorted({i for n in targets for i in groups[n]})
    # Every critical original line/phase is retained. Serial overlap is normalized
    # by exact topology adjacency and near-identical B0 flow trajectories.
    original=read(ROOT/'docs/ieee8500_v42_single_case/ORIGINAL_FEEDER_INVENTORY.json')
    buses={r['element']:{b.split('.')[0].lower() for b in r['buses']} for r in original['lines']}
    parent={n:n for n in targets}
    def find(n):
        while parent[n]!=n:n=parent[n]
        return n
    curves={n:base['line_rho'][:,groups[n]].max(axis=1) for n in targets}
    for a in targets:
        for b in targets:
            if a<b and buses[a]&buses[b] and np.max(np.abs(curves[a]-curves[b]))<=1e-5:
                parent[find(b)]=find(a)
    corridor={n:find(n) for n in targets};sizes={c:list(corridor.values()).count(c) for c in set(corridor.values())}
    weights=np.array([max(float(curves[axes['lines'][i]['element']].max()),.05)**2 /
        sizes[corridor[axes['lines'][i]['element']]] /len(groups[axes['lines'][i]['element']]) for i in li]);weights/=weights.sum()
    prereg=dict(schema='JOINT_MULTICORRIDOR_CANDIDATE_AC_V1',baseline=receipt(folder/'RECEIPT.json'),
        baseline_BG=.85,installed_GPU=780,baseline_mapping=receipt(MAPPING),source='PLANNING',probe_slots=SLOTS,
        target_rule='top20global+top3Primaryeachphase+top10Triplex+all96binding; adjacent near-identical serial flows normalized',
        targets=targets,line_axes_indices=li,corridors=corridor,weights=weights.tolist(),
        symmetric_step_kw_kvar=1.,finite_derivative_scope='fixed original automatic-settled B0 controls, mathematical PCC perturbation only',
        MV_probe='balanced3phase primary equivalent; final selected MV ports require dedicated750kVA480V TX and actual current gate',
        LV_probe='240Vsplit-phase, same two original hot nodes; final endpoints <=5kW3kvar6kVA27A',
        AIDC_score='mean weighted coupled known-mask relaxation sensitivity, all original jobs unchanged; certified nonzero96 bound=UNPROVEN',
        AIDC_total_load_impact_separate=True,PF=.95,
        MESS_score='mean normalized multiple-corridor signed P/Q response, reachable original traffic proxy weighting; no site full450kW Bphase injection',
        MESS_level_reference='M3 primary450kW orLV5kW, Q screening300kvar orLV3kvar; nonlinear security can tighten',
        candidate_score='mean weighted positive P relief+0.25absolute Q response, minus negative-P/new-bottleneck response; site ETA weighting; geometry/dispersal hard constraints dominate',
        full_global_phase_rating_and_voltage_checked_at_final_endpoints=True,Native_calls=0,
        geometry_selection_uses_Actual=False,policy_result_based_siting=False,global_optimality_claim=False)
    path=REPORT/'CONTROLLABILITY_PREREGISTRATION.json'
    if path.exists():assert read(path)==prereg
    else:write(path,prereg)
    table(REPORT/'CRITICAL_CORRIDOR_BASELINE.csv',[dict(line=n,group=axes['lines'][groups[n][0]]['group'],
        max96_rho=float(curves[n].max()),peak_slot=int(curves[n].argmax()),corridor=corridor[n],corridor_line_count=sizes[corridor[n]]) for n in targets])
    return axes,base,li,weights,folder


def run():
    begin=time.perf_counter();axes,base,li,weights,folder=prepare();candidates=rows(REPORT/'STA_MV_LV_CANDIDATES.csv')
    states=read(folder/'CONTROL_STATES.json');data=dict(np.load(ROOT/'ieee8500_v42_high/data/facility/recomputed/C0_PLANNING_INPUTS.npz'))
    e=HighEngine('CANDIDATE_AC',.85,report_dir=REPORT);mv=next(r for r in candidates if r['candidate_id'].startswith('MV:'))
    lv=next(r for r in candidates if r['candidate_id'].startswith('LV:'));e.add_pcc('PROBE_MV',mv['candidate_bus']);e.add_pcc('PROBE_LV',lv['candidate_bus'],'LV_SPLIT_240')
    result=np.zeros((len(SLOTS),len(candidates),2,len(li)));checks=[];max_error=0.
    for kt,t in enumerate(SLOTS):
        e.apply_inputs(t,data);a=e.settle('fixed',states[t]);error=float(np.abs(a['line_rho']-base['line_rho'][t]).max())
        assert error<1e-7;max_error=max(max_error,error)
        for k,r in enumerate(candidates):
            mode='MV' if r['candidate_id'].startswith('MV:') else 'LV';pid='PROBE_'+mode;load=e.pccs[pid]['element'];bus=r['candidate_bus']
            e.d.Text.Command(f'edit {load} bus1={bus}.1.2.3' if mode=='MV' else f'edit {load} bus1={bus}.1.2')
            endpoints=[]
            for dim in (0,1):
                samples=[]
                for sign in (-1.,1.):
                    e.d.Loads.Name(load.split('.',1)[1]);e.d.Loads.kW(sign if dim==0 else 0.);e.d.Loads.kvar(sign if dim==1 else 0.)
                    a=e.settle('fixed');samples.append(a['line_rho'][li].copy())
                    endpoints.append((float(a['node_voltage_pu'].min()),float(a['node_voltage_pu'].max()),float(a['line_rho'].max())))
                result[kt,k,dim]=(samples[1]-samples[0])/2
            e.d.Loads.Name(load.split('.',1)[1]);e.d.Loads.kW(0.);e.d.Loads.kvar(0.)
            checks.append(dict(slot=t,candidate_id=r['candidate_id'],symmetric_1kW_1kvar=True,
                probe_minV=min(x[0] for x in endpoints),probe_maxV=max(x[1] for x in endpoints),probe_global_rho_max=max(x[2] for x in endpoints),
                fixed_controls=True,full_MV_hardware_or_schedule_certificate=False))
            if (k+1)%300==0:
                write(REPORT/'CANDIDATE_AC_PROGRESS.json',dict(completed_slots=kt,slot=t,completed_candidates=k+1,total_candidates=len(candidates),Native_calls=0))
                print('CandidateAC',t,k+1,'/',len(candidates),flush=True)
        np.savez_compressed(REPORT/'CANDIDATE_CRITICAL_LINE_PQ_DERIVATIVES.npz',slots=np.array(SLOTS),candidate_ids=np.array([r['candidate_id'] for r in candidates]),
            line_indices=np.array(li),weights=weights,d_rho_d_consumption=result,completed_slots=np.array(kt+1))
    table(REPORT/'CANDIDATE_SMALL_SIGNAL_AC_CHECKS.csv',checks)
    scored=[];aidc=[];mess=[];qf=np.tan(np.arccos(.95));sites=list(map(str,data['sites']))
    traffic=rows(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv')
    ready={}
    for row in traffic:
        # Scores use only readiness from the original day-start departure.
        if float(row.get('departure_slot',-1))==0:ready.setdefault(row['destination_STA'],[]).append(900*float(row['earliest_day0_ready_slot']))
    for site in [f'AIDC{i:02d}' for i in range(1,13)]+[f'STA{i:02d}' for i in range(1,13)]:
        for k,r in enumerate(candidates):
            mv=r['candidate_id'].startswith('MV:')
            if site.startswith('AIDC') and not mv:continue
            dp=result[:,k,0];dq=result[:,k,1]
            if site.startswith('AIDC'):
                j=sites.index(site);bound=data['source_mask_P_upper_bound_kw'][SLOTS,j];P=data['PCC_P_kw'][SLOTS,j]
                relief=(dp+qf*dq)*bound[:,None];total=(dp+qf*dq)*P[:,None]
                value=float((relief@weights).mean());negative=float((np.maximum(-relief,0)@weights).mean())
                out=dict(location_id=site,candidate_id=r['candidate_id'],candidate_bus=r['candidate_bus'],electrical_region=r['electrical_region'],
                    score=value-negative,source_mask_relaxation_P_max_kw=float(bound.max()),certified_flexible_P_kw=0.,
                    certified_nonzero_dispatch='NOT_CERTIFIED',mean_total_AIDC_load_effect_rho=float((total@weights).mean()),
                    mean_relaxation_relief_rho=value,independent_Q=False,flexible_workload_multiplier=1)
                aidc.append(out)
            else:
                p=450. if mv else 5.;q=300. if mv else 3.
                reachable=np.array([sum(x<=900*t for x in ready.get(site,[]))/6 for t in SLOTS])
                relief=dp*p;value=float(((np.maximum(relief,0)+.25*np.abs(dq*q)-np.maximum(-relief,0))@weights*reachable).mean())
                out=dict(location_id=site,candidate_id=r['candidate_id'],candidate_bus=r['candidate_bus'],electrical_region=r['electrical_region'],
                    score=value,P_screening_kw=p,Q_screening_kvar=q,mean_reachable_vehicle_fraction=float(reachable.mean()),
                    mean_signed_P_relief_rho=float((relief@weights).mean()),mean_Q_response_rho=float((np.abs(dq*q)@weights).mean()),
                    hardware_actual_current_gate='FINAL_NONLINEAR_REQUIRED',field_ETA_access='UNVERIFIED',schedule_certificate=False)
                mess.append(out)
            scored.append(dict(location_id=site,candidate_id=r['candidate_id'],score=out['score']))
    table(REPORT/'AIDC_CONTROLLABILITY_SCORES.csv',aidc);table(REPORT/'MESS_CONTROLLABILITY_SCORES.csv',mess)
    table(REPORT/'JOINT_CANDIDATE_SCORES.csv',scored)
    write(REPORT/'CANDIDATE_AC_RECEIPT.json',dict(PASS=True,candidates=len(candidates),MV_candidates=sum(r['candidate_id'].startswith('MV:') for r in candidates),
        LV_candidates=sum(r['candidate_id'].startswith('LV:') for r in candidates),probe_slots=SLOTS,AC_calls=6*(1+4*len(candidates)),
        baseline_maximum_rho_error=max_error,parameters=e.verify_parameters(),derivative_archive=receipt(REPORT/'CANDIDATE_CRITICAL_LINE_PQ_DERIVATIVES.npz'),
        no_policy_or_Actual_used=True,Native_calls=0,physical_dispatch_certified=False,runtime_seconds=time.perf_counter()-begin))


if __name__=='__main__':run()
