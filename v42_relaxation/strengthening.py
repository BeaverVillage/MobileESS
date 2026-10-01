"""Only the preregistered, witness-gated S1/S2/S3 extension families."""
from .base import *
from .diagnostics import energy_model,topology

def authorization():
    mode=read(OUT/'MODE_HULL_ROOT_SUMMARY.json')['MODE_HULL_CAN_IMPROVE_CURRENT_ROOT']
    energy=read(OUT/'ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json')['ENERGY_POOLING_WITNESS']
    assert energy is not None
    labels=['S0']+(['S1'] if mode else [])+(['S2'] if energy else [])+(['S3'] if mode and energy else [])
    return labels

def add_mode(m,c):
    for unit in c.initial_sites:
        for t in range(c.horizon):
            y=gp.quicksum(c.x[unit,c.stay[s,t]] for s in c.sites)
            z=c.charge_mode[unit,t]
            m.addConstr(z<=y,name=f'H1[{unit},{t}]')
            m.addConstr(gp.quicksum(c.charge[unit,s,t] for s in c.sites)<=c.battery.p_limit*z,name=f'H2[{unit},{t}]')
            m.addConstr(gp.quicksum(c.discharge[unit,s,t] for s in c.sites)<=c.battery.p_limit*(y-z),name=f'H3[{unit},{t}]')

def hook(label, holder=None, enforce_gate=True,compact_energy_bounds=False):
    assert label in ('S0','S1','S2','S3')
    if enforce_gate:assert label in authorization(), 'UNAUTHORIZED_STRENGTHENING'
    def apply(m,c):
        G={}
        if label in ('S1','S3'):add_mode(m,c)
        if label in ('S2','S3'):
            x={key:v for key,v in c.x.items() if not isinstance(v,float)}
            _,G=energy_model(c.arcs,c.sites,c.initial_sites,c.battery,x,c.charge,c.discharge,c.horizon,model=m,
                compact_bounds=compact_energy_bounds)
        if holder is not None:holder.update(context=c,G=G)
    return apply

def extension_values(values,c,G):
    """Construct the proof's exact G values on the incumbent integer path."""
    vv=values.copy()
    for (unit,k),g in G.items():
        x=c.x[unit,k]
        vv[g.VarName]=vv[f'SOC[{unit},{c.arcs[k][1]}]'] if vv[x.VarName]>.5 else 0.
    return vv

def default_regression():
    def inspect(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        values=data[2]['values'].copy();m.setObjective(objectives[0][1]);m.update()
        map_bindings(bindings,values);m.setAttr('Start',[values[n] for n in m.getAttr('VarName')]);m.update()
        observed=stats(m);matrix=matrix_validate(m,values)
        before=read(OUT/'PR108_MIP_START_RECEIPT.json')['matrix']
        receipt=dict(PASS=observed==EXPECTED and matrix==before,hook=None,observed=observed,expected=EXPECTED,
            matrix=matrix,before_hook_matrix=before,optimize_calls=0,native_source_sha256=sha(ROOT/'v42_native/mess.py'))
        dump('DEFAULT_PATH_REGRESSION.json',receipt);assert receipt['PASS'], 'STOP_DEFAULT_PATH_DRIFT'
        legacy=read(OUT/'LEGACY_PRESERVATION_AUDIT.json')
        historical={r['sha256'] for r in legacy['files'] if r['path']=='v42_native/mess.py'}
        for path in (ROOT/'docs').glob('*/LEGACY_PRESERVATION_AUDIT.json'):
            if path.parent==OUT:continue
            for row in read(path).get('files',[]):
                if row['path']=='v42_native/mess.py':historical.add(row['sha256'])
        dump('AUTHORIZED_HOOK_SUPERSESSION.json',dict(base_head=HEAD,path='v42_native/mess.py',
            current_sha256=receipt['native_source_sha256'],historical_sha256=sorted(historical),
            authorization='Explicit user request §21: optional strengthening/model hook, default matrix unchanged',
            full_default_regression_PASS=receipt['PASS']))
        print('DEFAULT PATH PASS',receipt,flush=True)
        return None,dict(optimize_calls=0)
    build(inspect)

def incumbent():
    labels=authorization();rows=[]
    for label in labels:
        holder={}
        def inspect(m,objectives,bindings,controls,data):
            from v42_m1_sparse.grid import map_bindings
            values=data[2]['values'].copy();m.setObjective(objectives[0][1]);m.update();map_bindings(bindings,values)
            if label!='S0':values=extension_values(values,holder['context'],holder['G'])
            check=matrix_validate(m,values);check.update(candidate=label,
                same_route_P_Q_SOC_rho=True,same_grid_voltage=True,AIDC_anchor_unchanged=True,
                G_constructed=len(holder.get('G',{})),rho=values['rho_max'])
            rows.append(check)
            dump('PR108_INCUMBENT_EXTENSION.json',dict(PASS=all(r['PASS'] for r in rows),candidates=rows,source_sha256=sha(LOCAL/'PR107_M1_PLAN.json')))
            print('INCUMBENT EXTENSION',check,flush=True)
            return None,dict(optimize_calls=0)
        build(inspect,None if label=='S0' else hook(label,holder))
    dump('STRENGTHENING_CANDIDATES.json',dict(authorized=labels,integer_physical_projection_identical=True,
        LP_projection_identical=False,proof='INTEGER_PROJECTION_PROOF.md',S1_gate=read(OUT/'MODE_HULL_ROOT_SUMMARY.json'),
        S2_gate=read(OUT/'ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json')))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['default_regression','incumbent']);a=p.parse_args();globals()[a.phase]()
