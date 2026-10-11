"""Real May16/18 development continuation; never a production-date result.

Preserve the recorded original U4 runtime/point and reconstruct its exact
FULL/Compact/C3A transport. Invoke the released Phase2 and original measured
Native ledger, with a separately sealed development admission guard.
"""
from pathlib import Path
import sys, math, copy, contextlib, time, threading, traceback
import numpy as np
from scipy import sparse
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic, read, record, sha, digest, now
from v42_common_campaign.authority import source_files, singleton
from v42_svr11.resources import snapshot
from v42_svr11.processes import identity
OLD=Path(r'D:\v42_svr11_ldc_development_20261011')
ROOT=Path(r'D:\v42_svr11_full_milp_development_20261011')
SEAL=ROOT/'SOURCE_SEAL.json'


def sealed():
    value=read(SEAL)
    if (value['source_root']!=str(SOURCE) or value['sources']!=source_files()
            or value['source_SHA']!=digest(value['sources'])
            or value['diagnostic_script']!=record(__file__)):
        raise PermissionError('PHASE2_DEVELOPMENT_IMMUTABLE_SOURCE_DRIFT')
    return value


def seal():
    ROOT.mkdir(exist_ok=True)
    if SEAL.exists():return sealed()
    sources=source_files()
    atomic(SEAL,dict(source_root=str(SOURCE),sources=sources,source_SHA=digest(sources),
        diagnostic_script=record(__file__),development_only=True,production_results_promoted=0,
        reused_matrix_and_point_are_user_authorized_development_cases_only=True,UTC=now()))
    return sealed()


def load_case(day,output,progress):
    from v42_may_campaign_native90.m_model import CampaignMCase, verify_transport, verify_case, _freeze_transport, _domain_sha, _same
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_unified.mess_replay import graph_from_bundle
    old=OLD/'dates/B2'/day/'attempts/development_03/output'
    result=read(old/'M_STAGE_RESULT.json')
    prior=old.parent/'NATIVE_RUNTIME_LEDGER.json'; ledger=read(prior)
    runtime=float(ledger['measured_Native_Runtime'])
    if (ledger['inflight'] is not None or any(r.get('runtime_unavailable') for r in ledger['calls'])
            or not math.isfinite(runtime) or not 0<runtime<1800
            or runtime!=result['Native_Runtime'] or result['global_gap_certified']
            or result.get('feasible_accepted') is not True):
        raise ValueError('ORIGINAL_PHASE1_MEASURED_RUNTIME_REQUIRED')
    original_identity=read(old/'SCIENTIFIC_CASE_IDENTITY.json')
    data={}
    for name in ('FULL_DATA','C3A_DATA'):
        with np.load(old/(name+'.npz'),allow_pickle=False) as z:data[name]={k:z[k].copy() for k in z.files}
    A=sparse.load_npz(old/'FULL_A.npz');B=sparse.load_npz(old/'C3A_A.npz')
    if (matrix_sha(A)!=original_identity['original_matrix_sha']
            or matrix_sha(B)!=original_identity['selected_matrix_sha']
            or _domain_sha(data['FULL_DATA'])!=original_identity['original_domain_sha']
            or _domain_sha(data['C3A_DATA'])!=original_identity['selected_domain_sha']):
        raise PermissionError('ORIGINAL_DEVELOPMENT_SCIENTIFIC_MATRIX_BYTES_DRIFT')
    bundle=read(OLD/'inputs/B2'/day/'NATIVE_INPUT.json')
    anchor=read(old/'FIXED_AIDC_ANCHOR.json')
    if digest(bundle)!=original_identity['bundle_sha'] or digest(anchor)!=original_identity['anchor_sha']:
        raise PermissionError('ORIGINAL_DEVELOPMENT_INPUT_BINDING_DRIFT')
    graph=graph_from_bundle(bundle)
    progress(dict(phase='EXACT_OLD_DEVELOPMENT_TRANSPORT_RECONSTRUCTION',Native_Runtime=runtime))
    compact=Compact(A,data['FULL_DATA'],graph[2],graph[1],96)
    presolve=Presolve(compact.A,compact.d); selected,domain=presolve.run()
    if not _same(selected,B) or _domain_sha(domain)!=original_identity['selected_domain_sha']:
        raise PermissionError('DEVELOPMENT_REGENERATED_COMPACT_C3A_NOT_BIT_EXACT')
    transport=verify_transport(compact,presolve)
    authority=_freeze_transport(compact,presolve,graph,transport,output)
    identity_data={k:v for k,v in original_identity.items() if k!='case_sha'}
    identity_data.update(transport=transport,transport_authority=authority)
    with np.load(old/'BEST_STRICT_UB_POINT.npz',allow_pickle=False) as z:point=z['point'].copy()
    case=CampaignMCase(selected,domain,A,data['FULL_DATA'],point,graph,digest(identity_data),
        identity_data,compact,presolve,bundle,anchor,result['planning'],None,output)
    verify_case(case)
    receipts={name:record(old/name) for name in ('M_STAGE_RESULT.json','SCIENTIFIC_CASE_IDENTITY.json',
        'FULL_A.npz','FULL_DATA.npz','C3A_A.npz','C3A_DATA.npz','BEST_STRICT_UB_POINT.npz','BEST_STRICT_UB_CERTIFICATE.json')}
    atomic(output/'DEVELOPMENT_ORIGIN.json',dict(original_scientific_case_SHA=original_identity['case_sha'],
        current_diagnostic_case_SHA=case.case_sha,prior_native_ledger=record(prior),prior_measured_Native_Runtime=runtime,
        original_artifacts=receipts,Native_runtime_reset=False,production_date_promoted=False,
        immutable_old_case_receipts_preserved=True,reconstructed_transport=transport))
    return case,runtime,record(prior),receipts


