from .common import *
from .guard import Guard
from v42_m1_accel_vnext.local import load
from v42_m1_accel_vnext.labels import solve
from v42_dw_root.models import build
from v42_dw_root.run import exact_rc
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
from v42_degen.identity import inputs,signature
from v42_dw_root.partition import axes
import numpy as np
import time

def inspect_point(b,x,pi,alpha,matrix,attrs):
    start=time.perf_counter();physical=b.validate(x,True)
    raw=corrected_rows(matrix,attrs,x,True,pure_binary_equalities(matrix,attrs))
    a,c,key=b.column(x);exact,error=b.exact_coupling(x,a)
    rc=float(exact_rc(b,x,pi,alpha));dense=c-float(pi@a)-alpha
    assert physical['PASS'] and raw['PASS'] and error<=1e-12 and abs(rc-dense)<=EPS
    names=np.asarray(b.d['names']);route=np.array([str(n).startswith('arc[') for n in names])
    return dict(PASS=True,physical=physical,original_rows=raw,column_SHA=key,
        coupling_SHA=hashlib.sha256(a.tobytes()).hexdigest(),coupling_exact_error=error,
        route_SHA=hashlib.sha256(x[route].tobytes()).hexdigest(),recomputed_RC=rc,
        dense_master_RC=dense,reconstruction_wall_seconds=time.perf_counter()-start)

