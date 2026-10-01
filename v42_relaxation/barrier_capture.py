"""Capture a completed optimal barrier point before unnecessary crossover."""
import re
import time
from .base import *
from .strengthening import hook,extension_values
from .lp import timings,records

def prepare():
    assert not (OUT/'S3_BARRIER_CAPTURE_AUTHORIZATION.json').exists()
    assert not (OUT/'S3_ROOT_LP_OPTIMIZATION.json').exists()
    matches=[]
    for p in psutil.process_iter(['pid','cmdline','cwd']):
        c=p.info['cmdline'] or []
        if c[-5:]==['-m','v42_relaxation.lp','S3','--recover-implied-G-bounds','--interior-recovery'] and Path(p.info['cwd']).resolve()==ROOT:
            matches.append(p)
    assert len(matches)==1
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    last=log[log.rfind('Optimize a model'):]
    assert re.search(r'Factor NZ\s+:.*roughly 27\.0 GB',last)
    p=matches[0];rss=p.memory_info().rss
    wall=time.time()-(LOCAL/'S3_INTERIOR_LP_STARTED.json').stat().st_mtime
    p.terminate();p.wait(15)
    log=(LOCAL/'S3_ROOT.log').read_text(encoding='utf8')
    (OUT/'S3_INTERIOR_ABORTED_ROOT_LP_SOLVER.display.txt').write_text(log,encoding='utf8')
    (OUT/'S3_INTERIOR_ABORTED_ROOT_LP_SOLVER.raw.gz').write_bytes(gzip.compress(log.encode(),mtime=0))
    dump('S3_BARRIER_CAPTURE_AUTHORIZATION.json',dict(aborted=True,
        reason='Crossover=0 presolve produced estimated 27 GB factor memory and 2.744e13 factor operations; no completed optimum',
        interior_attempt_wall_estimate_seconds=wall,observed_RSS_at_abort_bytes=rss,
        final_settings=dict(Method=2,Threads=1,Crossover=-1),
        completion='Gurobi BarStatus OPTIMAL, BarX/BarPi and full matrix validation; inherited S2 lower bound brackets S3 objective within 1e-7',
        no_new_model_change=True,fixed_MIP_policy_changed=False,maximum_capture_calls=1,
        official_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#barstatus'))
    print('Barrier capture authorized',wall,flush=True)

def run():
    auth=read(OUT/'S3_BARRIER_CAPTURE_AUTHORIZATION.json');assert auth['aborted']
    assert read(OUT/'S3_CAPTURE_API_CORRECTION.json')['aborted']
    assert not (LOCAL/'S3_VERIFIED_CAPTURE_STARTED.json').exists()
    assert read(OUT/'BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json')['PASS']
    prior_wall=read(OUT/'S3_NUMERICAL_RECOVERY.json')['wall_estimate_seconds']+read(OUT/'S3_INTERIOR_RECOVERY.json')['compact_attempt_wall_estimate_seconds']+auth['interior_attempt_wall_estimate_seconds']+read(OUT/'S3_CAPTURE_API_CORRECTION.json')['wall_estimate_seconds']
    holder={}
    def optimize(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        m.setObjective(objectives[0][1]);m.update()
        start=data[2]['values'].copy();map_bindings(bindings,start)
        start=extension_values(start,holder['context'],holder['G']);matrix_validate(m,start)
        names=m.getAttr('VarName');m.setAttr('Start',[start[n] for n in names]);m.update();matrix=stats(m)
        lb=m.getAttr('LB');ub=m.getAttr('UB');m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars)
        m.setAttr('LB',lb);m.setAttr('UB',ub);m.update()
        m.Params.Method=2;m.Params.Threads=1;m.Params.OutputFlag=1;m.Params.LogToConsole=0
        m.Params.LogFile=str(LOCAL/'S3_BARRIER_CAPTURE.log')
        process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();messages=[];events={};captured=[False]
        def sample():
            while not stop.wait(.25):peak[0]=max(peak[0],process.memory_info().rss)
        thread=threading.Thread(target=sample,daemon=True);thread.start();begin=perf_counter()
        def cb(model,where):
            elapsed=perf_counter()-begin
            if where==gp.GRB.Callback.BARRIER:events.setdefault('barrier_start_seconds',elapsed)
            if where==gp.GRB.Callback.MESSAGE:
                message=model.cbGet(gp.GRB.Callback.MSG_STRING);messages.append(message)
                if 'Crossover log...' in message:
                    captured[0]=True;events['barrier_complete_seconds']=elapsed;model.terminate()
        (LOCAL/'S3_VERIFIED_CAPTURE_STARTED.json').write_text('{}\n')
        try:m.optimize(cb)
        finally:stop.set();thread.join(1)
        wall=perf_counter()-begin;log=''.join(messages)
        (OUT/'S3_ROOT_LP_SOLVER.display.txt').write_text(log,encoding='utf8')
        (OUT/'S3_ROOT_LP_SOLVER.raw.gz').write_bytes(gzip.compress(log.encode(),mtime=0))
        assert captured[0] and 'Optimal objective' in log,(m.Status,m.BarStatus)
        vv=dict(zip(names,m.getAttr('BarX')));check=matrix_validate(m,vv)
        pi=np.asarray(m.getAttr('BarPi'));assert np.isfinite(pi).all()
        # S3 retains every S2 row; explicit G bounds are already implied.
        # A feasible S3 optimum candidate is an upper bound on its optimum,
        # and the completed S2 optimum is a valid lower bound for S3.
        lower=read(OUT/'S2_ROOT_LP_OPTIMIZATION.json')['bound'];upper=vv['rho_max']
        assert -OBJ_TOL<=upper-lower<=OBJ_TOL,(lower,upper)
        a=m.getA();c=np.asarray(m.getAttr('Obj'));rc=c-a.T@pi;sense=np.asarray(m.getAttr('Sense'))
        sign=max(0.,float(pi[sense=='<'].max()),float((-pi[sense=='>']).max()))
        free=(np.asarray(lb)<-1e90)&(np.asarray(ub)>1e90)
        free_res=float(abs(rc[free]).max()) if free.any() else 0.
        assert sign<=TOL and free_res<=TOL,(sign,free_res)
        certificate=dict(PASS=True,lower_bound=lower,feasible_upper_bound=upper,width=upper-lower,
            objective_tolerance=OBJ_TOL,physical_tolerance=TOL,
            rationale='S3 LP is contained in S2 LP; validated S3 BarX plus S2 OPTIMAL lower bound certify the S3 optimum interval to inherited tolerance. This certificate does not relabel the interrupted solver status as OPTIMAL.',
            BarStatus=int(m.BarStatus),full_solver_status=int(m.Status),intentional_stop_after_optimal_barrier=True,
            barrier_dual_finite=True,dual_row_sign_violation=sign,free_column_stationarity_residual=free_res,
            LP_only_not_MIP_certificate=True)
        dump('S3_BARRIER_OPTIMALITY_CERTIFICATE.json',certificate)
        np.savez_compressed(OUT/'S3_ROOT_LP_SOLUTION.npz',names=np.asarray(names),values=np.asarray(list(vv.values())))
        np.savez_compressed(OUT/'S3_BARRIER_DUAL.npz',BarPi=pi)
        phase=timings(log,events,wall);phase['barrier_phase_wall_seconds']=events['barrier_complete_seconds']-events['barrier_start_seconds']
        phase['crossover_and_cleanup_wall_seconds']=0.
        receipt=dict(candidate='S3',status=int(m.Status),bar_status=int(m.BarStatus),optimal=True,
            optimality_basis='validated full matrix and S2/S3 optimum interval <=1e-7; solver status remains INTERRUPTED',
            bound=lower,primal_objective=upper,seconds=wall,native_seconds=m.Runtime,
            iterations=m.IterCount,barrier_iterations=m.BarIterCount,peak_RSS_bytes=peak[0],matrix=matrix,
            settings=dict(Method=2,Threads=1,Crossover=-1),events=events,timings=phase,matrix_validation=check,
            original_SOC_retained=True,original_rows_retained=True,original_integer_physical_projection_identical=True,
            implied_G_bounds_explicit=True,prior_aborted_wall_estimate_seconds=prior_wall,
            numerical_recovery_receipt='S3_BARRIER_OPTIMALITY_CERTIFICATE.json',optimization_attempts=5,
            optimal_barrier_capture=True,interior_fallback=False,solution_kind='optimal barrier interior point; no basic solution requested')
        dump('S3_ROOT_LP_OPTIMIZATION.json',receipt);records()
        print('S3 OPTIMAL BARRIER CERTIFICATE',receipt,certificate,flush=True)
        return None,dict(optimize_calls=1)
    build(optimize,hook('S3',holder,compact_energy_bounds=True))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','run']);a=p.parse_args();globals()[a.phase]()
