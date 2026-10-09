"""Frozen development surrogate: actual job footprint, bounded dock, original ETA.

This candidate-selection surrogate never replaces the min-rho production
objective and never certifies a simultaneous A/M dispatch or a hidden test day.
"""
from __future__ import annotations
import argparse
import gzip,json,shutil
import numpy as np
import pandas as pd
from .common import ROOT,REPORT,DATA,read,write,table,receipt
from .sensitivity import SLOTS

FOLDER=REPORT/'joint_selection_v3/selection_scores'


def freeze():
    original=ROOT.parent/'IEEE8500_PAPER_SCALE_ONLY_20260920/full_production_paper_BG055200_AIDC240_MESS200/PAPER_FLEET_BASE_AUTHORITY.json'
    copied=DATA/'research_case/PAPER_FLEET_BASE_AUTHORITY.json';copied.parent.mkdir(parents=True,exist_ok=True)
    if not copied.exists():shutil.copyfile(original,copied)
    fleet=read(copied)
    initial=fleet['initial_locations']
    if len(initial)!=6:raise ValueError('ORIGINAL_SIX_UNIT_INITIAL_LOCATIONS_REQUIRED')
    policy=dict(schema='JOINT_CONTROLLABILITY_SCORE_V3',development_date='2025-05-01',already_exposed=True,
        earlier_v2_diagnostics_and_preliminary_v3_slot0_known=True,
        method_frozen_before_final_score_guided_location_selection=True,B1_B2_B3_results_used=False,
        slots=list(SLOTS),targets=read(REPORT/'joint_selection_v2/sensitivity/PREREGISTRATION.json')['line_set'],
        weighting='equal20 target lines and equal4 times; no single Triplex target; original source-parent baseline-binding phase',
        AIDC_action='known_only original-UID activeGPU times originalC1*swing footprint bound, PF.95 Q/Pcoupled',
        AIDC_bound_is_relaxation=True,anonymous_CC4_and_installed_idle_in_flex=False,
        STA_action='one common per-time P/Q vector for all20lines, intersected with original local AC-linear voltage/CT/Triplex margins; never separately optimize Q perline',
        STA_actions='P-only uses local positive-P bound; Q-only uses local +/-Q bound; mixed actions use half of each axis-only bound (convex-combination screen), all <=P5/Q3/S6/hot27',
        local_bound_certification='linear settled-control screening only; selected finite nonlinear96slot tests remain mandatory',
        STA_hardware=dict(P_max_kw=5.,Q_max_kvar=3.,S_max_kva=6.,hot_current_max_A=27.),
        response_score='mean over times/lines of (negative predicted dRho magnitude -2*positive predicted dRho); signed benefit allowed negative',
        STA_fleet_exposure=.5,STA_fleet_exposure_reason='6 vehicles/12 STA; heuristic equal exposure, not simultaneous12dock dispatch or a routing guarantee',
        original_six_initial_locations=initial,initial_units_assumed_already_connected=True,
        mobility_factor='fraction of6 original initial vehicles whose original departure0 connect-slot<=sampledslot, based on unchanged safeETA plus600s',
        mobility_energy_model='original28000kg traction physics retained as research assumption; no battery-mass reestimate or actualSUMO outcomes',
        geometry='all276pairs/552axis and original sourceguards, LV primaryproxy not certified customergeography',
        physical_eligibility='full-rating and96slot AC tests follow selection; no globalfeasibility inferred from local derivative',
        final_model_objective='UNCHANGED min overall canonical line phase current / original NormalAmps',
        global_optimality_claim=False,known_job_QoS_WAN_dispatch_certified=False,
        independent_eval_date=None,production_ready=False,
        frozen_inputs={str(p.relative_to(ROOT)):receipt(p) for p in (copied,REPORT/'FLEXIBLE_WORKLOAD_AUDIT.csv',
            REPORT/'LV_PORT_SIMULATION_DESIGN.json',DATA/'traffic_audit/ROUTE_TABLE.json.gz')})
    path=FOLDER/'PREREGISTRATION.json'
    if path.exists() and read(path)!=policy:raise ValueError('JOINT_SCORE_POLICY_DRIFT')
    write(path,policy)
    return policy


