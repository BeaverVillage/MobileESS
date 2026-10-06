"""Lossless scientific interfaces for independently replaying expanded points.

No compression decisions are used here; descriptors are captured from the
unaltered original model and evaluated in its original variable coordinates.
"""
import pickle,gzip,time
import numpy as np
import gurobipy as gp
from .common import *

def encode(x):
    if isinstance(x,gp.Var):return ('v',x.index)
    if isinstance(x,gp.LinExpr):return ('e',x.getConstant(),np.array([x.getVar(i).index for i in range(x.size())]),np.array([x.getCoeff(i) for i in range(x.size())]))
    return ('c',float(x))

def evaluate(e,x):
    if e[0]=='v':return float(x[e[1]])
    if e[0]=='c':return e[1]
    return float(e[1]+sum(c*x[i] for i,c in zip(e[2],e[3])))

def capture(m,units,levels,controls,bindings,path):
    m.update()
    u=[dict(unit,v={n:{key:encode(x) for key,x in items.items()} for n,items in unit['v'].items()}) for unit in units]
    result=dict(units=u,levels=[(n,encode(e)) for n,e in levels],controls=[[encode(x) for x in row] for row in controls],
          known={k:encode(x) for k,x in bindings['known'].items()},risk={k:encode(x) for k,x in bindings['risk'].items()},
          globals={n:i for i,n in enumerate(m.getAttr('VarName')) if n.startswith(('CC4_','RT_reserve[','RT_shortfall[','rho_max'))},
          rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs,fingerprint=m.Fingerprint)
    with gzip.open(path,'wb') as f:pickle.dump(result,f,pickle.HIGHEST_PROTOCOL)
    return result

def certify(descriptor,data,x,row_certificate,coefficients):
    from collections import defaultdict
    from v42_root.native import reconstruct
    from v42_exact.validation import check
    from v42_native.voltage import Stage
    from v42_compact.native import completion_risk
    from v42_final.reserve import risk_exposure
    from v42_integrated.contract import grid_audit
    t=time.perf_counter();bundle,jobs,bounds,r,raw,graphs,old,prep=data
    numeric=[dict(unit,v={n:{key:evaluate(e,x) for key,e in items.items()} for n,items in unit['v'].items()}) for unit in descriptor['units']]
    selected=reconstruct(numeric,data);controls=[[evaluate(e,x) for e in row] for row in descriptor['controls']]
    globals={n:float(x[i]) for n,i in descriptor['globals'].items()};rho=evaluate(descriptor['levels'][0][1],x)
    cert=check(selected,data,controls,globals,rho,stage=Stage.A1)
    gpu=defaultdict(float)
    for uid,o in selected.items():
        for site,a,b in o['segments']:
            for t0 in range(a,b):gpu[site,t0]+=jobs[uid].gpu
    known=max((abs(evaluate(e,x)-r.fixed_gpu.get(key,0)-gpu[key]) for key,e in descriptor['known'].items()),default=0.)
    expected=defaultdict(float)
    for uid,o in selected.items():
        site,_,end=o['segments'][-1]
        for key,n in completion_risk(jobs[uid],raw[uid],site,end,bundle).items():expected[key]+=n
    for uid,row in raw.items():
        if uid not in jobs:
            for key,n in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():expected[key]+=bundle['runtime_reserve_gamma']*n
    runtime=max((abs(evaluate(e,x)-expected[key]) for key,e in descriptor['risk'].items()),default=0.)
    grid=grid_audit(coefficients,controls,rho)
    cert.update(independent_known_GPU_max_violation=known,independent_Runtime_binding_max_violation=runtime,
        all_original_rows=row_certificate,all_phase_grid=grid,P1_rho=rho,
        model_defined_scientific_objective_snapshot={n:evaluate(e,x) for n,e in descriptor['levels']},
        artificial_physical_slack=0,artificial_scientific_slack=0,validation_seconds=time.perf_counter()-t,
        accepted_point_rounded_or_clipped=False)
    cert['PASS']=cert['PASS'] and row_certificate['PASS'] and grid['PASS'] and max(known,runtime)<=1e-5
    return cert,selected,controls,globals

def capture_baseline():
    import os
    os.environ['V42_ROOT_OUTPUT']=str(OUT.relative_to(ROOT));os.environ['V42_ROOT_LOCAL']=str(LOCAL)
    from v42_root.data import prepare
    from v42_root.native import build
    from v42_integrated.contract import physical_authority,all_transformer_rows
    from v42_bootstrap.grid import coefficients
    from .build import replay
    import scipy.sparse as sp
    import v42_boundary.model as boundary
    original_model=gp.Model
    class StaticModel(original_model):
        def optimize(self,*a,**k):raise PermissionError('SNAPSHOT_CAPTURE_OPTIMIZE_FORBIDDEN')
    gp.Model=StaticModel
    class Context:
        folder=LOCAL
        def check(self):pass
        def progress(self,p):pass
    with physical_authority():
        data=prepare();original=boundary.add_grid;boundary.add_grid=all_transformer_rows(original)
        try:m,units,levels,controls,bindings=build(Context(),data,'F2-CRA')
        finally:boundary.add_grid=original
        m.setObjective(levels[0][1]);m.update()
        assert m.NumVars==7449002 and m.NumConstrs==9133426 and m.NumNZs==53767578
        descriptor=capture(m,units,levels,controls,bindings,LOCAL/'SCIENTIFIC_INTERFACES.pkl.gz')
        x=np.load(LOCAL/'ACCEPTED_POINT.npz')['values'];a=sp.load_npz(LOCAL/'A0_MATRIX.npz');z=attributes()
        delta=a-m.getA();delta.eliminate_zeros();assert delta.nnz==0
        _,coeff=coefficients(data[0]);cert,selected,values,_=certify(descriptor,data,x,replay(a,z,x),coeff)
        baseline=json.loads((ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json').read_text())
        assert cert['PASS'] and clean(selected)==baseline['selected_jobs'] and np.array_equal(values,baseline['anchor']['controls'])
        write('SCIENTIFIC_INTERFACE_CAPTURE_AUDIT.json',dict(PASS=True,accepted_selected_jobs_equal=True,
            accepted_controls_exactly_equal=True,original_matrix_equal=True,descriptor=record(LOCAL/'SCIENTIFIC_INTERFACES.pkl.gz'),
            physical=cert,optimization_calls=0))
        m.dispose()
    gp.Model=original_model

if __name__=='__main__':capture_baseline()
