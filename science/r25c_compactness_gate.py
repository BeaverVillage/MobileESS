#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json, math, hashlib

HERE=Path(__file__).resolve().parent
EVID=HERE/'embedded'/'a3_issue152_evidence'

def load(name):
    return json.loads((EVID/name).read_text())

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def evaluate():
    pre=load('BUILD7BR2_PREOPT_MODEL_AUDIT.json')
    pr=load('BUILD7BR6_EXACT_ROUTE_PRUNING_AUDIT.json')
    mv=load('BUILD7BR3_MV_DOMAIN_AUDIT.json')
    bnd=load('BUILD7BR14_IMPLIED_BOUND_PROOF_AUDIT.json')
    term=load('BUILD7BR6_GUROBI_TERMINATION.json')
    total_int=int(pre['candidate_move_binary_count']) + 216  # R24 turns 4,299 STAY binaries continuous; 4*54 charge/discharge mode binaries remain.
    move=int(pre['candidate_move_binary_count'])
    baseline=int(pre['baseline_move_binary_count'])
    reduction=baseline-move
    route_rank_floor=math.ceil(move/3) # absolute optimistic floor if every surviving OD/time group still had three K routes.
    node_rate=float(term['node_count'])/float(term['runtime_s'])
    rules={
      'absolute_move_binary_gate': move<=80000,
      'mobility_share_gate': move/max(1,total_int)<=0.90,
      'exact_pruning_fraction_gate': reduction/max(1,baseline)>=0.10,
      'eight_hour_certificate_gate': float(term['final_economic_achieved_mip_gap'])<=float(term['final_economic_target_mip_gap']),
    }
    decision='KEEP_MONOLITHIC' if all(rules.values()) else 'EXACT_DECOMPOSITION_REQUIRED'
    return {
      'status':'PASS_COMPACTNESS_DECISION_GATE',
      'stage':'A3/6','conversation':'A','decision':decision,
      'issue152_historical_authority':{
        'variables':int(pre['variables']),'linear_constraints':int(pre['linear_constraints']),
        'quadratic_constraints':int(pre['quadratic_constraints']),
        'historical_total_integer_binary':103798,
        'historical_stay_binary':int(pr['stay_binary_count_after_reachable_state_pruning']),
        'R24_estimated_integer_after_STAY_projection':total_int,
        'candidate_MOVE_binary':move,'candidate_MOVE_by_MESS':mv['candidate_move_by_mess'],
        'MOVE_fraction_of_R24_integer_estimate':move/max(1,total_int),
        'baseline_reachable_MOVE_binary':baseline,'existing_exact_MOVE_reduction':reduction,
        'existing_exact_MOVE_reduction_fraction':reduction/max(1,baseline),
        'route_level_pareto_move_records':int(bnd['planning_move_count']),
        'absolute_optimistic_one_of_K3_floor_from_current_MOVE':route_rank_floor,
        'eight_hour_runtime_s':float(term['runtime_s']),'eight_hour_gap':float(term['final_economic_achieved_mip_gap']),
        'target_gap':float(term['final_economic_target_mip_gap']),'node_count':float(term['node_count']),
        'nodes_per_second':node_rate,
      },
      'fixed_gate_policy':{
        'max_MOVE_binary_for_monolithic_continuation':80000,
        'max_MOVE_share_of_integer_for_monolithic_continuation':0.90,
        'min_existing_exact_pruning_fraction_for_monolithic_continuation':0.10,
        'long_run_certificate_must_already_pass':True,
        'rationale':'A3 was precommitted to stop monolithic tuning when the post-A1/A2 model remains in the 80k-90k+ MOVE regime. Scale-free concentration and pruning-efficiency gates prevent a decision based on one arbitrary count alone.'
      },
      'gate_results':rules,
      'structural_interpretation':{
        'K3_authority_changed':False,'scientific_feasible_set_changed':False,
        'dominant_block':'MESS time-expanded MOVE decisions',
        'why_decomposition':'R24 removes STAY integrality but leaves essentially all integer combinatorics in MOVE. A2 confirms K3 duration/Safe-energy dominance is already compiled upstream, so further route-rank-only work cannot attack the source×destination×time×MESS state explosion.',
        'long_solver_run_executed_in_A3':False,
      },
      'evidence_sha256':{p.name:sha256(p) for p in sorted(EVID.glob('*.json'))}
    }

if __name__=='__main__':
    print(json.dumps(evaluate(),indent=2,sort_keys=True))
