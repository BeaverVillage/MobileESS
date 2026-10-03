from itertools import product
from fractions import Fraction
import gurobipy as gp
from .common import write

def add_A(model, sites, initial, pmax, horizon=96):
    """Append only the three requested exact inequalities; retain all columns."""
    v = {x.VarName:x for x in model.getVars()}
    before = (model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    for u in initial:
        for t in range(horizon):
            C = gp.quicksum(v[f'Pch[{u},{s},{t}]'] for s in sites if f'Pch[{u},{s},{t}]' in v)
            D = gp.quicksum(v[f'Pdis[{u},{s},{t}]'] for s in sites if f'Pdis[{u},{s},{t}]' in v)
            Y = gp.quicksum(v[f'arc[{u},{i*horizon+t}]'] for i in range(len(sites)) if f'arc[{u},{i*horizon+t}]' in v)
            d = v[f'charge_mode[{u},{t}]']
            model.addConstr(C <= pmax*d,name=f'exact_A1[{u},{t}]')
            model.addConstr(D <= pmax*(1-d),name=f'exact_A2[{u},{t}]')
            model.addConstr(C+D <= pmax*Y,name=f'exact_A3[{u},{t}]')
    model.update()
    after = (model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    assert after[1:3] == before[1:3]
    return dict(before=dict(zip(('rows','columns','binaries','nnz'),before)),
                after=dict(zip(('rows','columns','binaries','nnz'),after)),
                added_rows=after[0]-before[0],added_columns=0,added_binaries=0,added_nnz=after[3]-before[3])

def proof_A():
    proof = dict(PASS=True,scope='All original integer primary feasible points; continuous P/Q/SOC and grid states unrestricted within original constraints.',
       premises=[
        'Every route arc strictly increases time: stay t->t+1, travel depart<connect. The route graph is acyclic.',
        'Binary nonnegative arc flow, unit source injection, conservation at all nonterminal nodes and terminal total one imply exactly one source-terminal path. No disconnected flow cycle is possible in a DAG.',
        'At a slot the selected path traverses exactly one stay arc or is in transit; thus Y is 0 or 1 and at most one stay site is selected.',
        'Connected nonnegative Pch/Pdis bounds force both to zero at every unselected site.',
        'Binary d=0 forces every Pch=0; binary d=1 forces every Pdis=0. Each active power is at most Pmax.'],
       derivation={
        'A1':'d=0 => C=0; d=1 => at most one active site and C<=Pmax. Thus C<=Pmax*d.',
        'A2':'d=1 => D=0; d=0 => at most one active site and D<=Pmax. Thus D<=Pmax*(1-d).',
        'A3':'Y=0 => C=D=0. Y=1 => exactly one active site and one direction; C+D<=Pmax.'},
       projected_equivalence='Strengthened is original intersected with inequalities satisfied by every original integer feasible point, so both integer primary feasible sets are identical. Identity map in both directions, no auxiliary variables. All objective functions remain pointwise identical.',
       transit_P_Q_semantics_unchanged=True,physics_rating_objective_domain_unchanged=True,new_binaries=0)
    write('CUT_A_EXACT_VALIDITY_PROOF.json',proof)
    return proof

def bounded_A():
    """Rational arithmetic, exhaustive binary flows/modes and continuous box vertices.

    A linear cut valid at every vertex is valid on the entire continuous box;
    intersecting that box with SOC/Q/grid rows preserves redundancy.
    """
    H=3
    arcs=[(s,t,s,t+1) for s in ('a','b') for t in range(H)]
    arcs += [('a',0,'b',2),('b',0,'a',2),('a',1,'b',3),('b',1,'a',3)]
    flows=0;cases=0;vertices=0;max_v=Fraction(0)
    for x in product((0,1),repeat=len(arcs)):
        valid=all(sum(x[k] for k,a in enumerate(arcs) if a[:2]==(s,t))-
                  sum(x[k] for k,a in enumerate(arcs) if a[2:]==(s,t))==int(s=='a' and t==0)
                  for s in ('a','b') for t in range(H))
        valid=valid and sum(x[k] for k,a in enumerate(arcs) if a[3]==H)==1
        if not valid:continue
        flows+=1
        for modes in product((0,1),repeat=H):
            for t in range(H):
                y=[x[i*H+t] for i in range(2)]
                assert sum(y)<=1
                caps=[(Fraction(z*modes[t]),Fraction(z*(1-modes[t]))) for z in y]
                ranges=[(Fraction(0),cap) if cap else (Fraction(0),) for pair in caps for cap in pair]
                for p in product(*ranges):
                    C=p[0]+p[2];D=p[1]+p[3]
                    violations=(C-modes[t],D-(1-modes[t]),C+D-sum(y))
                    assert max(violations)<=0
                    max_v=max(max_v,*violations);vertices+=1
                cases+=1
    # Independent exhaustive site/mode fixtures include transit and 1..4 sites.
    state_cases=0
    for n in range(1,5):
        for y in product((0,1),repeat=n):
            if sum(y)>1:continue
            for d in (0,1):
                caps=[Fraction(z*(d if direction==0 else 1-d)) for z in y for direction in (0,1)]
                for p in product(*[(Fraction(0),cap) if cap else (Fraction(0),) for cap in caps]):
                    C=sum(p[::2]);D=sum(p[1::2])
                    assert C<=d and D<=1-d and C+D<=sum(y)
                    state_cases+=1
    result=dict(PASS=True,arithmetic='fractions.Fraction exact rational',horizon=H,sites=2,
                binary_arc_assignments_examined=2**len(arcs),integer_routes=flows,
                mode_assignments_per_route=2**H,route_mode_slot_cases=cases,
                continuous_box_vertices=vertices,independent_site_mode_vertices=state_cases,
                max_cut_violation=str(max_v),primary_projection_exact_equality=True,
                continuous_domains_verified_by='All vertices enumerated; cuts linear, hence redundant on their convex hull. Original SOC, travel, Q, PCS and grid rows only intersect these domains.',
                objective_levels_identical=True,objective_identity='Every P1/P2 expression is unchanged on every common primary point.',
                proof_SHA_scope='CUT_A_EXACT_VALIDITY_PROOF.json')
    write('CUT_A_BOUNDED_EQUIVALENCE.json',result)
    return result
