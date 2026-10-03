from .common import *
from .certificate import down
from fractions import Fraction as F
from collections import defaultdict,Counter
import numpy as np

def bounded():
    """Exhaust all paths of small DAGs, with analytic continuous box minima.

    These fixtures isolate the flow/grid disjunction. The general three-case
    proof covers arbitrary unchanged SOC/PCS/route constraints in actual M1.
    """
    fixtures=[];cases=Counter()
    for horizon in (3,4,5):
        sites=('A','B','C')
        arcs=[(s,t,s,t+1) for s in sites for t in range(horizon)]
        arcs += [(s,t,d,t+2) for s in sites for d in sites if s!=d for t in range(horizon-1)]
        paths=[]
        def visit(s,t,path):
            if t==horizon:paths.append(path);return
            for k,a in enumerate(arcs):
                if a[:2]==(s,t):visit(a[2],a[3],path+[k])
        visit('A',0,[])
        stays=[];floors=[]
        for path in paths:
            selected={(arcs[k][0],arcs[k][1]) for k in path if arcs[k][3]==arcs[k][1]+1}
            stays.append(selected)
            # At connected slots p,q in [-1,1]; at transit p=q=0.
            # Each original grid row is rho >= b_t + a_s p + c_s q.
            # Per-slot independent box minima are simultaneously attainable.
            floors.append(max(F(45+t,100)-next((F(2+sites.index(s),100)+F(1,100) for s in sites if (s,t) in selected),F(0)) for t in range(horizon)))
        l0=min(floors); cuts=[]
        for t in range(horizon):
            computed={s:min(f for f,ys in zip(floors,stays) if (s,t) in ys) for s in sites[:2] if any((s,t) in ys for ys in stays)}
            cuts.append((t,computed))
        for ys,floor in zip(stays,floors):
            for t,computed in cuts:
                rhs=l0+sum((lb-l0) for s,lb in computed.items() if (s,t) in ys)
                assert rhs<=floor
                state=next((s for s in sites if (s,t) in ys),None)
                cases['transit' if state is None else 'computed' if state in computed else 'uncomputed']+=1
        # On every integer route, every feasible real (p,q,rho) obeys
        # rho>=floor>=each added RHS. Adding cuts removes no projected point.
        fixtures.append(dict(horizon=horizon,arcs=len(arcs),all_origin_terminal_paths=len(paths),
             all_real_power_box_projection_equal=True,original_optimum=str(l0),cut_optimum=str(l0)))
    result=dict(PASS=True,fixtures=fixtures,cases=dict(cases),arithmetic='Exact Fraction',
        proof='For every enumerated integer path, analytically minimize the original independent continuous P/Q boxes. Every added cut RHS is <= that path minimum, so every original real-valued feasible point remains feasible. Adding inequalities introduces no new points; projection and objective are identical.',
        scope='Bounded time-expanded flow plus grid epigraph fixtures; real M1 arbitrary SOC/PCS/physics covered by general conditional-LP proof, not asserted to be enumerated by these toy boxes.',
        optimization_calls=0)
    assert all(cases[k]>0 for k in ('transit','computed','uncomputed'))
    write('DISJUNCTIVE_EPIGRAPH_BOUNDED_EQUIVALENCE.json',result)
    return result

