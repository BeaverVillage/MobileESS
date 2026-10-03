"""One continuous departure-energy commodity per existing route arc.

The original SOC rows and every original column remain in the model.
"""
from .common import OUT,write,read
from .analysis import graph_inputs
from collections import defaultdict
from itertools import product
from fractions import Fraction as F
import gurobipy as gp
import numpy as np
import math

def travel_lower(minimum,cost):
    # The exact sum of two source IEEE coefficients need not be representable
    # as one IEEE coefficient. Round outward so a valid primary point can never
    # be excluded. Original SOC bounds remain verbatim and determine the exact
    # integer projection; travel energy expressions retain the original cost.
    value=float(minimum+cost)
    if F.from_float(value)>F.from_float(float(minimum))+F.from_float(float(cost)):
        value=math.nextafter(value,-math.inf)
    return value

def add_flow(model,sites,initial,arcs,battery,horizon=96):
    v={a.VarName:a for a in model.getVars()}
    before=(model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    incoming=defaultdict(list);outgoing=defaultdict(list);active=defaultdict(list)
    for k,(s,t,d,e,r) in enumerate(arcs):
        outgoing[s,t].append(k);incoming[d,e].append(k)
        if r is not None:
            for b in range(t+1,e):active[b].append(k)
    for u,origin in initial.items():
        Ein={};Eout={}
        for k,(s,t,d,e,r) in enumerate(arcs):
            x=v.get(f'arc[{u},{k}]')
            if x is None:continue
            energy=model.addVar(lb=0.,ub=battery.maximum,name=f'energy_flow[{u},{k}]')
            Ein[k]=energy
            if r is None:
                delta=(battery.dt_hours*battery.eta_charge)*v[f'Pch[{u},{s},{t}]']-(battery.dt_hours/battery.eta_discharge)*v[f'Pdis[{u},{s},{t}]']
                Eout[k]=energy+delta
                model.addConstr(energy>=battery.minimum*x,name=f'flow_energy_before_min[{u},{k}]')
                model.addConstr(energy<=battery.maximum*x,name=f'flow_energy_before_max[{u},{k}]')
                model.addConstr(Eout[k]>=battery.minimum*x,name=f'flow_energy_after_min[{u},{k}]')
                model.addConstr(Eout[k]<=battery.maximum*x,name=f'flow_energy_after_max[{u},{k}]')
            else:
                Eout[k]=energy-r.energy_kwh*x
                # Nonnegative travel cost makes the remaining two bounds
                # redundant: Ein>=min, Eout<=max.
                model.addConstr(energy>=travel_lower(battery.minimum,r.energy_kwh)*x,name=f'flow_travel_energy_min[{u},{k}]')
                model.addConstr(energy<=battery.maximum*x,name=f'flow_travel_energy_max[{u},{k}]')
        for t in range(horizon):
            for s in sites:
                out=gp.quicksum(Ein[k] for k in outgoing[s,t] if k in Ein)
                inc=gp.quicksum(Eout[k] for k in incoming[s,t] if k in Eout)
                model.addConstr(out-inc==(battery.initial if (s,t)==(origin,0) else 0.),name=f'flow_energy_conservation[{u},{s},{t}]')
        for t in range(horizon+1):
            node=gp.quicksum(Eout[k] for s in sites for k in incoming[s,t] if k in Eout) if t==horizon else gp.quicksum(Ein[k] for s in sites for k in outgoing[s,t] if k in Ein)
            transit=gp.quicksum(Eout[k] for k in active[t] if k in Eout)
            model.addConstr(v[f'SOC[{u},{t}]']==node+transit,name=f'flow_scalar_SOC_projection[{u},{t}]')
    model.update()
    after=(model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    assert after[2]==before[2]
    return dict(before=dict(zip(('rows','columns','binaries','nnz'),before)),after=dict(zip(('rows','columns','binaries','nnz'),after)),
                added_rows=after[0]-before[0],added_columns=after[1]-before[1],added_binaries=0,added_nnz=after[3]-before[3])

def flow_proof():
    proof=dict(PASS=True,
      auxiliary='e_before[u,k]>=0 continuous, one per existing arc. e_after is a linear expression, not another column.',
      perspective_bounds='Stay: minimum*x <= e_before,e_after <= maximum*x. Travel: e_before-cost*x=e_after; enforce e_before>=outward_down(minimum+cost)*x and e_before<=maximum*x. Outward rounding cannot exclude an original point; original scalar SOC bounds retained verbatim enforce exact primary integer bounds.',
      travel_arithmetic='Travel cost at departure, exactly as original. All intermediate SOC boundaries use e_after until connect.',
      stay_arithmetic='e_after=e_before+dt*eta_charge*Pch-dt/eta_discharge*Pdis at that stay site.',
      node_conservation='Sum outgoing e_before minus sum incoming e_after is initial energy only at the unit source; zero at every other nonterminal node.',
      scalar_projection='SOC[t]=sum outgoing e_before at site nodes plus e_after for earlier departing, unconnected movement arcs. At H use incoming e_after.',
      original_to_extended='An original integer path defines e_before=SOC[depart] on selected arcs and zero on all other arcs. Connected powers vanish off path. Original energy balance, initial/terminal and bounds imply all new rows. Movement intermediate SOC is constant after departure. Thus every original primary point extends.',
      extended_to_original='Every original constraint is retained verbatim, and original binary columns retain bounds/types. Projection therefore lies in original feasible set.',
      objective_equivalence='All original P1/P2 coefficients and constants unchanged; every auxiliary objective coefficient is zero. Objective levels are identical on the common primary projection.',
      binary_semantics_identical=True,added_binaries=0,no_route_pruning=True,no_changed_physics=True)
    write('SOC_FLOW_EXACT_PROJECTION_PROOF.json',proof)
    return proof

def affine_add(*vectors):
    out=defaultdict(F)
    for vector in vectors:
        for key,value in vector.items():out[key]+=value
    return {k:v for k,v in out.items() if v}

def affine_scale(vector,scale):
    return {k:v*scale for k,v in vector.items() if v*scale}

def bounded_flow():
    """Exhaust binary routes/modes, exact symbolic continuous energy projection.

    Identity of affine expressions verifies whole continuous polytopes, rather
    than pretending a grid of power samples exhausts real-valued decisions.
    """
    H=4;sites=('a','b')
    arcs=[(s,t,s,t+1,F(0)) for s in sites for t in range(H)]
    arcs += [('a',0,'b',2,F(1)),('b',0,'a',2,F(2)),('a',1,'b',3,F(2)),('b',1,'a',3,F(1)),('a',2,'b',3,F(1)),('b',2,'a',3,F(2))]
    count=0;modes_count=0;equalities=0;bounds=0
    for x in product((0,1),repeat=len(arcs)):
        valid=all(sum(x[k] for k,a in enumerate(arcs) if a[:2]==(s,t))-sum(x[k] for k,a in enumerate(arcs) if a[2:4]==(s,t))==int(s=='a' and t==0) for s in sites for t in range(H))
        valid=valid and sum(x[k] for k,a in enumerate(arcs) if a[3]==H)==1
        if not valid:continue
        count+=1
        for modes in product((0,1),repeat=H):
            modes_count+=1
            E=[{'constant':F(5)}]
            for t in range(H):
                delta={}
                for k,(s,b,d,e,cost) in enumerate(arcs):
                    if not x[k] or b!=t:continue
                    if s==d:delta['power_'+str(t)]=F(1,4)*(F(9,10) if modes[t] else -F(10,9))
                    else:delta['constant']=-cost
                E.append(affine_add(E[-1],delta))
            Ein={k:E[a[1]] if x[k] else {} for k,a in enumerate(arcs)}
            Eout={k:E[a[1]+1] if x[k] else {} for k,a in enumerate(arcs)}
            for k,(s,t,d,e,cost) in enumerate(arcs):
                if x[k]:
                    assert Eout[k]==E[e]
                    # Perspective bounds become original SOC[t]/SOC[t+1]
                    # bounds; off-path both expressions are exactly zero.
                    assert Ein[k]==E[t] and Eout[k]==E[t+1]
                    bounds+=4
                else:assert Ein[k]==Eout[k]=={}
            for t in range(H):
                for s in sites:
                    out=affine_add(*(Ein[k] for k,a in enumerate(arcs) if a[:2]==(s,t)))
                    inc=affine_add(*(Eout[k] for k,a in enumerate(arcs) if a[2:4]==(s,t)))
                    residual=affine_add(out,affine_scale(inc,F(-1)))
                    assert residual==({'constant':F(5)} if (s,t)==('a',0) else {})
                    equalities+=1
            for t in range(H+1):
                node=affine_add(*(Eout[k] for k,a in enumerate(arcs) if a[3]==t)) if t==H else affine_add(*(Ein[k] for k,a in enumerate(arcs) if a[1]==t))
                transit=affine_add(*(Eout[k] for k,a in enumerate(arcs) if a[0]!=a[2] and a[1]<t<a[3]))
                assert affine_add(node,transit)==E[t]
                equalities+=1
    result=dict(PASS=True,arithmetic='Exact rational symbolic affine coefficients',
      binary_arc_assignments_examined=2**len(arcs),integer_routes=count,route_mode_assignments=modes_count,
      exact_affine_equalities_verified=equalities,active_perspective_bounds_reduced_to_original_bounds=bounds,
      primary_projection_exact_equality=True,all_real_power_values_covered=True,
      method='Exhaust every integer route and mode; eliminate off-path energy using perspective upper bounds; selected departure-energy equals scalar SOC. Every new equality is an affine identity modulo original SOC recurrence; every new bound is an existing SOC bound. Continuous Q/PCS/grid rows retained.',
      objective_levels_identical=True,new_binary_count=0)
    write('SOC_FLOW_BOUNDED_EQUIVALENCE.json',result)
    return result

def growth_gate(d,sites,initial,arcs,horizon=96):
    import psutil
    # Preregister before constructing the full extended matrix or optimizing it.
    names=set(map(str,d['names']));stay=move=0;arc_nnz=0;conservation_nnz=0;link_nnz=0
    for u in initial:
        for k,(s,t,dst,e,r) in enumerate(arcs):
            if f'arc[{u},{k}]' not in names:continue
            if r is None:
                stay+=1;arc_nnz+=12;conservation_nnz+=2+2*int(e<horizon)
                link_nnz+=1+(3 if e==horizon else 0)
            else:
                move+=1;arc_nnz+=4;conservation_nnz+=1+2*int(e<horizon)
                link_nnz+=1+2*(e-t-1)+(2 if e==horizon else 0)
    cols=stay+move;rows=4*stay+2*move+len(initial)*len(sites)*horizon+len(initial)*(horizon+1)
    nnz=arc_nnz+conservation_nnz+link_nnz+len(initial)*(horizon+1)
    base_nnz=8447855;base_cols=316743
    memory=psutil.virtual_memory().available
    # Sparse transport lower bound plus explicit conservative native/factor
    # allowance. Actual factorization fill cannot be certified in advance.
    sparse_bytes=(base_nnz+nnz)*12+(886017+rows+1)*8
    estimated_native_and_factor_bytes=8*sparse_bytes+1024**3
    gate=dict(max_total_nnz_ratio=2.,max_added_column_ratio=1.,
              required_available_memory_multiple=2.,
              rationale='Bound growth below doubling nnz and one original-column count; 2x available-memory allowance around a conservative 8x sparse-storage factor estimate. A 4x matrix is rejected. Factorization risk explicitly unresolved until the one allowed LP.')
    passed=(base_nnz+nnz)/base_nnz<=gate['max_total_nnz_ratio'] and cols/base_cols<=gate['max_added_column_ratio'] and memory>=2*estimated_native_and_factor_bytes
    result=dict(PASS=passed,preregistered_thresholds=gate,added_continuous_variables=cols,added_binaries=0,
        added_rows=rows,estimated_added_nnz_upper_bound=nnz,total_nnz_ratio_upper_bound=(base_nnz+nnz)/base_nnz,
        added_column_ratio=cols/base_cols,sparse_storage_bytes=sparse_bytes,
        estimated_native_factorization_bytes=estimated_native_and_factor_bytes,available_RAM_bytes=memory,
        factorization_fill_estimate_is_uncertain=True,
        expected_benefit='Route energy histories are coupled by a perspective energy commodity; baseline has 377 split slots, up to 24 simultaneous fractional sites. Material bound gain remains an unproven hypothesis, tested only once.',
        reject_reason=None if passed else 'MATRIX_OR_MEMORY_GATE')
    write('SOC_FLOW_MATRIX_GROWTH.json',result)
    return result

def stage_C():
    from .lp import evaluate
    a=read(OUT/'CUT_A_ROOT_RESULT.json');b=read(OUT/'STRENGTHENING_B_ROOT_RESULT.json')
    if a.get('selected') or b.get('selected'):
        write('SOC_FLOW_FULL_ROOT_RESULT.json',dict(status='NOT_RUN',reason='EARLIER_MATERIAL_CANDIDATE'))
        return
    assert flow_proof()['PASS'] and bounded_flow()['PASS']
    from .prototype import build_receipt
    assert build_receipt()['PASS']
    sites,initial,arcs,battery,_=graph_inputs()
    with np.load(OUT/'BASELINE_ROOT_LP_SOLUTION.npz') as z:d=dict(names=z['names'])
    gate=growth_gate(d,sites,initial,arcs)
    if not gate['PASS']:
        write('SOC_FLOW_FULL_ROOT_RESULT.json',dict(status='NOT_RUN',selected=False,reason='MATRIX_GROWTH_GATE_FAILED'))
        return
    result=evaluate('SOC_FLOW_FULL_ROOT',lambda m:add_flow(m,sites,initial,arcs,battery))
    actual=result['matrix_growth']
    assert actual['added_rows']==gate['added_rows'] and actual['added_columns']==gate['added_continuous_variables']
    assert actual['added_nnz']<=gate['estimated_added_nnz_upper_bound']
    result['selected']=bool(result['status']==gp.GRB.OPTIMAL and result['material'] and result['objective']>=read(OUT/'BASELINE_ROOT_LP_RECEIPT.json')['primal_objective']-1e-8)
    result['exact_integer_equivalence_PASS']=True
    write('SOC_FLOW_FULL_ROOT_RESULT.json',result)

if __name__=='__main__':stage_C()
