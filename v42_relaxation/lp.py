"""One full continuous P1 comparison per authorized exact candidate."""
import re
from .base import *
from .strengthening import authorization,hook,extension_values

def timings(log,events,wall):
    ps=re.findall(r'Presolve time: ([\d.]+)s',log)
    barrier=re.findall(r'Barrier solved model in \d+ iterations and ([\d.]+) seconds',log)
    barrier_begin=events.get('barrier_start_seconds');cross=events.get('simplex_start_seconds')
    return dict(presolve_seconds=float(ps[-1]) if ps else None,
        barrier_reported_seconds=float(barrier[-1]) if barrier else None,
        barrier_phase_wall_seconds=cross-barrier_begin if cross is not None and barrier_begin is not None else None,
        crossover_and_cleanup_wall_seconds=wall-cross if cross is not None else None)

def records():
    labels=authorization();rows=[]
    base=read(OUT/'BASE_ROOT_LP_OPTIMIZATION.json')
    log=(OUT/'BASE_ROOT_LP_SOLVER.display.txt').read_text(encoding='utf8')
    rows.append(dict(candidate='S0',**base['identity'],LB=base['bound'],delta_LB=0.,
        implied_gap=(UB-base['bound'])/UB,total_LP_wall_seconds=base['seconds'],successful_LP_wall_seconds=base['seconds'],
        prior_aborted_wall_estimate_seconds=0.,
        peak_RSS_bytes=base['peak_RSS_bytes'],**timings(log,base['events'],base['seconds'])))
    for label in labels[1:]:
        p=OUT/(label+'_ROOT_LP_OPTIMIZATION.json')
        if p.exists():
            d=read(p);assert d['optimal'] and d['matrix_validation']['PASS']
            rows.append(dict(candidate=label,**d['matrix'],LB=d['bound'],
                delta_LB=d['bound']-base['bound'],implied_gap=(UB-d['bound'])/UB,
                total_LP_wall_seconds=d['seconds']+d.get('prior_aborted_wall_estimate_seconds',0.),successful_LP_wall_seconds=d['seconds'],
                prior_aborted_wall_estimate_seconds=d.get('prior_aborted_wall_estimate_seconds',0.),
                peak_RSS_bytes=d['peak_RSS_bytes'],**d['timings']))
    table('ROOT_LP_STRENGTHENING_COMPARISON.csv',rows)
    table('STRUCTURAL_COMPARISON.csv',[{k:r[k] for k in ['candidate','binary','continuous','rows','columns','nonzeros','fingerprint']} for r in rows])
    return rows

