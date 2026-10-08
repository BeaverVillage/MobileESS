"""New bounded ledger; never resets or edits completed research ledgers."""
from contextlib import contextmanager
from datetime import datetime,timezone
from math import isfinite
from pathlib import Path
from time import perf_counter
import re
import gurobipy as gp
from v42_unified.audit import ROOT,write

PARAMETERS=dict(Threads=1,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8)
ALLOCATIONS={'UB':1350.,'PRICING':1200.,'RMP':150.}


class HybridLedger:
    def __init__(self,path,case_sha,*,clock=perf_counter,started=None):
        self.path=Path(path).resolve();self.clock=clock
        if not self.path.is_relative_to((ROOT/'runtime/v42_m1_fast_hybrid').resolve()):
            raise ValueError('NEW_D_HYBRID_LEDGER_REQUIRED')
        if self.path.exists():raise ValueError('NO_COMPLETED_LEDGER_REUSE_OR_RESET')
        self.started=clock() if started is None else started;self.case_sha=case_sha
        self.calls=[];self.costs=[];self.inflight=None;self.persist()

    def used(self,track=None):
        return sum(c['Native_Runtime'] for c in self.calls if track is None or c['track']==track)

    def remaining(self,track):
        return min(2700.-self.used(),ALLOCATIONS[track]-self.used(track))

    def check(self):
        if self.used()>2700. or any(self.used(k)>v for k,v in ALLOCATIONS.items()):
            raise RuntimeError('HYBRID_NATIVE_ACCOUNTING_QUARANTINED')
        if any(c['runtime_unavailable'] for c in self.calls):
            raise RuntimeError('HYBRID_UNKNOWN_RUNTIME_QUARANTINED')

    @contextmanager
    def cost(self,kind,label,track=None):
        start=self.clock();first_call=len(self.calls)
        try:yield
        finally:
            elapsed=self.clock()-start
            native_wall=sum(c['optimize_wall_seconds'] for c in self.calls[first_call:])
            self.costs.append(dict(kind=kind,label=label,track=track,wall_seconds=elapsed,
                nested_native_optimize_wall_seconds=native_wall,
                exclusive_non_native_wall_seconds=max(0.,elapsed-native_wall),
                enclosing_cost_records_may_overlap=True))
            self.persist()

    def optimize(self,model,*,track,label,requested_seconds,callback=None):
        self.check()
        limit=min(float(requested_seconds),self.remaining(track))
        if not isfinite(limit) or limit<=0:raise TimeoutError('HYBRID_NATIVE_BUDGET_EXHAUSTED')
        for k,v in PARAMETERS.items():setattr(model.Params,k,v)
        if any(getattr(model.Params,k)!=float('inf') for k in ('MemLimit','SoftMemLimit')):
            raise ValueError('MEMORY_LIMIT_FORBIDDEN')
        model.Params.TimeLimit=limit
        log=self.path.parent/f'{len(self.calls):02d}_{track}_{label}_NATIVE.log'
        model.Params.LogFile=str(log)
        row=dict(track=track,label=label,case_sha=self.case_sha,requested_seconds=requested_seconds,
            allocated_native_seconds=limit,started_utc=datetime.now(timezone.utc).isoformat(),
            state='IN_FLIGHT',parameters=dict(PARAMETERS),log=str(log))
        self.inflight=row;self.persist();start=self.clock();error=None;observed=[]

        def observe(m,where):
            if where==gp.GRB.Callback.PRESOLVE:observed.append(self.clock()-start)
            if callback is not None:callback(m,where)

        try:model.optimize(observe)
        except BaseException as exc:
            error=type(exc).__name__+':'+str(exc)
            raise
        finally:
            def attr(name,default=None):
                try:return getattr(model,name)
                except (gp.GurobiError,AttributeError):return default
            runtime=attr('Runtime');unknown=runtime is None or not isfinite(float(runtime)) or float(runtime)<0
            runtime=limit if unknown else float(runtime)
            row.update(state='FAILED' if error else 'FINISHED',Native_Runtime=runtime,
                measured_Native_Runtime=None if unknown else runtime,runtime_unavailable=unknown,
                Native_Work=attr('Work',0.),optimize_wall_seconds=self.clock()-start,
                status=attr('Status'),SolCount=attr('SolCount',0),error=error,
                peak_Gurobi_memory_GB=attr('MaxMemUsed'),
                objective_diagnostic=attr('ObjVal') if attr('SolCount',0) else None,
                native_ObjBound_diagnostic=attr('ObjBound'),native_BestBd_is_not_exact_certificate=True,
                presolve_callback_count=len(observed),
                presolve_callback_span_seconds=(observed[-1]-observed[0]) if observed else None,
                presolve_callback_span_is_not_exact_presolve_runtime=True,
                historical_ledger_writes=0)
            # Solver-reported rounded timing; already included in Native Runtime.
            text=log.read_text(encoding='utf-8',errors='replace') if log.is_file() else ''
            times=re.findall(r'Presolve time:\s*([0-9.]+)s',text)
            row['solver_reported_presolve_seconds_rounded']=[float(t) for t in times]
            row['presolve_included_in_Native_Runtime']=True
            self.calls.append(row);self.inflight=None;self.persist()
        self.check();return row

    def persist(self):
        elapsed=self.clock()-self.started
        receipt=dict(schema='V42_M1_FAST_HYBRID_LEDGER_V1',case_sha=self.case_sha,
            pilot_native_limit_seconds=2700.,original_M1_native_ceiling_seconds=5400.,
            allocations=dict(ALLOCATIONS),Native_Runtime_sum=self.used(),
            Native_Work_sum=sum(c.get('Native_Work') or 0. for c in self.calls),
            track_Runtime={k:self.used(k) for k in ALLOCATIONS},calls=self.calls,inflight=self.inflight,
            non_native_wall_costs=self.costs,wall_seconds=elapsed,wall_60_minutes_PASS=elapsed<=3600.,
            wall_90_minutes_PASS=elapsed<=5400.,parameters=dict(PARAMETERS),
            independent_global_gap_goal=.05,A1_A2_gap_preserved=.005,
            inner_solver_gap_is_not_global_acceptance=True,memory_limits=False,
            memory_automatic_stop=False,historical_ledgers_modified=False,budget_transfers=[],
            measured_Runtime_complete=not any(c['runtime_unavailable'] for c in self.calls))
        write(self.path,receipt);return receipt
