"""One Discovery round plus one cold RMP; no continuation/Certification loop."""
from .common import *
from .prepare import preserved
from .selection import projection_key
from .resources import Monitor
from .worker import main as worker_main
from .adapter import exact_projection
from fractions import Fraction as F
from concurrent.futures import ThreadPoolExecutor
import multiprocessing as mp
import time,sys,gc
import numpy as np


def payload(path):
    with np.load(path) as z:
        x=z['x'].copy() if 'x' in z else z['local_values'].copy()
        a=z['a'].copy() if 'a' in z else z['master_coefficients'].copy()
        c=float(z['c'] if 'c' in z else z['objective'])
        axis=z['axis'].copy() if 'axis' in z else z['original_columns'].copy()
    return x,a,c,axis


def run(mode):
    assert mode in ('BASELINE','CHALLENGER')
    assert read(OUT/'MULTICOLUMN_LIGHTWEIGHT_TESTS.json')['PASS']
    preserved()
    leg=OUT/mode.lower();live=leg/'live';cp=read(leg/'immutable/DW_CHECKPOINT_LATEST.json')
    with (leg/'BENCHMARK_STARTED.json').open('x',encoding='utf8') as f:
        f.write('{"rounds":1,"RMP_calls":1,"retries":0}\n')
    owned=[];monitor=Monitor(owned);processes=[];pipes=[];cancel=mp.get_context('spawn').Event()
    native_intervals=[];active_calls={};rmp_model=None
    monitor.budget_used=lambda:sum(e-s for s,e in native_intervals)+sum(time.perf_counter()-s for s in active_calls.values())
    try:
        admission=monitor.gate(mode+'_START');write(leg/'ADMISSION.json',admission)
        started=time.perf_counter()
        from v42_degen.identity import inputs,signature
        from v42_dw_root.partition import axes
        from v42_dw_resume.audit import prototypes,Master,corrected_rows,pure_binary_equalities
        from v42_dw_root.run import exact_rc
        from v42_dw_root.common import UNITS
        from v42_dw_continuation.common import OLD as NATIVE_NAMES
        A,d,B,e,*_=inputs();owner,row_owner=axes()
        assert signature(A,d)==read(OLD/'DW_CONTINUATION_BASE_AUDIT.json')['full_matrix_signature']
        with np.load(NATIVE_NAMES/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        blocks=prototypes(B,e,owner,row_owner,native)
        assert all(not np.any(b.d['objective']) for b in blocks),'Saved exact local zero-cost authority'
        with np.load(live/'TRUE_DUAL.npz') as z:tp=z['pi'].copy();ta=z['alpha'].copy()
        with np.load(live/'SEARCH_DUAL.npz') as z:sp=z['pi'].copy();sa=z['alpha'].copy()
        true_SHA=hashlib.sha256(tp.tobytes()+ta.tobytes()).hexdigest()
        search_SHA=hashlib.sha256(sp.tobytes()+sa.tobytes()).hexdigest()
        assert true_SHA==cp['RMP']['dual_SHA']
        indexes=[{} for _ in range(4)];seen=[set() for _ in range(4)]
        original_local_rows=[[] for _ in range(4)]
        for i in range(A.shape[0]):
            deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
            if len(deps)==1 and next(iter(deps))>=0:original_local_rows[next(iter(deps))].append(i)
        for c in cp['pool']:
            m=UNITS.index(c['MESS']);seen[m].add(c['column_SHA'])
            path=leg/c['file'];assert sha(path)==c['file_SHA']
            with np.load(path) as z:
                a={int(i):F(int(n),int(den)) for i,n,den in zip(z['exact_rows'],z['exact_numerators'],z['exact_denominators'])}
                cost=float(z['c'] if 'c' in z else z['objective']);assert cost==0.
            key=projection_key(m,a);indexes[m][key]=F(0)
        context=mp.get_context('spawn')
        monitor.gate(mode+'_PRICING_BUILD')
        for m in range(4):
            parent,child=context.Pipe();p=context.Process(target=worker_main,args=(child,m,cancel,str(leg),mode,indexes[m]));p.start();child.close()
            processes.append(p);pipes.append(parent);owned.append(p.pid)
        for m,pipe in enumerate(pipes):
            while not pipe.poll(.5):
                if any(not p.is_alive() for p in processes):raise RuntimeError('WORKER_BUILD_EXIT')
            ready=pipe.recv();assert ready.get('ready'),ready
            assert ready['census'][m]['signature']==read(ROOT/'docs/v42_m1_dw_certified_dual_bound/DW_BOUND_BUILD_RECEIPT.json')['pricing_census'][m]['signature']
        monitor.gate(mode+'_PRICING');monitor.phase='PRICING';pricing_begin=time.perf_counter()
        for m,pipe in enumerate(pipes):
            pipe.send(dict(type='DISCOVERY',unit=m,call=m+1,round=29,dual_SHA=search_SHA,dual_file='SEARCH_DUAL.npz',true_dual_SHA=true_SHA,true_dual_file='TRUE_DUAL.npz',stabilized_discovery=True,smoothing_alpha=.1,RMP_objective=cp['RMP']['objective'],retained_SHAs=sorted(seen[m]),cap=20.,log=f'logs/PRICE_{m+1:04d}.log',receipt=f'pricing_receipts/PRICE_{m+1:04d}.json'))
        results={};pending=set(range(4))
        while pending:
            if monitor.cancel.is_set():cancel.set()
            for m in list(pending):
                if pipes[m].poll(.1):
                    value=pipes[m].recv()
                    if 'native_started' in value:active_calls[m]=value['native_started']
                    elif 'native_ended' in value:
                        native_intervals.append([active_calls.pop(m),value['native_ended']])
                    elif 'result' in value:
                        r=read(live/value['result']);results[m]=r;pending.remove(m)
                        assert r['callback_observations']['optimize_calls']==1 and not r['valid_bound']
                        assert r['dual_SHA']==search_SHA and r['true_dual_SHA']==true_SHA
                        assert r['full_original_domain'] and r['no_fixing'] and r['settings']['Threads']==1
                        assert not r['capture_errors']
                    else:raise RuntimeError(repr(value))
                elif not processes[m].is_alive():raise RuntimeError('PRICING_EXIT_NO_RECEIPT')
        pricing_wall=time.perf_counter()-pricing_begin
        for pipe in pipes:pipe.send(None)
        for p in processes:p.join()
        for pipe in pipes:pipe.close()
        processes.clear();pipes.clear();owned.clear();monitor.phase='BUILD';gc.collect()
        # Independent same-iteration true-dual validation of every admission.
        def validate_unit(m):
            admitted=[];b=blocks[m];r=results[m]
            rows=np.asarray(original_local_rows[m]);matrix=A[rows][:,b.columns]
            attrs=dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],lower=d['lower'][b.columns],upper=d['upper'][b.columns],types=d['types'][b.columns],objective=d['objective'][b.columns],constant=np.array(0.))
            mask=pure_binary_equalities(matrix,attrs)
            chosen=set()
            for c in r['candidates']:
                if not c['selected']:continue
                with np.load(live/c['point_file']) as z:x=z['x'].copy();assert np.array_equal(z['axis'],b.columns)
                assert b.validate(x,True)['PASS'] and corrected_rows(matrix,attrs,x,True,mask)['PASS']
                rc=exact_rc(b,x,tp,ta[m]);src=exact_rc(b,x,sp,sa[m])
                assert rc<=F(float(-1e-7)) and src<=F(float(-1e-7))
                a,cost,key=b.column(x);assert key not in seen[m] and key not in chosen
                if mode=='CHALLENGER':
                    projection,exactcost=exact_projection(b,x);pk=projection_key(m,projection)
                    assert pk not in indexes[m] or exactcost<indexes[m][pk]
                chosen.add(key);admitted.append(dict(unit=m,x=x,a=a,c=cost,key=key,source=c['point_file'],true_RC=float(rc),search_RC=float(src)))
            assert len(admitted)<=(4 if mode=='BASELINE' else 8)
            return admitted
        with ThreadPoolExecutor(max_workers=4) as executor:
            batches=list(executor.map(validate_unit,range(4)))
        admitted=[c for batch in batches for c in batch];assert len(admitted)<=(16 if mode=='BASELINE' else 32)
        monitor.gate(mode+'_RMP_BUILD')
        master=Master(B,e,owner,row_owner,native);rmp_model=master.model
        for old in cp['pool']:
            m=UNITS.index(old['MESS']);x,a,c,axis=payload(leg/old['file'])
            assert np.array_equal(axis,blocks[m].columns) and blocks[m].column(x)[2]==old['column_SHA']
            master.add(m,x,a,c,old['column_SHA'])
        assert len(master.lambdas)==1604
        for c in admitted:master.add(c['unit'],c['x'],c['a'],c['c'],c['key'])
        monitor.gate(mode+'_RMP');rmp_model.reset(1)
        pricing_sum=sum(end-start for start,end in native_intervals)
        cap=min(200.,max(.001,300.-pricing_sum-10.))
        cfg=dict(cp['RMP']['settings'],TimeLimit=cap)
        for k,v in cfg.items():rmp_model.setParam(k,v)
        rmp_model.Params.LogFile=str(live/'logs/RMP_ONCE.log')
        monitor.phase='RMP';start=time.perf_counter();active_calls['RMP']=start;monitor.active=rmp_model
        rmp_model.optimize()  # Exactly one subsequent cold LP call.
        end=time.perf_counter();monitor.active=None;active_calls.pop('RMP');native_intervals.append([start,end])
        rmp_status=int(rmp_model.Status);audit=None;native_upper=None;point=None
        if rmp_model.SolCount:
            point=np.zeros(len(owner));point[master.columns]=rmp_model.getAttr('X',master.z)
            for variable,c in zip(master.lambdas,master.column_data):point[blocks[c['unit']].columns]+=float(variable.X)*c['x']
            audit=corrected_rows(A,d,point,False,pure_binary_equalities(A,d))
            raw=master.raw_audit();assert audit['PASS'] and raw['PASS']
            native_upper=float(d['objective']@point+d['constant']);assert abs(native_upper-rmp_model.ObjVal)<=1e-6
            np.savez_compressed(live/'RMP_POINT_ONCE.npz',point=point,pi=rmp_model.getAttr('Pi',master.coupling) if rmp_status==2 else np.array([]))
        audited_upper=min(cp['RMP']['objective'],native_upper) if native_upper is not None else None
        total_wall=time.perf_counter()-started
        delta=cp['RMP']['objective']-audited_upper if audited_upper is not None else None
        native_sum=sum(b-a for a,b in native_intervals);assert native_sum<=300.
        resource=monitor.summary()
        success=audited_upper is not None and not resource['guard_failures'] and all(r['native_status'] in (2,9,11) for r in results.values())
        result=dict(mode=mode,status='AUDITED_BENCHMARK' if success else 'MICROBENCHMARK_INCONCLUSIVE',
            starting_columns=1604,ending_columns=1604+len(admitted),retained_new_columns=len(admitted),
            Discovery_rounds=1,pricing_calls=4,RMP_calls=1,Certification_calls=0,
            pricing_native_sum_seconds=pricing_sum,pricing_wall_seconds=pricing_wall,
            pricing=[dict(MESS=r['MESS'],native_status=r['native_status'],native_seconds=r['wall_seconds'],solver_runtime=r['runtime'],**r['callback_observations'],**r['harvest_metrics']) for m,r in sorted(results.items())],
            RMP_native_seconds=end-start,RMP_status=rmp_status,RMP_cap=cap,
            U_before=cp['RMP']['objective'],native_primal_upper=native_upper,U_after=audited_upper,upper_improvement=delta,
            total_wall_seconds=total_wall,efficiency=delta/total_wall if delta is not None else None,
            retained_per_pricing_native_minute=len(admitted)*60/pricing_sum if pricing_sum else 0.,
            native_sum_seconds=native_sum,native_intervals=native_intervals,original_primal_audit=audit,
            true_dual_SHA=true_SHA,search_dual_SHA=search_SHA,checkpoint_SHA=sha(leg/'immutable/DW_CHECKPOINT_LATEST.json'),pool_SHA=cp['pool_SHA'],settings=cfg,
            resource=resource,authoritative_continuation_calls=0,Branch_and_Price_calls=0,scientific_certificate_merge=False)
        write(OUT/f'MULTICOLUMN_{mode}_1ROUND.json',result)
        rmp_model.dispose();rmp_model=None;master=None;gc.collect()
        print('BENCHMARK_DONE',mode,result['status'],len(admitted),native_sum,delta,result['efficiency'],flush=True)
    finally:
        cancel.set()
        for p,pipe in zip(processes,pipes):
            if p.is_alive():
                try:pipe.send(None)
                except (BrokenPipeError,EOFError):pass
        for p in processes:p.join()
        for pipe in pipes:pipe.close()
        if rmp_model is not None:rmp_model.dispose()
        monitor.close();table(leg/'RESOURCE_LEDGER.csv',monitor.rows)
    preserved()


if __name__=='__main__':run(sys.argv[1])