def run(day):
    import psutil
    from v42_may_campaign import execution
    from v42_may_campaign_native90.execution import native_scope
    from v42_may_campaign_native90.a_routing import rebound
    from v42_b2_seed_recovery_v19.budget import DateBudget
    from v42_autonomous_b2.worker import proof_routes
    from v42_common_mess.budget import StageBudget
    from v42_common_mess.engine import _validate, _full_milp_phase
    from v42_common_mess.model import memory_observation
    source=sealed();attempt=ROOT/'dates/B2'/day/'attempts/phase2_01';output=attempt/'output'
    attempt.mkdir(parents=True,exist_ok=True);output.mkdir(exist_ok=True)
    if (attempt/'RESULT.json').exists():raise PermissionError('DEVELOPMENT_COMPLETED_NATIVE_NEVER_REPEATED')
    started=time.perf_counter();state=dict(day=day,source_SHA=source['source_SHA'],diagnostic_only=True,
        actual_calls=0,production_results_promoted=0,process=identity())
    mutex=threading.RLock()
    def progress(value):
        with mutex:
            state.update(value,UTC=now(),wall_seconds=time.perf_counter()-started,memory=memory_observation())
            atomic(attempt/'progress.json',dict(state))
    stop=threading.Event()
    def sample():
        while not stop.wait(5):progress({})
    sampler=threading.Thread(target=sample,daemon=True);sampler.start()
    try:
        case,runtime,prior,origins=load_case(day,output,progress)
        request=dict(root=str(ROOT),arm='B2',day=day,attempt_id='phase2_01',output=str(output),worker_slot=1,
            source_SHA=source['source_SHA'],Native_limit_seconds=1800,development_only=True)
        atomic(attempt/'request.json',request)
        def guard(model):
            sealed()
            current=execution._model.get()
            if current is None or current['model'] is not model or current['track']!='M_FULL_MILP':
                raise PermissionError('DEVELOPMENT_UNRESTRICTED_FULL_MILP_SCOPE_REQUIRED')
            if model.Params.Threads!=1 or model.Params.MIPGap!=0 or model.Params.MIPGapAbs!=0:
                raise PermissionError('DEVELOPMENT_NATIVE_THREADS_OR_UNVERIFIED_GAP_DRIFT')
            if model.NumConstrs!=case.A.shape[0] or model.NumVars!=case.A.shape[1]:
                raise PermissionError('DEVELOPMENT_FULL_MILP_ROW_COLUMN_IDENTITY_DRIFT')
            for receipt in origins.values():
                if record(receipt['path'])!=receipt:raise PermissionError('DEVELOPMENT_ORIGINAL_BYTES_DRIFT')
        method=rebound(DateBudget.native_optimize,dict(DateBudget.native_optimize.__globals__,guard=guard,native_scope=native_scope))
        Parent=type('SealedDevelopmentDateBudget',(DateBudget,),dict(native_optimize=method))
        token=execution._active.set(dict(request=request,manifest=dict(development_only=True),worker_slot=None))
        try:
            parent=Parent(attempt/'NATIVE_RUNTIME_LEDGER.json',native_limit=1800,wall_limit=None,progress=progress)
            parent.native_used=runtime
            parent.prior_attempt=dict(ledger=prior,Native_Runtime=runtime,same_case_development_continuation=True,
                production_results_promoted=0,original_execution_Source11_preserved=True)
            parent.persist();budget=StageBudget(parent)
            validator=proof_routes(request)['final']['_strict_ub']
            strict=_validate(case,case.point,output/'INITIAL_BEST_FULL.npz',validator,budget,'PHASE1_ORIGINAL_FULL_RECHECK')
            if strict is None:raise ValueError('DEVELOPMENT_PRIOR_BEST_NO_LONGER_FULL_FEASIBLE')
            initial_ub=strict['Global_UB']
            point,checked,rows,termination=_full_milp_phase(case,budget,case.point,strict,validator,progress,
                dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-8,NumericFocus=3,ScaleFlag=2),
                None,'ORIGINAL_OPTIONAL_PRIMAL_SEARCH_EXHAUSTED')
            final=_validate(case,point,output/'FINAL_BEST_FULL.npz',validator,budget,'FINAL_ORIGINAL_FULL_REPLAY')
            if final is None:raise ValueError('DEVELOPMENT_FINAL_FULL_REPLAY_FAILED')
            after=sealed()
            result=dict(PASS=True,day=day,development_only=True,production_results_promoted=0,
                source_SHA=after['source_SHA'],initial_UB=initial_ub,final_UB=final['Global_UB'],
                exact_initial_UB=strict['exact_Global_UB'],exact_final_UB=final['exact_Global_UB'],
                UB_nonregression=final['Global_UB']<=initial_ub,FULL_feasible_certified=True,
                Phase2_started=True,Phase2_calls=len(rows),Phase2_rows=rows,
                certified_Global_LB=None,certified_Global_Gap=None,global_gap_certified=False,
                Native_Runtime=budget.used(),prior_measured_Native_Runtime=runtime,
                new_measured_Native_Runtime=budget.used()-runtime,native_budget_overshoot_seconds=max(0,budget.used()-1800),
                termination_reason=termination,wall_seconds=time.perf_counter()-started,memory=memory_observation(),
                native_ledger=record(parent.path),native_logs=[record(p) for p in sorted(attempt.glob('*_NATIVE.log'))],
                final_FULL_certificate=record(output/'FINAL_BEST_FULL.REPLAY.json'))
            if not result['UB_nonregression']:raise ValueError('DEVELOPMENT_UB_REGRESSION')
            atomic(attempt/'RESULT.json',result);progress(dict(phase='TERMINAL',PASS=True,termination=termination))
        finally:execution._active.reset(token)
    except Exception as error:
        atomic(attempt/'DIAGNOSTIC_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),
            development_only=True,source_SHA=source['source_SHA'],original_UB_preserved=True,UTC=now()))
        raise
    finally:stop.set();sampler.join(timeout=2)


def coordinator():
    with singleton(ROOT/'VALIDATION_COORDINATOR.lock'):
        atomic(ROOT/'VALIDATION_PROCESS.json',dict(identity(),source_SHA=sealed()['source_SHA'],diagnostic_only=True))
        for day in ('2025-05-16','2025-05-18'):
            while snapshot()['RAM_available']<9*1024**3 or snapshot()['Commit_available']<9*1024**3:
                atomic(ROOT/'MEMORY_WAIT.json',dict(day=day,memory=snapshot(),healthy_workers_terminated=0,UTC=now()))
                time.sleep(5)
            run(day)


if __name__=='__main__':
    if sys.argv[1]=='seal':print(seal()['source_SHA'])
    elif sys.argv[1]=='coordinator':coordinator()
    else:run(sys.argv[1])
