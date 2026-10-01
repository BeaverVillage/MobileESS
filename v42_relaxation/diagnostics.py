"""Fractional mechanism witnesses on the frozen baseline optimum."""
from collections import defaultdict
from dataclasses import asdict
from .base import *

def solution():
    receipt=read(OUT/'BASE_ROOT_LP_OPTIMIZATION.json')
    assert receipt['reproduced'] and read(OUT/'BASE_F3_IDENTITY.json')['PASS']
    with np.load(OUT/'BASE_ROOT_LP_SOLUTION.npz',allow_pickle=False) as z:
        assert sha(OUT/'BASE_ROOT_LP_SOLUTION.npz')==read(OUT/'BASE_ROOT_LP_SOLUTION_SUMMARY.json')['solution_sha256']
        return dict(zip(map(str,z['names']),map(float,z['values']))), list(map(str,z['model_names'])), list(map(str,z['original_types']))

def topology(sites,routes,horizon=96):
    return [(s,t,s,t+1,None) for s in sites for t in range(horizon)]+[(r.source,r.depart,r.destination,r.connect,r) for r in routes]

def census(v,model_names,types,arcs):
    families=defaultdict(list)
    for name,kind in zip(model_names,types):
        if kind!='B':continue
        if name.startswith('arc['):
            k=int(name.rsplit(',',1)[1][:-1]);family='stay_arcs' if arcs[k][-1] is None else 'travel_arcs'
        else:family=name.split('[')[0]
        families[family].append(v[name])
    rows=[]
    for family,values in families.items():
        a=np.asarray(values);f=a[(a>TOL)&(a<1-TOL)];fractionality=np.minimum(f,1-f)
        row=dict(family=family,total_variables=len(a),exactly_zero=int(np.count_nonzero(abs(a)<=TOL)),
            exactly_one=int(np.count_nonzero(abs(a-1)<=TOL)),fractional_count=len(f),tolerance=TOL,
            out_of_bounds_count=int(np.count_nonzero((a < -TOL)|(a>1+TOL))))
        for label,vals in [('value',f),('fractionality',fractionality)]:
            for key,q in [('min',0),('Q05',.05),('Q25',.25),('median',.5),('Q75',.75),('Q95',.95),('max',1)]:
                row[label+'_'+key]=float(np.quantile(vals,q)) if len(vals) else None
        rows.append(row)
    table('ROOT_FRACTIONALITY_BY_FAMILY.csv',rows)
    return rows

def mode_rows(v,sites,initial,battery,horizon=96):
    rows=[]
    for m in initial:
        for t in range(horizon):
            y=sum(v[f'arc[{m},{sites.index(s)*horizon+t}]'] for s in sites)
            z=v[f'charge_mode[{m},{t}]']
            ch=sum(v[f'Pch[{m},{s},{t}]'] for s in sites)
            dis=sum(v[f'Pdis[{m},{s},{t}]'] for s in sites)
            rows.append(dict(MESS=m,time=t,stay_mass=y,charge_mode=z,Pch_sum=ch,Pdis_sum=dis,
                H1_residual=z-y,H2_residual=ch-battery.p_limit*z,
                H3_residual=dis-battery.p_limit*(y-z)))
    return rows

