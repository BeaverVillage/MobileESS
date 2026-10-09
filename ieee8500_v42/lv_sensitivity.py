"""Preregistered all-customer LV AC response, simulation design only.

Positive P/Q denotes injection. Existing split-phase transformers and original
Triplex conductors are retained. This module never imports a Native solver,
reconstructs workload schedules, or writes historical sensitivity outputs.
"""
from __future__ import annotations

import collections
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import time
from pathlib import Path
import numpy as np

from .ac import IEEE8500AC, _complex
from .capacity import FIXED_AIDC
from .common import ROOT, DATA, REPORT, read, write, table, receipt, sha
from .geometry import read_csv

SLOTS = (0, 9, 48, 75)
STEP = .1
BG = .552
FOLDER = REPORT / 'joint_selection_v3' / 'lv_sensitivity'
BASE_POWER = DATA / 'v42_inputs' / 'PLANNING_PHYSICAL.npz'


def freeze_policy():
    """Persist candidate and endpoint definitions before constructing DSS."""
    candidates = sorted(read_csv(REPORT / 'LV_STA_CANDIDATES.csv'), key=lambda r:r['candidate_bus'])
    if len(candidates) != 1177 or len({r['candidate_bus'] for r in candidates}) != 1177:
        raise ValueError('ALL_1177_ORIGINAL_CUSTOMER_BUSES_REQUIRED')
    v2 = REPORT / 'joint_selection_v2/sensitivity/PREREGISTRATION.json'
    line_set = read(v2)['line_set']
    if len(line_set) != 20 or len(set(line_set)) != 20:
        raise ValueError('PREDEFINED_20_LINE_SET_INVALID')
    inv = read(REPORT / 'ORIGINAL_FEEDER_INVENTORY.json')
    inputs = {name: receipt(path) for name, path in {
        'LV_source_inventory': REPORT / 'LV_STA_CANDIDATES.csv',
        'original_electrical_inventory': REPORT / 'ORIGINAL_FEEDER_INVENTORY.json',
        'predefined_v2_lines': v2, 'unchanged_V42_REFERENCE_power': BASE_POWER,
        'V42_power_authority': DATA / 'v42_inputs/POWER_AUTHORITY.json',
        'V42_planning_bundle': DATA / 'v42_inputs/PLANNING_INPUT_BUNDLE.json',
        'AC_engine_source': ROOT / 'ieee8500_v42/ac.py',
        'LV_auditor_source': Path(__file__),
    }.items()}
    policy = dict(schema='ALL_LV_AC_SENSITIVITY_V3', scope='SIMULATION_DESIGN_NOT_FIELD',
        development_date='2025-05-01', already_exposed_date=True, independent_validation_date=None,
        B1_B2_B3_results_used=False, candidate_count=1177,
        candidate_buses=[r['candidate_bus'] for r in candidates],
        probe_ids=[f'LVv3{k:04d}' for k in range(1,1178)],
        connection_mode='LV_SPLIT_240: one phase constant-power delta across original hot nodes 1/2',
        coordinates='upstream primary proxy; unknown CRS; customer survey not claimed',
        new_customer_transformers=0, original_CT_Triplex_ratings_unchanged=True,
        background_scale=BG, background_shape='static original customer P/Q times .552',
        AIDC_map=FIXED_AIDC, AIDC_scale=1.0, workload='portable unchanged current V42 REFERENCE; historical v3 electrical hosts',
        MESS_base_power=0, reference_is_final_qualified_B0=False,
        source_pu=1.05, source_regulators_and_capacitors='all original policies and ratings',
        slots=list(SLOTS), delta_kw=STEP, delta_kvar=STEP,
        actual_endpoint_injection_PQ=[[-STEP,0],[STEP,0],[0,-STEP],[0,STEP]],
        planned_endpoint_AC_solves=1177*4*len(SLOTS),
        line_set=line_set, line_set_rule='unchanged v2 preregistration; no reranking from new probes',
        binding_phase_rule='highest baseline canonical parent-terminal phase per line; lexical axis order breaks ties',
        positive_sign='injection decreases positive PCC demand',
        controls='each sampled slot independently settles from original initial taps/caps; all endpoints restore that common settled state; controlmode off',
        all_original_axes_global_checks=True, endpoints_must_converge_and_controls_unchanged=True,
        neutral='original Kron reduced; inferred -(I_hot1+I_hot2); original independent neutral ampacity absent',
        assumed_hardware=dict(model='Schneider XW Pro 6848 NA simulation proposal',
            absolute_P_kw=5., absolute_Q_kvar=3., apparent_kva=6., hot_current_A=27.,
            status='SIMULATION_DESIGN_NOT_FIELD', full_rating_AC_test_in_this_run=False),
        local_linear_potential='intersect original local CT current/nameplate, every local Triplex hot, PCC node .95/1.05, assumed 5kW/3kvar and 27A voltage-dependent ceiling; first-order screening only',
        score_rule='maximum positive top20 rho relief over sampled slots/components using local first-order axis-only available bounds; no finite-dispatch prediction',
        unrelated_global_B0_violations='record FAIL, do not discard every local candidate based on unrelated source overvoltage',
        full_96_slot_port_qualification='NOT_EXECUTED; selected designs require actual +/-5kW,+/-3kvar and combined +/-5,+/-3 tests',
        reverse_power_protection='UNVERIFIED original protection; no invented reverse-flow ban or approval',
        physical_status='SIMULATION_DESIGN_NOT_FIELD', production_certificate=False,
        source_sha256=inv['source_sha256'], inputs=inputs, Native_calls=0, full_model_builds=0)
    dest=FOLDER/'PREREGISTRATION.json'
    if dest.exists() and read(dest) != policy:
        raise ValueError('PREREGISTRATION_DRIFT')
    write(dest,policy)
    table(FOLDER/'ALL_1177_PROBES.csv',[dict(probe_id=pid,bus=r['candidate_bus'],
        upstream_transformer=r['upstream_transformer'],upstream_primary_bus=r['upstream_primary_bus'],
        upstream_primary_phase=r['upstream_primary_phase'],proxy_x=r['proxy_x'],proxy_y=r['proxy_y'],
        coordinate_authority=r['coordinate_authority'],original_CT_kva=r['transformer_primary_kva'],
        original_Triplex_path=r['triplex_path'],simulation_design_status='SIMULATION_DESIGN_NOT_FIELD',
        actual_allowed_power_verified=False) for pid,r in zip(policy['probe_ids'],candidates)])
    return policy,candidates