def run():
    policy=freeze()
    mvfile=REPORT/'joint_selection_v3/mv_sensitivity/TOP20_RESPONSE.csv'
    lvfiles=[REPORT/f'joint_selection_v3/lv_sensitivity/LV_SLOT_{t:02d}.npz' for t in SLOTS]
    if not mvfile.exists() or not all(f.exists() for f in lvfiles):raise ValueError('COMPLETE_ALL_CANDIDATE_RESPONSES_REQUIRED')
    mv=pd.read_csv(mvfile)
    if set(mv.slot)!=set(SLOTS):raise ValueError('FOUR_TIME_SCORE_COVERAGE_REQUIRED')
    if mv.bus.nunique()!=606:raise ValueError('ALL_SOURCE_CANDIDATES_REQUIRED')
    flex=pd.read_csv(REPORT/'FLEXIBLE_WORKLOAD_AUDIT.csv')
    routes=json.load(gzip.open(DATA/'traffic_audit/ROUTE_TABLE.json.gz','rt',encoding='utf8'))['routes']
    connections={(r['origin_service_id'],r['destination_service_id']):r['connection_ready_slots_15min']
        for r in routes if r['departure_slot_15']==0}
    initial=policy['original_six_initial_locations']
    score_rows=[];components=[]
    for site in sorted(flex.aidc_id.unique()):
        bounds=dict(zip(flex[flex.aidc_id.eq(site)].slot,flex[flex.aidc_id.eq(site)].known_only_reducible_P_upper_bound_kW))
        for bus,g in mv.groupby('bus',sort=True):
            effects=g.dRho_AIDC_PF95_per_kw.to_numpy()*g.slot.map(bounds).to_numpy()
            score=float(np.mean(np.maximum(-effects,0)-2*np.maximum(effects,0)))
            score_rows.append(dict(location_id=site,role='AIDC',candidate_bus=bus,score=score,
                score_source='ALL606_MV_BG0552_4TIME20LINE_KNOWN_UID_PF95_BOUND',
                available_flexible_power_certified=False,flexibility_upper_bound_kw=max(bounds.values()),
                vehicle_port_P_kw='',vehicle_port_Q_kvar='',actual_AC_full_rating_pass='PENDING',
                no_global_policy_performance_claim=True))
    frames=[]
    for t,f in zip(SLOTS,lvfiles):
        a=np.load(f,allow_pickle=False);dr=a['dRho'];lines=a['line'];buses=a['candidate_bus']
        if len(buses)!=1177 or list(lines)!=policy['targets']:raise ValueError('ALL_LV_TARGET_AXES_REQUIRED')
        frames.append(pd.DataFrame(dict(bus=np.repeat(buses,len(lines)),slot=t,line=np.tile(lines,len(buses)),
            P=dr[:,0,:].ravel(),Q=dr[:,1,:].ravel())))
    lvp=pd.concat(frames,ignore_index=True).set_index(['bus','slot','line'])
    intervals={}
    for t in SLOTS:
        a=np.load(REPORT/f'joint_selection_v3/lv_sensitivity/LV_SLOT_{t:02d}.npz',allow_pickle=False)
        for bus,iv in zip(a['candidate_bus'],a['local_linear_interval']):intervals[(str(bus),t)]=iv
    if lvp[['P','Q']].isna().any().any():raise ValueError('LV_PQ_PARTIAL_PAIRS_REQUIRED')
    for number in range(1,13):
        site=f'STA{number:02d}'
        reachable={t:sum(connections[(origin,site)]<=t for origin in initial.values())/6 for t in SLOTS}
        for bus,g in lvp.groupby(level='bus',sort=True):
            scores=[];qchoices=[]
            for t in SLOTS:
                gt=g.xs(t,level='slot')
                iv=intervals[(bus,t)]
                pcap=max(0.,min(5.,iv[0,1])) if iv[0,2]>0 else 0.
                qlo=max(0.,min(3.,-iv[1,0])) if iv[1,2]>0 else 0.
                qhi=max(0.,min(3.,iv[1,1])) if iv[1,2]>0 else 0.
                actions=((0.,0.),(pcap,0.),(0.,-qlo),(0.,qhi),(pcap/2,-qlo/2),(pcap/2,qhi/2))
                choices=[]
                for p,q in actions:
                    change=gt.P.to_numpy()*p+gt.Q.to_numpy()*q
                    choices.append((float(np.mean(np.maximum(-change,0)-2*np.maximum(change,0))),p,q))
                best,p,q=max(choices,key=lambda x:(x[0],-abs(x[2]),-x[1],-x[2]))
                scores.append(best*reachable[t]*.5);qchoices.append(q)
                components.append(dict(location_id=site,candidate_bus=bus,slot=t,P_design_choice_kw=p,Q_design_choice_kvar=q,
                    potential_score_before_mobility=best,initial_fleet_reachable_fraction=reachable[t],
                    fleet_exposure_factor=.5,weighted_score=scores[-1],feasible_dispatch_verified=False))
            score_rows.append(dict(location_id=site,role='STA',candidate_bus=bus,score=float(np.mean(scores)),
                score_source='ALL1177_LV_BG0552_4TIME20LINE_5KW3KVAR_COMMON_Q_VECTOR_INITIAL_ETA',
                available_flexible_power_certified=False,flexibility_upper_bound_kw='',vehicle_port_P_kw=5.,vehicle_port_Q_kvar=3.,
                actual_AC_full_rating_pass='PENDING',no_global_policy_performance_claim=True))
    table(FOLDER/'CANDIDATE_SELECTION_SCORES.csv',score_rows)
    table(FOLDER/'STA_SCORE_MOBILITY_AND_Q.csv',components)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_DEVELOPMENT_SURROGATE_NOT_DISPATCH',rows=len(score_rows),
        AIDC606_each12=True,LV1177_each12=True,no_post_B3_tuning=True,Native_calls=0,
        score_policy=receipt(FOLDER/'PREREGISTRATION.json'),responses=[receipt(mvfile)]+[receipt(f) for f in lvfiles],
        scores=receipt(FOLDER/'CANDIDATE_SELECTION_SCORES.csv')))
    print('joint candidate surrogate scores ready',len(score_rows),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze-only',action='store_true');a=p.parse_args()
    freeze() if a.freeze_only else run()
