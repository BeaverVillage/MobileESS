"""Enumerate every tiny route path; optimize all mode bits exactly."""
from dataclasses import replace
from .base import *
from .strengthening import authorization,hook,extension_values
from v42_m1_sparse.equivalence import fixture,route_patterns

CASES={
 'all_stay_path':'all_stay', 'one_travel':'one_movement',
 'two_route_alternatives':'multiple_movement_choices',
 'route_reconvergence':'multiple_movement_choices',
 'fractional_looking_topology_integer_solve':'multiple_movement_choices',
 'charging':'P_charge_only','discharging':'P_discharge_only',
 'zero_active_power':'all_stay','positive_Q':'positive_Q','negative_Q':'negative_Q',
 'simultaneous_P_Q':'PQ_within_PCS','near_PCS_boundary':'near_PCS_boundary',
 'SOC_minimum_binding':'all_stay','SOC_maximum_binding':'all_stay',
 'terminal_SOC_binding':'terminal_SOC_binding','travel_energy_binding':'one_movement',
 'upper_voltage_binding':'upper_voltage_binding','lower_voltage_binding':'lower_voltage_binding',
 'line_thermal_binding':'line_face_binding','transformer_binding':'transformer_kVA_binding'}

def compare(case,label):
    import math
    import v42_native.mess as native
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage
    from v42_m1_sparse.grid import response,add_compressed
    source=CASES[case];sites,H,initial,b,routes,coeff=fixture(source)
    zero_power=case in ('zero_active_power','SOC_minimum_binding','SOC_maximum_binding','travel_energy_binding')
    if case=='SOC_minimum_binding':b=replace(b,initial=b.minimum,terminal=b.minimum)
    if case=='SOC_maximum_binding':b=replace(b,initial=b.maximum,terminal=b.maximum)
    if case=='travel_energy_binding':
        b=replace(b,initial=.1,terminal=0);initial={'M0':'A'}
    patterns,arcs=route_patterns(sites,H,routes,initial);output=[];holder={}
    authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
    def builder(m,p,q):
        bindings=[]
        p={key:response(m,f'injection_P[{key[0]},{key[1]}]',v,bindings) for key,v in p.items()}
        q={key:response(m,f'injection_Q[{key[0]},{key[1]}]',v,bindings) for key,v in q.items()}
        controls=[[0.]+[p[s,t] for s in sites]+[q[s,t] for s in sites] for t in range(H)]
        rho=add_compressed(m,coeff,controls,authority,'M1-F3',bindings,[]);m.update()
        def var(prefix,t=0,s='A',u='M0'):return m.getVarByName(f'{prefix}[{u},{s},{t}]')
        if zero_power:
            for v in m.getVars():
                if v.VarName.startswith(('Pch[','Pdis[')):m.addConstr(v==0)
        if source=='P_charge_only':
            for v in m.getVars():
                if v.VarName.startswith('Pdis['):m.addConstr(v==0)
            m.addConstr(var('Pch')==1)
        if source=='P_discharge_only':
            for v in m.getVars():
                if v.VarName.startswith('Pch['):m.addConstr(v==0)
            m.addConstr(var('Pdis')==1)
        if source in ('positive_Q','negative_Q','near_PCS_boundary'):
            target={'positive_Q':2.,'negative_Q':-2.,'near_PCS_boundary':b.pcs_kva*math.cos(math.pi/16)}[source]
            m.addConstr(var('Q')==target)
            if source=='near_PCS_boundary':m.addConstr(var('Pch')==0);m.addConstr(var('Pdis')==0)
        if source=='PQ_within_PCS':m.addConstr(var('Pdis')==1);m.addConstr(var('Q')==2)
        if source=='one_movement':m.addConstr(m.getVarByName(f'arc[M0,{len(sites)*H}]')==1)
        return [('rho',rho),('reserve_shortfall',0.)]
    # Collect the structured context for S0 too, without adding any row.
    def collect(m,c):holder.update(context=c,G={})
    compact=label=='S3' and (OUT/'S3_NUMERICAL_RECOVERY.json').exists()
    callback=collect if label=='S0' else hook(label,holder,compact_energy_bounds=compact)
    def optimizer(m,legacy,deadline,*args,**kwargs):
        m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=0;m.Params.TimeLimit=90
        m.Params.FeasibilityTol=1e-9;m.Params.OptimalityTol=1e-9;m.Params.IntFeasTol=1e-9;m.update()
        objectives=[legacy[0][1],legacy[2][1],legacy[3][1]]
        variables=[v for v in m.getVars() if v.VarName.startswith('arc[')]
        for index,pattern in enumerate(patterns):
            selected={f'arc[{u},{k}]' for u,ks in pattern.items() for k in ks}
            for v in variables:v.LB=v.UB=float(v.VarName in selected)
            locks=[];scores=[];physical_pass=False
            for i,obj in enumerate(objectives):
                m.setObjective(obj);m.optimize()
                if m.Status==gp.GRB.INFEASIBLE:break
                assert m.Status==gp.GRB.OPTIMAL,(case,label,m.Status)
                scores.append(m.ObjVal)
                values=dict(zip(m.getAttr('VarName'),m.getAttr('X')))
                # Restore native removed zero columns for independent physical validation.
                for u in initial:
                    for k in range(len(arcs)):values.setdefault(f'arc[{u},{k}]',0.)
                    for s in sites:
                        for t in range(H):
                            for prefix in ['Pch','Pdis','Q']:values.setdefault(f'{prefix}[{u},{s},{t}]',0.)
                physical=native.validate(dict(values=values,initial_sites=initial,chosen_arcs=pattern,mode='MILP'),sites,routes,b,H)
                assert physical['PASS'],(case,label,physical)
                if label!='S0':matrix_validate(m,extension_values(values,holder['context'],holder['G']))
                physical_pass=True
                if i<2:locks.append(m.addConstr(obj<=m.ObjVal+(1e-7 if i==0 else 1e-8)))
            feasible=len(scores)==3
            output.append(dict(pattern=index,feasible=feasible,scores=scores if feasible else [],route=pattern,physical_PASS=physical_pass if feasible else None))
            for lock in locks:m.remove(lock)
            m.update()
        return None,dict(bounded_only=True)
    class Budget:
        stage='M1'
        def check(self):pass
    old=native.optimize;native.optimize=optimizer
    try:native.solve('M1',Budget(),sites,initial,routes,b,H,builder,strengthening_hook=callback)
    finally:native.optimize=old
    return output