def original_paths(engine):
    """Include the SourceBus reactor, which is absent from inventory collections."""
    adj=collections.defaultdict(list)
    equipment=list(engine.inventory['lines'])+list(engine.inventory['transformers'])
    for name in engine.d.Reactors.AllNames():
        engine.d.Reactors.Name(name)
        equipment.append(dict(element='Reactor.'+name,buses=engine.d.CktElement.BusNames(),
                              enabled=bool(engine.d.CktElement.Enabled())))
    for r in equipment:
        if not r['enabled']: continue
        u=r['buses'][0].split('.')[0].lower()
        for bus in r['buses'][1:]:
            v=bus.split('.')[0].lower()
            if u==v:continue
            adj[u].append((v,r['element'].lower()));adj[v].append((u,r['element'].lower()))
    parent={'sourcebus':None};edges={};todo=collections.deque(['sourcebus'])
    while todo:
        u=todo.popleft()
        for v,e in sorted(adj[u]):
            if v not in parent:parent[v]=u;edges[v]=e;todo.append(v)
    result={}
    for bus in parent:
        u=bus;path=set()
        while parent[u] is not None:path.add(edges[u]);u=parent[u]
        result[bus]=path
    return result


def linear_interval(base, derivative, lower, upper, hardware_limit):
    """Exact intersection of first-order affine bounds, not an AC certificate."""
    lo,hi=-float(hardware_limit),float(hardware_limit)
    for b,d,l,u in zip(base,derivative,lower,upper):
        if abs(float(d))<=1e-12:
            if b<l-1e-9 or b>u+1e-9:return (0.,0.,False)
            continue
        a,z=(l-b)/d,(u-b)/d
        lo=max(lo,min(a,z));hi=min(hi,max(a,z))
    if lo>hi+1e-9:return (0.,0.,False)
    return float(lo),float(hi),True


