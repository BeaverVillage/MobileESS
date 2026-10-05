from .common import *
from .local import load
from .resources import Guard
from .labels import solve
from v42_dw_root.models import build
from v42_dw_root.run import exact_rc
import time
import numpy as np
from collections import Counter

def run():
    assert (OUT/'02_STABILIZATION_BENCHMARK.json').exists()
    assert not (OUT/'03_EXACT_PRICING_BENCHMARK.json').exists()
    freeze=read(OUT/'03_SOURCE_FREEZE.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    blocks,cp,pi,alpha,seeds=load();b=blocks[0]
    families=Counter(str(n).split('[',1)[0] for n in b.d['names'])
    write(OUT/'03_STRUCTURE_MATRIX_AUDIT.json',dict(classification='HYBRID_DP_LP_POSSIBLE',
        full_model_rows=b.A.shape[0],columns=b.A.shape[1],nnz=b.A.nnz,
        binary_coordinates=int(b.mask.sum()),families=dict(families),
        continuous_SOC=True,continuous_P_Q=True,finite_state_SOC_discretization_rejected=True,
        finite_binary_labels_with_full_original_LP=True,global_coupling_single_signed_entry=bool(np.all(np.diff(b.CSC.indptr)<=1)),
        route_arcs=len(b.arcs),horizon=96,original_pricing_domain_changed=False))
    cost=np.asarray(b.d['objective']-b.B.T@pi);attrs=dict(b.d,objective=cost,constant=np.array(-float(alpha[0])))
    guard=Guard('03',[]);guard.gate();started=time.perf_counter();guard.start(started+600)
    result=dict(stage=3,unit='MESS01',same_true_dual_SHA=cp['RMP']['dual_SHA'],
        classification='HYBRID_DP_LP_POSSIBLE',selected=False,baseline={},hybrid={},continuation_calls=0,Branch_and_Price_calls=0)
    m=None
    try:
        begin=time.perf_counter();m=build(b.A,attrs,'ORIGINAL_MIP_PRICING')
        cfg=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
                 MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,TimeLimit=60.)
        for k,v in cfg.items():m.setParam(k,v)
        m.setAttr('Start',m.getVars(),seeds[0].tolist());m.Params.LogFile=str(OUT/'03_BASELINE.log')
        tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None;native=time.perf_counter()-tick
        incumbent=None;point=None
        if m.SolCount:
            point=np.asarray(m.getAttr('X'));assert b.validate(point,True)['PASS'];incumbent=float(exact_rc(b,point,pi,alpha[0]))
        result['baseline']=dict(status=m.Status,native_seconds=native,wall_seconds=time.perf_counter()-begin,
            incumbent=incumbent,global_native_BestBd=m.ObjBound,exact_optimum=incumbent if m.Status==2 else None,
            nodes=m.NodeCount,settings=cfg,scientific_DW_certificate_eligible=False)
        if point is not None:np.savez_compressed(OUT/'03_BASELINE_POINT.npz',x=point,axis=b.columns)
        m.dispose();m=None
        if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
        hybrid,x=solve(b.A,attrs,seconds=60.,validator=lambda v:b.validate(v,True)['PASS'],seed=seeds[0],guard=guard,log=OUT/'03_HYBRID.log')
        result['hybrid']=hybrid
        if x is not None:
            assert b.validate(x,True)['PASS'];np.savez_compressed(OUT/'03_HYBRID_POINT.npz',x=x,axis=b.columns)
            result['hybrid']['validated_true_RC']=float(exact_rc(b,x,pi,alpha[0]))
        exact=result['baseline']['exact_optimum'] is not None and hybrid['optimum'] is not None
        equivalent=exact and abs(result['baseline']['exact_optimum']-hybrid['optimum'])<=1e-8
        ratio=result['baseline']['wall_seconds']/hybrid['wall_seconds']
        selected=equivalent and ratio>=1.2
        result.update(full_scale_optimum_identity=bool(equivalent) if exact else None,runtime_ratio=ratio,
            selected=selected,status='RETAINED' if selected else 'REJECTED_INCOMPLETE_OR_NO_WORK_REDUCTION',
            specialized_shortest_path_solver_claimed=False)
    except Exception as exc:
        if m is not None:m.dispose()
        result.update(status='INCONCLUSIVE',error=repr(exc),selected=False)
    finally:
        resource=guard.close()
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(resource=resource,continuous_wall_seconds=time.perf_counter()-started,wall_cap_seconds=600)
        write(OUT/'03_EXACT_PRICING_BENCHMARK.json',result);print('STAGE3_TERMINAL',result['status'],flush=True)

if __name__=='__main__':run()