def audit():
    v,names,types=solution();_,_,_,sites,initial,routes,battery=inputs();arcs=topology(sites,routes)
    counts=census(v,names,types,arcs);rows=[];by_time=defaultdict(list)
    for k,a in enumerate(arcs):by_time[a[1]].append(k)
    for m in initial:
        for t in range(96):
            stay=np.array([v[f'arc[{m},{sites.index(s)*96+t}]'] for s in sites])
            positive=stay[stay>TOL];y=float(stay.sum())
            weights=positive/positive.sum() if len(positive) else positive
            travel=[v[f'arc[{m},{k}]'] for k in by_time[t] if arcs[k][-1] is not None]
            rows.append(dict(MESS=m,time=t,stay_mass=y,positive_sites=len(positive),
                positive_fractional_sites=int(np.count_nonzero((stay>TOL)&(stay<1-TOL))),
                max_site_mass=float(stay.max()),location_entropy=float(-sum(weights*np.log(weights))),
                travel_departure_mass=float(sum(travel)),fractional_travel_mass=float(sum(x for x in travel if TOL<x<1-TOL)),
                fractional_travel_decisions=sum(TOL<x<1-TOL for x in travel),
                positive_route_branches=int(len(positive)+sum(x>TOL for x in travel))))
    table('ROOT_ROUTE_SPLIT_AUDIT.csv',rows)
    summary=dict(tolerance=TOL,total_MESS_slots=len(rows),
        maximum_simultaneous_fractional_sites=max(r['positive_fractional_sites'] for r in rows),
        maximum_positive_sites=max(r['positive_sites'] for r in rows),
        fraction_slots_multiple_positive_sites=sum(r['positive_sites']>1 for r in rows)/len(rows),
        fraction_slots_fractional_travel=sum(r['fractional_travel_decisions']>0 for r in rows)/len(rows),
        maximum_simultaneous_route_branches=max(r['positive_route_branches'] for r in rows),
        interpretation='LP relaxation diagnostic; route splitting alone is not a physical-invalidity claim',
        travel_mass_semantics='departure decisions; in-transit arcs have no new departure mass')
    dump('ROOT_ROUTE_SPLIT_SUMMARY.json',summary)
    rows=mode_rows(v,sites,initial,battery);table('MODE_HULL_ROOT_VIOLATIONS.csv',rows)
    per={}
    for h in ['H1','H2','H3']:
        residual=np.array([r[h+'_residual'] for r in rows]);positive=residual[residual>TOL]
        per[h]=dict(violation_count=len(positive),maximum_violation=max(0.,float(residual.max())),
            mean_positive_violation=float(positive.mean()) if len(positive) else 0.,total_positive_violation=float(positive.sum()))
    count=sum(r['violation_count'] for r in per.values())
    mode=dict(tolerance=TOL,per_inequality=per,violation_count=count,
        maximum_violation=max(r['maximum_violation'] for r in per.values()),
        MODE_HULL_CAN_IMPROVE_CURRENT_ROOT=count>0,
        conclusion='A violation authorizes a test; it does not guarantee an objective gain')
    dump('MODE_HULL_ROOT_SUMMARY.json',mode)
    print('FRACTIONAL DIAGNOSTICS',counts,summary,mode,flush=True)

def energy_model(arcs,sites,initial,battery,x,ch,dis,horizon=96,model=None,compact_bounds=False):
    """Same linear arc-energy equations in fixed diagnostic and S2 extension."""
    m=model or gp.Model('FIXED_ROOT_ARC_ENERGY');m.Params.OutputFlag=0
    incoming=defaultdict(list);outgoing=defaultdict(list);G={};arrivals={}
    for unit,origin in initial.items():
        for k,(s,t,d,e,r) in enumerate(arcs):
            key=unit,k
            if key not in x:continue
            mass=x[key]
            # For variable x in [0,1], the retained rows already imply these
            # compact bounds. This optional representation changes no LP point.
            G[key]=m.addVar(lb=0. if compact_bounds else -gp.GRB.INFINITY,
                ub=battery.maximum if compact_bounds else gp.GRB.INFINITY,name=f'G[{unit},{k}]')
            m.addConstr(G[key]>=battery.minimum*mass,name=f'G_min[{unit},{k}]')
            m.addConstr(G[key]<=battery.maximum*mass,name=f'G_max[{unit},{k}]')
            a=G[key]-r.energy_kwh*mass if r else G[key]+battery.dt_hours*(battery.eta_charge*ch[unit,s,t]-dis[unit,s,t]/battery.eta_discharge)
            arrivals[key]=a
            m.addConstr(a>=battery.minimum*mass,name=f'A_min[{unit},{k}]')
            m.addConstr(a<=battery.maximum*mass,name=f'A_max[{unit},{k}]')
            outgoing[unit,s,t].append(G[key]);incoming[unit,d,e].append(a)
        m.addConstr(gp.quicksum(outgoing[unit,origin,0])==battery.initial,name=f'G_source[{unit}]')
        for s in sites:
            for t in range(horizon):
                if (s,t)==(origin,0):continue
                m.addConstr(gp.quicksum(outgoing[unit,s,t])==gp.quicksum(incoming[unit,s,t]),name=f'G_node[{unit},{s},{t}]')
        m.addConstr(gp.quicksum(a for s in sites for a in incoming[unit,s,horizon])==battery.terminal,name=f'G_terminal[{unit}]')
    return m,G