def global_check(a,base,mask):
    bv=base['node_voltage_pu'];v=a['node_voltage_pu']
    br=base['line_rho'];r=a['line_rho']
    btc=base['transformer_current_rho'];tc=a['transformer_current_rho']
    btk=base['transformer_winding_nameplate_kva_rho'];tk=a['transformer_winding_nameplate_kva_rho']
    return dict(canonical_rho_max=float(r[mask].max()),all_terminal_rho_max=float(r.max()),
        vmin_pu=float(v.min()),vmax_pu=float(v.max()),
        voltage_violation_cells=int(((v<.95)|(v>1.05)).sum()),line_overload_cells=int((r>1).sum()),
        CT_current_rho_max=float(tc.max()),CT_nameplate_kva_rho_max=float(tk.max()),
        CT_current_overload_cells=int((tc>1).sum()),CT_nameplate_overload_cells=int((tk>1).sum()),
        new_line_overload_cells=int(((r>1+1e-9)&(br<=1+1e-9)).sum()),
        new_voltage_violation_cells=int((((v<.95-1e-9)|(v>1.05+1e-9))&((bv>=.95-1e-9)&(bv<=1.05+1e-9))).sum()),
        new_CT_current_overload_cells=int(((tc>1+1e-9)&(btc<=1+1e-9)).sum()),
        new_CT_nameplate_overload_cells=int(((tk>1+1e-9)&(btk<=1+1e-9)).sum()),
        canonical_worst_axis=int(np.argmax(np.where(mask,r,-np.inf))),
        all_terminal_worst_axis=int(np.argmax(r)), vmin_axis=int(np.argmin(v)),vmax_axis=int(np.argmax(v)))


def read_pcc(engine,pid):
    engine.d.Circuit.SetActiveElement(engine.pccs[pid]['element'])
    powers=_complex(engine.d.CktElement.Powers())
    currents=_complex(engine.d.CktElement.Currents())
    if len(currents)!=2:raise ValueError('SPLIT_PHASE_PCC_MUST_HAVE_TWO_HOT_CONDUCTORS')
    return np.array([powers.real.sum(),powers.imag.sum()]),currents


def axes_for_candidate(engine,row):
    bus=row['candidate_bus'];tx=row['upstream_transformer'].lower()
    path=row['triplex_path'].split('|')
    local_line=np.array([i for i,r in enumerate(engine.line_axes) if r['element'].lower() in path],int)
    hot=np.full((len(path),2,2),-1,int);neutral=np.full((len(path),2),-1,int)
    for k,name in enumerate(path):
        for i,r in enumerate(engine.line_axes):
            if r['element'].lower()==name and r['node'] in (1,2):hot[k,r['terminal']-1,r['node']-1]=i
        for i,r in enumerate(engine.triplex_terminal_axes):
            if r['element'].lower()==name:neutral[k,r['terminal']-1]=i
    nodes=np.array([i for i,name in enumerate(engine.node_axes) if name.lower() in (bus+'.1',bus+'.2')],int)
    tx_current=np.array([i for i,r in enumerate(engine.transformer_axes) if r['element'].lower()==tx],int)
    tx_kva=np.array([i for i,r in enumerate(engine.transformer_winding_axes) if r['element'].lower()==tx],int)
    if len(nodes)!=2 or len(tx_kva)!=3 or (hot<0).any() or (neutral<0).any() or not len(local_line):
        raise ValueError('ORIGINAL_LOCAL_AXES_MISSING:'+bus)
    return dict(line=local_line,hot=hot,neutral=neutral,nodes=nodes,tx_current=tx_current,tx_kva=tx_kva,path=path)