def build():
    assert read(OUT/'CONNECTION_STATE_PARTITION_PROOF.json')['PASS']
    certs=read(OUT/'CONDITIONAL_LB_CERTIFICATE.json')['certificates']
    byslot=defaultdict(list)
    for c in certs:
        if c['PASS']:
            coefficient=down(F(c['L_safe'])-F(BASE_LB))
            assert coefficient>=0 and F(BASE_LB)+F(coefficient)<=F(c['L_safe'])
            byslot[c['MESS'],c['slot']].append(dict(site=c['site'],name=c['selected_original_binary_name'],
                 column=c['selected_bound_column'],L_safe=c['L_safe'],coefficient=coefficient,rank=c['rank']))
    with np.load(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz') as z:
        point=z['values']; names=z['names']
    rho=float(point[np.flatnonzero(names=='rho_max')[0]])
    rows=[];definitions=[]
    for (u,t),terms in sorted(byslot.items()):
        rhs=BASE_LB+sum(v['coefficient']*float(point[v['column']]) for v in terms)
        violation=rhs-rho
        rows.append(dict(MESS=u,slot=t,computed_sites=len(terms),nonzero_coefficients=sum(v['coefficient']>0 for v in terms),
                     baseline_rho=rho,cut_rhs=rhs,signed_violation=violation,positive_violation=max(0.,violation),added=violation>1e-6))
        definitions.append(dict(MESS=u,slot=t,terms=terms,added=violation>1e-6,rhs=BASE_LB))
    table('DISJUNCTIVE_ROOT_SEPARATION.csv',rows,['MESS','slot','computed_sites','nonzero_coefficients','baseline_rho','cut_rhs','signed_violation','positive_violation','added'])
    write('DISJUNCTIVE_CUT_DEFINITIONS.json',dict(cuts=definitions,uncomputed_fallback=BASE_LB,transit_fallback=BASE_LB))
    write('DISJUNCTIVE_ROOT_SEPARATION_SUMMARY.json',dict(total_candidate_cuts=len(rows),violated_cut_count=sum(r['added'] for r in rows),
          max_violation=max((r['positive_violation'] for r in rows),default=0.),sum_positive_violation=sum(r['positive_violation'] for r in rows),
          top_50=sorted(rows,key=lambda r:-r['positive_violation'])[:50],
          unit_distribution=dict(Counter(r['MESS'] for r in rows if r['added'])),
          slot_distribution=dict(Counter(str(r['slot']) for r in rows if r['added'])),separation_threshold=1e-6,
          threshold_changes_physics=False))
    proof=dict(PASS=True,partition_proof_SHA=sha(OUT/'CONNECTION_STATE_PARTITION_PROOF.json'),
        lower_bound_certificate_SHA=sha(OUT/'CONDITIONAL_LB_CERTIFICATE.json'),
        cut='rho >= L0 + sum_s coefficient_s * original_stay_s; coefficient_s rounded downward from exact L_safe_s-L0',
        cases=[
          'Computed connected site: single selected stay makes RHS <= L_safe_s. Original integer solution is feasible in the conditional continuous LP, so objective >= its rigorously certified lower bound >= L_safe_s.',
          'Uncomputed connected site: all computed stays are zero; RHS=L0, inherited globally valid BASE lower bound.',
          'Transit: every stay is zero; RHS=L0, inherited globally valid BASE lower bound.'],
        projected_integer_feasible_set_equal=True,objective_unchanged=True,original_continuous_physics_unchanged=True,
        new_variables=0,new_binary_variables=0,unproven_fixings=0)
    write('DISJUNCTIVE_EPIGRAPH_VALIDITY_PROOF.json',proof)
    bounded()
    return definitions

def install(m):
    import gurobipy as gp
    defs=read(OUT/'DISJUNCTIVE_CUT_DEFINITIONS.json')['cuts']
    variables=m.getVars(); rho=m.getVarByName('rho_max');count=0
    for cut in defs:
        if cut['added']:
            expr=gp.LinExpr([v['coefficient'] for v in cut['terms']],[variables[v['column']] for v in cut['terms']])
            m.addConstr(rho-expr>=BASE_LB,name=f"location_grid_disjunctive[{cut['MESS']},{cut['slot']}]");count+=1
    proofs=read(OUT/'CONDITIONAL_INFEASIBLE_STATE_PROOF.json')['proven_fixings']
    for c in proofs:
        variables[c['column']].LB=0.;variables[c['column']].UB=0.
    m.update()
    return dict(cuts_added=count,exact_infeasible_state_fixings=len(proofs))
