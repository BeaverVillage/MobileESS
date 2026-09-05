"""Bounded stage state machine; no convergence loop and no second route search."""
from __future__ import annotations
from copy import deepcopy
import time
from .invariants import digest, route_sha, terminal_audit, monotone, joint_decision


def coordinate(a0, full_search, feedback, recourse, evaluate, authority, tolerance=1e-6):
    """Callbacks are Planning-only. Fresh/Actual are available only to the caller after return."""
    counts={'MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS':0,'SECOND_MESS_FULL_ROUTE_SEARCH_CALLS':0,
            'AIDC_FEEDBACK_PASSES':0,'FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS':0,'FRESH_CALLS_INSIDE_COOPT_LOOP':0}
    runtime={};objectives={};initial=deepcopy(a0)
    if terminal_audit(initial,initial)['status']!='PASS':
        raise ValueError('INVALID_ACCEPTED_A0_TERMINAL_AUTHORITY')
    objectives['J_A0']=float(evaluate(initial,None)['rho_max'])
    started=time.perf_counter();counts['MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS']+=1
    m1,search_info=full_search(deepcopy(initial));runtime['M1']=time.perf_counter()-started
    original_route=route_sha(m1.slots);original_trajectory=digest(m1)
    grid_m1=evaluate(initial,m1)
    if grid_m1['status']!='PASS':raise RuntimeError('M1_PLANNING_NOT_FEASIBLE')
    objectives['J_M1']=float(grid_m1['rho_max'])
    started=time.perf_counter();counts['AIDC_FEEDBACK_PASSES']+=1
    frozen_for_a1=deepcopy(m1)
    a1_result=feedback(deepcopy(initial),frozen_for_a1)
    runtime['A1']=time.perf_counter()-started
    if digest(frozen_for_a1)!=original_trajectory:raise RuntimeError('A1_MUTATED_FROZEN_M1')
    candidate=deepcopy(a1_result['jobs'])
    try:
        terminal=terminal_audit(initial,candidate)
        candidate_grid=evaluate(candidate,m1)
    except ValueError as error:
        terminal={'status':'FAIL','reason':str(error)}
        candidate_grid={'status':'FAIL','rho_max':float('inf'),'reason':str(error)}
        a1_result['candidate_validation_error']=str(error)
    # Additional RUNNING migration is forbidden by the user's explicit clarification.
    old={r['job_uid']:r for r in initial}
    running_unchanged=all(all(row[k]==old[row['job_uid']][k] for k in
        ('start_slot','end_slot','AIDC_site','migration_selected','migration_destination'))
        for row in candidate if row['state_at_issue']=='RUNNING')
    accepted=monotone(objectives['J_M1'],float(candidate_grid['rho_max']),
                      a1_result['status']=='PASS' and terminal['status']=='PASS' and candidate_grid['status']=='PASS' and running_unchanged,tolerance)
    a1=candidate if accepted else initial;grid_a1=candidate_grid if accepted else grid_m1
    objectives['J_A1']=float(grid_a1['rho_max'])
    started=time.perf_counter();counts['FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS']+=1
    frozen_for_mf=deepcopy(m1);mf_result=recourse(deepcopy(a1),frozen_for_mf)
    runtime['MF']=time.perf_counter()-started
    if digest(frozen_for_mf)!=original_trajectory:raise RuntimeError('MF_MUTATED_INPUT_M1')
    mf=mf_result['trajectory'];same_route=route_sha(mf.slots)==original_route
    try:
        grid_final_candidate=evaluate(a1,mf)
    except ValueError as error:
        grid_final_candidate={'status':'FAIL','rho_max':float('inf'),'reason':str(error)}
        mf_result['candidate_validation_error']=str(error)
    mf_accepted=monotone(objectives['J_A1'],float(grid_final_candidate['rho_max']),
                         same_route and mf_result['status']=='PASS' and grid_final_candidate['status']=='PASS',tolerance)
    final=mf if mf_accepted else m1;final_grid=grid_final_candidate if mf_accepted else grid_a1
    # The fallback M1 electrical state was re-evaluated as feasible against accepted A1.
    if final_grid['status']!='PASS':raise RuntimeError('NO_FEASIBLE_FIXED_ROUTE_ELECTRICAL_STATE')
    objectives['J_FINAL']=float(final_grid['rho_max'])
    objectives.update(DELTA_J_MESS=objectives['J_A0']-objectives['J_M1'],
                      DELTA_J_AIDC_FEEDBACK=objectives['J_M1']-objectives['J_A1'],
                      DELTA_J_FINAL_PQ=objectives['J_A1']-objectives['J_FINAL'],
                      DELTA_J_TOTAL=objectives['J_A0']-objectives['J_FINAL'])
    joint=joint_decision(a1,final.slots,authority)
    return {'a0':initial,'m1':m1,'a1':a1,'mf':final,'joint':joint,'objectives':objectives,'runtime':runtime,'counts':counts,
            'AIDC_FEEDBACK_ACCEPTED':accepted,'FINAL_PQ_RECOURSE_ACCEPTED':mf_accepted,'M1_grid':grid_m1,'A1_grid':grid_a1,
            'FINAL_grid':final_grid,'terminal_audit':terminal_audit(initial,a1),'search_info':search_info,
            'a1_candidate_result':a1_result,'mf_candidate_result':mf_result}
