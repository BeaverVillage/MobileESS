"""Overnight source-bound native LP; raw persistence before validation."""
from pathlib import Path
from time import perf_counter
from dataclasses import replace
import json
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,digest,table
from .execution import verify, native_scope,active_freeze
from v42_a_stage_domain_v2.execution import install_gurobi_backstop,guard_model_optimize
from v42_a_stage_domain_v2.stress_backend import materialize
from v42_a_stage_domain_v2.solver_policy import apply_policy
from v42_a_stage_domain_v2.fast_telemetry import FastTelemetry
from v42_a_stage_domain_v2.telemetry import native_scalar
from v42_a_stage_domain_v2.postsolve_review import internal_attempts
from .policy import OUT,STATIC,POLICY
DAY=None
from v42_a_stage_phase1.setup import HISTORY
from .memory import sample


from v42_a_stage_early.native import BudgetStop


class Native:
    def __init__(self, budget,day):
        global DAY
        DAY=day
        self.freeze_path=active_freeze()
        self.policy=read(HISTORY/'SOLVER_POLICY.json')
        self.budget=budget;self.parent_budget=budget
        self.native_seconds=0.;self.calls=[];self.resources=[];self.system_samples=[]
        install_gurobi_backstop(gp)

    def verify(self):return verify()
    def remaining(self):return self.budget.remaining()

    def solve(self,snapshot,folder,component):
        if component not in ('PHASE_I','ORIGINAL_P1','INTEGER_CONTROL','NODE_LP','LOCAL_PRICING','P2'):raise PermissionError('PHASE1_LP_ONLY_AUTHORIZATION')
        self.verify();remaining=self.remaining();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        build_started=perf_counter()
        model,objectives=materialize(snapshot,DAY)
        if model.NumIntVars and component not in ('INTEGER_CONTROL','P2'):raise PermissionError('INTEGER_COMPONENT_REQUIRED')
        model.setObjective(objectives[0][1],gp.GRB.MINIMIZE)
        # Independent read-back before trusting a CURRENT full-domain MIP bound.
        compiled=model.getA().tocsr();compiled.sum_duplicates();compiled.sort_indices()
        delta=compiled-snapshot.matrix;delta.eliminate_zeros()
        expected=np.zeros(model.NumVars)
        for j,c in snapshot.objectives[0].coefficients().items():expected[j]=float(c)
        box=lambda a,b:np.array_equal(a,b) or np.all((a==b)|((abs(a)>=1e100)&(abs(b)>=1e100)&(np.sign(a)==np.sign(b))))
        actual=dict(PASS=delta.nnz==0 and box(np.asarray(model.getAttr('LB')),snapshot.lower)
            and box(np.asarray(model.getAttr('UB')),snapshot.upper)
            and np.array_equal(model.getAttr('VType'),snapshot.vtypes)
            and np.array_equal(model.getAttr('Sense'),snapshot.senses)
            and np.array_equal(model.getAttr('RHS'),snapshot.rhs)
            and np.array_equal(model.getAttr('Obj'),expected)
            and model.ObjCon==float(snapshot.objectives[0].constant),
            differing_matrix_coefficients=int(delta.nnz),original_snapshot_sha256=snapshot.fingerprint(),
            current_actual_native_model_read_back=True)
        atomic(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json',actual)
        if not actual['PASS']:
            model.dispose();raise ValueError('ACTUAL_NATIVE_MODEL_NOT_EXACT_ORIGINAL_MATRIX')
        effective=apply_policy(model,self.policy,gp)
        model.setParam('MemLimit',float('inf'));model.setParam('SoftMemLimit',float('inf'))
        atomic(folder/'MEMORY_LIMITS_DISABLED.json',dict(PASS=True,
            MemLimit=str(model.Params.MemLimit),SoftMemLimit=str(model.Params.SoftMemLimit),
            automatic_memory_stop=False,allocation_cap=False,telemetry_only=True,
            authority=record(OUT/'MEMORY_GUARDS_USER_OVERRIDE.json')))
        self.live_model=model
        if component=='NODE_LP':
            model.setParam('InfUnbdInfo',1);effective['InfUnbdInfo']=1
        if getattr(self,'warm_point',None) is not None:
            if len(self.warm_point)!=model.NumVars:raise ValueError('INTEGER_WARM_POINT_AXES')
            model.setAttr('Start',model.getVars(),list(self.warm_point))
        if getattr(self,'warm_basis',None) is not None and not model.NumIntVars:
            vb,cb=self.warm_basis
            if len(vb)!=model.NumVars or len(cb)!=model.NumConstrs:raise ValueError('PARENT_BASIS_AXES')
            model.setAttr('VBasis',model.getVars(),list(map(int,vb)));model.setAttr('CBasis',model.getConstrs(),list(map(int,cb)))
            model.setParam('Method',1);model.setParam('LPWarmStart',2)
            effective.update(Method=1,LPWarmStart=2,basis_reoptimization=True)
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
            source_commit=read(getattr(self,'freeze_path',OUT/'PHASE1_SOURCE_FREEZE.json'))['git_head'],
            source_manifest=record(getattr(self,'freeze_path',OUT/'PHASE1_SOURCE_FREEZE.json')),bound_variables_relaxed=False,
            FarkasDual_access=component=='NODE_LP',solver_policy_unchanged=True)
        atomic(folder/'MODEL_IDENTITY.json',identity)
        try:remaining=self.remaining()
        except BudgetStop:
            atomic(folder/'BUILD_STOP.json',dict(native_optimize_entered=False,reason='BUDGET_EXHAUSTED_DURING_BUILD'))
            model.dispose();raise
        model.setParam('TimeLimit',remaining)
        atomic(folder/'SOLVER_PARAMETERS.json',dict(effective=effective,TimeLimit=remaining,component=component,
            parameter_sweep=False,artificial_information_parameter=False))
        telemetry=FastTelemetry(model,day=DAY,objective=component,group='LP',remaining_seconds=remaining)
        failure=None;entered=False;callback_errors=[];last_checkpoint=[perf_counter(),-10.]
        def observe(m,w):
            try:
                telemetry.callback(m,w,gp.GRB)
                if w==gp.GRB.Callback.MIP:
                    nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT))
                    if nodes-last_checkpoint[1]>=10 or perf_counter()-last_checkpoint[0]>=300:
                        atomic(folder/'INFLIGHT_BEST_BOUND_CHECKPOINT.json',dict(day=DAY,component=component,
                            processed_native_nodes=nodes,callback_bound=float(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),
                            callback_incumbent=float(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),
                            source=identity['source_manifest'],model_identity=record(folder/'MODEL_IDENTITY.json'),
                            external_queue=getattr(self,'queue_checkpoint',None),deadline=read(OUT/'CONTINUATION_BUDGET.json'),
                            callback_bound_is_progress_only=True,original_incumbent_preserved=True))
                        last_checkpoint[:]=[perf_counter(),nodes]
                if w==gp.GRB.Callback.MIPSOL and getattr(self,'incumbent_callback',None) is not None:
                    self.incumbent_callback(np.asarray(m.cbGetSolution(m.getVars()),dtype=float),m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                from time import time
                if not self.system_samples or time()-self.system_samples[-1]['unix']>=2:
                    s=dict(unix=time(),**sample());self.system_samples.append(s)
                    atomic(folder/'SYSTEM_MEMORY.json',dict(samples=self.system_samples))
                try:self.remaining()
                except BudgetStop:m.terminate()
            except Exception as error:
                callback_errors.append(type(error).__name__+': '+str(error));m.terminate()
        telemetry.start_resources()
        try:
            with native_scope(model,component,self.remaining):
                guard_model_optimize(model);entered=True
                model.optimize(observe)
        except Exception as error:failure=type(error).__name__+': '+str(error)
        finally:
            telemetry.stop_resources()
            used=native_scalar(model,'Runtime') if entered else 0.
            if callback_errors:failure='TELEMETRY_CALLBACK_ERROR:'+repr(callback_errors)
            if entered and used is None:failure='NATIVE_RUNTIME_UNAVAILABLE'
            self.native_seconds+=used or 0.
            self.budget.charge(used or 0.)
            arrays={};errors={}
            # A missing Pi must never prevent persistence of an available X.
            for attr in ('X','Pi','RC','Slack','VBasis','CBasis','FarkasDual'):
                try:arrays[attr]=np.asarray(model.getAttr(attr),dtype=float)
                except Exception as error:errors[attr]=str(error)
            np.savez_compressed(static/'NATIVE_RAW.npz',**arrays)
            result=dict(status=native_scalar(model,'Status'),objective=native_scalar(model,'ObjVal'),
                ObjBound=native_scalar(model,'ObjBound'),native_seconds=used,cumulative_native_seconds=self.native_seconds,
                NodeCount=native_scalar(model,'NodeCount'),SolCount=native_scalar(model,'SolCount'),MIPGap=native_scalar(model,'MIPGap'),Work=native_scalar(model,'Work'),IterCount=native_scalar(model,'IterCount'),BarIterCount=native_scalar(model,'BarIterCount'),
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
            table(folder/'RESOURCE_TELEMETRY.csv',self.resources,sorted(set().union(*(r.keys() for r in self.resources))) if self.resources else ['status'])
            self.calls.append(dict(folder=str(folder),component=component,**result))
            atomic(folder/'NATIVE_CALLS.json',dict(calls=self.calls,cumulative_native_seconds=self.native_seconds,
                budget_accounted_seconds=self.budget.accounted(),budget_overshoot_seconds=max(0.,self.native_seconds-3600)))
            model.dispose();self.live_model=None
        if failure:raise RuntimeError(failure)
        return result,arrays
