"""One fresh May01 construction, fresh U4 start, one bounded Full root probe.

Only immutable input/Forecast coefficients are read from the held campaign.
No predecessor matrix, incumbent, UB, LB or optimization checkpoint is read.
The root probe terminates after the completed native root message (at the next
non-message callback), or its 600-second cap. It cannot release a campaign.
"""
from contextlib import contextmanager
from pathlib import Path
import copy, json, math, sys, time, traceback
import numpy as np

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic, read, record, digest, now, sha
from v42_common_campaign.authority import source_files

OLD=Path(r'D:\v42_svr11_may_20261011_16')
DEV=Path(r'D:\v42_root180_development_20261011')
DAY='2025-05-01'
PRECISION=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-8,
    NumericFocus=3,ScaleFlag=2)


class ProbeBudget:
    def __init__(self,path,sources,progress):
        self.path,self.sources,self.progress=path,sources,progress
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
        row=dict(component=component,track=track,label=label,requested_seconds=requested_seconds,
            effective_TimeLimit=effective,entered_native=True,status='IN_FLIGHT',UTC=now())
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


def run():
    if (DEV/'NATIVE_RUNTIME_LEDGER.json').exists():
        raise PermissionError('ROOT180_PROBE_LEDGER_ALREADY_EXISTS_NO_REPEATED_SOLVER')
    DEV.mkdir(exist_ok=True)
    output=DEV/'dates/B2'/DAY/'attempts/root180_once/output'
    output.mkdir(parents=True,exist_ok=False)
    sources=source_files();source_sha=digest(sources);started=time.perf_counter()
    def progress(value):
        atomic(DEV/'PROGRESS.json',dict(value,source_SHA=source_sha,
            wall_seconds=time.perf_counter()-started,development_only=True,UTC=now()))
    old=read(OLD/'CAMPAIGN_MANIFEST.json')
    from prepare_svr11_epoch15 import preserved_science
    unchanged_science=preserved_science(old,sources)
    source_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    atomic(DEV/'SOURCE17_SEAL.json',dict(source_SHA=source_sha,source_commit=source_commit,
        execution_sources=sources,representative_day=DAY,Threads=1,
        strict_numeric_parameters=PRECISION,M_native_ceiling_seconds=1800,
        single_Full_probe_cap_seconds=600,root180_acceptance_seconds=200,
        immutable_coefficient_origin_source_SHA=old['execution_SHA'],
        unchanged_physical_and_A_science=unchanged_science,UTC=now()))
    # Independent replay is mandatory for this one representative construction.
    active=copy.deepcopy(old);active['independent_model_proof_replay']=True
    folder=OLD/'inputs/B2'/DAY
    bundle=read(folder/'NATIVE_INPUT.json');fixed=read(folder/'B2_FIXED_AIDC.json')
    if record(fixed['physical']['path'])!=fixed['physical']:raise PermissionError('ROOT180_FIXED_INPUT_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as z:planning={k:z[k].copy() for k in z.files}
    payload=dict(bundle=bundle,planning=planning,identity=fixed['identity'],selected_jobs=fixed['selected_jobs'])
    request=dict(root=str(DEV),campaign_root=str(DEV),arm='B2',day=DAY,attempt_id='root180_once',
        output=str(output),source_SHA=source_sha,development_only=True,production_results_promoted=0)
    atomic(DEV/'REQUEST.json',request)
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    token=_active.set(active);current_authority.cache_clear()
    exact_proven=False
    try:
        import v42_may_campaign_native90.m_model as constructor
        import v42_native.mess as native
        from v42_bootstrap.m1 import native_inputs
        from v42_b2_build_authority_v13.source_port import instrument_builder
        from v42_b2_build_authority_v13.build_runtime import BuildProfile
        from v42_b2_build_authority_v13.scalar_math import original_pcs_math_scope
        from v42_may_campaign_native90.preflight import native_zero
        profile=BuildProfile(source_sha,'OPTIMIZED')
        port,copy_proof=instrument_builder(constructor.__file__,vars(constructor),native_inputs,
            profile,sha(constructor.__file__))
        progress(dict(phase='FRESH_EXACT_MODEL_BUILD'))
        build_start=time.perf_counter()
        with native_zero() as calls:
            with original_pcs_math_scope(native,native.__file__,sha(native.__file__)):
                case=port(payload,request,progress)
        build_wall=time.perf_counter()-build_start
        if calls or not constructor.verify_case(case)['PASS']:raise ValueError('ROOT180_EXACT_BUILD_PROOF_REQUIRED')
        exact_proven=True
        sizes=dict(original=census(case.original_A,case.original_d),
            compact=census(case.compact.A,case.compact.d),C2=census(case.presolve.A,case.presolve.d),
            C3A=census(case.A,case.d))
        atomic(DEV/'MATRIX_CENSUS.json',sizes)
        from v42_common_mess.engine import _initialize,_trial,_validate,full_milp_parameters
        from v42_common_mess.budget import StageBudget
        from v42_common_mess.neighborhood import current_grid,select
        from v42_autonomous_b2.worker import proof_routes
        from v42_common_mess.model import memory_observation
        budget=ProbeBudget(DEV/'NATIVE_RUNTIME_LEDGER.json',sources,progress);stage=StageBudget(budget)
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
        if source_files()!=sources:raise PermissionError('ROOT180_FINAL_SOURCE_DRIFT')
        from root180_completion import verified_report
        root_completion=verified_report(dict(full=full))
        root=root_completion['completed_seconds'];complete=root_completion['completed']
        met=complete and 0<root<=200. and full.get('native_error') is None
        report=dict(PASS=True,exact_reduction_proven=True,root180_validated=met,
            classification='EXACT_REDUCTION_AND_ROOT180_VALIDATED' if met else 'EXACT_REDUCTION_VALID_ROOT180_UNMET',
            native_root_completion=root_completion,
            root180_acceptance_seconds=200.,historical_reference_seconds=180.21,
            source_SHA=source_sha,source_commit=source_commit,source_seal=record(DEV/'SOURCE17_SEAL.json'),
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
        print(json.dumps(dict(classification=report['classification'],root_seconds=root,sizes=sizes['C3A'],
            UB=report['final_UB'],LB=full['solver_global_LB'],gap=full['solver_global_gap']),ensure_ascii=False))
        return report
    except Exception as error:
        atomic(DEV/'VALIDATION_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),
            source_SHA=source_sha,exact_reduction_proven=exact_proven,
            classification='EXACT_REDUCTION_VALID_ROOT180_UNMET' if exact_proven else 'EXACT_REDUCTION_NOT_PROVEN',UTC=now()))
        raise
    finally:_active.reset(token);current_authority.cache_clear()


if __name__=='__main__':run()
