from .common import *
from .root import install
import numpy as np
import gurobipy as gp
from v42_degen.identity import inputs,model
from v42_cutpass.monitor import Monitor,start_receipt
from v42_integrated.matrix import audit
def run():
    result=read(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json')
    if not result['material_gate']['PASS']:return
    gate('canary');A,d,B,e,i,_=inputs();m,_=model(B,e,i);install(m)
    policy=dict(read(REF/'M1_CUTPASSES1_SOLVE_RESULT.json')['settings'],TimeLimit=600)
    assert all(policy[k]==v for k,v in dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8).items())
    for k,v in policy.items():m.setParam(k,v)
    log=OUT/'MOVEMENT_GRID_MIP_CANARY.log';m.Params.LogFile=log.relative_to(ROOT).as_posix()
    available=read(OUT/'M1_FIXED_DISCRETE_POLISH_RESULT.json')['POLISHED_START_AVAILABLE']
    if available:
        with np.load(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz') as z:
            assert np.array_equal(z['names'],d['names']);x=z['values']
        assert audit(A,d,x,integral=True,tolerance=1e-8)['PASS']
        m.setAttr('Start',m.getVars(),x.tolist())
    m.update();once('MIP_CANARY');monitor=Monitor(m.getVars(),checkpoint=False);m.optimize(monitor)
    native_binding=start_receipt(monitor.start_messages) if available else dict(START_ATTEMPTED=False,START_SOLVER_ACCEPTED=False,rejection_message_observed=False,messages=[])
    write('POLISHED_START_SOLVER_BINDING.json',dict(START_ATTEMPTED=available,native_log_binding=native_binding,
          START_ACCEPTED=native_binding.get('START_SOLVER_ACCEPTED') if available else False,
          START_REJECTED=native_binding.get('rejection_message_observed') if available else False,
          all_columns_bound=m.NumVars if available else 0,raw_point_SHA=sha(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz') if available else None,
          log_SHA=sha(log),point_repairs=0,solver_tolerance_relaxations=0))
    LB=float(m.ObjBound) if abs(m.ObjBound)<1e100 and not monitor.errors else None;UB=None;checked=None
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));raw=audit(A,d,x,integral=True,tolerance=1e-8)
        import v42_integrated.solve as solve
        from v42_integrated.contract import physical_authority
        solve.OUT=OUT;solve.LOCAL=SOURCE;solve.write=write
        with physical_authority():physical=solve.physical(x,d);units=solve.grid_point(x,d)
        checked=dict(PASS=raw['PASS'] and physical['PASS'] and units['PASS'],raw=raw,physical=physical,units=units)
        if checked['PASS']:UB=raw['objective']
        np.savez_compressed(OUT/'CANARY_TERMINAL_POINT.npz',names=d['names'],values=x)
    observed=[r['last_MIP_observation']['LB'] for r in monitor.trace if r['last_MIP_observation'] and r['last_MIP_observation']['LB'] is not None]
    progress=bool(LB is not None and len(observed)>1 and max(observed)-min(observed)>1e-8)
    branch=monitor.times['first_nonroot'] is not None or monitor.times['first_branch'] is not None
    verdict='SUCCESS' if branch and progress else 'PARTIAL' if result['material_gate']['PASS'] and not branch else 'FAILED'
    write('MOVEMENT_GRID_MIP_CANARY_RESULT.json',dict(status=verdict,native_status=m.Status,optimization_calls=1,settings=policy,
          runtime=m.Runtime,barrier_iterations=m.BarIterCount,simplex_iterations=m.IterCount,node_count=m.NodeCount,
          first_nonroot=monitor.times['first_nonroot'],first_branch=monitor.times['first_branch'],first_incumbent=monitor.times['first_incumbent'],
          UB=UB,LB=LB,gap=None if UB is None or LB is None else (UB-LB)/abs(UB),solver_incumbents=m.SolCount,
          incumbent_audit=checked,bound_progression=progress,timeline=monitor.json(),callback_errors=monitor.errors,
          Start_attempted=available,Start_binding=native_binding,production_calls=0,global_UB_from_old_polish=False))
    m.dispose()
if __name__=='__main__':run()