def potential_interval(a0,d,local,component):
    b=np.concatenate([a0['line_rho'][local['line']],a0['transformer_current_rho'][local['tx_current']],
        a0['transformer_winding_nameplate_kva_rho'][local['tx_kva']],a0['node_voltage_pu'][local['nodes']]])
    der=np.concatenate([d['line_rho'][local['line']],d['transformer_current_rho'][local['tx_current']],
        d['transformer_winding_nameplate_kva_rho'][local['tx_kva']],d['node_voltage_pu'][local['nodes']]])
    low=np.zeros_like(b);up=np.ones_like(b);low[-2:]=.95;up[-2:]=1.05
    # Original LV node base is 0.208/sqrt(3), not exactly nameplate 120V.
    vll_ceiling=2*float(a0['node_voltage_pu'][local['nodes']].min())*.208/np.sqrt(3)*27
    hardware=min(5. if component=='P' else 3.,6.,vll_ceiling)
    return linear_interval(b,der,low,up,hardware)


def write_scores(policy,candidates,mat,intervals,completed_slots):
    rows=[]
    for k,r in enumerate(candidates):
        dr=mat[:completed_slots,k]
        iv=intervals[:completed_slots,k]
        valid=iv[:,:,2]>0
        positive=np.where(valid,np.maximum(iv[:,:,1],0),0)
        negative=np.where(valid,np.maximum(-iv[:,:,0],0),0)
        relief=np.maximum(np.maximum(-dr,0)*positive[:,:,None],np.maximum(dr,0)*negative[:,:,None])
        best=np.unravel_index(int(np.argmax(relief)),relief.shape)
        rows.append(dict(candidate_bus=r['candidate_bus'],probe_id=policy['probe_ids'][k],
            upstream_primary_bus=r['upstream_primary_bus'],upstream_primary_phase=r['upstream_primary_phase'],
            upstream_transformer=r['upstream_transformer'],proxy_x=r['proxy_x'],proxy_y=r['proxy_y'],
            sampled_slots_completed=completed_slots,all_planned_slots_complete=completed_slots==len(SLOTS),
            maximum_abs_dRho_P_per_kw=float(np.abs(dr[:,0]).max()),
            maximum_abs_dRho_Q_per_kvar=float(np.abs(dr[:,1]).max()),
            local_linear_P_injection_upper_kw=float(positive[:,0].max()),
            local_linear_P_consumption_upper_kw=float(negative[:,0].max()),
            local_linear_Q_injection_upper_kvar=float(positive[:,1].max()),
            local_linear_Q_consumption_upper_kvar=float(negative[:,1].max()),
            unqualified_upper_potential_rho_relief=float(relief[best]),
            upper_potential_slot=SLOTS[best[0]],upper_potential_component=('P','Q')[best[1]],
            upper_potential_line=policy['line_set'][best[2]],
            actual_finite_power_verified=False,physical_status='SIMULATION_DESIGN_NOT_FIELD',
            production_certificate=False))
    table(FOLDER/'CANDIDATE_SCORES.csv',rows)
    top=sorted(rows,key=lambda r:(-r['unqualified_upper_potential_rho_relief'],r['candidate_bus']))[:20]
    table(FOLDER/'TOP20_CANDIDATE_SCORES.csv',top)


