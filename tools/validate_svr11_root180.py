"""One verified live May01 case, fresh U4 start, one bounded Full root probe.

Only immutable input/Forecast coefficients are read from the held campaign.
No predecessor matrix, incumbent, UB, LB or optimization checkpoint is read.
The root probe terminates after the completed native root message (at the next
non-message callback), or its 600-second cap. It cannot release a campaign.
"""
from contextlib import contextmanager
from pathlib import Path
import json, math, sys, time
import numpy as np

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic, read, record, digest, now, sha
from v42_common_campaign.authority import source_files

OLD=Path(r'D:\v42_svr11_may_20261011_16')
DEV=Path(r'D:\v42_dense_response_root_measurement_20261011')
NATIVE0=Path(r'D:\v42_dense_response_development_20261011')
DAY='2025-05-01'
PRECISION=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-8,
    NumericFocus=3,ScaleFlag=2)


class ProbeBudget:
    def __init__(self,path,sources,progress,runner_sources=None):
        self.path,self.sources,self.progress=path,sources,progress
        self.runner_sources=runner_sources or {}
        self.calls,self.costs,self.inflight,self.native_used=[],[],None,0.
        self.full_calls=0
        self.persist()

    def used(self):return self.native_used
    def remaining(self):return max(0.,1800.-self.native_used)

    @contextmanager
    def cost(self,phase,label):
        started=time.perf_counter()
        try:yield
        finally:
            self.costs.append(dict(phase=phase,label=label,wall_seconds=time.perf_counter()-started))
            self.persist()

    def persist(self):
        atomic(self.path,dict(source_SHA=digest(self.sources),calls=self.calls,inflight=self.inflight,
            measured_Native_Runtime=self.native_used,Native_ceiling_seconds=1800,
            development_only=True,production_results_promoted=0,costs=self.costs,UTC=now()))

    def native_optimize(self,model,callback=None,*,component,track,label,requested_seconds):
        import gurobipy as gp
        if source_files()!=self.sources:raise PermissionError('ROOT180_SOURCE_DRIFT')
        if any(sha(SOURCE/name)!=item['sha256'] for name,item in self.runner_sources.items()):
            raise PermissionError('ROOT180_RUNNER_SOURCE_DRIFT_BEFORE_NATIVE')
        if model.Params.Threads!=1:raise PermissionError('ROOT180_THREADS_ONE_REQUIRED')
        full=track=='M_FULL_MILP'
        if full:
            if self.full_calls:raise PermissionError('ROOT180_SINGLE_FULL_NATIVE_CALL_ONLY')
            self.full_calls+=1
        effective=min(float(requested_seconds),self.remaining(),600. if full else 1800.)
        if effective<=0:raise ValueError('ROOT180_NATIVE_BUDGET_EXHAUSTED')
        model.Params.TimeLimit=effective
        model.Params.NodefileDir=str(DEV/'native_nodes')
        (DEV/'native_nodes').mkdir(exist_ok=True)
        from v42_ultracompact.native_readback import snapshot,verify_root_readback
        actual=snapshot(model)
        verification=verify_root_readback(actual) if full else None
        readback=Path(str(model.Params.LogFile)).parent/'ACTUAL_PARAMETERS_BEFORE_NATIVE.json'
        atomic(readback,dict(actual,verification=verification))
        row=dict(component=component,track=track,label=label,requested_seconds=requested_seconds,
            effective_TimeLimit=effective,actual_parameter_readback=record(readback),
            entered_native=True,status='IN_FLIGHT',UTC=now())
        self.inflight=row;self.persist()
        completed=[False]
        last_progress=[0.]
        def observe(m,where):
            if callback:callback(m,where)
            if where==gp.GRB.Callback.POLLING:return
            runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
            if full and where==gp.GRB.Callback.MESSAGE:
                message=m.cbGet(gp.GRB.Callback.MSG_STRING)
                if message.lstrip().startswith('Root relaxation: objective') and not any(
                        word in message.lower() for word in ('interrupted','time limit','infeasible','unbounded')):
                    completed[0]=True;row['root_completed_native_elapsed_seconds']=runtime
            if full and completed[0] and where!=gp.GRB.Callback.MESSAGE:
                m.terminate()
            if time.monotonic()-last_progress[0]>=5:
                self.progress(dict(phase='FULL_ROOT_PROBE' if full else track,
                    completed_Native_Runtime=self.native_used,inflight_Native_Runtime=runtime,
                    root_completed=completed[0]))
                last_progress[0]=time.monotonic()
        try:model.optimize(observe)
        finally:
            runtime=float(model.Runtime)
            if not math.isfinite(runtime) or runtime<0:raise ValueError('ROOT180_UNMEASURED_NATIVE_RUNTIME')
            row.update(Native_Runtime=runtime,Native_status=model.Status,status='FINISHED',
                runtime_unavailable=False,root_completed=completed[0],finished_UTC=now())
            self.calls.append(row);self.native_used+=runtime;self.inflight=None;self.persist()
        return row


