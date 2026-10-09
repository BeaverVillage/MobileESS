"""Single durable sum of all LB/UB native calls, including failed calls."""
from contextlib import contextmanager
from datetime import datetime,timezone
from math import isfinite
from pathlib import Path
from time import perf_counter
import os
import gurobipy as gp
from v42_unified.audit import ROOT,write
from v42_unified.policy import Policy


class ResearchLedger:
    def __init__(self,path,case_sha,*,clock=perf_counter):
        self.path=Path(path).resolve()
        if not self.path.is_relative_to(ROOT.resolve()):raise ValueError('D_V42_LEDGER_REQUIRED')
        if self.path.exists():raise ValueError('NEW_LEDGER_REQUIRED_NO_HISTORICAL_REWRITE')
        self.case_sha=case_sha;self.clock=clock;self.started=clock()
        self.allocation={'LB':3600.,'UB':1800.};self.calls=[];self.transfers=[];self.costs=[]
        self.persist()

    def used(self,track=None):return sum(r['Native_Runtime'] for r in self.calls if track is None or r['track']==track)
    def remaining(self,track):return min(5400.-self.used(),self.allocation[track]-self.used(track))

    def check_accounting(self):
        if self.used()>5400. or any(self.used(k)>self.allocation[k] for k in self.allocation):
            raise RuntimeError('NATIVE_RUNTIME_LIMIT_EXCEEDED_ACCOUNTING_QUARANTINED')
        if any(r.get('runtime_unavailable') for r in self.calls):
            raise RuntimeError('NATIVE_RUNTIME_UNAVAILABLE_ACCOUNTING_QUARANTINED')

    def transfer(self,source,target,seconds):
        self.check_accounting()
        if {source,target}!={'LB','UB'} or not 0<seconds<=self.remaining(source):raise ValueError('UNUSED_BUDGET_TRANSFER_REQUIRED')
        self.allocation[source]-=seconds;self.allocation[target]+=seconds
        self.transfers.append(dict(source=source,target=target,seconds=seconds,used_before=self.used(),
            source_used_before=self.used(source),target_used_before=self.used(target)))
        self.persist()

    @contextmanager
    def cost(self,kind,label,track=None):
        t=self.clock()
        try:yield
        finally:
            self.costs.append(dict(kind=kind,label=label,track=track,wall_seconds=self.clock()-t));self.persist()

    def optimize(self,model,*,track,label,requested_seconds,callback=None):
        self.check_accounting()
        limit=min(float(requested_seconds),self.remaining(track))
        if limit<=0:raise TimeoutError('COMBINED_M1_RESEARCH_BUDGET_EXHAUSTED')
        for k,v in Policy().parameters('M1').items():setattr(model.Params,k,v)
        if any(getattr(model.Params,k)!=float('inf') for k in ('MemLimit','SoftMemLimit')):raise ValueError('FINITE_MEMORY_LIMIT_FORBIDDEN')
        model.Params.TimeLimit=limit
        model.Params.LogFile=str(self.path.parent/(f'{len(self.calls):02d}_{track}_{label}_NATIVE.log'))
        row=dict(track=track,label=label,case_sha=self.case_sha,requested_seconds=requested_seconds,
                 allocated_native_seconds=limit,started_utc=datetime.now(timezone.utc).isoformat(),state='IN_FLIGHT')
        # Persist an in-flight marker without claiming its runtime or changing past calls.
        self.inflight=row;self.persist();t=self.clock();error=None
        try:
            if callback is None:model.optimize()
            else:model.optimize(callback)
        except BaseException as exc:
            error=type(exc).__name__+':'+str(exc)
            raise
        finally:
            def attr(name,default=None):
                try:return getattr(model,name)
                except (gp.GurobiError,AttributeError):return default
            runtime=attr('Runtime')
            unavailable=runtime is None or not isfinite(float(runtime)) or float(runtime)<0
            # Unknown native cost is quarantined and conservatively reserved;
            # this is explicitly not a reported measured Runtime.
            runtime=limit if unavailable else float(runtime)
            row.update(state='FINISHED' if error is None else 'FAILED',Native_Runtime=runtime,
                Native_Work=attr('Work',0.),optimize_wall_seconds=self.clock()-t,status=attr('Status'),
                SolCount=attr('SolCount',0),error=error,peak_memory_GB=attr('MaxMemUsed'),
                runtime_unavailable=unavailable,measured_Native_Runtime=None if unavailable else runtime,
                runtime_accounting_scope='CONSERVATIVE_RESERVED_UNKNOWN_COST' if unavailable else 'MEASURED')
            if row['SolCount']:row['objective']=attr('ObjVal')
            bound=attr('ObjBound')
            row['native_solver_bound_diagnostic']=float(bound) if bound is not None and isfinite(float(bound)) else None
            self.calls.append(row);self.inflight=None;self.persist()
        self.check_accounting()
        return row

    def persist(self):
        elapsed=self.clock()-self.started
        r=dict(schema='V42_M1_COMBINED_RESEARCH_RUNTIME_V1',case_sha=self.case_sha,total_native_limit_seconds=5400.,
               allocations=self.allocation,Native_Runtime_sum=self.used(),track_Runtime={k:self.used(k) for k in self.allocation},
               Native_Work_sum=sum(r.get('Native_Work',0.) for r in self.calls),calls=self.calls,transfers=self.transfers,
               inflight=getattr(self,'inflight',None),non_native_wall_costs=self.costs,wall_seconds=elapsed,
               practical_wall_PASS=elapsed<=5400.,Threads=1,scientific_tolerances=Policy().parameters('M1'),
               memory_limits=False,memory_automatic_stop=False,historical_ledgers_modified=False)
        r['native_accounting_PASS']=self.used()<=5400. and all(self.used(k)<=self.allocation[k] for k in self.allocation)
        r['native_measured_Runtime_sum']=sum(row['measured_Native_Runtime'] or 0. for row in self.calls)
        r['native_runtime_measurement_complete']=not any(row.get('runtime_unavailable') for row in self.calls)
        write(self.path,r);return r
