"""Complete the remaining three pairs; never replay the completed MESS01 MILP."""
from .common import *
from .benchmark import inspect_point
from .guard import Guard
from v42_m1_accel_vnext.local import load
from v42_m1_accel_vnext.labels import solve
from v42_dw_root.models import build
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
from v42_degen.identity import inputs,signature
from v42_dw_root.partition import axes
import numpy as np
import re
import time
import traceback
import shutil

def run():
    assert not (OUT/'HYBRID_RESUME_STARTED.json').exists(),'No repeated benchmark extension'
    prior=read(OUT/'HYBRID_PRICING_CLEAN_BENCHMARK.json')
    assert prior['units']==[] and not read(OUT/'HYBRID_PRICING_SELECTION.json')['HYBRID_SELECTED']
    for name in ('HYBRID_PRICING_CLEAN_BENCHMARK.json','HYBRID_PRICING_FULLSCALE_EQUIVALENCE.json',
                 'HYBRID_PRICING_SELECTION.json','HYBRID_RESOURCE_LEDGER.csv','HYBRID_PROCESS_PROOFS.json'):
        shutil.copyfile(OUT/name,OUT/('FAILED_ATTEMPT_'+name))
    carried=prior['continuous_wall_seconds'];guard=Guard('HYBRID_REMAINING',[]);guard.gate()
    blocks,cp,pi,alpha,seeds=load();A,d,*_=inputs();owner,_=axes();local=[]
    for m,b in enumerate(blocks):
        has=np.asarray(abs(A)@(owner==m).astype(float)).ravel()>0
        others=np.asarray(abs(A)@(owner!=m).astype(float)).ravel()>0
        rows=np.flatnonzero(has & ~others)
        local.append((A[rows][:,b.columns],dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],
            lower=d['lower'][b.columns],upper=d['upper'][b.columns],types=d['types'][b.columns],
            objective=d['objective'][b.columns],constant=np.array(0.))))
    del A,d,owner
    first=blocks[0]
    with np.load(OUT/'HYBRID_ORIGINAL_MESS01.npz') as z:bx=z['x'].copy();assert np.array_equal(z['axis'],first.columns)
    log=(OUT/'HYBRID_ORIGINAL_MESS01.log').read_text(encoding='utf8')
    assert 'Optimal solution found (tolerance 0.00e+00)' in log
    match=re.search(r'Best objective ([\-\deE.+]+), best bound ([\-\deE.+]+)',log)
    runtime=float(re.search(r'Explored .* in ([\d.]+) seconds',log).group(1))
    audit=inspect_point(first,bx,pi,alpha[0],*local[0]);assert abs(audit['recomputed_RC']-float(match.group(1)))<=EPS
    result=[dict(MESS='MESS01',true_dual_SHA=cp['RMP']['dual_SHA'],full_original_domain=True,
        baseline=dict(status=2,exact_optimum_RC=audit['recomputed_RC'],global_BestBd=float(match.group(2)),
            Gurobi_runtime_from_log_rounded_seconds=runtime,wall_seconds=None,point=audit,
            recovered_from_completed_native_log_and_point=True,reoptimized=False),
        hybrid=dict(status='CERTIFICATE_REJECTED',optimum=None,error='RAW_PI_SIGN_INVALID',
            valid_global_optimum_certificate=False,wall_seconds=None),
        global_optimum_equivalent=False,reconstructed_columns_identical=None)]
    write('HYBRID_RESUME_STARTED.json',dict(carried_active_wall_seconds=carried,remaining_cap=600-carried,
        completed_MESS01_original_replayed=False,prior_failed_attempt_preserved=True,
        user_pause_excluded_from_active_compute_ledger=True,backend_decision_unchanged=True))
    started=time.perf_counter();guard.start(started+600-carried)
    try:
        for m in range(1,4):
            b=blocks[m];assert not guard.cancel.is_set()
            attrs=dict(b.d,objective=np.asarray(b.d['objective']-b.B.T@pi),constant=np.array(-float(alpha[m])))
            record=dict(MESS=b.unit,true_dual_SHA=cp['RMP']['dual_SHA'],matrix_signature=signature(b.A,attrs),
                full_original_domain=True,continuous_SOC_P_Q=True,baseline={},hybrid={})
            tick=time.perf_counter();native=build(b.A,attrs,'EXACT_ORIGINAL_'+b.unit);build_seconds=time.perf_counter()-tick
            cfg=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
                MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,Seed=20260929,TimeLimit=60.)
            for k,v in cfg.items():native.setParam(k,v)
            native.setAttr('Start',native.getVars(),seeds[m].tolist());native.Params.LogFile=str(OUT/f'HYBRID_ORIGINAL_{b.unit}.log')
            guard.active=native;tick=time.perf_counter();native.optimize();elapsed=time.perf_counter()-tick;guard.active=None
            bound=float(native.ObjBound)
            base=dict(status=native.Status,build_seconds=build_seconds,native_seconds=elapsed,
                Gurobi_runtime=native.Runtime,global_BestBd=bound if np.isfinite(bound) and abs(bound)<1e90 else None,
                nodes=native.NodeCount,settings=cfg)
            if native.SolCount:
                x=np.asarray(native.getAttr('X'));base['point']=inspect_point(b,x,pi,alpha[m],*local[m])
                np.savez_compressed(OUT/f'HYBRID_ORIGINAL_{b.unit}.npz',x=x,axis=b.columns)
            base['exact_optimum_RC']=base['point']['recomputed_RC'] if native.Status==2 and native.SolCount else None
            base['wall_seconds']=build_seconds+elapsed+base.get('point',{}).get('reconstruction_wall_seconds',0.)
            native.dispose();record['baseline']=base
            hybrid_start=time.perf_counter()
            try:
                hybrid,x=solve(b.A,attrs,seconds=60.,validator=lambda v:b.validate(v,True)['PASS'] and
                    corrected_rows(*local[m],v,True,pure_binary_equalities(*local[m]))['PASS'],
                    seed=seeds[m],guard=guard,log=OUT/f'HYBRID_LABELS_{b.unit}.log')
                if x is not None:
                    hybrid['point']=inspect_point(b,x,pi,alpha[m],*local[m])
                    np.savez_compressed(OUT/f'HYBRID_LABELS_{b.unit}.npz',x=x,axis=b.columns)
                hybrid['valid_global_optimum_certificate']=bool(hybrid['optimum'] is not None and
                    hybrid.get('scientific_DW_certificate_eligible',False))
            except Exception as error:
                hybrid=dict(status='CERTIFICATE_REJECTED',optimum=None,error=repr(error),
                    traceback=traceback.format_exc(),wall_seconds=time.perf_counter()-hybrid_start,
                    valid_global_optimum_certificate=False)
            record.update(hybrid=hybrid,global_optimum_equivalent=False,reconstructed_columns_identical=None)
            result.append(record);write('HYBRID_PRICING_CLEAN_BENCHMARK_PROGRESS.json',dict(units=result))
            print('HYBRID_UNIT',b.unit,base['status'],hybrid['status'],False,flush=True)
    finally:
        resource=guard.close();wall=time.perf_counter()-started
        complete=len(result)==4
        write('HYBRID_PRICING_FULLSCALE_EQUIVALENCE.json',dict(PASS=False,units=result,
            global_optimum_equivalence_proven=False,existing_numerical_authority=EPS,
            four_MESS_examined=complete,scientific_certificate_failures_preserved=True))
        write('HYBRID_PRICING_CLEAN_BENCHMARK.json',dict(units=result,
            continuous_wall_seconds=None,execution_segment_wall_seconds=[carried,wall],
            total_active_benchmark_wall_seconds=carried+wall,cap=600,
            user_pause_between_segments=True,performance_comparison='INCONCLUSIVE_CERTIFICATE_FAILURE',
            practical_speed_improvement=None,resource=resource,clean=not resource['failures'] and not prior['resource']['failures'],
            all_four_MESS_examined=complete,completed_pricing_replayed=False))
        # The rejection frozen before the user pause remains exactly the same.
        assert not read(OUT/'HYBRID_PRICING_SELECTION.json')['HYBRID_SELECTED']
        write('HYBRID_PRICING_DECISION_READBACK.json',dict(HYBRID_SELECTED=False,
            PRICING_BACKEND='ORIGINAL_GUROBI_EXACT',decision_changed=False,all_four_MESS_examined=complete,
            performance_comparison='INCONCLUSIVE',global_equivalence_proven=False))
        print('HYBRID_REMAINING_DONE',complete,carried+wall,flush=True)

if __name__=='__main__':run()
