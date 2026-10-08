from contextlib import contextmanager
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter, process_time
from v42_unified.storage import sha
import csv
import json
import threading
import math
import gurobipy as gp

ROOT=Path(__file__).resolve().parents[1]
BASE='e26790e9f10217fb8f5a3cecddb1e578b879efb7'
CASE='cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a'
REPORTS=ROOT/'docs/v42_m1_anytime_gap_frontier'
RUNTIME=ROOT/'runtime/v42_m1_anytime_gap_frontier'
PARAMETERS=dict(Threads=1,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8)
TARGETS=(600,1200,1800,2400,3600,4500)
THRESHOLDS=(F(4),F(7,2),F(3),F(5,2),F(2),F(3,2),F(1),F(1,2))

def utc():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    path=Path(path).resolve()
    if path.drive.upper()!='D:' or not path.is_relative_to(ROOT.resolve()):raise ValueError('D_ONLY')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def table(path,rows,fields=None):
    rows=list(rows);fields=fields or list(rows[0])
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

class Ledger:
    def __init__(self,path,started,clock=perf_counter):
        self.path=Path(path).resolve();self.started=started;self.clock=clock
        if self.path.exists() or not self.path.is_relative_to(RUNTIME.resolve()):raise ValueError('NEW_LEDGER_ONLY')
        self.calls=[];self.costs=[];self.inflight=None;self.progress={};self.lock=threading.RLock();self.frontier=None
        self.persist()
    def wall(self):return self.clock()-self.started
    def used(self):return sum(r['Native_Runtime'] for r in self.calls)
    def work(self):return sum(r.get('Native_Work') or 0 for r in self.calls)
    def remaining(self):return max(0.,5400-self.used())
    def snapshot(self):
        with self.lock:
            return dict(Native_Runtime=self.used()+self.progress.get('Runtime',0),Work=self.work()+self.progress.get('Work',0),
                Native_Runtime_completed=self.used(),Work_completed=self.work(),
                inflight=self.inflight is not None,inflight_Runtime_sample_age_seconds=None if not self.progress else max(0,self.clock()-self.progress['sample_clock']),
                accounting='completed exact Runtime plus last actual Gurobi callback sample; no extrapolation')
    @contextmanager
    def cost(self,kind,label):
        begin=self.clock();cpu=process_time();n=len(self.calls)
        try:yield
        finally:
            elapsed=self.clock()-begin;native=sum(r['optimize_wall_seconds'] for r in self.calls[n:])
            self.costs.append(dict(kind=kind,label=label,wall_seconds=elapsed,process_CPU_seconds=process_time()-cpu,
                nested_optimize_wall_seconds=native,exclusive_non_native_wall_seconds=max(0,elapsed-native),nested_costs_may_overlap=True))
            self.persist()
    def optimize(self,model,*,track,label,requested_seconds,callback=None):
        if any(r['runtime_unavailable'] for r in self.calls):raise RuntimeError('UNKNOWN_RUNTIME_QUARANTINE')
        limit=min(float(requested_seconds),self.remaining(),4500-self.wall()-5)
        if limit<1:raise TimeoutError('NATIVE_WINDOW_OR_BUDGET_CLOSED')
        for k,v in PARAMETERS.items():setattr(model.Params,k,v)
        if any(getattr(model.Params,k)!=math.inf for k in ('MemLimit','SoftMemLimit')):raise ValueError('MEMORY_LIMIT_FORBIDDEN')
        model.Params.TimeLimit=limit
        log=self.path.parent/(f'{len(self.calls):03d}_{track}_{label}_NATIVE.log');model.Params.LogFile=str(log)
        row=dict(track=track,label=label,case_sha=CASE,allocated_native_seconds=limit,requested_seconds=requested_seconds,
            started_wall_seconds=self.wall(),started_utc=utc(),parameters=dict(PARAMETERS),log=str(log),state='IN_FLIGHT')
        self.inflight=row;self.progress={};self.persist();begin=self.clock();cpu=process_time();error=None;presolve=[]
        def observe(m,where):
            if where!=gp.GRB.Callback.POLLING:
                try:
                    with self.lock:self.progress=dict(Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)),Work=float(m.cbGet(gp.GRB.Callback.WORK)),sample_clock=self.clock())
                except gp.GurobiError:pass
            if where==gp.GRB.Callback.PRESOLVE:presolve.append(self.clock()-begin)
            if callback is not None:callback(m,where)
        try:model.optimize(observe)
        except BaseException as exc:error=type(exc).__name__+':'+str(exc);raise
        finally:
            def attr(k,default=None):
                try:return getattr(model,k)
                except (gp.GurobiError,AttributeError):return default
            runtime=attr('Runtime');unknown=runtime is None or not math.isfinite(float(runtime)) or float(runtime)<0
            row.update(state='FAILED' if error else 'FINISHED',Native_Runtime=limit if unknown else float(runtime),
                runtime_unavailable=unknown,Native_Work=attr('Work',0),optimize_wall_seconds=self.clock()-begin,
                process_CPU_seconds=process_time()-cpu,finished_wall_seconds=self.wall(),finished_utc=utc(),
                status=attr('Status'),SolCount=attr('SolCount',0),error=error,peak_Gurobi_memory_GB=attr('MaxMemUsed'),
                native_objective_diagnostic=attr('ObjVal') if attr('SolCount',0) else None,
                restricted_or_native_ObjBound_diagnostic=attr('ObjBound'),native_bound_is_Global_LB=False,
                presolve_callback_span_seconds=None if not presolve else presolve[-1]-presolve[0],presolve_span_is_not_exact_Runtime=True)
            try:
                import psutil
                row['process_RSS_bytes_at_solve_end']=psutil.Process().memory_info().rss
            except ImportError:row['process_RSS_bytes_at_solve_end']=None
            with self.lock:self.calls.append(row);self.inflight=None;self.progress={}
            self.persist()
        if self.used()>5400 or unknown:raise RuntimeError('NATIVE_ACCOUNTING_QUARANTINE')
        return row
    def persist(self):
        with self.lock:
            data=dict(schema='ANYTIME_INDEPENDENT_LEDGER_V1',case_sha=CASE,Native_Runtime_sum=self.used(),Native_Work_sum=self.work(),
                Native_limit=5400,Native_wall_cutoff=4500,final_wall_limit=5400,calls=self.calls,inflight=self.inflight,
                costs=self.costs,wall_seconds=self.wall(),no_memory_limits=True,historical_ledger_writes=0,failed_costs_included=True)
            write(self.path,data)
        return data