def run():
    policy,candidates=freeze_policy()
    print('LVv3 preregistered',policy['candidate_count'],'customers; endpoint solves',policy['planned_endpoint_AC_solves'],flush=True)
    e=IEEE8500AC(output_dir=FOLDER/'dss')
    if e.source_hashes!=policy['source_sha256']:raise ValueError('FEEDER_SOURCE_IDENTITY_DRIFT')
    for site,bus in FIXED_AIDC.items():e.add_pcc(site,bus,'MV_3PH')
    for pid,r in zip(policy['probe_ids'],candidates):e.add_pcc(pid,r['candidate_bus'],'LV_SPLIT_240')
    with np.load(BASE_POWER,allow_pickle=False) as z:
        p=z['PCC_P_kw'];q=z['PCC_Q_kvar']
    sites=sorted(FIXED_AIDC)
    if p.shape!=(96,12) or q.shape!=p.shape:raise ValueError('REFERENCE_POWER_SHAPE_DRIFT')
    paths=original_paths(e)
    locals_=[axes_for_candidate(e,r) for r in candidates]
    maxpath=max(len(x['path']) for x in locals_);maxct=max(len(x['tx_current']) for x in locals_)
    n=len(candidates); shape=(4,n,2,2)
    drho=np.zeros((4,n,2,20));di=np.zeros_like(drho)
    actual=np.zeros(shape+(2,));hotcurrent=np.zeros(shape+(2,),complex)
    pathhot=np.full(shape+(maxpath,2,2),np.nan);pathneutral=np.full(shape+(maxpath,2),np.nan)
    localvoltage=np.zeros(shape+(2,));ctcurrent=np.full(shape+(maxct,),np.nan)
    ctcurrentrho=np.full_like(ctcurrent,np.nan);ctkva=np.zeros(shape+(3,),complex);ctkvarho=np.zeros(shape+(3,))
    endrho=np.zeros(shape+(20,));intervals=np.zeros((4,n,2,3));baserho=np.zeros((4,20));binding=np.zeros((4,20),int)
    pathintersection=np.array([[line in paths.get(r['candidate_bus'],set()) for line in policy['line_set']] for r in candidates],bool)
    if not all('reactor.hvmv_sub_hsb' in paths.get(r['candidate_bus'],set()) for r in candidates):
        raise ValueError('SOURCE_REACTOR_PATH_INCOMPLETE')
    write(FOLDER/'AXES.json',dict(line_set=policy['line_set'],lines=e.line_axes,nodes=e.node_axes,
        transformers=e.transformer_axes,windings=e.transformer_winding_axes,triplex_neutral=e.triplex_terminal_axes,
        objective_mask=e.objective_line_mask.tolist(),candidate_local_axes=[{key:(v.tolist() if isinstance(v,np.ndarray) else v)
            for key,v in local.items()} for local in locals_],
        axis_contract='slot,candidate,component P/Q,sign minus/plus injection,local equipment axes'))
    target=[np.array([i for i,a in enumerate(e.line_axes) if a['element'].lower()==line and e.objective_line_mask[i]],int) for line in policy['line_set']]
    if any(not len(x) for x in target):raise ValueError('CANONICAL_LINE_SET_AXIS_MISSING')
    baseline_records=[];summary=[];top20rows=[];validations=[];count=0;started=time.perf_counter()
    for t,slot in enumerate(SLOTS):
        base_demand={site:(float(p[slot,k]),float(q[slot,k])) for k,site in enumerate(sites)}
        base=e.solve(BG,base_demand,'auto',reset_controls=True)
        a0=e.measurement_arrays()
        if not a0['converged'] or not a0['control_actions_done'] or a0['control_queue_size']:
            raise ValueError('BASE_AC_CONTROLS_NOT_SETTLED')
        state=base['control_state']; binding[t]=[indices[int(np.argmax(a0['line_rho'][indices]))] for indices in target]
        baserho[t]=a0['line_rho'][binding[t]]
        baseline_records.append(dict(slot=slot,summary=base['summary'],control_state=state,
            all_original_axes=global_check(a0,a0,e.objective_line_mask),
            qualified_final_B0=False,reason='development equivalent; global source-voltage or thermal failures explicitly retained'))
        write(FOLDER/'BASELINE_SUMMARIES.json',baseline_records)
        for k,(pid,r,local) in enumerate(zip(policy['probe_ids'],candidates,locals_)):
            responses={}; endpoints={}
            for c,component in enumerate(('P','Q')):
                ends=[]
                for signindex,sign in enumerate((-1,1)):
                    changed=dict(base_demand);changed[pid]=(-sign*STEP,0.) if c==0 else (0.,-sign*STEP)
                    e.solve(BG,changed,'fixed',state,snapshot=False)
                    a=e.measurement_arrays();readback,ihot=read_pcc(e,pid)
                    expected=np.array(changed[pid])
                    if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
                        raise ValueError('ENDPOINT_AC_OR_CONTROL_NOT_SETTLED:'+pid)
                    if e.control_state()!=state:raise ValueError('ENDPOINT_TAP_CAP_DRIFT:'+pid)
                    if np.max(np.abs(readback-expected))>1e-6:raise ValueError('ACTUAL_PCC_POWER_READBACK_FAILED:'+pid)
                    actual[t,k,c,signindex]=readback;hotcurrent[t,k,c,signindex]=ihot
                    pathhot[t,k,c,signindex,:len(local['path'])]=a['line_amps'][local['hot']]
                    pathneutral[t,k,c,signindex,:len(local['path'])]=a['triplex_implied_neutral_amps'][local['neutral']]
                    localvoltage[t,k,c,signindex]=a['node_voltage_pu'][local['nodes']]
                    ctcurrent[t,k,c,signindex,:len(local['tx_current'])]=a['transformer_amps'][local['tx_current']]
                    ctcurrentrho[t,k,c,signindex,:len(local['tx_current'])]=a['transformer_current_rho'][local['tx_current']]
                    ctkva[t,k,c,signindex]=a['transformer_winding_complex_kva'][local['tx_kva']]
                    ctkvarho[t,k,c,signindex]=a['transformer_winding_nameplate_kva_rho'][local['tx_kva']]
                    endrho[t,k,c,signindex]=[float(a['line_rho'][indices].max()) for indices in target]
                    gc=global_check(a,a0,e.objective_line_mask)
                    summary.append(dict(slot=slot,probe_id=pid,bus=r['candidate_bus'],component=component,
                        injection_sign=sign,injection_step=STEP,actual_P_demand_kw=float(readback[0]),
                        actual_Q_demand_kvar=float(readback[1]),PCC_hot1_A=float(abs(ihot[0])),PCC_hot2_A=float(abs(ihot[1])),
                        PCC_implied_neutral_A=float(abs(ihot.sum())),PCC_vminpu=float(localvoltage[t,k,c,signindex].min()),
                        PCC_vmaxpu=float(localvoltage[t,k,c,signindex].max()),
                        local_Triplex_both_end_hot_max_A=float(np.nanmax(pathhot[t,k,c,signindex])),
                        local_Triplex_implied_neutral_max_A=float(np.nanmax(pathneutral[t,k,c,signindex])),
                        local_CT_current_rho_max=float(np.nanmax(ctcurrentrho[t,k,c,signindex])),
                        local_CT_nameplate_kva_rho_max=float(ctkvarho[t,k,c,signindex].max()),
                        converged=True,settled=True,taps_caps_equal_common_base=True,**gc,
                        physical_status='SIMULATION_DESIGN_NOT_FIELD',actual_full_rating_qualified=False))
                    ends.append(a);count+=1
                minus,plus=ends
                d={key:(plus[key]-minus[key])/(2*STEP) for key in ('line_amps','line_rho','node_voltage_pu',
                    'transformer_current_rho','transformer_winding_nameplate_kva_rho')}
                drho[t,k,c]=d['line_rho'][binding[t]];di[t,k,c]=d['line_amps'][binding[t]]
                intervals[t,k,c]=potential_interval(a0,d,local,component)
                responses[component]=d;endpoints[component]=ends
                for j,line in enumerate(policy['line_set']):
                    axis=e.line_axes[binding[t,j]]
                    top20rows.append(dict(slot=slot,probe_id=pid,bus=r['candidate_bus'],component=component,
                        line=line,baseline_binding_terminal=axis['terminal'],baseline_binding_node=axis['node'],
                        baseline_canonical_rho=float(baserho[t,j]),dI_A_per_unit=float(di[t,k,c,j]),
                        dRho_pu_per_unit=float(drho[t,k,c,j]),source_path_contains_line=bool(pathintersection[k,j]),
                        minus_injection_line_rho_max=float(endrho[t,k,c,0,j]),plus_injection_line_rho_max=float(endrho[t,k,c,1,j]),
                        simulation_design_status='SIMULATION_DESIGN_NOT_FIELD',actual_full_rating_qualified=False))
            if k==0:
                half=e.local_injection_sensitivity(pid,BG,base_demand,STEP/2,STEP/2,'fixed',base)
                for component in ('P','Q'):
                    error=float(np.max(np.abs(responses[component]['line_amps']-half['derivatives'][component]['line_amps'])))
                    validations.append(dict(slot=slot,probe_id=pid,component=component,
                        half_step_max_dI_difference_A_per_unit=error,PASS=error<.01))
                count+=4
            if (k+1)%100==0 or k==n-1:
                write(FOLDER/'PROGRESS.json',dict(slot=slot,completed_candidates=k+1,total_candidates=n,
                    endpoint_solves=count,elapsed_seconds=time.perf_counter()-started,Native_calls=0))
                print('LVv3 slot',slot,'customer',k+1,'/',n,'solves',count,'elapsed',round(time.perf_counter()-started,1),flush=True)
        table(FOLDER/f'PCC_ENDPOINT_SUMMARY_SLOT_{slot:02d}.csv',[r for r in summary if r['slot']==slot])
        table(FOLDER/f'TOP20_RESPONSE_SLOT_{slot:02d}.csv',[r for r in top20rows if r['slot']==slot])
        write_scores(policy,candidates,drho,intervals,t+1)
        np.savez_compressed(FOLDER/f'LV_SLOT_{slot:02d}.npz',
            candidate_bus=np.array(policy['candidate_buses']),probe_id=np.array(policy['probe_ids']),
            line=np.array(policy['line_set']),slot=slot,component=np.array(['P','Q']),injection_sign=np.array([-1,1]),
            dRho=drho[t],dI=di[t],baseline_rho=baserho[t],baseline_binding_axis=binding[t],
            source_path_contains_line=pathintersection,actual_PQ_demand=actual[t],PCC_hot_complex_A=hotcurrent[t],
            Triplex_hot_A=pathhot[t],Triplex_implied_neutral_A=pathneutral[t],PCC_node_voltage_pu=localvoltage[t],
            CT_current_A=ctcurrent[t],CT_current_rho=ctcurrentrho[t],CT_winding_complex_kva=ctkva[t],
            CT_winding_nameplate_kva_rho=ctkvarho[t],endpoint_line_max_rho=endrho[t],local_linear_interval=intervals[t])
    table(FOLDER/'HALF_STEP_VALIDATION.csv',validations)
    files=sorted(p for p in FOLDER.iterdir() if p.is_file() and p.name not in ('RECEIPT.json','PROGRESS.json'))
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_ALL_1177_LV_SMALL_SIGNAL_AC_SIMULATION_DESIGN',
        candidates=n,slots=list(SLOTS),central_P_Q_rows=n*2*4,central_endpoint_AC_solves=n*4*4,
        validation_endpoint_AC_solves=16,total_endpoint_AC_solves=count,base_AC_solves=4,
        canonical_line_response_rows=len(top20rows),all_endpoints_converged=True,
        all_common_taps_caps_unchanged=True,all_actual_P_Q_readbacks_PASS=True,
        half_step_validation_PASS=all(r['PASS'] for r in validations),source_unchanged=e.verify_source_unchanged(),
        full_96_slot_selected_port_AC_qualification=False,full_assumed_hardware_rating_qualified=False,
        neutral_rating_absent=True,source_voltage_global_baseline_qualified=False,
        physical_status='SIMULATION_DESIGN_NOT_FIELD',production_certificate=False,
        Native_calls=0,full_model_builds=0,elapsed_seconds=time.perf_counter()-started,
        artifacts={p.name:receipt(p) for p in files}))
    print('LVv3 complete',count,'endpoint solves',flush=True)


if __name__=='__main__':run()
