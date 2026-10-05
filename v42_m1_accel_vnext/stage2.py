from .common import *
from .inputs import Snapshot
from .resources import Guard
from .discovery import pricing
from .box import initial_box,install,update
import time
import numpy as np

def run():
    assert read(OUT/'01_PERSISTENT_RMP_BENCHMARK.json')['status'] in ['REJECTED','RETAINED','INCONCLUSIVE','NONCOMPARABLE']
    assert not (OUT/'02_STABILIZATION_BENCHMARK.json').exists()
    freeze=read(OUT/'02_SOURCE_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    snapshot=Snapshot()
    with np.load(OLD/snapshot.cp['smooth_file']) as z:previous=z['pi'].copy();pa=z['alpha'].copy()
    active=np.unique(np.concatenate([b.B.tocoo().row for b in snapshot.blocks]))
    state=initial_box(snapshot.pi,previous,active)
    guard=Guard('02',[]);guard.gate();started=time.perf_counter();guard.start(started+600)
    result=dict(stage=2,variants={},stabilization='coordinate dual box step',alpha_baseline=.1,
                pricing_and_certification_sources_unchanged=True,selected=False)
    master=None
    try:
        for variant in ['baseline','box']:
            begin=time.perf_counter();leg=OUT/'02'/variant;leg.mkdir(parents=True,exist_ok=True)
            pi=.1*snapshot.pi+.9*previous;alpha=.1*snapshot.alpha+.9*pa;guidance=None
            if variant=='box':
                master=snapshot.master(snapshot.pool);guidance=install(master,state);m=master.model
                cfg=dict(snapshot.cp['RMP']['settings'],TimeLimit=min(90,guard.deadline-time.perf_counter()-40))
                for k,v in cfg.items():m.setParam(k,v)
                m.Params.LogFile=str(leg/'BOX_GUIDANCE.log');tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None
                assert m.Status==2 and not guard.cancel.is_set(),'BOX_GUIDANCE_NOT_OPTIMAL'
                pi=np.asarray(m.getAttr('Pi',master.coupling));alpha=np.asarray(m.getAttr('Pi',master.conv))
                assert np.max(abs(pi[active]-state['center'][active])-state['width'][active])<=1e-8
                guidance.update(native_wall_seconds=time.perf_counter()-tick,objective=m.ObjVal,
                                used_as_scientific_bound=False)
                m.dispose();master=None
            columns,prices=pricing(snapshot,pi,alpha,leg,guard)
            if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
            tick=time.perf_counter();master=snapshot.master(snapshot.pool+columns);build=time.perf_counter()-tick;m=master.model
            for k,v in dict(snapshot.cp['RMP']['settings'],TimeLimit=min(120.,guard.deadline-time.perf_counter()-30)).items():m.setParam(k,v)
            m.Params.LogFile=str(leg/'TRUE_RMP.log');tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None
            native=time.perf_counter()-tick;assert m.Status==2,'TRUE_RMP_NOT_OPTIMAL'
            audit=snapshot.audit(master);new_pi=np.asarray(m.getAttr('Pi',master.coupling))
            upper=audit['upper'];m.dispose();master=None;elapsed=time.perf_counter()-begin
            delta=snapshot.cp['RMP']['objective']-upper
            result['variants'][variant]=dict(prices,upper=upper,audit=audit,UB_decrease=delta,
                RMP_build_seconds=build,RMP_native_seconds=native,wall_seconds=elapsed,efficiency=delta/elapsed,
                guidance=guidance,search_dual_oscillation_L2=float(np.linalg.norm(pi-previous)),
                post_RMP_true_dual_oscillation_L2=float(np.linalg.norm(new_pi-snapshot.pi)))
            if variant=='box':
                newstate=update(state,new_pi,snapshot.cp['RMP']['objective'],upper)
                result['state_update']=dict(serious_steps=newstate['serious_steps'],null_steps=newstate['null_steps'])
            print('STAGE2',variant,'UPPER',upper,'EFFICIENCY',delta/elapsed,flush=True)
        baseline=result['variants']['baseline']['efficiency'];challenger=result['variants']['box']['efficiency']
        ratio=challenger/baseline if baseline>0 else None
        result.update(efficiency_ratio=ratio,selected=ratio is not None and ratio>=1.2,
                      status='RETAINED' if ratio is not None and ratio>=1.2 else 'REJECTED')
    except Exception as exc:
        if master is not None:master.model.dispose()
        result.update(status='INCONCLUSIVE',selected=False,error=repr(exc))
    finally:
        resource=guard.close()
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(resource=resource,continuous_wall_seconds=time.perf_counter()-started,wall_cap_seconds=600,
                      authoritative_checkpoint_changed=False,continuation_calls=0,Branch_and_Price_calls=0)
        write(OUT/'02_STABILIZATION_BENCHMARK.json',result);print('STAGE2_TERMINAL',result['status'],flush=True)

if __name__=='__main__':run()