def run(label,recover=False,interior=False):
    assert label in authorization()[1:]
    assert read(OUT/'DEFAULT_PATH_REGRESSION.json')['PASS']
    assert read(OUT/'BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json')['PASS']
    extensions=read(OUT/'PR108_INCUMBENT_EXTENSION.json');assert extensions['PASS']
    assert {r['candidate'] for r in extensions['candidates']}==set(authorization())
    marker=LOCAL/(label+'_LP_STARTED.json')
    recovery=None
    if recover:
        assert label=='S3' and marker.exists() and not (OUT/'S3_ROOT_LP_OPTIMIZATION.json').exists()
        recovery=read(OUT/'S3_NUMERICAL_RECOVERY.json')
        assert recovery['aborted'] and recovery['LP_projection_identical'] and recovery['no_solver_parameter_change']
        assert read(OUT/'BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json')['S3_implied_compact_G_bounds']
        if interior:
            fallback=read(OUT/'S3_INTERIOR_RECOVERY.json');assert fallback['aborted']
            assert fallback['next_LP_settings']==dict(Method=2,Threads=1,Crossover=0)
            recovery['wall_estimate_seconds']+=fallback['compact_attempt_wall_estimate_seconds']
            marker=LOCAL/'S3_INTERIOR_LP_STARTED.json';assert not marker.exists(), 'NO_INTERIOR_FALLBACK_RETRY'
        else:
            assert not (LOCAL/'S3_COMPACT_LP_STARTED.json').exists(), 'NO_RECOVERY_RETRY'
            marker=LOCAL/'S3_COMPACT_LP_STARTED.json'
    else:assert not marker.exists(), 'NO_CANDIDATE_LP_RETRY'
    assert not interior or recover
    holder={}
    def optimize(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        m.setObjective(objectives[0][1]);m.update()
        values=data[2]['values'].copy();map_bindings(bindings,values)
        values=extension_values(values,holder['context'],holder['G']);start_check=matrix_validate(m,values)
        if recover:
            dump('S3_COMPACT_INCUMBENT_EXTENSION.json',dict(**start_check,same_route_P_Q_SOC_rho=True,
                same_grid_voltage=True,implied_G_bounds=True,LP_projection_identical=True))
        names=m.getAttr('VarName');m.setAttr('Start',[values[n] for n in names]);m.update();matrix=stats(m)
        lb=m.getAttr('LB');ub=m.getAttr('UB')
        m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars);m.setAttr('LB',lb);m.setAttr('UB',ub);m.update()
        m.Params.Method=2;m.Params.Threads=1;m.Params.OutputFlag=1;m.Params.LogToConsole=0
        if interior:m.Params.Crossover=0
        m.Params.LogFile=str(LOCAL/(label+'_ROOT.log'))
        process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();events={};messages=[]
        def sample():
            while not stop.wait(.25):peak[0]=max(peak[0],process.memory_info().rss)
        thread=threading.Thread(target=sample,daemon=True);thread.start();begin=perf_counter()
        def cb(model,where):
            elapsed=perf_counter()-begin
            if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING))
            if where==gp.GRB.Callback.BARRIER:events.setdefault('barrier_start_seconds',elapsed)
            if where==gp.GRB.Callback.SIMPLEX:events.setdefault('simplex_start_seconds',elapsed)
        marker.write_text('{}\n')
        try:m.optimize(cb)
        finally:stop.set();thread.join(1)
        wall=perf_counter()-begin;log=''.join(messages)
        (OUT/(label+'_ROOT_LP_SOLVER.display.txt')).write_text(log,encoding='utf8')
        (OUT/(label+'_ROOT_LP_SOLVER.raw.gz')).write_bytes(gzip.compress(log.encode(),mtime=0))
        receipt=dict(candidate=label,status=m.Status,optimal=m.Status==gp.GRB.OPTIMAL,
            bound=m.ObjVal if m.SolCount else None,seconds=wall,native_seconds=m.Runtime,
            iterations=m.IterCount,barrier_iterations=m.BarIterCount,peak_RSS_bytes=peak[0],
            matrix=matrix,settings=dict(Method=2,Threads=1,**({'Crossover':0} if interior else {})),events=events,timings=timings(log,events,wall),
            original_SOC_retained=True,original_rows_retained=True,original_integer_physical_projection_identical=True,
            implied_G_bounds_explicit=recover,prior_aborted_wall_estimate_seconds=recovery['wall_estimate_seconds'] if recovery else 0.,
            numerical_recovery_receipt='S3_NUMERICAL_RECOVERY.json' if recovery else None,
            interior_fallback=interior,optimization_attempts=3 if interior else 2 if recover else 1)
        dump(label+'_ROOT_LP_OPTIMIZATION.json',receipt)
        assert receipt['optimal'], 'INCONCLUSIVE_CANDIDATE_LP_STOP'
        if interior:
            quality={n:float(m.getAttr(n)) for n in ['ConstrVio','BoundVio','DualVio','MaxVio']}
            assert all(np.isfinite(v) and v<=TOL for v in quality.values()),quality
            receipt['solver_quality']=quality
            receipt['timings']['crossover_and_cleanup_wall_seconds']=0.
            receipt['timings']['barrier_phase_wall_seconds']=wall-events['barrier_start_seconds']
        assert m.ObjVal<=UB+OBJ_TOL and m.ObjVal>=read(OUT/'BASE_ROOT_LP_OPTIMIZATION.json')['bound']-OBJ_TOL
        vv=dict(zip(names,m.getAttr('X')));receipt['matrix_validation']=matrix_validate(m,vv)
        np.savez_compressed(OUT/(label+'_ROOT_LP_SOLUTION.npz'),names=np.asarray(names),values=np.asarray(list(vv.values())))
        dump(label+'_ROOT_LP_OPTIMIZATION.json',receipt);records()
        print('CANDIDATE ROOT COMPLETE',label,receipt,flush=True)
        return None,dict(optimize_calls=1)
    build(optimize,hook(label,holder,compact_energy_bounds=recover))

def select():
    rows=records();assert len(rows)==len(authorization())
    selected=min(rows,key=lambda r:(-r['LB'],r['implied_gap'],r['total_LP_wall_seconds'],r['nonzeros'],r['rows']+r['columns']))
    material=selected['delta_LB']>=.001
    categories=dict(material=material,strong=selected['delta_LB']>=.01,
        very_strong=selected['LB']>=.62,target_region=selected['LB']>=.65)
    dump('ROOT_BOUND_GAIN_REPORT.json',dict(UB_existing=UB,LB_target=UB*(1-.005),baseline_LB=rows[0]['LB'],
        candidates=rows,thresholds=read(OUT/'PREREGISTRATION.json')['gain_categories'],selected_categories=categories,
        LP_only_not_MIP_certificate=True))
    dump('SELECTED_STRENGTHENING.json',dict(selected=selected['candidate'],frozen=True,
        integer_physical_projection_identical=True,selected_root_LB=selected['LB'],delta_LB=selected['delta_LB'],
        implied_gap=selected['implied_gap'],material=material,canary_authorized=material,
        numerical_tie_tolerance=OBJ_TOL,ranking='highest optimal root LB; implied gap; LP wall; matrix size',
        S3_implied_compact_G_bounds=(OUT/'S3_NUMERICAL_RECOVERY.json').exists(),
        decision='one 600-s proof canary' if material else 'STOP: every tested exact candidate gain < .001'))
    print('SELECTION',selected,categories,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('candidate',choices=['S1','S2','S3','select'])
    p.add_argument('--recover-implied-G-bounds',action='store_true');p.add_argument('--interior-recovery',action='store_true');a=p.parse_args()
    select() if a.candidate=='select' else run(a.candidate,a.recover_implied_G_bounds,getattr(a,'interior_recovery',False))
