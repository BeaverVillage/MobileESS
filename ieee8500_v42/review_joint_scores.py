"""Independent archived-score reconstruction; no producer import, AC or Native."""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import ROOT,DATA,REPORT,read,write,receipt,sha

FOLDER=REPORT/'joint_selection_v3/selection_scores'
LV=REPORT/'joint_selection_v3/lv_sensitivity'
MV=REPORT/'joint_selection_v3/mv_sensitivity'


def merit(change):
    return float(np.mean(np.where(change<=0,-change,-2*change)))


def review():
    policy=read(FOLDER/'PREREGISTRATION.json')
    score=pd.read_csv(FOLDER/'CANDIDATE_SELECTION_SCORES.csv')
    components=pd.read_csv(FOLDER/'STA_SCORE_MOBILITY_AND_Q.csv')
    flex=pd.read_csv(REPORT/'FLEXIBLE_WORKLOAD_AUDIT.csv')
    mv=pd.read_csv(MV/'TOP20_RESPONSE.csv')
    sourcefleet=DATA/'research_case/PAPER_FLEET_BASE_AUTHORITY.json'
    originalfleet=ROOT.parent/'IEEE8500_PAPER_SCALE_ONLY_20260920/full_production_paper_BG055200_AIDC240_MESS200/PAPER_FLEET_BASE_AUTHORITY.json'
    if sha(sourcefleet)!=sha(originalfleet):raise ValueError('ORIGINAL_SIX_FLEET_COPY_IDENTITY_FAILED')
    fleet=read(sourcefleet)
    expected_initial={'MESS01':'STA01','MESS02':'STA12','MESS03':'STA08','MESS04':'STA06','MESS05':'STA03','MESS06':'STA10'}
    if fleet['initial_locations']!=expected_initial or policy['original_six_initial_locations']!=expected_initial:
        raise ValueError('ORIGINAL_SIX_INITIAL_LOCATIONS_CHANGED')
    for _,r in policy['frozen_inputs'].items():
        if sha(Path(r['path']))!=r['sha256']:raise ValueError('FROZEN_SCORE_INPUT_SHA_DRIFT')
    if len(score)!=21396 or score.duplicated(['location_id','candidate_bus']).any():
        raise ValueError('JOINT_SCORE_21396_UNIQUE_SITE_PAIRS_REQUIRED')
    if len(components)!=56496 or components.duplicated(['location_id','candidate_bus','slot']).any():
        raise ValueError('STA_COMPONENT_56496_COVERAGE_REQUIRED')
    counts=score.groupby(['role','location_id']).size()
    if any(counts[role,site]!=(606 if role=='AIDC' else 1177) for role,site in counts.index) or len(counts)!=24:
        raise ValueError('JOINT_SITE_CANDIDATE_COVERAGE_FAILED')
    if len(mv)!=606*4*20 or mv.duplicated(['bus','slot','line']).any():raise ValueError('MV_ALL_TARGET_AXIS_COVERAGE_FAILED')
    if set(mv.slot)!=set(policy['slots']) or set(mv.line)!=set(policy['targets']):raise ValueError('FROZEN_MV_LINE_TIME_MISMATCH')
    formula=flex.eligible_union_active_GPU*flex.C1_slope*flex.IT_swing_kW_per_GPU
    flexerr=float(np.abs(formula-flex.known_only_reducible_P_upper_bound_kW).max())
    if flexerr>1e-10 or (flex.eligible_union_active_GPU>flex.known_active_GPU+1e-10).any():
        raise ValueError('KNOWN_ONLY_ACTIVE_GPU_FLEX_FORMULA_FAILED')
    if flex.anonymous_CC4_in_bound.any() or flex.installed_idle_in_bound.any():
        raise ValueError('ANONYMOUS_OR_IDLE_COUNTED_AS_FLEX')
    native=read(DATA/'workload_flexibility/NATIVE_INPUT.json')
    originaluids={str(r['job_uid']) for r in native['known_population']};unionerr=0.
    for r in flex.itertuples():
        jobs=json.loads(r.eligible_jobs_and_source_masks)
        if any(str(j['uid']) not in originaluids for j in jobs) or len({str(j['uid']) for j in jobs})!=len(jobs):
            raise ValueError('FLEX_UNKNOWN_OR_DUPLICATE_UID')
        unionerr=max(unionerr,abs(sum(j['active_gpu'] for j in jobs)-r.eligible_union_active_GPU))
    if unionerr>1e-10:raise ValueError('KNOWN_UID_UNION_ACTIVE_GPU_MISMATCH')
    ratio=float(np.sqrt(1-.95**2)/.95)
    pferr=float(np.abs(mv.dRho_AIDC_PF95_per_kw-(mv.dRho_P_per_kw+ratio*mv.dRho_Q_per_kvar)).max())
    qerr=float(np.abs(flex.coupled_Q_reduction_upper_bound_kvar-ratio*flex.known_only_reducible_P_upper_bound_kW).max())
    if pferr>1e-12 or qerr>1e-10:raise ValueError('FIXED_PF_QP_COUPLING_FAILED')
    # Score reconstruction uses arrays and direct signed merit, independent of
    # producer group/DataFrame operations. Every site/candidate is checked.
    keys=score.set_index(['location_id','candidate_bus']).score.to_dict()
    aidcerr=0.
    for site in sorted(flex.aidc_id.unique()):
        bounds=flex[flex.aidc_id.eq(site)].set_index('slot').known_only_reducible_P_upper_bound_kW.to_dict()
        for bus,g in mv.groupby('bus'):
            changes=np.array([float(row.dRho_AIDC_PF95_per_kw)*float(bounds[row.slot]) for row in g.itertuples()])
            aidcerr=max(aidcerr,abs(merit(changes)-keys[(site,bus)]))
    with gzip.open(DATA/'traffic_audit/ROUTE_TABLE.json.gz','rt',encoding='utf8') as stream:
        routes=json.load(stream)['routes']
    depart0={(r['origin_service_id'],r['destination_service_id']):r for r in routes if r['departure_slot_15']==0}
    reach={};etaerr=0.;same=0
    for site in [f'STA{k:02d}' for k in range(1,13)]:
        for slot in policy['slots']:
            ready=[]
            for origin in expected_initial.values():
                row=depart0[(origin,site)]
                ready.append(row['connection_ready_slots_15min'])
                if origin==site:
                    if row['connection_ready_slots_15min']!=0:raise ValueError('INITIAL_CONNECTED_STAY_MISMATCH')
                    same+=1
                else:
                    safe=row['route_safe_eta_sec']
                    etaerr=max(etaerr,abs(row['connection_ready_slots_15min']-np.ceil((safe+600)/900)))
            reach[(site,slot)]=sum(r<=slot for r in ready)/6
    if etaerr:raise ValueError('SAFE_ETA_600_SECOND_READY_SLOT_MISMATCH')
    with np.load(LV/'BASE_LOCAL.npz',allow_pickle=False) as z:
        base={name:z[name].copy() for name in z.files}
    source_axes=read(LV/'AXES.json')
    line_axes=source_axes['lines']
    compkeys=components.set_index(['location_id','candidate_bus','slot']).to_dict('index')
    staerr=0.;componenterr=0.;actionerr=0.;affineexcess=0.;localzero=True;points_checked=0;baseportcurrent=0.
    weighted={}
    for t,slot in enumerate(policy['slots']):
        with np.load(LV/f'LV_SLOT_{slot:02d}.npz',allow_pickle=False) as archive:
            a={name:archive[name] for name in archive.files}
            if list(a['component'])!=['P','Q'] or list(a['line'])!=policy['targets'] or a['dRho'].shape!=(1177,2,20):
                raise ValueError('LV_NPZ_COMPONENT_AXIS_ORDER_MISMATCH')
            iv=a['local_linear_interval'];localzero=localzero and bool(((iv[:,:,0]<=0)&(iv[:,:,1]>=0)&(iv[:,:,2]>0)).all())
            for k,bus in enumerate(a['candidate_bus']):
                # Reconstruct every affine local constraint from actual +/- .1
                # endpoint values and exact independently reproduced base values.
                local=source_axes['candidate_local_axes'][k];pathcount=len(local['path']);ctcount=len(local['tx_current'])
                hotb=base['Triplex_hot_A'][t,k,:pathcount].ravel()
                hotrating=np.repeat(base['Triplex_normal_amps'][k,:pathcount],4)
                b=np.r_[hotb/hotrating,base['CT_current_rho'][t,k,:ctcount],
                    base['CT_winding_nameplate_kva_rho'][t,k],base['PCC_node_voltage_pu'][t,k]]
                hote=a['Triplex_hot_A'][k,:,:,:pathcount].reshape(2,2,-1)/hotrating
                ce=a['CT_current_rho'][k,:,:,:ctcount];ke=a['CT_winding_nameplate_kva_rho'][k]
                ve=a['PCC_node_voltage_pu'][k]
                derivative=np.concatenate([(hote[:,1]-hote[:,0])/.2,(ce[:,1]-ce[:,0])/.2,
                    (ke[:,1]-ke[:,0])/.2,(ve[:,1]-ve[:,0])/.2],axis=1)
                lower=np.zeros_like(b);upper=np.ones_like(b);lower[-2:]=.95;upper[-2:]=1.05
                pmax=min(5.,max(0.,float(iv[k,0,1]))) if iv[k,0,2] else 0.
                qminus=min(3.,max(0.,-float(iv[k,1,0]))) if iv[k,1,2] else 0.
                qplus=min(3.,max(0.,float(iv[k,1,1]))) if iv[k,1,2] else 0.
                actions=[(0.,0.),(pmax,0.),(0.,-qminus),(0.,qplus),(pmax/2,-qminus/2),(pmax/2,qplus/2)]
                merits=[]
                for p,q in actions:
                    predicted=b+p*derivative[0]+q*derivative[1]
                    affineexcess=max(affineexcess,float(np.maximum(lower-predicted,0).max()),float(np.maximum(predicted-upper,0).max()))
                    if abs(p)>5+1e-9 or abs(q)>3+1e-9 or np.hypot(p,q)>6+1e-9:
                        raise ValueError('ASSUMED_HARDWARE_BOX_OR_S_VIOLATION')
                    baseportcurrent=max(baseportcurrent,float(np.hypot(p,q)*1000/base['PCC_line_to_line_voltage_V'][t,k]))
                    points_checked+=1;merits.append(merit(a['dRho'][k,0]*p+a['dRho'][k,1]*q))
                # Match the frozen deterministic equal-merit preference without
                # optimizing separately for each of the twenty target lines.
                idx=max(range(6),key=lambda j:(merits[j],-abs(actions[j][1]),-actions[j][0],-actions[j][1]))
                pbest,qbest=actions[idx];best=merits[idx]
                for number in range(1,13):
                    site=f'STA{number:02d}';row=compkeys[(site,str(bus),slot)]
                    value=best*reach[(site,slot)]*.5
                    componenterr=max(componenterr,abs(row['potential_score_before_mobility']-best),
                        abs(row['initial_fleet_reachable_fraction']-reach[(site,slot)]),abs(row['weighted_score']-value))
                    actionerr=max(actionerr,abs(row['P_design_choice_kw']-pbest),abs(row['Q_design_choice_kvar']-qbest))
                    weighted.setdefault((site,str(bus)),[]).append(value)
    for key,values in weighted.items():staerr=max(staerr,abs(float(np.mean(values))-keys[key]))
    if max(aidcerr,staerr,componenterr,actionerr)>1e-10 or affineexcess>1e-9 or not localzero:
        raise ValueError('INDEPENDENT_SCORE_OR_LOCAL_AFFINE_BOUND_MISMATCH')
    physics=read(DATA/'traffic_audit/MOBILITY_PHYSICS.json')
    if physics['parameters']['gross_vehicle_mass_kg']!=28000:raise ValueError('ORIGINAL_28_TON_PHYSICS_CHANGED')
    port=read(REPORT/'LV_PORT_SIMULATION_DESIGN.json')
    if (port['vehicle_main_PCS_kw_NOT_LV_port'],port['vehicle_main_PCS_kva_NOT_LV_port'],port['vehicle_main_energy_kwh_NOT_port_output'])!=(450,600,1800):
        raise ValueError('USER_VEHICLE_RESEARCH_RATING_MISMATCH')
    report=dict(status='PASS_INDEPENDENT_JOINT_SCORE_RECONSTRUCTION',site_candidate_rows=21396,
        AIDC_rows=12*606,STA_rows=12*1177,STA_time_component_rows=56496,all20_lines_all4_times=True,
        flex_known_UID_population=1649,flex_power_formula_error=flexerr,UID_union_GPU_error=unionerr,
        no_CC4_idle_or_all_facility_power_in_flex=True,PF95_ratio=ratio,PF_coupled_derivative_error=pferr,
        PF_coupled_power_error=qerr,AIDC_score_maximum_error=aidcerr,STA_score_maximum_error=staerr,
        STA_component_maximum_error=componenterr,common_PQ_action_maximum_error=actionerr,
        origin_local_affine_feasible_for_every_1177_and4=True,affine_actions_checked=points_checked,
        affine_local_original_rating_and_voltage_maximum_excess=affineexcess,
        convex_mixed_action='half of each individually feasible axis endpoint; common20-line P/Q vector',
        original_six_initial_locations=expected_initial,original_fleet_copied_SHA_equal=True,
        original_fleet_source_sha_proof=dict(path=str(originalfleet),sha256=sha(originalfleet),
            bytes=originalfleet.stat().st_size,copied_source=receipt(sourcefleet)),
        unchanged_source_fleet_physical=fleet['physical'],user_research_vehicle_P_PCS_E=[450,600,1800],
        vehicle_research_ratings_are_1p5_scaled_assumptions=True,road_physics_mass_kg=28000,
        ETA_delay_ready_slot_maximum_error=etaerr,initial_stays_assumed_already_connected=True,
        maximum_assumed_port_current_at_exact_baseline_VLL_A=baseportcurrent,
        base_voltage_current_check_is_not_finite_power_endpoint_qualification=True,
        fleet_exposure=.5,exposure_is_heuristic_not_dispatch=True,energy_SOC_optimization_in_score=False,
        baseline_global_voltage_qualified=False,score_sum_is_not_global_minrho_or_dispatch_improvement=True,
        independent_test_day=None,production_ready=False,Native_calls=0,AC_solves=0,full_model_builds=0,
        limitations=['Derivative and known-only power bounds are local relaxations; original service/QoS/WAN/restart coupling is not solved',
            'One-time initial-origin ETA reachability does not plan subsequent moves, route conflicts, SoC or simultaneous dock ownership',
            'Local zero feasibility was checked in this frozen dataset; future locally infeasible baselines require a zero-feasibility guard before convex mixing',
            'Original unknown CRS/proxy topology mapping cannot prove physical road accessibility',
            'Four exposed development times and surrogate sum do not predict whole-day B3 minrho or hidden-day performance',
            'Source CT normal current and strict winding nameplate kVA remain distinct; absent neutral rating remains unresolved'],
        inputs={str(p.relative_to(ROOT)):receipt(p) for p in [Path(__file__),ROOT/'ieee8500_v42/joint_scores.py',
            FOLDER/'PREREGISTRATION.json',FOLDER/'PHYSICAL_MARGIN_REVIEW_AMENDMENT.json',
            FOLDER/'CANDIDATE_SELECTION_SCORES.csv',FOLDER/'STA_SCORE_MOBILITY_AND_Q.csv',
            MV/'TOP20_RESPONSE.csv',REPORT/'FLEXIBLE_WORKLOAD_AUDIT.csv',sourcefleet,
            DATA/'traffic_audit/ROUTE_TABLE.json.gz',DATA/'traffic_audit/MOBILITY_PHYSICS.json',
            REPORT/'LV_PORT_SIMULATION_DESIGN.json',LV/'BASE_LOCAL.npz']+
            [LV/f'LV_SLOT_{t:02d}.npz' for t in policy['slots']]})
    write(FOLDER/'JOINT_SCORE_REVIEW.json',report)
    return report


if __name__=='__main__':print(review()['status'])
