"""Narrow May19 LP execution with persistence before every validation."""
from pathlib import Path
from time import perf_counter
from dataclasses import replace
import json
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,digest,table
from v42_a_stage_domain_v2.fast_execution import FastRunPermit,fast_run_scope,fast_native_scope
from v42_a_stage_domain_v2.execution import install_gurobi_backstop,guard_model_optimize
from v42_a_stage_domain_v2.stress_backend import materialize
from v42_a_stage_domain_v2.solver_policy import apply_policy
from v42_a_stage_domain_v2.fast_telemetry import FastTelemetry
from v42_a_stage_domain_v2.telemetry import native_scalar
from v42_a_stage_domain_v2.postsolve_review import internal_attempts
from .setup import OUT,HISTORY,STATIC,DAY,POLICY


class BudgetStop(RuntimeError):pass


class Native:
    def __init__(self):
        doc=read(OUT/'CANARY_EXECUTION_PERMIT.json')
        self.permit=FastRunPermit(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False))
        self.policy=read(HISTORY/'SOLVER_POLICY.json')
        self.native_seconds=0.;self.pricing_wall_seconds=0.;self.pricing_started=None;self.calls=[];self.resources=[]
        install_gurobi_backstop(gp)

    def verify(self):
        self.permit.verify()
        freeze=read(OUT/'PHASE1_SOURCE_FREEZE.json')
        for r in freeze['additional_gate_receipts']:
            if record(r['path'])!=r or read(r['path']).get('PASS') is not True:raise PermissionError('PHASE1_GATE_BYTE_DRIFT')
        if read(OUT/'PHASE1_ENGINEERING_POLICY.json')!=POLICY:raise PermissionError('PHASE1_POLICY_DRIFT')
        return True

    def remaining(self):
        inflight=0. if self.pricing_started is None else perf_counter()-self.pricing_started
        remaining=min(POLICY['cumulative_native_seconds']-self.native_seconds,
            (POLICY['native_plus_pricing_wall_seconds']-self.native_seconds-self.pricing_wall_seconds-inflight)/
            (2 if self.pricing_started is not None else 1))
        if remaining<=0:raise BudgetStop('PHASE1_PREREGISTERED_CUMULATIVE_BUDGET')
        return remaining

    def solve(self,snapshot,folder,component):
        if component not in ('PHASE_I','ORIGINAL_P1','LOCAL_PRICING'):raise PermissionError('PHASE1_LP_ONLY_AUTHORIZATION')
        self.verify();remaining=self.remaining();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        build_started=perf_counter()
        model,objectives=materialize(snapshot,DAY)
        if model.NumIntVars:raise PermissionError('PHASE1_NATIVE_INTEGER_MODEL_FORBIDDEN')
        model.setObjective(objectives[0][1],gp.GRB.MINIMIZE)
        effective=apply_policy(model,self.policy,gp)
        model.setParam('OutputFlag',1);model.setParam('LogToConsole',0)
        model.setParam('LogFile',str(folder/'NATIVE_SOLVER.log'))
        static=STATIC/folder.relative_to(OUT)
        static.mkdir(parents=True,exist_ok=True)
        sp.save_npz(static/'MATRIX.npz',snapshot.matrix)
        c=np.zeros(snapshot.matrix.shape[1])
        for j,v in snapshot.objectives[0].coefficients().items():c[j]=float(v)
        np.savez_compressed(static/'ATTRIBUTES.npz',lower=snapshot.lower,upper=snapshot.upper,
            senses=snapshot.senses,rhs=snapshot.rhs,vtypes=snapshot.vtypes,objective=c)
        identity=dict(day=DAY,component=component,original_snapshot_sha256=snapshot.fingerprint(),
            rows=snapshot.matrix.shape[0],cols=snapshot.matrix.shape[1],nnz=snapshot.matrix.nnz,
            row_identity='CURRENT_EXACT_CSR_ROW_INDEX_AND_COEFFICIENT_HASH',
            column_identity='CURRENT_EXACT_CSR_COLUMN_INDEX_AND_COEFFICIENT_HASH',
            matrix=record(static/'MATRIX.npz'),attributes=record(static/'ATTRIBUTES.npz'),
            source_commit=read(OUT/'PHASE1_SOURCE_FREEZE.json')['git_head'],
            source_manifest=record(OUT/'PHASE1_SOURCE_FREEZE.json'),bound_variables_relaxed=False,
            FarkasDual_access=False,solver_policy_unchanged=True)
        atomic(folder/'MODEL_IDENTITY.json',identity)
        try:remaining=self.remaining()
        except BudgetStop:
            atomic(folder/'BUILD_STOP.json',dict(native_optimize_entered=False,reason='BUDGET_EXHAUSTED_DURING_BUILD'))
            model.dispose();raise
        model.setParam('TimeLimit',remaining)
        atomic(folder/'SOLVER_PARAMETERS.json',dict(effective=effective,TimeLimit=remaining,component=component,
            parameter_sweep=False,artificial_information_parameter=False))
        telemetry=FastTelemetry(model,day=DAY,objective=component,group='LP',remaining_seconds=remaining)
        failure=None;entered=False;callback_errors=[]
        def observe(m,w):
            try:telemetry.callback(m,w,gp.GRB)
            except Exception as error:
                callback_errors.append(type(error).__name__+': '+str(error));m.terminate()
        telemetry.start_resources()
        try:
            with fast_run_scope(self.permit),fast_native_scope(model,DAY,'LP'):
                guard_model_optimize(model);entered=True
                model.optimize(observe)
        except Exception as error:failure=type(error).__name__+': '+str(error)
        finally:
            telemetry.stop_resources()
            used=native_scalar(model,'Runtime') if entered else 0.
            if callback_errors:failure='TELEMETRY_CALLBACK_ERROR:'+repr(callback_errors)
            if entered and used is None:failure='NATIVE_RUNTIME_UNAVAILABLE'
            self.native_seconds+=used or 0.
            arrays={};errors={}
            # A missing Pi must never prevent persistence of an available X.
            for attr in ('X','Pi','RC','Slack'):
                try:arrays[attr]=np.asarray(model.getAttr(attr),dtype=float)
                except Exception as error:errors[attr]=str(error)
            np.savez_compressed(static/'NATIVE_RAW.npz',**arrays)
            result=dict(status=native_scalar(model,'Status'),objective=native_scalar(model,'ObjVal'),
                ObjBound=native_scalar(model,'ObjBound'),native_seconds=used,cumulative_native_seconds=self.native_seconds,
                Work=native_scalar(model,'Work'),IterCount=native_scalar(model,'IterCount'),BarIterCount=native_scalar(model,'BarIterCount'),
                raw_attributes=record(static/'NATIVE_RAW.npz'),raw_attribute_errors=errors,native_error=failure,
                all_available_attributes_persisted_before_assertions=True,model_identity=record(folder/'MODEL_IDENTITY.json'),
                build_and_snapshot_seconds=perf_counter()-build_started-(used or 0.),source_commit=identity['source_commit'])
            atomic(folder/'NATIVE_RESULT.json',result)
            telemetry.finish_objective(model);observation=telemetry.receipt()
            log=folder/'NATIVE_SOLVER.log'
            attempts=internal_attempts(log.read_text(encoding='utf8')) if log.exists() else []
            result['internal_barrier_attempts']=attempts
            result['max_factor_nnz']=max((a.get('factor_nnz',0) for a in attempts),default=None)
            result['max_factor_memory_GB']=max((a.get('factor_memory_GB',0) for a in attempts),default=None)
            result['peak_RSS_bytes']=observation['fill_in'].get('peak_RSS_bytes')
            result['presolved_matrix']=observation.get('presolved_matrix')
            result['telemetry']=record(folder/'NATIVE_TELEMETRY.json') if (folder/'NATIVE_TELEMETRY.json').exists() else None
            atomic(folder/'NATIVE_TELEMETRY.json',observation)
            result['telemetry']=record(folder/'NATIVE_TELEMETRY.json')
            atomic(folder/'NATIVE_RESULT.json',result)
            self.resources.extend(observation['resource_samples'])
            table(OUT/'MAY19/RESOURCE_TELEMETRY.csv',self.resources,sorted(set().union(*(r.keys() for r in self.resources))) if self.resources else ['status'])
            self.calls.append(dict(folder=str(folder),component=component,**result))
            atomic(OUT/'MAY19/NATIVE_CALLS.json',dict(calls=self.calls,cumulative_native_seconds=self.native_seconds,
                pricing_wall_seconds=self.pricing_wall_seconds,budget_overshoot_seconds=max(0.,self.native_seconds-POLICY['cumulative_native_seconds'])))
            model.dispose()
        if failure:raise RuntimeError(failure)
        return result,arrays