def run():
    assert (OUT/'PREREGISTRATION_AUTHORITY.json').exists()
    assert not (OUT/'HYBRID_PRICING_SELECTION.json').exists(),'Decision already frozen'
    guard=Guard('HYBRID',[]);guard.gate()
    blocks,cp,pi,alpha,seeds=load();A,d,*_=inputs();owner,_=axes();local=[]
    for m,b in enumerate(blocks):
        has=np.asarray(abs(A)@(owner==m).astype(float)).ravel()>0
        others=np.asarray(abs(A)@(owner!=m).astype(float)).ravel()>0
        rows=np.flatnonzero(has & ~others)
        local.append((A[rows][:,b.columns],dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],
            lower=d['lower'][b.columns],upper=d['upper'][b.columns],types=d['types'][b.columns],
            objective=d['objective'][b.columns],constant=np.array(0.))))
    del A,d,owner
    started=time.perf_counter();guard.start(started+600);result=[]
    try:
        for m,b in enumerate(blocks):
            assert not guard.cancel.is_set()
            attrs=dict(b.d,objective=np.asarray(b.d['objective']-b.B.T@pi),constant=np.array(-float(alpha[m])))
            record=dict(MESS=b.unit,true_dual_SHA=cp['RMP']['dual_SHA'],matrix_signature=signature(b.A,attrs),
                full_original_domain=True,continuous_SOC_P_Q=True,baseline={},hybrid={})
            tick=time.perf_counter();native=build(b.A,attrs,'EXACT_ORIGINAL_'+b.unit)
            build_seconds=time.perf_counter()-tick
            cfg=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
                MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,Seed=20260929,TimeLimit=60.)
            for k,v in cfg.items():native.setParam(k,v)
            native.setAttr('Start',native.getVars(),seeds[m].tolist())
            native.Params.LogFile=str(OUT/f'HYBRID_ORIGINAL_{b.unit}.log')
            guard.active=native;tick=time.perf_counter();native.optimize();elapsed=time.perf_counter()-tick;guard.active=None
            def finite(v):return float(v) if np.isfinite(v) and abs(v)<1e90 else None
            base=dict(status=native.Status,build_seconds=build_seconds,native_seconds=elapsed,
                Gurobi_runtime=native.Runtime,global_BestBd=finite(native.ObjBound),nodes=native.NodeCount,settings=cfg)
            bx=None
            if native.SolCount:
                bx=np.asarray(native.getAttr('X'));base['point']=inspect_point(b,bx,pi,alpha[m],*local[m])
                np.savez_compressed(OUT/f'HYBRID_ORIGINAL_{b.unit}.npz',x=bx,axis=b.columns)
            base['exact_optimum_RC']=base['point']['recomputed_RC'] if native.Status==2 and bx is not None else None
            base['wall_seconds']=build_seconds+elapsed+(base.get('point',{}).get('reconstruction_wall_seconds',0))
            native.dispose();record['baseline']=base
            hybrid,x=solve(b.A,attrs,seconds=60.,validator=lambda v:b.validate(v,True)['PASS'] and
                corrected_rows(*local[m],v,True,pure_binary_equalities(*local[m]))['PASS'],
                seed=seeds[m],guard=guard,log=OUT/f'HYBRID_LABELS_{b.unit}.log')
            if x is not None:
                hybrid['point']=inspect_point(b,x,pi,alpha[m],*local[m])
                np.savez_compressed(OUT/f'HYBRID_LABELS_{b.unit}.npz',x=x,axis=b.columns)
            # PR154 explicitly marks this coverage prototype ineligible for a
            # D-W scientific certificate. A bounded incomplete search cannot override it.
            hybrid['valid_global_optimum_certificate']=bool(hybrid['optimum'] is not None and
                hybrid.get('scientific_DW_certificate_eligible',False))
            record['hybrid']=hybrid
            record['global_optimum_equivalent']=bool(base['exact_optimum_RC'] is not None and
                hybrid['valid_global_optimum_certificate'] and abs(base['exact_optimum_RC']-hybrid['optimum'])<=EPS)
            record['reconstructed_columns_identical']=bool(bx is not None and x is not None and
                base['point']['column_SHA']==hybrid['point']['column_SHA'])
            result.append(record);write('HYBRID_PRICING_CLEAN_BENCHMARK_PROGRESS.json',dict(units=result))
            print('HYBRID_UNIT',b.unit,base['status'],hybrid['status'],record['global_optimum_equivalent'],flush=True)
    finally:
        resource=guard.close();wall=time.perf_counter()-started
        original=sum(r['baseline']['wall_seconds'] for r in result)
        hybrid_wall=sum(r['hybrid']['wall_seconds'] for r in result)
        gain=1-hybrid_wall/original if original else None
        equivalent=len(result)==4 and all(r['global_optimum_equivalent'] for r in result)
        selected=bool(equivalent and gain is not None and gain>=.20 and not resource['failures'] and wall<=600)
        write('HYBRID_PRICING_FULLSCALE_EQUIVALENCE.json',dict(PASS=equivalent,units=result,
            feasible_set_coverage='Binary 0/1 branching retains the complete original continuous polyhedron',
            global_optimum_equivalence_proven=equivalent,existing_numerical_authority=EPS))
        write('HYBRID_PRICING_CLEAN_BENCHMARK.json',dict(units=result,continuous_wall_seconds=wall,
            cap=600,original_practical_wall=original,hybrid_practical_wall=hybrid_wall,
            practical_speed_improvement=gain,resource=resource,clean=not resource['failures']))
        write('HYBRID_PRICING_SELECTION.json',dict(HYBRID_SELECTED=selected,
            PRICING_BACKEND='HYBRID_DP_LP' if selected else 'ORIGINAL_GUROBI_EXACT',
            global_optimum_equivalence_proven=equivalent,practical_speed_improvement=gain,
            reason='FOUR_VALID_EQUIVALENT_GLOBAL_OPTIMA_AND_20_PERCENT_GAIN' if selected else
                'REJECTED_GLOBAL_OPTIMUM_CERTIFICATE_OR_EQUIVALENCE_OR_20_PERCENT_GAIN_NOT_PROVEN',
            frozen=True,true_dual_SHA=cp['RMP']['dual_SHA']))
        print('HYBRID_DECISION',selected,wall,gain,flush=True)

if __name__=='__main__':run()
