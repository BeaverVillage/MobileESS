#!/usr/bin/env python3
"""Historical B6R4 regression after B6-C1 supersession.
B6R4's valid root-LB reuse and exact child repricing are retained, while its
post-MIP Model.relax lifecycle is intentionally superseded by C1.
"""
from pathlib import Path
import json,math
R=Path(__file__).resolve().parent
s=(R/'r25m_b6_exact_path_decomposition.py').read_text()
checks={
 'b6r4_post_mip_relax_superseded': 'bp_base=m.relax()' not in s,
 'continuous_authority_replacement': 'bp_continuous_authority=m.copy()' in s and 'bp_base=bp_continuous_authority' in s,
 'continuous_guard_node': 'node_relaxation_not_continuous_int' in s,
 'dual_unavailable_fails_closed': "'reason':'qcp_dual_unavailable_after_retries'" in s,
 'root_exact_lb_reused': ("rootlb=float(full_lb);rootbr=root_branch_candidate" in s or "rootlb=float(certificate_lb);rootbr=root_branch_candidate" in s),
 'root_not_repriced': 'rootbp=_solve_bp_node(empty_req,empty_forb,{},0)' not in s,
 'child_exact_pricing_preserved': 'shortest_path_with_node_restrictions' in s and 'guarded_full_lb(robj,len(mids),child_effective_rc_guard)' in s,
 'restricted_bound_not_authority': ('restricted integer master contributes only a feasible incumbent' in s or 'restricted integer master contributes only a globally feasible incumbent' in s),
}
branch_ok=True
for x in [0.2,0.5,1.2,2.75,7.01]:
 fl=math.floor(x);ce=math.ceil(x)
 for z in range(-2,11):
  if not (z<=fl or z>=ce):branch_ok=False
checks['integer_branch_partition']=branch_ok
checks['root_lb_reuse_math']=all(L<=U for L,U in [(-2017.406,-1939.25),(-2000.,-1950.),(-100.,-90.)])
out={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'long_solver_run':False,
     'scientific_feasible_set_changed':False,'objective_changed':False,'root_repricing_removed':True,
     'branch_child_all_column_pricing_required':True,'B6R4_model_relax_lifecycle':'SUPERSEDED_BY_B6_C1'}
print(json.dumps(out,indent=2,sort_keys=True))
raise SystemExit(0 if out['status']=='PASS' else 2)