def energy():
    assert not (LOCAL/'ENERGY_STARTED.json').exists(), 'NO_ENERGY_RETRY'
    (LOCAL/'ENERGY_STARTED.json').write_text('{}\n')
    v,names,types=solution();_,_,_,sites,initial,routes,battery=inputs();arcs=topology(sites,routes)
    # Exactly surviving native columns; omitted zero columns are structurally unreachable.
    x={}
    for n in names:
        if n.startswith('arc['):
            unit,k=n[4:-1].rsplit(',',1);x[unit,int(k)]=v[n]
    ch={(u,s,t):v[f'Pch[{u},{s},{t}]'] for u in initial for s in sites for t in range(96)}
    dis={(u,s,t):v[f'Pdis[{u},{s},{t}]'] for u,s,t in ch}
    m,G=energy_model(arcs,sites,initial,battery,x,ch,dis)
    try:
        m.Params.Method=2;m.Params.Threads=1;m.Params.OutputFlag=1;m.Params.LogToConsole=0
        m.Params.LogFile=str(LOCAL/'ENERGY.log');m.setObjective(0);m.update();before=stats(m)
        begin=perf_counter();m.optimize();wall=perf_counter()-begin
        status=m.Status;feasible=status==gp.GRB.OPTIMAL;infeasible=status==gp.GRB.INFEASIBLE
        report=dict(status=status,feasible=feasible,certified_infeasible=infeasible,
            ENERGY_POOLING_WITNESS=True if infeasible else False if feasible else None,
            seconds=wall,model=before,settings=dict(Method=2,Threads=1),battery=asdict(battery),
            original_x_Pch_Pdis_fixed=True,coefficient_clipping=False,original_variables_changed=False,
            original_root_solution_sha256=sha(OUT/'BASE_ROOT_LP_SOLUTION.npz'),
            max_violation=m.MaxVio if feasible else None)
        dump('ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json',report)
        assert feasible or infeasible, 'ENERGY_DIAGNOSTIC_INCONCLUSIVE_STOP'
        if feasible:
            np.savez_compressed(OUT/'ROOT_ENERGY_EXTENSION.npz',names=np.array([g.VarName for g in G.values()]),values=np.array([g.X for g in G.values()]))
            iis=dict(run=False,reason='Feasible fixed-root extension; no IIS exists')
        else:
            # Full IIS on this 800k-row diagnostic may be expensive; the native
            # infeasibility status itself is the preregistered witness.
            iis=dict(run=False,reason='Full arc-energy IIS deferred; certified LP infeasibility is sufficient for the gate',rows=m.NumConstrs,columns=m.NumVars)
        dump('ROOT_ENERGY_DISAGGREGATION_IIS.json',iis)
        (OUT/'ROOT_ENERGY_DISAGGREGATION_SOLVER.display.txt').write_text((LOCAL/'ENERGY.log').read_text(encoding='utf8'),encoding='utf8')
        print('ENERGY DIAGNOSTIC',report,flush=True)
    finally:m.dispose()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['audit','energy']);a=p.parse_args();globals()[a.phase]()
