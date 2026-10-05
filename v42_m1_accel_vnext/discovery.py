"""Isolated adapter around byte-unchanged PR152 four-column Discovery worker."""
from .common import *
import multiprocessing as mp
import time
import numpy as np

def child(connection,unit,cancel,leg):
    import v42_dw_continuation.common as common
    import v42_dw_continuation.worker as worker
    common.OUT=Path(leg);common.STOP=common.OUT/'STOP_REQUEST.json'
    worker.OUT=common.OUT;worker.STOP=common.STOP;worker.SCI=OLD
    worker.main(connection,[unit],cancel)

def pricing(snapshot,pi,alpha,leg,guard):
    context=mp.get_context('spawn');cancel=context.Event();processes=[];pipes=[];result={}
    for directory in ['logs','pricing_receipts','pricing_points']:(leg/directory).mkdir(parents=True,exist_ok=True)
    np.savez_compressed(leg/'SEARCH_DUAL.npz',pi=pi,alpha=alpha)
    np.savez_compressed(leg/'TRUE_DUAL.npz',pi=snapshot.pi,alpha=snapshot.alpha)
    search_SHA=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()
    true_SHA=snapshot.cp['RMP']['dual_SHA'];begin=time.perf_counter()
    try:
        for unit in range(4):
            a,b=context.Pipe();p=context.Process(target=child,args=(b,unit,cancel,str(leg)))
            p.start();b.close();processes.append(p);pipes.append(a);guard.excluded.append(p.pid)
        for pipe in pipes:
            while not pipe.poll(.2):
                if guard.cancel.is_set() or any(not p.is_alive() for p in processes):raise RuntimeError('PRICING_BUILD_INTERRUPTED')
            ready=pipe.recv();assert ready.get('ready'),ready
        native_begin=time.perf_counter()
        for unit,pipe in enumerate(pipes):
            pipe.send(dict(type='DISCOVERY',unit=unit,call=unit+1,round=29,
                dual_SHA=search_SHA,dual_file='SEARCH_DUAL.npz',true_dual_SHA=true_SHA,
                true_dual_file='TRUE_DUAL.npz',smoothing_alpha=.1,stabilized_discovery=True,
                RMP_objective=snapshot.cp['RMP']['objective'],cap=20.,
                retained_SHAs=[c['key'] for c in snapshot.pool if c['unit']==unit],
                log=f'logs/PRICE_{unit+1:04d}.log',receipt=f'pricing_receipts/PRICE_{unit+1:04d}.json'))
        pending=set(range(4))
        while pending:
            if guard.cancel.is_set():cancel.set()
            for unit in list(pending):
                if pipes[unit].poll(.1):
                    response=pipes[unit].recv();assert 'result' in response,response
                    result[unit]=read(leg/response['result']);pending.remove(unit)
                elif not processes[unit].is_alive():raise RuntimeError('PRICING_EXIT_WITHOUT_TERMINAL_RECEIPT')
        native_wall=time.perf_counter()-native_begin
        from v42_dw_root.run import exact_rc
        from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
        columns=[];seen={c['key'] for c in snapshot.pool}
        for unit,r in result.items():
            assert r['true_dual_SHA']==true_SHA and r['dual_SHA']==search_SHA
            assert not r['valid_bound'] and r['settings']['Threads']==1 and r['full_original_domain']
            assert not r['capture_errors'] and not r['pricing_optimality_claimed']
            b=snapshot.blocks[unit];matrix,attrs=snapshot.original_local[unit];accepted=0
            for c in r['candidates']:
                if not c['selected']:continue
                with np.load(leg/c['point_file']) as z:x=z['x'].copy();assert np.array_equal(z['axis'],b.columns)
                assert b.validate(x,True)['PASS'] and corrected_rows(matrix,attrs,x,True,pure_binary_equalities(matrix,attrs))['PASS']
                rc=exact_rc(b,x,snapshot.pi,snapshot.alpha[unit]);assert rc<=-1e-7
                a,cost,key=b.column(x);assert key not in seen;seen.add(key);accepted+=1
                columns.append(dict(unit=unit,x=x,a=a,c=cost,key=key,true_RC=float(rc)))
            assert accepted<=4
        return columns,dict(pricing_batch_wall_seconds=native_wall,
            pricing_build_native_audit_seconds=time.perf_counter()-begin,
            pricing_native_seconds=sum(r['wall_seconds'] for r in result.values()),
            captured=sum(len(r['candidates']) for r in result.values()),accepted=len(columns),invalid_admitted=0,
            true_dual_SHA=true_SHA,search_dual_SHA=search_SHA,Certification_calls=0)
    finally:
        for pipe,p in zip(pipes,processes):
            try:
                if p.is_alive():pipe.send(None)
            except (BrokenPipeError,EOFError,OSError):pass
        cancel.set()
        for p in processes:
            p.join(timeout=max(.1,min(5,guard.deadline-time.perf_counter()-5)))
            if p.is_alive():p.terminate();p.join(timeout=3) # owned pricing child only
            if p.pid in guard.excluded:guard.excluded.remove(p.pid)
        for pipe in pipes:pipe.close()