def census(A,d):
    from collections import Counter
    names=[str(n).split('[',1)[0] for n in d['row_names']]
    nnz=np.diff(A.indptr);count=Counter(names);nonzeros=Counter()
    for family,n in zip(names,nnz):nonzeros[family]+=int(n)
    return dict(rows=A.shape[0],columns=A.shape[1],binary=int(np.count_nonzero(d['types']=='B')),
        nnz=A.nnz,row_families={f:dict(rows=count[f],nnz=nonzeros[f]) for f in sorted(count)},
        column_families=dict(Counter(str(n).split('[',1)[0] for n in d['names'])))


def measure_case_once(case,request,*,sources,source_sha,source_commit,build_wall,copy_proof,progress,sizes):
    """Consume the freshly verified live case; do not rebuild the FULL model."""
    validation=read(NATIVE0/'NATIVE0_VALIDATION.json')
    gate=validation['Root_measurement_gate']
    if (validation.get('PASS') is not True or validation.get('source_SHA')!=source_sha
            or validation.get('case_SHA')!=case.case_sha or digest(source_files())!=source_sha
            or gate.get('allowed') is not True):
        raise PermissionError('DENSE_ROOT_EXACT_PROOF_AND_ACTUAL_COMPRESSION_REQUIRED')
    from v42_may_campaign_native90.m_model import verify_case
    if not verify_case(case)['PASS']:
        raise PermissionError('DENSE_ROOT_CURRENT_CASE_PROOF_REQUIRED')
    if (DEV/'NATIVE_RUNTIME_LEDGER.json').exists():
        raise PermissionError('ROOT180_SINGLE_MEASUREMENT_LEDGER_ALREADY_EXISTS')
    DEV.mkdir(exist_ok=True)
    output=case.output;folder=OLD/'inputs/B2'/DAY;bundle=case.bundle
    runner_sources={name:record(SOURCE/name) for name in (
        'tools/validate_svr11_dense_response.py','tools/validate_svr11_root180.py',
        'tools/root180_completion.py')}
    atomic(DEV/'SOURCE18_SEAL.json',dict(source_SHA=source_sha,source_commit=source_commit,
        execution_sources=sources,runner_sources=runner_sources,
        actual_selected_matrix_SHA=case.identity['selected_matrix_sha'],
        actual_selected_domain_SHA=case.identity['selected_domain_sha'],
        actual_case_SHA=case.case_sha,Native0_validation=record(NATIVE0/'NATIVE0_VALIDATION.json'),
        single_Full_probe_cap_seconds=600,root180_acceptance_seconds=180,
        M_native_ceiling_seconds=1800,duplicate_original_model_builds=0,UTC=now()))
    from v42_common_mess.engine import _initialize,_trial,_validate,full_milp_parameters
    from v42_common_mess.budget import StageBudget
    from v42_common_mess.neighborhood import current_grid,select
    from v42_autonomous_b2.worker import proof_routes
    from v42_common_mess.model import memory_observation
    budget=ProbeBudget(DEV/'NATIVE_RUNTIME_LEDGER.json',sources,progress,runner_sources);stage=StageBudget(budget)
    validator=proof_routes(request)['final']['_strict_ub']
    point,strict,initialization=_initialize(case,stage,validator,progress,PRECISION)
    if strict is None:raise ValueError('ROOT180_NO_FRESH_VERIFIED_START')
    grid=current_grid(case,point,output/'FRESH_U4_GRID.json')
    spec=select(case,point,'U4',0,grid)
    if not spec['route_openness']['PASS']:raise ValueError('ROOT180_FRESH_U4_ROUTE_CLOSED')
    low,high=case.d['lower'].copy(),case.d['upper'].copy()
    fixed_columns=spec['fixed_binary_columns'];low[fixed_columns]=point[fixed_columns];high[fixed_columns]=point[fixed_columns]
    point,strict,u4=_trial(case,stage,output/'FRESH_U4',validator=validator,seconds=min(90.,stage.remaining()),
        lower=low,upper=high,point=point,strict=strict,spec=spec,numeric_parameters=PRECISION)
    initial_strict=strict
    from v42_m1_research.check_ub import vector_sha
    full_start_sha=vector_sha(point)
    point,strict,full=_trial(case,stage,output/'FULL_ROOT_ONCE',validator=validator,
        seconds=min(600.,stage.remaining()),point=point,strict=strict,unrestricted=True,
        numeric_parameters=full_milp_parameters(PRECISION))
    final=_validate(case,point,output/'FINAL_FULL_POINT.npz',validator,stage,'FINAL_ORIGINAL_FULL_REPLAY')
    if final is None:raise ValueError('ROOT180_FINAL_FULL_REPLAY_FAILED')
    if source_files()!=sources or any(sha(SOURCE/name)!=item['sha256'] for name,item in runner_sources.items()):
        raise PermissionError('ROOT180_FINAL_SOURCE_OR_RUNNER_DRIFT')
    from root180_completion import verified_report
    root_completion=verified_report(dict(full=full))
    root=root_completion['completed_seconds'];complete=root_completion['completed']
    met=(complete and 0<root<=180. and full.get('native_error') is None
        and full.get('Native_status') in (2,9,11))
    report=dict(PASS=True,exact_reduction_proven=True,root180_validated=met,
        classification='ROOT180_PASS' if met else 'ROOT180_UNMET' if complete else 'ROOT_INCOMPLETE',
        native_root_completion=root_completion,
        root180_acceptance_seconds=180.,historical_reference_seconds=180.21,
        source_SHA=source_sha,source_commit=source_commit,source_seal=record(DEV/'SOURCE18_SEAL.json'),
        fresh_inputs={name:record(folder/name) for name in ('NATIVE_INPUT.json','B2_FIXED_AIDC.json')},
        coefficient_input=record(bundle['electrical_certificate']['path']),
        original_matrix_SHA=case.identity['original_matrix_sha'],original_domain_SHA=case.identity['original_domain_sha'],
        selected_matrix_SHA=case.identity['selected_matrix_sha'],selected_domain_SHA=case.identity['selected_domain_sha'],
        selected_Bound_SHA=__import__('hashlib').sha256(case.d['lower'].tobytes()+case.d['upper'].tobytes()).hexdigest(),
        original_and_LP_and_integer_domains_identical=True,model_build_wall_seconds=build_wall,
        sizes=sizes,transport=case.identity['transport'],C3A_proof=record(output/'CURRENT_EXACT_C3A_PROOF.json'),
        old_optimization_results_read=0,old_UB_LB_gap_reused=0,fresh_initial_UB=initial_strict['Global_UB'],
        fresh_U4_start_vector_SHA=full_start_sha,fresh_U4_result=u4,
        final_UB=final['Global_UB'],final_original_FULL_replay=record(output/'FINAL_FULL_POINT.REPLAY.json'),
        full=full,U4_bound_global=False,Native_Runtime=budget.used(),Full_native_calls=budget.full_calls,
        memory=memory_observation(),copy_elision=copy_proof,production_results_promoted=0,
        development_only=True,campaign_automatically_released=False,UTC=now())
    atomic(DEV/'ROOT180_VALIDATION.json',report)
    print(json.dumps(dict(classification=report['classification'],root_seconds=root,sizes=sizes['Dense'],
        UB=report['final_UB'],LB=full['solver_global_LB'],gap=full['solver_global_gap']),ensure_ascii=False))
    return report


def run():
    raise PermissionError('ROOT18_REQUIRES_FRESH_LIVE_NATIVE0_CASE_USE_VALIDATE_DENSE_RESPONSE_ROOT_ONCE')


if __name__=='__main__':run()
