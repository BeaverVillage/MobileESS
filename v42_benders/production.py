"""Conditional original-domain canary/production/P2, never downstream stages."""
import numpy as np
import gurobipy as gp
from .common import *
from .audit import model
from .canonical import from_model
from .engine import solve,relative_gap
from .runner import write_tables

def movement_coefficients(can):
    from v42_threshold.common import arcs
    graph=arcs();energy=[];count=[]
    for i in can.xi:
        name=str(can.names[i]);r=None
        if name.startswith('arc['):r=graph[int(name[4:-1].split(',')[1])][-1]
        energy.append(0. if r is None else r.energy_kwh);count.append(float(r is not None))
    return np.asarray(energy),np.asarray(count)

def run_one(kind,seconds,lock=None):
    marker=LOCAL/(kind+'_STARTED.json');assert not marker.exists(),'NO_RUN_RETRY'
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=model(env)
    if lock is not None:m.addConstr(m.getVarByName('rho_max')<=lock+1e-7,name='inherited_P1_lock')
    m.update();can=from_model(m)
    assert len(can.xi)==208312 and len(can.yi)==108431
    from .validation import original_point
    def validate(z):
        return original_point(m,can.names,z)
    start=np.load(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz')['values']
    assert validate(start)['PASS'] if lock is None else True
    from v42_threshold.common import resource_snapshot
    resource=resource_snapshot();threads=1 if resource['other_heavy_solve'] else read('PREREGISTRATION.json')['threads']
    record=read('RESOURCE_RECEIPT.json');record[kind]=resource;dump('RESOURCE_RECEIPT.json',record)
    marker.write_text(__import__('json').dumps(dict(commit=git('rev-parse','HEAD'),budget=seconds,master=208312,
        P1_lock=None if lock is None else lock+1e-7,threads=threads))+'\n')
    log_dir=LOCAL/kind;log_dir.mkdir(exist_ok=True)
    kwargs=dict(initial_lower=ORIGINAL_LB,initial_upper=ORIGINAL_UB,warm_start=start) if lock is None else dict(
        movement=movement_coefficients(can)[0],count=movement_coefficients(can)[1],accepted_p1=lock)
    def progress(mr,rr,cuts):print(kind,'iteration',mr['iteration'],'LP',rr['status'],'cuts',len(cuts),'LB',mr['lower'],'UB',mr['upper'],flush=True)
    try:
        result,point,cuts=solve(can,env=env,seconds=seconds,threads=threads,validate=validate,
            progress=progress,log_dir=log_dir,**kwargs)
        result['executed']=True
        if point is not None:
            np.savez_compressed(OUT/(kind+'_SOLUTION.npz'),names=can.names,values=point)
            result['original_validation']=validate(point)
    finally:m.dispose();env.dispose()
    write_tables(kind,result,cuts)
    result['accepted']=bool(lock is None and result['status']=='P1_GAP_TARGET' and point is not None and
        result['original_validation']['PASS'] and result['relative_gap']<=.005)
    dump(kind+'_RESULT.json',result)
    return result

def run():
    gate=read('FULL_M1_CANARY_AUTHORIZATION.json')
    if not gate['authorized']:return
    assert read('ACTUAL_SOLVER_RECOURSE_MATRIX_AUDIT.json')['PASS']
    assert read('INDEPENDENT_CUT_REPLAY_AUDIT.json')['PASS']
    c=run_one('FULL_M1_CANARY',600)
    original_gap=relative_gap(ORIGINAL_UB,ORIGINAL_LB)
    authorized=bool(c['status'] not in ['STOP_UNCERTIFIABLE','UNSAFE_MASTER_STATUS'] and
        sum(r['status'] in [2,3] for r in c['recourse_log'])>=2 and c['lower'] is not None and c['upper'] is not None and
        (c['relative_gap']<=.005 or original_gap-c['relative_gap']>=.001))
    dump('M1_PRODUCTION_AUTHORIZATION.json',dict(authorized=authorized,budget_seconds=1800,
        max_runs=1,canary_status=c['status'],finite_valid_LB=c['lower'],validated_UB=c['upper'],
        gap_progression=original_gap-c['relative_gap'],exactness=read('FIXTURE_EXACTNESS.json')['PASS'],
        stable_recourse=sum(r['status'] in [2,3] for r in c['recourse_log'])>=2))
    if not authorized:return
    p1=run_one('M1_P1_DECOMPOSITION',1800)
    if p1['accepted']:run_one('M1_P2_DECOMPOSITION',1800,p1['upper'])

if __name__=='__main__':run()
