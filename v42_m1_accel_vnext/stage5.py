from .common import *
from .inputs import Snapshot
from .resources import Guard
from .cuts import coefficients,install
from v42_dw_root.models import build
from v42_dw_root.run import exact_rc
import time
import numpy as np

def run():
    assert (OUT/'04_PRICING_REDUCTION_BENCHMARK.json').exists()
    assert not (OUT/'05_ROOT_CUT_BENCHMARK.json').exists()
    freeze=read(OUT/'05_SOURCE_FREEZE.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    # Wait before holding the dense checkpoint pool; B1 remains higher priority.
    guard=Guard('05',[]);guard.gate();snapshot=Snapshot()
    values=[coefficients(snapshot.blocks[c['unit']],c['x']) for c in snapshot.pool]
    guard.gate();started=time.perf_counter();guard.start(started+600)
    result=dict(stage=5,variants={},selected=False,root_bound_effect_theoretical=0.,
        inherited_certified_LB=.5687115725336208,new_corrected_LB=None,
        corrected_LB_not_recomputed_reason='root-only experiment, no four-way terminal Certification',
        continuation_calls=0,Branch_and_Price_calls=0,branch_nodes_explored=0)
    master=None;price=None
    try:
        for variant in ['original','cuts']:
            begin=time.perf_counter();master=snapshot.master(snapshot.pool);growth=None;cutrows=[]
            if variant=='cuts':cutrows,growth=install(master,snapshot.blocks,values)
            m=master.model;build_seconds=time.perf_counter()-begin
            for k,v in dict(snapshot.cp['RMP']['settings'],TimeLimit=min(90.,guard.deadline-time.perf_counter()-40)).items():m.setParam(k,v)
            m.Params.LogFile=str(OUT/f'05_{variant}_RMP.log');tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None
            RMP=time.perf_counter()-tick;assert m.Status==2 and not guard.cancel.is_set(),'ROOT_RMP_INCOMPLETE'
            audit=snapshot.audit(master);pi=np.asarray(m.getAttr('Pi',master.coupling));alpha=np.asarray(m.getAttr('Pi',master.conv))
            from .combination import save_point
            save_point(snapshot,master,OUT/f'05_{variant}_POINT.npz')
            if cutrows:
                assert max(float(r.Slack)*-1 for r in cutrows)<=1e-6
                assert max(float(r.Pi) for r in cutrows)<=0
                # Independently ensure eliminated-dual retained constraints hold.
                assert min(float(exact_rc(snapshot.blocks[c['unit']],c['x'],pi,alpha[c['unit']])) for c in snapshot.pool)>=-1e-8
            m.dispose();master=None;prices=[]
            for unit,b in enumerate(snapshot.blocks):
                if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
                attrs=dict(b.d,objective=b.d['objective']-b.B.T@pi,constant=np.array(-float(alpha[unit])))
                price=build(b.A,attrs,'ROOT_PRICING_ONLY')
                for k,v in dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
                    MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,NodeLimit=1,TimeLimit=20.).items():price.setParam(k,v)
                seed=next(c['x'] for c in reversed(snapshot.pool) if c['unit']==unit)
                price.setAttr('Start',price.getVars(),seed.tolist());price.Params.LogFile=str(OUT/f'05_{variant}_PRICE_{unit}.log')
                tick=time.perf_counter();guard.active=price;price.optimize();guard.active=None
                assert price.NodeCount<=1,'CHILD_NODE_FORBIDDEN'
                bound=float(price.ObjBound);bound=bound if np.isfinite(bound) else None
                prices.append(dict(unit=unit,native_seconds=time.perf_counter()-tick,status=price.Status,
                    nodes=price.NodeCount,root_global_BestBd_diagnostic=bound,scientific_certificate_eligible=False))
                price.dispose();price=None
            elapsed=time.perf_counter()-begin
            result['variants'][variant]=dict(upper=audit['upper'],audit=audit,RMP_build_seconds=build_seconds,
                RMP_native_seconds=RMP,pricing_root_native_seconds=sum(p['native_seconds'] for p in prices),
                pricing_roots=prices,matrix_growth=growth,total_root_wall_seconds=elapsed)
            print('STAGE5',variant,'UPPER',audit['upper'],'WALL',elapsed,flush=True)
        a=result['variants']['original'];b=result['variants']['cuts'];ratio=a['total_root_wall_seconds']/b['total_root_wall_seconds']
        equal=abs(a['upper']-b['upper'])<=1e-8;selected=equal and ratio>=1.2
        result.update(objective_identity=equal,runtime_ratio=ratio,selected=selected,status='RETAINED' if selected else 'REJECTED_NO_GAIN')
    except Exception as exc:
        if master:master.model.dispose()
        if price:price.dispose()
        result.update(status='INCONCLUSIVE',error=repr(exc),selected=False)
    finally:
        resource=guard.close()
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(resource=resource,continuous_wall_seconds=time.perf_counter()-started,wall_cap_seconds=600)
        write(OUT/'05_ROOT_CUT_BENCHMARK.json',result);print('STAGE5_TERMINAL',result['status'],flush=True)

if __name__=='__main__':run()
