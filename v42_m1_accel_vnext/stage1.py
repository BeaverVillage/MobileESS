from .common import *
from .basis import BasisSession
from .inputs import Snapshot,controlled_columns
from .resources import Guard
from v42_dw_accelerated.persistent import sparse_identity
import time

def run():
    assert not (OUT/'01_PERSISTENT_RMP_BENCHMARK.json').exists()
    freeze=read(OUT/'01_SOURCE_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    assert sha(OUT/'M1_ACCEL_VNEXT_PREREGISTRATION.md')==freeze['preregistration_SHA']
    snapshot=Snapshot(); extra=controlled_columns(snapshot)
    guard=Guard('01');guard.gate();started=time.perf_counter();guard.start(started+600)
    result=dict(stage=1,columns=1604,controlled_additions=[5,5],variants={},source_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    identities={};native_calls=0
    try:
        for variant in ['cold','persistent']:
            master=None;session=None;points=[];begin=time.perf_counter()
            for iteration in range(3):
                if guard.cancel.is_set():raise RuntimeError('GUARD_STOP')
                tick=time.perf_counter()
                if variant=='cold' or iteration==0:
                    if master:master.model.dispose()
                    master=snapshot.master(snapshot.pool+extra[:5*iteration]);session=BasisSession(master.model)
                else:
                    for c in extra[5*(iteration-1):5*iteration]:master.add(c['unit'],c['x'],c['a'],c['c'],c['key'])
                build=time.perf_counter()-tick;m=master.model
                identity=sparse_identity(m);identities[(variant,iteration)]=identity
                cfg=dict(snapshot.cp['RMP']['settings'],TimeLimit=min(90.,guard.deadline-time.perf_counter()-30))
                if cfg['TimeLimit']<=0:raise TimeoutError('WALL_CAP')
                for k,v in cfg.items():m.setParam(k,v)
                basis=session.restore() if variant=='persistent' and iteration>0 else dict(supplied=False)
                log=OUT/f'01_{variant}_{iteration}.log';m.Params.LogFile=str(log)
                tick=time.perf_counter();guard.active=m;m.optimize();guard.active=None;native_calls+=1
                native=time.perf_counter()-tick
                if m.Status!=2:raise RuntimeError(f'NONOPTIMAL_RMP:{variant}:{iteration}:{m.Status}')
                audit=snapshot.audit(master)
                if variant=='persistent':session.capture()
                logfile=log.read_text(encoding='utf8',errors='replace')
                points.append(dict(iteration=iteration,columns=1604+5*iteration,build_update_seconds=build,
                    native_wall_seconds=native,native_runtime=m.Runtime,iterations=m.IterCount,
                    upper=audit['upper'],audit=audit,basis=basis,
                    native_basis_log_evidence='LP warm-start' in logfile or 'use basis' in logfile.lower(),matrix=identity))
                print('STAGE1',variant,iteration,'UPPER',audit['upper'],'NATIVE',native,flush=True)
            master.model.dispose();master=None
            result['variants'][variant]=dict(points=points,total_RMP_wall_seconds=time.perf_counter()-begin)
        cold=result['variants']['cold'];warm=result['variants']['persistent']
        matrix=all(identities['cold',i]==identities['persistent',i] for i in range(3))
        objectives=all(abs(cold['points'][i]['upper']-warm['points'][i]['upper'])<=1e-8 for i in range(3))
        ratio=cold['total_RMP_wall_seconds']/warm['total_RMP_wall_seconds']
        result.update(matrix_identity=matrix,objective_identity=objectives,runtime_ratio=ratio,
                      selected=matrix and objectives and ratio>1.,status='RETAINED' if matrix and objectives and ratio>1 else 'REJECTED')
    except Exception as exc:
        if master is not None:master.model.dispose()
        result.update(status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in guard.failures else 'INCONCLUSIVE',selected=False,error=repr(exc))
    finally:
        resource=guard.close();elapsed=time.perf_counter()-started
        if resource['failures']:result.update(selected=False,status='NONCOMPARABLE' if 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' in resource['failures'] else 'INCONCLUSIVE')
        result.update(continuous_wall_seconds=elapsed,wall_cap_seconds=600,native_calls=native_calls,resource=resource,
                      authoritative_checkpoint_changed=False,continuation_calls=0,Branch_and_Price_calls=0)
        write(OUT/'01_PERSISTENT_RMP_BENCHMARK.json',result)
        print('STAGE1_TERMINAL',result['status'],elapsed,flush=True)

if __name__=='__main__':run()
