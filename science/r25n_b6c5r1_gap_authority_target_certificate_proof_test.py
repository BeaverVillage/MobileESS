#!/usr/bin/env python3
from __future__ import annotations
import json, math, random
from pathlib import Path
from r25m_b6_exact_path_decomposition import global_relative_gap,gap_target_lower_bound,gap_certificate_diagnostics

R=Path(__file__).resolve().parent
rng=random.Random(250813)
checks={}

# 1) Exact equivalence of Gurobi-style relative gap and target-LB threshold.
eq_cases=0
for sign in (-1,1):
    for _ in range(5000):
        mag=10**rng.uniform(-2,4)
        u=sign*mag
        g=rng.uniform(0.0,0.20)
        # Valid minimization LB.
        l=u-rng.uniform(0.0,2.0*mag)
        a=global_relative_gap(u,l)<=g+1e-12
        b=l>=gap_target_lower_bound(u,g)-1e-12
        if a!=b:
            raise AssertionError((u,l,g,a,b))
        eq_cases+=1
checks['gap_threshold_equivalence_cases']=eq_cases

# 1b) Near-zero/sign-crossing behavior is explicit and fail-safe.
if global_relative_gap(0.0,0.0)!=0.0:raise AssertionError('zero-zero gap')
if not math.isinf(global_relative_gap(0.0,-1.0)):raise AssertionError('zero incumbent must not get finite relative certificate')
try:
    global_relative_gap(-10.0,-9.0)
    raise AssertionError('invalid lower bound above incumbent accepted')
except ValueError:
    pass
checks['zero_and_invalid_bound_edge_cases']='PASS'

# 2) Constant translation leaves absolute gap unchanged but can change relative gap.
translation_cases=0
relative_changed=0
for _ in range(5000):
    u=-rng.uniform(10,1000)
    l=u-rng.uniform(0,100)
    c=rng.uniform(-5000,5000)
    if abs(u-c)<1e-6: continue
    abs0=u-l;abs1=(u-c)-(l-c)
    if abs(abs0-abs1)>1e-10: raise AssertionError('absolute gap translation drift')
    g0=global_relative_gap(u,l)
    g1=global_relative_gap(u-c,l-c)
    if abs(g0-g1)>1e-8:relative_changed+=1
    translation_cases+=1
checks['constant_translation_cases']=translation_cases
checks['relative_gap_changed_cases']=relative_changed
if relative_changed==0:raise AssertionError('relative gap unexpectedly translation invariant')

# 3) Fixed-dual child bound algebra.
# D is an already valid root dual objective.  For each independent path block,
# selecting a path with reduced cost r adds at least r to the primal objective
# above D (all omitted Lagrangian/slack terms are nonnegative).  Restricting each
# block to a subset therefore admits D+sum(min r) as a valid child bound.
fd_cases=0
for _ in range(4000):
    blocks=[]
    for m in range(rng.randint(1,6)):
        vals=[rng.uniform(-1e-6,50.0) for _ in range(rng.randint(2,12))]
        keep=[v for v in vals if rng.random()<0.65]
        if not keep:keep=[rng.choice(vals)]
        blocks.append(keep)
    D=rng.uniform(-5000,5000)
    safety=1e-3
    lb=D+sum(min(v) for v in blocks)-safety
    for _j in range(10):
        obj=D+sum(rng.choice(v) for v in blocks)+rng.uniform(0,20)
        if lb>obj+1e-10:raise AssertionError((lb,obj,blocks))
        fd_cases+=1
checks['fixed_dual_child_bound_random_objectives']=fd_cases

# 4) Uploaded C5 numeric diagnosis regression.
u=-1937.9964663366604
l=-2017.405996772834
c=-1596.625445057639
g=0.03
d=gap_certificate_diagnostics(u,l,g)
checks['issue152_full_gap']=d['relative_gap']
checks['issue152_target_lb']=d['target_lower_bound_for_current_incumbent']
checks['issue152_bound_shortfall']=d['additional_bound_improvement_required']
checks['issue152_translated_gap']=global_relative_gap(u-c,l-c)
if not (0.0409<checks['issue152_full_gap']<0.0411):raise AssertionError('issue152 full gap')
if not (21.2<checks['issue152_bound_shortfall']<21.4):raise AssertionError('issue152 bound shortfall')
if not (0.232<checks['issue152_translated_gap']<0.234):raise AssertionError('issue152 translated gap')

# 5) Static fail-closed and authority guards.
main=(R/'main.py').read_text()
dec=(R/'r25m_b6_exact_path_decomposition.py').read_text()
checks['explicit_stage1_3pct_required']='B6-C5R1 Stage-1 gap target must equal 0.03 exactly' in main
checks['gap_audit_uses_certificate_lb']='b6_result.get("certificate_lower_bound",b6_result["full_all_column_relaxation_lower_bound"])' in main
checks['restricted_native_gap_non_authority']='"restricted_master_native_mip_gap_is_global_authority":False' in main
checks['restricted_rmp_infeasible_not_pruned']="restricted_rmp_infeasible_requires_phase1_pricing" in dec
checks['unresolved_ancestor_lb_preserved']="conservative ancestor LBs for unresolved children" in dec
checks['fixed_dual_prepass_present']="ROOT_TRUE_DUAL_PLUS_EXACT_RESTRICTED_DAG_MIN_RC_WITH_CONVEXITY_DUAL_SHIFT" in dec
checks['partial_valid_bound_promoted']="certificate_lb=max(float(certificate_lb),float(bp_global_lb))" in dec
checks['child_bound_monotone_with_parent']="lb=max(float(plb),float(rr['lb']))" in dec
checks['nonfinite_fixed_dual_cannot_pass']="math.isfinite(fd_global_lb) and fd_gap<=float(target_gap)+1e-12" in dec
checks['nonfinite_bp_cannot_pass']="math.isfinite(bp_global_lb) and bp_gap<=float(target_gap)+1e-12" in dec
checks['route_tiebreak_semantics_explicit']='procurement_only_relative_gap_not_separately_certified' in main and 'route_tiebreak_weight' in main
checks['translated_gap_diagnostic_only']='translated_decision_dependent_gap_is_diagnostic_not_stage1_acceptance' in main
for k,v in list(checks.items()):
    if isinstance(v,bool) and not v:raise AssertionError(k)

print(json.dumps({'PASS':True,'checks':checks},indent=2))
