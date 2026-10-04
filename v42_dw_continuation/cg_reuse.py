"""Unchanged PR142 dispatch/capture/add mechanics, new artifact namespace only."""
from .common import *
import numpy as np,multiprocessing as mp,gurobipy as gp,math
from v42_dw_root.run import exact_rc
from .worker import main as worker_main

class Mechanics:
    def start_workers(self,count):
        self.resource_gate('PRICING_MODEL_BUILD');self.workers=count;self.processes=[];self.pipes=[];self.pids.clear();self.monitor.baseline=__import__('psutil').swap_memory().used
        for k in range(count):
            parent,child=self.context.Pipe();p=self.context.Process(target=worker_main,args=(child,list(range(k,4,count)),self.cancel));p.start();child.close();self.processes.append(p);self.pipes.append(parent);self.pids.append(p.pid)
        errors=[]
        for pipe in self.pipes:
            while not pipe.poll(.5):
                if STOP.exists():self.cancel.set()
                if any(not p.is_alive() for p in self.processes):raise RuntimeError('WORKER_EXIT_DURING_BUILD')
            value=pipe.recv()
            if 'error' in value:errors.append(value)
            else:
                old=read(PREVIOUS/'DW_BOUND_BUILD_RECEIPT.json')['pricing_census']
                for m,c in value['census'].items():assert c['signature']==old[m]['signature']
        if errors:raise RuntimeError('WORKER_BUILD_ERROR:'+repr(errors))
        self.monitor.sample()

    def close_workers(self):
        for pipe,p in zip(self.pipes,self.processes):
            if p.is_alive():
                try:pipe.send(None)
                except (EOFError,BrokenPipeError):pass
        for p in self.processes:p.join()
        for pipe in self.pipes:pipe.close()
        self.processes=[];self.pipes=[];self.pids.clear()

    def pricing_round(self,kind,dual,cap):
        self.resource_gate(kind);pi,alpha,key,file=dual;results=[];self.monitor.phase=kind;sample_start=len(self.monitor.rows);batch_start=time.perf_counter();write('DW_INFLIGHT.json',dict(kind=kind,spent_before=self.spent(),reserved_optimize_seconds=min(self.remaining(),cap*math.ceil(4/self.workers)+4),round=self.current_round,dual_SHA=key))
        phase=getattr(self,'resume_phase',None)
        if phase:
            assert phase['kind']==kind and phase['true_dual_SHA']==key
            search_file,search_key=phase['search_file'],phase['search_key'];jobs=phase['jobs'];self.resume_phase=None
        else:
            if kind=='DISCOVERY':search_file,search_key=self.smooth_snapshot(dual)
            else:search_file,search_key=file,key
            jobs=[]
        assert self.workers==4
        if not phase:
            for m in range(4):
                self.call+=1
                jobs.append(dict(RMP_objective=self.authority_rmp()['objective'],smoothing_alpha=self.smoothing_rows[-1]['alpha_used'] if kind=='DISCOVERY' else 1.,retained_SHAs=sorted(self.seen[m]),call=self.call,round=self.current_round,type=kind,unit=m,dual_SHA=search_key,dual_file=search_file,true_dual_SHA=key,true_dual_file=file,stabilized_discovery=search_key!=key,cap=cap,log=f'logs/PRICE_{self.call:04d}_{UNITS[m]}.log',receipt=f'pricing_receipts/PRICE_{self.call:04d}.json'))
        assert len(jobs)==4
        # Durably bind ALL job identities before the first native dispatch.
        write('DW_PHASE_STATE.json',dict(kind=kind,true_dual_SHA=key,search_file=search_file,search_key=search_key,jobs=jobs,committed=False,alpha_next=self.smooth_weight,smoothing_rows=self.smoothing_rows))
        self.active_spent=self.spent();self.active_start=time.perf_counter();pending=[]
        for k,job in enumerate(jobs):
            self.call=max(self.call,job['call'])
            if (OUT/job['receipt']).exists():
                r=read(OUT/job['receipt']);assert r['true_dual_SHA']==key and r['dual_SHA']==search_key
                if not any(p['call']==r['call'] for p in self.prices):self.prices.append(r)
                results.append(r)
            else:self.pipes[k].send(job);pending.append(k)
        while pending:
            for k in pending[:]:
                if self.pipes[k].poll(.2):
                    value=self.pipes[k].recv();pending.remove(k)
                    if 'error' in value:self.cancel.set();write(f'WORKER_ERROR_{self.current_round:04d}_{k}.json',value)
                    else:r=read(OUT/value['result']);self.intervals.append(r['interval']);self.prices.append(r);results.append(r)
            if STOP.exists():self.cancel.set()
            for k in pending:
                if not self.processes[k].is_alive():raise RuntimeError('WORKER_EXIT_DURING_NATIVE_SOLVE')
        self.active_start=None;self.monitor.sample();samples=[r for r in self.monitor.rows[sample_start:] if any(p['interval'][0]<=r['perf']<=p['interval'][1] for p in results)];stats=self.monitor.summary(samples)
        if phase and not samples:
            # Native receipts are recovered without replay. Reuse their actual
            # persisted resource samples, never synthesize a past successful solve.
            with (OUT/'DW_CONTINUATION_RESOURCE_LEDGER.csv').open(encoding='utf8',newline='') as f:history=list(csv.DictReader(f))
            past=[r for r in history if any(p['interval'][0]<=float(r['perf'])<=p['interval'][1] for p in results)]
            if past:
                stats['min_available_RAM']=min(float(r['available_RAM']) for r in past)
                stats['max_commit_percent']=max(float(r['commit_percent']) for r in past)
                stats['recovered_persisted_sample_count']=len(past)
        overlap=overlap_seconds([p['interval'] for p in results],4)
        safe=bool(len(results)==4 and not self.monitor.failed and all((r['native_status'] in (2,9) or kind=='DISCOVERY' and r['native_status']==11 and r['early_stop']['STOP_REASON']=='DISCOVERY_QUOTA_FILLED' and r['early_stop']['accepted_count']==4) and not r['capture_errors'] and (r['ObjVal'] is None or r['valid_point']) for r in results) and stats['min_available_RAM'] is not None and stats['min_available_RAM']>=1024**3 and stats['max_commit_percent'] is not None and stats['max_commit_percent']<95 and (self.workers!=4 or overlap>0))
        canary=dict(round=self.current_round,workers=self.workers,PASS=safe,failures=list(set(self.monitor.failed)),solver_or_model_errors=len(results)!=4,all_same_dual=all(r['dual_SHA']==search_key and r['true_dual_SHA']==key for r in results),actual_four_overlap_seconds=overlap,native_calls=[r['call'] for r in results],batch_wall_seconds=time.perf_counter()-batch_start,**stats)
        self.canaries.append(canary);write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=self.workers,resource_PASS=safe,resource_safety_failure_observed=any(not c['PASS'] for c in self.canaries)))
        self.debit_done();return sorted(results,key=lambda r:r['unit']),safe

    def add(self,r,pi,alpha):
        assert r['type']=='DISCOVERY' and r['valid_negative'] and r['rc_inc']<=DISCOVERY_RC
        m=r['unit'];b=self.blocks[m]
        with np.load(OUT/r['point_file']) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
        assert b.validate(x,True)['PASS'] and r['full_original_local']['PASS'];rc=float(exact_rc(b,x,pi,alpha[m]));assert abs(rc-r['rc_inc'])<=EPS
        a,c,key=b.column(x)
        if key in self.seen[m]:return False
        exact,error=b.exact_coupling(x,a);assert error<=1e-12
        n=self.column_id;self.column_id+=1;file=f'columns/COLUMN_{n:06d}_{b.unit}.npz';ix=sorted(i for i,v in exact.items() if v)
        np.savez_compressed(OUT/file,x=x,axis=b.columns,a=a,c=np.array(c),exact_rows=ix,exact_numerators=np.array([str(exact[i].numerator) for i in ix]),exact_denominators=np.array([str(exact[i].denominator) for i in ix]))
        (self.persistent_adapter.append([dict(unit=m,x=x,a=a,c=c,key=key)]) if self.persistent_selected else self.master.add(m,x,a,c,key));self.seen[m].add(key);self.columns.append(dict(number=n,round=self.current_round,MESS=b.unit,file=file,file_SHA=sha(OUT/file),SHA256=key,pricing_call=r['call'],rc_inc=rc,label='VALID_NEGATIVE_DISCOVERY_COLUMNS',pricing_optimum_claimed=False,native_status=r['native_status']))
        return True
