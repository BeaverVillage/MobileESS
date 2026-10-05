from .common import *
from .local import load
from .resources import Guard
from .reduction import duplicate_groups,quotient,lift
from v42_dw_root.models import build
from v42_dw_root.run import exact_rc
from v42_degen.identity import signature
import numpy as np
import time

def run():
    assert (OUT/'03_EXACT_PRICING_BENCHMARK.json').exists()
    assert not (OUT/'04_PRICING_REDUCTION_BENCHMARK.json').exists()
    freeze=read(OUT/'04_SOURCE_FREEZE.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    blocks,cp,pi,alpha,seeds=load();b=blocks[0]
    eligible=[j for j,n in enumerate(b.d['names']) if str(n).startswith('arc[')]
    assert all(a[1]<a[3] for a in b.arcs),'Graph must be acyclic in time'
    groups=duplicate_groups(b.A,b.B,b.d,eligible,True)
    # Identical row columns must ALSO be parallel in native route provenance.
    for g in groups:
        arcs=[b.arcs[int(str(b.d['names'][j]).rsplit(',',1)[1][:-1])] for j in g]
        assert all(a[:4]==arcs[0][:4] for a in arcs)
    reduced,coupling,data,keep=quotient(b.A,b.B,b.d,groups)
    audit=dict(groups=groups,removed_columns=b.A.shape[1]-reduced.shape[1],
        original_rows=b.A.shape[0],original_columns=b.A.shape[1],original_nnz=b.A.nnz,
        reduced_rows=reduced.shape[0],reduced_columns=reduced.shape[1],reduced_nnz=reduced.nnz,
        exact_unit_DAG_flow_lift=True,full_original_integer_preimages_preserved=True,
        original_signature=signature(b.A,b.d),reduced_signature=signature(reduced,data))
    write(OUT/'04_REDUCTION_MATRIX_AUDIT.json',audit)
    guard=Guard('04',[]);guard.gate();started=time.perf_counter();guard.start(started+600)
    result=dict(stage=4,matrix_audit=audit,variants={},selected=False,full_scale_optimum_identity=None,
                same_true_dual_SHA=cp['RMP']['dual_SHA'],continuation_calls=0,Branch_and_Price_calls=0)
    m=None
    try:
        for variant in ['original','quotient']:
            if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
            matrix=b.A if variant=='original' else reduced;attrs=b.d if variant=='original' else data
            projection=b.B if variant=='original' else coupling
            attrs=dict(attrs,objective=attrs['objective']-projection.T@pi,constant=np.array(-float(alpha[0])))
            begin=time.perf_counter();m=build(matrix,attrs,'PRICING_'+variant)
            cfg=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
                     MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,TimeLimit=30.)
            for k,v in cfg.items():m.setParam(k,v)
            seed=seeds[0].copy()
            if variant=='quotient':
                for g in groups:seed[g[0]]=sum(seed[j] for j in g);seed[g[1:]]=0
                seed=seed[keep]
            m.setAttr('Start',m.getVars(),seed.tolist());m.Params.LogFile=str(OUT/f'04_{variant}.log')
            tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None;native=time.perf_counter()-tick
            rc=None
            if m.SolCount:
                x=np.asarray(m.getAttr('X'));x=x if variant=='original' else lift(x,keep,len(b.d['names']))
                assert b.validate(x,True)['PASS'];rc=float(exact_rc(b,x,pi,alpha[0]))
            result['variants'][variant]=dict(native_status=m.Status,native_seconds=native,wall_seconds=time.perf_counter()-begin,
                incumbent_RC=rc,exact_optimum_RC=rc if m.Status==2 else None,global_BestBd=m.ObjBound,
                nodes=m.NodeCount,scientific_certificate_eligible=False)
            m.dispose();m=None
        original=result['variants']['original'];q=result['variants']['quotient']
        exact=original['exact_optimum_RC'] is not None and q['exact_optimum_RC'] is not None
        equivalent=exact and abs(original['exact_optimum_RC']-q['exact_optimum_RC'])<=1e-8
        ratio=original['wall_seconds']/q['wall_seconds']
        selected=audit['removed_columns']>0 and equivalent and ratio>=1.2
        result.update(selected=selected,runtime_ratio=ratio,full_scale_optimum_identity=bool(equivalent) if exact else None,
            status='RETAINED' if selected else 'REJECTED_NO_ELIMINATION' if audit['removed_columns']==0 else 'REJECTED_INCOMPLETE_OR_NO_GAIN',
            no_elimination_implies_identical_optimum_for_every_dual=audit['removed_columns']==0)
    except Exception as exc:
        if m is not None:m.dispose()
        result.update(status='INCONCLUSIVE',error=repr(exc),selected=False)
    finally:
        resource=guard.close()
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(resource=resource,continuous_wall_seconds=time.perf_counter()-started,wall_cap_seconds=600)
        write(OUT/'04_PRICING_REDUCTION_BENCHMARK.json',result);print('STAGE4_TERMINAL',result['status'],flush=True)

if __name__=='__main__':run()