def run():
    labels=authorization();rows=[];details={}
    assert read(OUT/'DEFAULT_PATH_REGRESSION.json')['PASS']
    for case in CASES:
        baseline=compare(case,'S0');details[case]={'S0':baseline}
        for label in labels[1:]:
            candidate=compare(case,label);assert len(candidate)==len(baseline)
            for a,b in zip(baseline,candidate):
                assert a['route']==b['route'] and a['feasible']==b['feasible'],(case,label,a,b)
                if a['feasible']:assert max(abs(x-y) for x,y in zip(a['scores'],b['scores']))<=TOL,(case,label,a,b)
            details[case][label]=candidate
            feasible=[r for r in candidate if r['feasible']];best=min((tuple(r['scores']) for r in feasible),default=None)
            rows.append(dict(case=case,candidate=label,PASS=True,exhaustive_route_patterns=len(baseline),
                feasible_patterns=len(feasible),same_feasibility=True,same_P1=True,same_P2_energy=True,same_P2_count=True,
                valid_physical_projection=True,P1=best[0] if best else None,P2_energy=best[1] if best else None,P2_count=best[2] if best else None))
        print('EXHAUSTIVE INTEGER EQUIVALENCE',case,len(baseline),'PASS',flush=True)
    table('BOUNDED_INTEGER_EQUIVALENCE.csv',rows)
    dump('BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json',dict(PASS=True,case_count=len(CASES),authorized=labels,
        tolerance=TOL,exhaustive_complete_route_paths=True,mode_bits_globally_optimized=True,
        S3_implied_compact_G_bounds=(OUT/'S3_NUMERICAL_RECOVERY.json').exists(),
        degeneracy_policy='Returned continuous points may differ; every returned point is independently physical-valid. Entire physical fiber equivalence follows from the constructive proof.',results=details))

if __name__=='__main__':run()