class Frontier:
    def __init__(self,path,ledger,lb,ub,lb_path,ub_path,clock=perf_counter):
        self.path=Path(path);self.ledger=ledger;self.clock=clock;self.lock=threading.RLock();self.stop=threading.Event()
        self.lb=F(lb);self.ub=F(ub);self.events=[];self.checkpoints=[];self.passages={};self.algorithm='VERIFIED_WARM_START'
        self.lb_path=str(lb_path);self.ub_path=str(ub_path);self.lb_hash=sha(lb_path);self.ub_hash=sha(ub_path)
        self.status='STRICT_FULL_MATRIX_PHYSICAL_AND_EXACT_DUAL';self.errors=[]
        self.event('T0_VERIFIED_WARM_START',0.,0.,False,False)
        self.checkpoint(0)
    def wall(self):return self.clock()-self.ledger.started
    def gap(self):return (self.ub-self.lb)/abs(self.ub)
    def common(self):
        return dict(case_sha=CASE,wall_seconds=self.wall(),wall_minutes=self.wall()/60,UTC=utc(),
            certified_LB=float(self.lb),validated_UB=float(self.ub),certified_gap_percent=float(100*self.gap()),
            exact_LB=str(self.lb),exact_UB=str(self.ub),exact_gap=str(self.gap()),algorithm=self.algorithm,
            LB_certificate_path=self.lb_path,UB_certificate_path=self.ub_path,LB_certificate_sha256=self.lb_hash,UB_certificate_sha256=self.ub_hash,
            physical_replay='PASS',certification=self.status,failure_or_not_run=';'.join(self.errors[-3:]),
            M1_ACCEPTED=False,P2_certificate='null',**self.ledger.snapshot())
    def event(self,kind,discovery,completion,ub_gain,lb_gain):
        with self.lock:
            row=dict(event=kind,retrospectively_validated_candidate_discovery_time=discovery,
                actual_certificate_completion_time=completion,UB_improved=bool(ub_gain),LB_improved=bool(lb_gain),**self.common())
            self.events.append(row)
            for target in THRESHOLDS:
                if 100*self.gap()<=target and str(target) not in self.passages:
                    self.passages[str(target)]=dict(threshold_percent=float(target),status='REACHED',
                        actual_certificate_completion_seconds=completion,wall_minutes=completion/60,
                        retrospectively_validated_candidate_discovery_seconds=discovery,event=len(self.events)-1)
            self.save()
    def publish(self,kind,value,certificate,path,digest,discovery=None):
        with self.lock:
            value=F(value);old=self.ub if kind=='UB' else self.lb
            improving=value<old if kind=='UB' else value>old
            if not improving:return False
            if not certificate.get('PASS') or certificate.get('case_sha',CASE)!=CASE:raise ValueError('CERTIFICATE_REQUIRED')
            expected_key='exact_Global_UB' if kind=='UB' else 'exact_Global_LB'
            if sha(path)!=digest or read(path)!=certificate or F(certificate[expected_key])!=value:
                raise ValueError('CERTIFICATE_PACKET_BINDING_REQUIRED')
            if (kind=='LB' and value>self.ub) or (kind=='UB' and value<self.lb):
                raise ValueError('INCONSISTENT_GLOBAL_LB_UB')
            if kind=='UB':self.ub=value;self.ub_path=str(path);self.ub_hash=digest
            else:self.lb=value;self.lb_path=str(path);self.lb_hash=digest
            done=self.wall();self.event(kind+'_CERTIFIED_IMPROVEMENT',done if discovery is None else discovery,done,kind=='UB',kind=='LB')
            return True
    def checkpoint(self,target):
        with self.lock:
            last=self.checkpoints[-1] if self.checkpoints else None
            row=dict(target_wall_seconds=target,actual_snapshot_wall_seconds=self.wall(),
                UB_improved_since_checkpoint=False if last is None else self.ub<F(last['exact_UB']),
                LB_improved_since_checkpoint=False if last is None else self.lb>F(last['exact_LB']),**self.common())
            self.checkpoints.append(row);self.save()
    def save(self):
        self.path.mkdir(parents=True,exist_ok=True)
        table(self.path/'FRONTIER_EVENTS.csv',self.events)
        if self.checkpoints:table(self.path/'FRONTIER_CHECKPOINTS.csv',self.checkpoints)
        write(self.path/'CURRENT_CERTIFIED_STATE.json',dict(self.common(),events=len(self.events)))
    def start_observer(self):
        def observe():
            for target in TARGETS:
                delay=max(0,target-self.wall())
                if self.stop.wait(delay):return
                self.checkpoint(target)
        self.thread=threading.Thread(target=observe,name='CertifiedCheckpointObserver',daemon=True);self.thread.start()
    def finish(self):
        self.stop.set();self.thread.join(timeout=2);self.checkpoint('FINAL')
        rows=[self.passages.get(str(t),dict(threshold_percent=float(t),status='NOT_REACHED',actual_certificate_completion_seconds='',wall_minutes='',retrospectively_validated_candidate_discovery_seconds='',event='')) for t in THRESHOLDS]
        table(self.path/'GAP_FIRST_PASSAGE_TIMES.csv',rows)

