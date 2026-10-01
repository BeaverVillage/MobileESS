"""Bounded IIS extraction from the exact fixed-root diagnostic."""
from .diagnostics import *

def run():
    assert read(OUT/'ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json')['certified_infeasible']
    v,names,_=solution();_,_,_,sites,initial,routes,battery=inputs();arcs=topology(sites,routes)
    x={}
    for n in names:
        if n.startswith('arc['):
            unit,k=n[4:-1].rsplit(',',1);x[unit,int(k)]=v[n]
    ch={(u,s,t):v[f'Pch[{u},{s},{t}]'] for u in initial for s in sites for t in range(96)}
    dis={(u,s,t):v[f'Pdis[{u},{s},{t}]'] for u,s,t in ch}
    m,_=energy_model(arcs,sites,initial,battery,x,ch,dis)
    try:
        m.Params.Threads=1;m.Params.TimeLimit=60;m.update();begin=perf_counter();m.computeIIS()
        selected=[c for c in m.getConstrs() if c.IISConstr]
        rows=[]
        for c in selected:
            r=m.getRow(c)
            rows.append(dict(name=c.ConstrName,sense=c.Sense,RHS=c.RHS,
                terms=[dict(variable=r.getVar(i).VarName,coefficient=r.getCoeff(i)) for i in range(r.size())]))
        report=dict(run=True,seconds=perf_counter()-begin,minimal=bool(m.IISMinimal),rows=rows,
            family_counts=dict(Counter(c.ConstrName.split('[')[0] for c in selected)),
            fixed_root_unmodified=True,source_sha256=sha(OUT/'BASE_ROOT_LP_SOLUTION.npz'),
            original_binary_min=min(v[n] for n in names if n.startswith('arc[')),
            original_matrix_max_violation=read(OUT/'BASE_ROOT_LP_SOLUTION_SUMMARY.json')['original_matrix_validation']['matrix_max_violation'])
        dump('ROOT_ENERGY_DISAGGREGATION_IIS.json',report)
        print('IIS',len(rows),report['family_counts'],report['seconds'],flush=True)
    finally:m.dispose()

if __name__=='__main__':run()
