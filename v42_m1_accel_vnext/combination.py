"""Exactly one final paired Discovery/RMP experiment, then STOP."""
from .common import *
from .inputs import Snapshot
from .resources import Guard
from .discovery import pricing
from .cuts import install
import numpy as np
import time

def save_point(snapshot,master,path):
    point=np.zeros(len(snapshot.owner));point[master.columns]=master.model.getAttr('X',master.z)
    for v,c in zip(master.lambdas,master.column_data):point[snapshot.blocks[c['unit']].columns]+=float(v.X)*c['x']
    np.savez_compressed(path,point=point,pi=master.model.getAttr('Pi',master.coupling),alpha=master.model.getAttr('Pi',master.conv))

def run():
    assert not (OUT/'M1_ACCEL_FINAL_COMBINATION.json').exists()
    names=['01_PERSISTENT_RMP_BENCHMARK.json','02_STABILIZATION_BENCHMARK.json','03_EXACT_PRICING_BENCHMARK.json','04_PRICING_REDUCTION_BENCHMARK.json','05_ROOT_CUT_BENCHMARK.json']
    results=[read(OUT/n) for n in names];retained=[i+1 for i,r in enumerate(results) if r['selected']]
    # Source adapters for unselected methods are never activated.
    assert not set(retained)&{1,2,3,4},'Unexpected selection requires a new explicitly audited combined adapter'
    cuts=5 in retained
    freeze=read(OUT/'FINAL_SOURCE_FREEZE.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    # Latest human instruction permits running with a B1 worker. Observe actual
    # overlap without pausing; overlapping timings remain NONCOMPARABLE.
    guard=Guard('FINAL',[],foreign_policy='observe');guard.gate();snapshot=Snapshot();guard.gate()
    with np.load(OLD/snapshot.cp['smooth_file']) as z:
        pi=.1*snapshot.pi+.9*z['pi'];alpha=.1*snapshot.alpha+.9*z['alpha']
    started=time.perf_counter();guard.start(started+600)
    result=dict(variants={},retained_stages=retained,selected=False,wall_cap_seconds=600,
        candidate='root mode-linking cuts' if cuts else 'PR152 identity: no individually retained modifications',
        foreign_native_policy='observe_without_pause; overlap excludes selection evidence',
        authoritative_continuation_calls=0,Branch_and_Price_calls=0,Certification_calls=0,May_production_calls=[0,0,0],
        root_CG_10_15_minutes_estimate=None,estimate_reason='one bounded round cannot establish exact CG convergence runtime')
    master=None
    try:
        for variant in ['PR152','candidate']:
            begin=time.perf_counter();leg=OUT/'FINAL'/variant;leg.mkdir(parents=True,exist_ok=True)
            columns,prices=pricing(snapshot,pi,alpha,leg,guard)
            if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
            tick=time.perf_counter();master=snapshot.master(snapshot.pool+columns);growth=None
            if variant=='candidate' and cuts:_,growth=install(master,snapshot.blocks)
            build=time.perf_counter()-tick;m=master.model
            cap=min(120.,guard.deadline-time.perf_counter()-30);assert cap>0
            for k,v in dict(snapshot.cp['RMP']['settings'],TimeLimit=cap).items():m.setParam(k,v)
            m.Params.LogFile=str(leg/'TRUE_RMP.log');tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None
            native=time.perf_counter()-tick;assert m.Status==2 and not guard.cancel.is_set()
            audit=snapshot.audit(master);save_point(snapshot,master,leg/'TRUE_RMP_POINT.npz')
            m.dispose();master=None;elapsed=time.perf_counter()-begin;delta=snapshot.cp['RMP']['objective']-audit['upper']
            assert delta>=-1e-8
            result['variants'][variant]=dict(prices,RMP_build_seconds=build,RMP_native_seconds=native,
                upper=audit['upper'],audit=audit,UB_decrease=delta,wall_seconds=elapsed,efficiency=delta/elapsed,
                matrix_growth=growth,point_file=(leg/'TRUE_RMP_POINT.npz').relative_to(OUT).as_posix(),
                point_SHA=sha(leg/'TRUE_RMP_POINT.npz'))
            print('FINAL',variant,'UPPER',audit['upper'],'EFFICIENCY',delta/elapsed,flush=True)
        a=result['variants']['PR152'];b=result['variants']['candidate']
        ratio=b['efficiency']/a['efficiency'] if a['efficiency']>0 else None
        selected=bool(retained) and ratio is not None and ratio>=1.2
        result.update(efficiency_ratio=ratio,selected=selected,status='SELECTED' if selected else 'NOT_SELECTED')
    except Exception as exc:
        if master:master.model.dispose()
        result.update(status='INCONCLUSIVE',error=repr(exc),selected=False)
    finally:
        resource=guard.close()
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(resource=resource,continuous_wall_seconds=time.perf_counter()-started,STOP_AFTER_THIS_EXPERIMENT=True)
        write(OUT/'M1_ACCEL_FINAL_COMBINATION.json',result);print('FINAL_TERMINAL',result['status'],'STOP',flush=True)

if __name__=='__main__':run()