def schedule_choice(history,iteration,wall):
    """Deterministic efficiency-weighted exploration, not a Gap stop rule."""
    pilots=('U1','U2','U3','U4','L1','L2','L3','L4')
    if iteration<len(pilots):return pilots[iteration],dict(reason='PREREGISTERED_PILOT',iteration=iteration)
    scores={k:0. for k in pilots}
    for k in pilots:
        rows=[r for r in history if r['method']==k][-3:]
        cost=sum(r['wall_seconds'] for r in rows);gain=sum(r['certified_gain'] for r in rows)
        scores[k]=gain/cost if cost else 0.
    # Periodic diversity; bounded LB passes prevent repeatedly weak prices.
    eligible=[k for k in pilots if not k.startswith('L') or sum(r['method']==k for r in history)<(2 if k in ('L2','L3') else 1)]
    if max(scores[k] for k in eligible)<=0:
        k=min([k for k in eligible if k.startswith('U')],key=lambda k:sum(r['method']==k for r in history))
        return k,dict(reason='NO_RECENT_CERTIFIED_GAIN_DIVERSIFY_LEAST_USED_UB',scores=scores,wall_seconds=wall,iteration=iteration)
    if iteration%5==0:
        k=min([k for k in eligible if k.startswith('U')],key=lambda k:sum(r['method']==k for r in history))
        reason='PERIODIC_UB_DIVERSIFICATION'
    else:
        k=max(eligible,key=lambda k:(scores[k],-pilots.index(k)));reason='CERTIFIED_GAIN_PER_WALL_SECOND'
    return k,dict(reason=reason,scores=scores,wall_seconds=wall,iteration=iteration)
