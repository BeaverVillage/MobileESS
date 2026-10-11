"""One fresh representative build and short native smoke; no production reuse.

Rebuild May01 from the immutable Epoch14 input/sensitivity bundle, verify the
original FULL matrix byte identity, and replay its already verified incumbent
only as development evidence. Every new production attempt starts Native0.
"""
from pathlib import Path
from contextlib import contextmanager
from fractions import Fraction
import sys, math, time, traceback, json
import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from v42_pr134_b1.common import read, record, atomic, digest, now, sha
from v42_common_campaign.authority import source_files

OLD = Path(r'D:\v42_svr11_may_20261011_14')
DEV = Path(r'D:\v42_svr11_c3a_development_20261011')
DAY = '2025-05-01'


class MeasuredSmokeBudget:
    """Actual Runtime ledger, using the production StageBudget cap wrapper."""
    def __init__(self, path, sources):
        self.path, self.sources = path, sources
        self.calls, self.inflight, self.native_used = [], None, 0.
        self.costs = []
        self.persist()

    def used(self): return self.native_used
    def remaining(self): return max(0., 1800. - self.native_used)

    @contextmanager
    def cost(self, phase, label):
        start = time.perf_counter()
        try: yield
        finally: self.costs.append(dict(phase=phase, label=label, wall_seconds=time.perf_counter()-start))

    def persist(self):
        atomic(self.path, dict(calls=self.calls, inflight=self.inflight,
            measured_Native_Runtime=self.native_used, Native_ceiling_seconds=1800,
            development_only=True, production_results_promoted=0,
            source_SHA=digest(self.sources), costs=self.costs, UTC=now()))

    def native_optimize(self, model, callback=None, *, component, track, label, requested_seconds):
        if source_files() != self.sources: raise PermissionError('C3A_SMOKE_SOURCE_CHANGED')
        if track != 'M_FULL_MILP' or model.Params.Threads != 1:
            raise PermissionError('C3A_SMOKE_UNRESTRICTED_FULL_SCOPE_REQUIRED')
        effective = min(float(requested_seconds), self.remaining(), 60.)
        if effective <= 0: raise ValueError('C3A_SMOKE_NATIVE_CAP')
        model.Params.TimeLimit = effective
        model.Params.LogFile = str(self.path.parent/'FULL_MILP_SMOKE_NATIVE.log')
        self.inflight = dict(component=component, track=track, label=label,
            requested_seconds=requested_seconds, effective_TimeLimit=effective,
            prior_measured_Native_Runtime=self.native_used, entered_native=True,
            status='IN_FLIGHT', UTC=now())
        self.persist()
        row = self.inflight
        try:
            model.optimize(callback)
        finally:
            runtime = float(model.Runtime)
            if not math.isfinite(runtime) or runtime < 0:
                raise RuntimeError('C3A_SMOKE_UNMEASURED_RUNTIME')
            row.update(status='FINISHED', Native_Runtime=runtime, runtime_unavailable=False,
                Native_status=model.Status, finished_UTC=now())
            self.calls.append(row); self.native_used += runtime; self.inflight = None; self.persist()
        return row


def run(seconds=30.):
    if not 0 < seconds <= 60: raise ValueError('SHORT_SMOKE_ONLY')
    DEV.mkdir(parents=True, exist_ok=True)
    sources=source_files(); source_sha=digest(sources)
    attempt=DEV/'dates/B2'/DAY/'attempts/representative01'
    output=attempt/'output'
    if (DEV/'RUNTIME_SMOKE.json').exists():
        raise PermissionError('COMPLETED_DEVELOPMENT_NATIVE_NEVER_REPEATED')
    output.mkdir(parents=True, exist_ok=True)
    original=OLD/'dates/B2'/DAY/'attempts/attempt_01/output'
    folder=OLD/'inputs/B2'/DAY
    old_manifest=read(OLD/'CAMPAIGN_MANIFEST.json')
    old_identity=read(original/'SCIENTIFIC_CASE_IDENTITY.json')
    old_result=read(original.parent/'RESULT.json')
    if not old_result.get('PASS') or not old_result.get('FULL_feasible_certified'):
        raise ValueError('REPRESENTATIVE_ORIGINAL_FULL_ACTUAL_PASS_REQUIRED')
    bundle=read(folder/'NATIVE_INPUT.json')
    fixed=read(folder/'B2_FIXED_AIDC.json')
    if record(fixed['physical']['path']) != fixed['physical']:
        raise PermissionError('REPRESENTATIVE_FIXED_INPUT_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as data:
        planning={k:data[k].copy() for k in data.files}
    payload=dict(bundle=bundle,planning=planning,identity=fixed['identity'],selected_jobs=fixed['selected_jobs'])
    origins={k:record(p) for k,p in dict(manifest=OLD/'CAMPAIGN_MANIFEST.json',
        input=folder/'NATIVE_INPUT.json',fixed_input=folder/'B2_FIXED_AIDC.json',
        original_identity=original/'SCIENTIFIC_CASE_IDENTITY.json',
        original_FULL_matrix=original/'FULL_A.npz',original_FULL_data=original/'FULL_DATA.npz',
        original_incumbent=original/'BEST_STRICT_UB_POINT.npz',
        original_result=original.parent/'RESULT.json').items()}
    origins['electrical_certificate']=record(bundle['electrical_certificate']['path'])
    request=dict(root=str(DEV),arm='B2',day=DAY,attempt_id='representative01',output=str(output),
        source_SHA=source_sha,development_only=True,production_results_promoted=0)
    atomic(attempt/'request.json',request)
    def progress(value):
        atomic(attempt/'progress.json',dict(value,source_SHA=source_sha,development_only=True,UTC=now()))
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    # This isolated construction reads only unchanged electrical authorities;
    # it is never admitted to the production controller or native campaign.
    token=_active.set(old_manifest);current_authority.cache_clear()
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
        began=time.perf_counter()
        with native_zero() as native_calls:
            with original_pcs_math_scope(native,native.__file__,sha(native.__file__)):
                case=port(payload,request,progress)
        if native_calls: raise ValueError('REPRESENTATIVE_BUILD_MUST_BE_NATIVE_ZERO')
        if (case.identity['original_matrix_sha'] != old_identity['original_matrix_sha'] or
                case.identity['original_domain_sha'] != old_identity['original_domain_sha']):
            raise ValueError('REPRESENTATIVE_FRESH_ORIGINAL_MATRIX_OR_DOMAIN_SHA_DIFFERENT')
        verified=constructor.verify_case(case)
        if not verified['PASS']:raise ValueError('REPRESENTATIVE_TRANSPORT_PROOF')
        with np.load(original/'BEST_STRICT_UB_POINT.npz',allow_pickle=False) as point_data:
            point=point_data['point'].copy()
        if point.shape != (case.A.shape[1],):raise ValueError('REPRESENTATIVE_C2_COLUMN_AXIS_CHANGED')
        from v42_autonomous_b2.worker import proof_routes
        from v42_common_mess.engine import _validate,_trial
        from v42_common_mess.budget import StageBudget
        from v42_common_mess.model import memory_observation
        parent=MeasuredSmokeBudget(attempt/'NATIVE_RUNTIME_LEDGER.json',sources)
        budget=StageBudget(parent)
        validator=proof_routes(request)['final']['_strict_ub']
        strict=_validate(case,point,output/'INITIAL_DEVELOPMENT_FULL_POINT.npz',validator,budget,'ORIGINAL_POINT_NEW_EXACT_C3A_REPLAY')
        if strict is None:raise ValueError('REPRESENTATIVE_ORIGINAL_INCUMBENT_FAILED_NEW_FULL_REPLAY')
        def census(A,d):return dict(rows=A.shape[0],columns=A.shape[1],binary=int(np.count_nonzero(d['types']=='B')),nonzeros=A.nnz)
        equivalence=dict(PASS=True,source_SHA=source_sha,development_only=True,production_results_promoted=0,
            day=DAY,fresh_original_matrix_bitwise_equal=True,fresh_original_domain_bitwise_equal=True,
            original_integer_and_LP_domain_preserved=True,original_objective_preserved=True,
            original_matrix_SHA=case.identity['original_matrix_sha'],original_domain_SHA=case.identity['original_domain_sha'],
            selected_matrix_SHA=case.identity['selected_matrix_sha'],selected_domain_SHA=case.identity['selected_domain_sha'],
            original=census(case.original_A,case.original_d),before_C2=census(case.presolve.A,case.presolve.d),
            after_C3A=census(case.A,case.d),transport=verified,copy_elision=copy_proof,
            original_incumbent_FULL_recheck=record(output/'INITIAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),
            Native_optimizer_calls=0,build_wall_seconds=time.perf_counter()-began,
            memory=memory_observation(),original_evidence=origins,UTC=now())
        atomic(DEV/'ORIGINAL_EQUIVALENCE_VALIDATION.json',equivalence)
        from v42_svr11.resources import snapshot
        while True:
            memory=snapshot()
            if min(memory['RAM_available'],memory['Commit_available']) >= 6*1024**3:
                break
            progress(dict(phase='WAITING_NEW_SMOKE_MODEL_MEMORY_ADMISSION',memory=memory,
                healthy_workers_terminated=0))
            time.sleep(5)
        progress(dict(phase='SHORT_FULL_MILP_SMOKE',requested_seconds=seconds))
        point,final,row=_trial(case,budget,output/'SHORT_FULL_MILP',validator=validator,seconds=seconds,
            point=point,strict=strict,unrestricted=True,
            numeric_parameters=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-8,NumericFocus=3,ScaleFlag=2))
        final_checked=_validate(case,point,output/'FINAL_DEVELOPMENT_FULL_POINT.npz',validator,budget,'FINAL_SMOKE_FULL_REPLAY')
        if final_checked is None or Fraction(final_checked['exact_Global_UB'])>Fraction(strict['exact_Global_UB']):
            raise ValueError('REPRESENTATIVE_SMOKE_FULL_UB_REGRESSION')
        if len(parent.calls)!=1 or not parent.calls[0]['entered_native'] or parent.inflight is not None:
            raise ValueError('REPRESENTATIVE_SINGLE_COMPLETED_NATIVE_CALL_REQUIRED')
        runtime=parent.native_used
        if not math.isfinite(runtime) or runtime<=0:raise ValueError('REPRESENTATIVE_NATIVE_RUNTIME_REQUIRED')
        smoke=dict(PASS=True,source_SHA=source_sha,development_only=True,production_results_promoted=0,day=DAY,
            Native_Runtime=runtime,effective_TimeLimit=row['effective_TimeLimit'],
            cumulative_native_budget_preserved=(row['effective_TimeLimit']==min(seconds,1800.)),
            native_limit_seconds=1800,native_budget_overshoot_seconds=max(0.,runtime-seconds),
            FULL_feasible_certified=True,UB_nonregression=True,initial_UB=strict['Global_UB'],final_UB=final_checked['Global_UB'],
            original_model_identity=record(row['original_model_identity']['path']),native_ledger=record(parent.path),
            initial_FULL_certificate=record(output/'INITIAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),
            final_FULL_certificate=record(output/'FINAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),
            full_MILP_result=record(output/'SHORT_FULL_MILP/RESULT.json'),telemetry=row,memory=memory_observation(),UTC=now())
        atomic(DEV/'RUNTIME_SMOKE.json',smoke)
        if source_files()!=sources:raise PermissionError('REPRESENTATIVE_SOURCE_DRIFT_DURING_VALIDATION')
        print(json.dumps(dict(source_SHA=source_sha,counts=equivalence['after_C3A'],
            before=equivalence['before_C2'],runtime=runtime,UB=smoke['final_UB']),ensure_ascii=False))
        return smoke
    except Exception as error:
        atomic(DEV/'VALIDATION_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),source_SHA=source_sha,UTC=now()))
        raise
    finally:_active.reset(token);current_authority.cache_clear()


def _load_resumed_case(fresh, original, payload, output, memory_checkpoint=None):
    """Recover proof-bound current arrays; never build a Gurobi FULL model.

    Epoch14 C2 arrays are only used after their exact current baseline SHA,
    metadata, transport state and original FULL identity have been checked.
    If a bound-history reconstruction differs, fresh FULL CSR static presolve
    is the safe fallback. The scientific production files stay unchanged.
    """
    from scipy import sparse
    import v42_may_campaign_native90.m_model as constructor
    from v42_ultracompact.current import CurrentC3A
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_bootstrap.m1 import native_inputs
    from v42_temporal.native import load_power
    from v42_pr134_b1.native import original_coefficients_for_day
    import v42_may01.prepare as preparation
    from v42_native.contracts import digest as case_digest

    required=('FULL_A.npz','FULL_DATA.npz','C3A_A.npz','C3A_DATA.npz',
        'SCIENTIFIC_CASE_IDENTITY.json','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json',
        'CURRENT_C2_ROW_PROOFS.json','CURRENT_C3A_AXES.npz','CURRENT_C3A_ROW_CERTIFICATES.json',
        'CURRENT_C3A_BOUND_PROOFS.json','CURRENT_EXACT_C3A_PROOF.json',
        'ORIGINAL_DOMAIN_EQUIVALENCE.json','FIXED_AIDC_ANCHOR.json')
    if any(not (fresh/name).is_file() for name in required):
        raise PermissionError('RESUME_FRESH_CONSTRUCTION_NOT_COMPLETE')
    records={name:record(fresh/name) for name in required}
    raw=read(fresh/'SCIENTIFIC_CASE_IDENTITY.json');case_sha=raw.pop('case_sha')
    if case_digest(raw)!=case_sha:raise PermissionError('RESUME_FRESH_SCIENTIFIC_IDENTITY_DRIFT')
    old=read(original/'SCIENTIFIC_CASE_IDENTITY.json')
    for key in ('original_matrix_sha','original_domain_sha'):
        if raw[key]!=old[key]:raise PermissionError('RESUME_ORIGINAL_FULL_IDENTITY_CHANGED')
    full=sparse.load_npz(fresh/'FULL_A.npz');selected=sparse.load_npz(fresh/'C3A_A.npz')
    with np.load(fresh/'FULL_DATA.npz',allow_pickle=False) as z:fd={k:z[k].copy() for k in z.files}
    with np.load(fresh/'C3A_DATA.npz',allow_pickle=False) as z:sd={k:z[k].copy() for k in z.files}
    if (constructor.matrix_sha(full)!=raw['original_matrix_sha'] or constructor._domain_sha(fd)!=raw['original_domain_sha']
            or constructor.matrix_sha(selected)!=raw['selected_matrix_sha'] or constructor._domain_sha(sd)!=raw['selected_domain_sha']):
        raise PermissionError('RESUME_FRESH_FULL_OR_C3_BYTES_DRIFT')
    sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    compact=Compact(full,fd,graph[2],initial,96)
    with np.load(fresh/'CURRENT_C2_AXES.npz',allow_pickle=False) as z:
        rowids=z['rows'].copy();colids=z['columns'].copy()
    presolve=Presolve(compact.A,compact.d)
    presolve.steps=read(fresh/'CURRENT_C2_ALIASES.json');presolve.rows=read(fresh/'CURRENT_C2_ROW_PROOFS.json')
    presolve.row_ids=rowids;presolve.col_ids=colids
    reused_old_arrays=False;fallback=False
    try:
        if memory_checkpoint is not None:
            for item in (memory_checkpoint['C2_matrix'],memory_checkpoint['C2_data'],memory_checkpoint['C2_bound_history']):
                if record(item['path'])!=item:raise PermissionError('MEMORY_REFRESH_C2_CACHE_BYTES_DRIFT')
            baseline=sparse.load_npz(memory_checkpoint['C2_matrix']['path'])
            with np.load(memory_checkpoint['C2_data']['path'],allow_pickle=False) as z:bd={k:z[k].copy() for k in z.files}
        else:
            baseline=sparse.load_npz(original/'C3A_A.npz')
            with np.load(original/'C3A_DATA.npz',allow_pickle=False) as z:bd={k:z[k].copy() for k in z.files}
        proof=read(fresh/'CURRENT_EXACT_C3A_PROOF.json')
        if (constructor.matrix_sha(baseline)!=proof['baseline_matrix_SHA256']
                or not np.array_equal(bd['row_names'],compact.d['row_names'][rowids])
                or not np.array_equal(bd['names'],compact.d['names'][colids])
                or not np.array_equal(bd['types'],compact.d['types'][colids])):
            raise ValueError('RESUME_OLD_C2_NOT_BYTE_IDENTICAL_CURRENT_BASELINE')
        presolve.A,presolve.d=baseline,bd
        # Recover only the exact singleton-bound history. The persisted state
        # SHA decides acceptance; inferred history never bypasses a mismatch.
        bounds=[];definitions={int(p['column']):p for p in presolve.steps}
        for p in presolve.steps:
            j=int(p['column']);i=p['defining_row'];value=float(p['constant'])
            if (i is not None and not p['terms'] and p['kind'].startswith('FIXED')
                    and (compact.d['lower'][j]!=value or compact.d['upper'][j]!=value)):
                bounds.append(dict(column=j,name=str(compact.d['names'][j]),old_lower=float(compact.d['lower'][j]),
                    old_upper=float(compact.d['upper'][j]),new_lower=value,new_upper=value,proof='SINGLETON_EQUALITY:'+str(i)))
        csc=compact.A.tocsc()
        for k,j in enumerate(colids):
            j=int(j)
            if bd['lower'][k]==compact.d['lower'][j] and bd['upper'][k]==compact.d['upper'][j]:continue
            if bd['lower'][k]!=bd['upper'][k]:raise ValueError('RESUME_UNKNOWN_C2_BOUND_HISTORY')
            value=Fraction(float(bd['lower'][k]));candidates=[]
            for i in csc.indices[csc.indptr[j]:csc.indptr[j+1]]:
                i=int(i)
                if compact.d['sense'][i]!='=':continue
                terms,rhs=constructor._project_row(compact.A,compact.d['rhs'],i,definitions)
                if set(terms)=={j} and rhs/terms[j]==value:candidates.append(i)
            if not candidates:raise ValueError('RESUME_RETAINED_C2_BOUND_HISTORY_MISSING')
            i=min(candidates)
            bounds.append(dict(column=j,name=str(compact.d['names'][j]),old_lower=float(compact.d['lower'][j]),
                old_upper=float(compact.d['upper'][j]),new_lower=float(value),new_upper=float(value),proof='SINGLETON_EQUALITY:'+str(i)))
        presolve.bound=(read(memory_checkpoint['C2_bound_history']['path']) if memory_checkpoint is not None
            else sorted(bounds,key=lambda p:int(p['proof'].split(':',1)[1])))
        if constructor._transport_state_sha(compact,presolve,graph)!=raw['transport_authority']['state_sha']:
            raise ValueError('RESUME_C2_RECONSTRUCTION_STATE_SHA_MISMATCH')
        reused_old_arrays=True
    except (ValueError,KeyError,OSError):
        # One sparse static reconstruction from the *fresh* FULL arrays. No
        # native model construction, optimizer, FULL assignment enumeration or
        # OpenDSS solve is repeated here.
        del presolve
        presolve=Presolve(compact.A,compact.d);presolve.run();fallback=True
        if constructor._transport_state_sha(compact,presolve,graph)!=raw['transport_authority']['state_sha']:
            raise PermissionError('RESUME_REBUILT_FRESH_C2_STATE_SHA_MISMATCH')
    with np.load(fresh/'CURRENT_C3A_AXES.npz',allow_pickle=False) as z:retained=z['rows'].copy();columns=z['columns'].copy()
    if not np.array_equal(columns,np.arange(selected.shape[1])):raise PermissionError('RESUME_C3_COLUMN_AXIS_DRIFT')
    ultra=CurrentC3A(presolve.A,presolve.d,selected,sd,retained,
        read(fresh/'CURRENT_C3A_ROW_CERTIFICATES.json'),read(fresh/'CURRENT_C3A_BOUND_PROOFS.json'),
        read(fresh/'CURRENT_EXACT_C3A_PROOF.json'),full,fd)
    cert,_,_,_=load_power(payload['bundle']);coeff=original_coefficients_for_day(preparation,cert,DAY)
    case=constructor.CampaignMCase(selected,sd,full,fd,None,graph,case_sha,raw,compact,presolve,
        payload['bundle'],read(fresh/'FIXED_AIDC_ANCHOR.json'),payload['planning'],coeff,fresh,ultra)
    if memory_checkpoint is None:
        verified=constructor.verify_case(case)
        if verified.get('PASS') is not True:raise PermissionError('RESUME_CURRENT_SOURCE_TRANSPORT_AND_C3_PROOF_FAILED')
    else:
        _verify_memory_delete_source(case,memory_checkpoint)
    return case,dict(PASS=True,fresh_artifacts=records,original_FULL_bytes_equal=True,
        source_proof_fingerprints_rechecked=True,all_C2_and_C3_state_SHAs_rechecked=True,
        old_C2_arrays_reused_only_after_exact_current_state_SHA=reused_old_arrays,
        fresh_FULL_static_presolve_fallback=fallback,Gurobi_FULL_models_rebuilt=0,Native_optimizer_calls=0)


DELETE_NAMES=('src','keys','vectors','constants','times','defs','_','cache','dom','pairs','eligible')

def _verify_memory_delete_source(case, checkpoint):
    """Admit exactly one Delete statement, with the old producer archived.

    This is a development transition proof, not permission to replace producer
    fingerprints generally. Every other mathematical source remains exact.
    """
    import ast,copy
    import v42_may_campaign_native90.m_model as constructor
    archive=checkpoint['producer_source_before_delete']
    if record(archive['path'])!=archive:raise PermissionError('MEMORY_REFRESH_ARCHIVED_PRODUCER_DRIFT')
    old=ast.parse(Path(archive['path']).read_text(encoding='utf-8-sig'))
    new=ast.parse((SOURCE/'v42_ultracompact/current.py').read_text(encoding='utf-8-sig'))
    definitions=[n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='reduce_current_c3a']
    if len(definitions)!=1:raise PermissionError('MEMORY_REFRESH_PRODUCER_FUNCTION_DRIFT')
    body=definitions[0].body;deletes=[(i,n) for i,n in enumerate(body) if isinstance(n,ast.Delete)]
    if len(deletes)!=1:raise PermissionError('MEMORY_REFRESH_EXACTLY_ONE_DELETE_REQUIRED')
    index,node=deletes[0]
    if tuple(n.id for n in node.targets if isinstance(n,ast.Name))!=DELETE_NAMES or len(node.targets)!=len(DELETE_NAMES):
        raise PermissionError('MEMORY_REFRESH_DELETE_TARGETS_DRIFT')
    if (index+1>=len(body) or not isinstance(body[index+1],ast.ImportFrom)
            or body[index+1].module!='current_verify' or body[index+1].level!=1):
        raise PermissionError('MEMORY_REFRESH_DELETE_POSITION_DRIFT')
    del body[index]
    if ast.dump(old,include_attributes=False)!=ast.dump(new,include_attributes=False):
        raise PermissionError('MEMORY_REFRESH_NON_DELETE_SCIENTIFIC_SOURCE_CHANGE')
    authority=case.identity['c3_authority']
    producer='v42_ultracompact/current.py'
    if authority['sources'][producer]['sha256']!=archive['sha256']:
        raise PermissionError('MEMORY_REFRESH_OLD_PRODUCER_NOT_PROOF_BOUND')
    for name,item in authority['sources'].items():
        if name!=producer and sha(SOURCE/name)!=item['sha256']:raise PermissionError('MEMORY_REFRESH_OTHER_C3_SOURCE_CHANGED:'+name)
    transport=case.identity['transport_authority']
    if any(sha(SOURCE/name)!=item['sha256'] for name,item in transport['sources'].items()):
        raise PermissionError('MEMORY_REFRESH_ORIGINAL_TRANSPORT_SOURCE_CHANGED')
    for auth in (transport,authority):
        if record(auth['certificate']['path'])!=auth['certificate']:raise PermissionError('MEMORY_REFRESH_ORIGINAL_PROOF_PACKET_DRIFT')
    if (constructor._transport_state_sha(case.compact,case.presolve,case.graph)!=transport['state_sha']
            or constructor._c3_state_sha(case.ultra)!=authority['state_sha']
            or read(authority['certificate']['path'])!=authority['proof']):
        raise PermissionError('MEMORY_REFRESH_ORIGINAL_FULL_C2_C3_STATE_DRIFT')
    if any(record(item['path'])!=item for item in checkpoint['fresh_artifacts'].values()):
        raise PermissionError('MEMORY_REFRESH_ORIGINAL_ARTIFACT_CHANGED')
    return dict(PASS=True,AST_identical_after_removing_single_unused_temporary_Delete=True,
        deleted_names=list(DELETE_NAMES),producer_before=archive,
        producer_after=record(SOURCE/producer),other_mathematical_sources_unchanged=True)


def prepare_memory_refresh():
    """Record and verify the old proof-bound case before changing its producer."""
    from scipy import sparse
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    construction=DEV/'dates/B2'/DAY/'attempts/representative01';fresh=construction/'output'
    previous=construction/'NATIVE_RUNTIME_LEDGER.json';prior=read(previous)
    if prior.get('calls') or prior.get('inflight') is not None or prior.get('measured_Native_Runtime')!=0:
        raise PermissionError('MEMORY_REFRESH_ORIGINAL_NATIVE0_REQUIRED')
    construction_request=read(construction/'request.json')
    if prior['source_SHA']!=construction_request['source_SHA']:raise PermissionError('MEMORY_REFRESH_ORIGINAL_NATIVE0_SOURCE_DRIFT')
    original=OLD/'dates/B2'/DAY/'attempts/attempt_01/output';folder=OLD/'inputs/B2'/DAY
    manifest=read(OLD/'CAMPAIGN_MANIFEST.json');bundle=read(folder/'NATIVE_INPUT.json');fixed=read(folder/'B2_FIXED_AIDC.json')
    if record(fixed['physical']['path'])!=fixed['physical']:raise PermissionError('MEMORY_REFRESH_FIXED_INPUT_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as z:planning={k:z[k].copy() for k in z.files}
    payload=dict(bundle=bundle,planning=planning,identity=fixed['identity'],selected_jobs=fixed['selected_jobs'])
    cache=DEV/'memory_refresh_inputs';cache.mkdir(parents=True,exist_ok=True)
    path=cache/'CHECKPOINT.json'
    if path.exists():raise PermissionError('MEMORY_REFRESH_CHECKPOINT_ALREADY_RECORDED')
    token=_active.set(manifest);current_authority.cache_clear()
    try:
        case,recovery=_load_resumed_case(fresh,original,payload,fresh)
        archived=cache/'current.before_delete.py'
        archived.write_bytes((SOURCE/'v42_ultracompact/current.py').read_bytes())
        sparse.save_npz(cache/'FRESH_VERIFIED_C2_A.npz',case.presolve.A)
        np.savez_compressed(cache/'FRESH_VERIFIED_C2_DATA.npz',**case.presolve.d)
        atomic(cache/'FRESH_VERIFIED_C2_BOUND_HISTORY.json',case.presolve.bound)
        checkpoint=dict(PASS=True,Native_optimizer_calls=0,original_construction_source_SHA=construction_request['source_SHA'],
            original_case_SHA=case.case_sha,original_identity=record(fresh/'SCIENTIFIC_CASE_IDENTITY.json'),
            original_native0_ledger=record(previous),producer_source_before_delete=record(archived),
            C2_matrix=record(cache/'FRESH_VERIFIED_C2_A.npz'),C2_data=record(cache/'FRESH_VERIFIED_C2_DATA.npz'),
            C2_bound_history=record(cache/'FRESH_VERIFIED_C2_BOUND_HISTORY.json'),fresh_artifacts=recovery['fresh_artifacts'],
            original_case_current_source_verification=case.identity['transport'],recovery=recovery,
            development_only=True,production_results_promoted=0,UTC=now())
        atomic(path,checkpoint)
        print(json.dumps(dict(PASS=True,checkpoint=record(path),Native_optimizer_calls=0),ensure_ascii=False))
        return checkpoint
    finally:_active.reset(token);current_authority.cache_clear()


def resume(seconds=30., refresh_memory=False):
    """Run one final-source smoke after an earlier construction stayed Native0."""
    if not 0<seconds<=60:raise ValueError('SHORT_SMOKE_ONLY')
    sources=source_files();source_sha=digest(sources)
    construction=DEV/'dates/B2'/DAY/'attempts/representative01';fresh=construction/'output'
    previous=construction/'NATIVE_RUNTIME_LEDGER.json'
    if (DEV/'RUNTIME_SMOKE.json').exists():raise PermissionError('COMPLETED_DEVELOPMENT_NATIVE_NEVER_REPEATED')
    if not previous.is_file():raise PermissionError('RESUME_PREVIOUS_NATIVE0_LEDGER_REQUIRED')
    prior=read(previous)
    if prior.get('calls') or prior.get('inflight') is not None or prior.get('measured_Native_Runtime')!=0:
        raise PermissionError('RESUME_PRIOR_ATTEMPT_MUST_BE_NATIVE0')
    prior_receipt=record(previous);construction_request=read(construction/'request.json')
    if prior.get('source_SHA')!=construction_request['source_SHA']:
        raise PermissionError('RESUME_PREVIOUS_LEDGER_CONSTRUCTION_SOURCE_DRIFT')
    original=OLD/'dates/B2'/DAY/'attempts/attempt_01/output';folder=OLD/'inputs/B2'/DAY
    old_manifest=read(OLD/'CAMPAIGN_MANIFEST.json');bundle=read(folder/'NATIVE_INPUT.json');fixed=read(folder/'B2_FIXED_AIDC.json')
    if record(fixed['physical']['path'])!=fixed['physical']:raise PermissionError('RESUME_FIXED_INPUT_SHA_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as z:planning={k:z[k].copy() for k in z.files}
    payload=dict(bundle=bundle,planning=planning,identity=fixed['identity'],selected_jobs=fixed['selected_jobs'])
    attempt_id='representative_memory_final01' if refresh_memory else 'representative_final_source01'
    attempt=DEV/'dates/B2'/DAY/'attempts'/attempt_id;output=attempt/'output'
    if (attempt/'NATIVE_RUNTIME_LEDGER.json').exists():raise PermissionError('RESUME_NEW_LEDGER_ALREADY_EXISTS')
    output.mkdir(parents=True,exist_ok=True)
    request=dict(root=str(DEV),arm='B2',day=DAY,attempt_id=attempt_id,output=str(output),
        source_SHA=source_sha,construction_source_SHA=construction_request['source_SHA'],development_only=True,production_results_promoted=0)
    atomic(attempt/'request.json',request)
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    token=_active.set(old_manifest);current_authority.cache_clear()
    try:
        checkpoint=read(DEV/'memory_refresh_inputs/CHECKPOINT.json') if refresh_memory else None
        if checkpoint is not None and (checkpoint['original_native0_ledger']!=prior_receipt
                or checkpoint['original_construction_source_SHA']!=construction_request['source_SHA']):
            raise PermissionError('MEMORY_REFRESH_CHECKPOINT_NATIVE0_BINDING_DRIFT')
        case,recovery=_load_resumed_case(fresh,original,payload,output,checkpoint)
        refreshed_memory=None
        if refresh_memory:
            import v42_may_campaign_native90.m_model as constructor
            from v42_ultracompact.current import reduce_current_c3a,POLICY
            from v42_common_mess.model import memory_observation
            from v42_native.contracts import digest as case_digest
            semantic=_verify_memory_delete_source(case,checkpoint)
            old_identity=dict(case.identity);old_ultra=case.ultra;old_case_sha=case.case_sha
            memory_before=memory_observation();began=time.perf_counter()
            ultra=reduce_current_c3a(case.presolve.A,case.presolve.d,case.graph,
                lambda value:atomic(attempt/'progress.json',dict(value,source_SHA=source_sha,UTC=now())),
                physical_original=(case.original_A,case.original_d))
            if (constructor.matrix_sha(ultra.A)!=old_identity['selected_matrix_sha']
                    or constructor._domain_sha(ultra.d)!=old_identity['selected_domain_sha']
                    or digest(ultra.certificates)!=digest(old_ultra.certificates)
                    or digest(ultra.bounds)!=digest(old_ultra.bounds)):
                raise PermissionError('MEMORY_REFRESH_SELECTED_C3_MATRIX_DOMAIN_OR_PROOF_CHANGED')
            memory_after=memory_observation()
            refreshed_memory=dict(before=memory_before,after=memory_after,
                measured_process_peak_private_commit_bytes=memory_after['peak_private_commit_bytes'],
                measured_process_peak_RSS_bytes=memory_after['peak_RSS_bytes'],
                preparation_wall_seconds=time.perf_counter()-began,producer_temporaries_released_before_independent_verifier=True)
            c3_authority=constructor._freeze_c3(ultra,output)
            merged=dict(old_identity['transport'],C3A_policy=POLICY,
                selected_C3A_independent_proof_PASS=ultra.proof['PASS'],
                selected_C3A_rows_removed=ultra.proof['removed_rows'],selected_C3A_bounds_tightened=ultra.proof['bounds_tightened'],
                selected_C3A_original_P1_bit_exact=ultra.proof['original_P1_bit_exact'],
                selected_C3A_integer_and_full_LP_domains_identical=ultra.proof['integer_and_full_LP_domains_identical'])
            transport=constructor._freeze_transport(case.compact,case.presolve,case.graph,merged,output)
            case.identity=dict(old_identity,transport=merged,transport_authority=transport,c3_authority=c3_authority,
                C2_size=ultra.proof['baseline'],C3A_size=ultra.proof['selected'])
            case.A,case.d,case.ultra,case.output=ultra.A,ultra.d,ultra,output
            case.case_sha=case_digest(case.identity)
            atomic(output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
            atomic(output/'FIXED_AIDC_ANCHOR.json',case.anchor)
            verified=constructor.verify_case(case)
            if verified.get('PASS') is not True:raise PermissionError('MEMORY_REFRESH_FINAL_CASE_PROOF_FAILED')
            equality=dict(PASS=True,source_SHA=source_sha,construction_source_SHA=construction_request['source_SHA'],
                original_case_SHA=old_case_sha,refreshed_case_SHA=case.case_sha,
                selected_matrix_bitwise_equal=True,selected_domain_bitwise_equal=True,
                all_removed_row_certificates_identical=True,all_bound_certificates_identical=True,
                mathematical_source_transition=semantic,old_native0_ledger=prior_receipt,
                original_construction_proof=record(fresh/'CURRENT_EXACT_C3A_PROOF.json'),
                refreshed_exact_reduction_proof=record(output/'CURRENT_EXACT_C3A_PROOF.json'),
                refreshed_preparation_memory=refreshed_memory,Native_optimizer_calls=0,
                Gurobi_FULL_models_rebuilt=0,development_only=True,production_results_promoted=0,UTC=now())
            atomic(output/'MEMORY_REFRESH_EQUALITY.json',equality)
            recovery=dict(recovery,memory_Delete_only_refresh=record(output/'MEMORY_REFRESH_EQUALITY.json'))
        # Keep original construction attribution immutable. This receipt names
        # the final-source reuse verification and separate native execution.
        atomic(attempt/'FRESH_STATE_RECOVERY.json',dict(recovery,source_SHA=source_sha,
            construction_source_SHA=construction_request['source_SHA'],prior_native0_ledger=prior_receipt,UTC=now()))
        from v42_autonomous_b2.worker import proof_routes
        from v42_common_mess.engine import _validate,_trial
        from v42_common_mess.budget import StageBudget
        from v42_common_mess.model import memory_observation
        parent=MeasuredSmokeBudget(attempt/'NATIVE_RUNTIME_LEDGER.json',sources);budget=StageBudget(parent)
        validator=proof_routes(request)['final']['_strict_ub']
        with np.load(original/'BEST_STRICT_UB_POINT.npz',allow_pickle=False) as z:point=z['point'].copy()
        strict=_validate(case,point,output/'INITIAL_DEVELOPMENT_FULL_POINT.npz',validator,budget,'FINAL_SOURCE_ORIGINAL_POINT_FULL_REPLAY')
        if strict is None:raise ValueError('RESUME_ORIGINAL_INCUMBENT_FULL_RECHECK_FAILED')
        equivalence=read(DEV/'ORIGINAL_EQUIVALENCE_VALIDATION.json')
        if (equivalence.get('source_SHA')!=construction_request['source_SHA']
                or equivalence['original_matrix_SHA']!=case.identity['original_matrix_sha']
                or equivalence['selected_matrix_SHA']!=case.identity['selected_matrix_sha']):
            raise PermissionError('RESUME_ORIGINAL_CONSTRUCTION_EQUIVALENCE_BINDING_DRIFT')
        final_equivalence=dict(equivalence,source_SHA=source_sha,construction_source_SHA=construction_request['source_SHA'],
            original_construction_validation=record(DEV/'ORIGINAL_EQUIVALENCE_VALIDATION.json'),
            prior_native0_ledger=prior_receipt,resume_recovery=recovery,
            original_incumbent_FULL_recheck=record(output/'INITIAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),UTC=now())
        final_equivalence['exact_reduction_proof']=record(case.output/'CURRENT_EXACT_C3A_PROOF.json')
        if refresh_memory:
            final_equivalence.update(transport=constructor.verify_case(case),refreshed_case_SHA=case.case_sha,
                original_construction_memory=equivalence['memory'],refreshed_C3A_preparation_memory=refreshed_memory,
                memory=refreshed_memory['after'],memory_Delete_only_equality=record(output/'MEMORY_REFRESH_EQUALITY.json'))
        atomic(DEV/'ORIGINAL_EQUIVALENCE_VALIDATION_FINAL_SOURCE.json',final_equivalence)
        from v42_svr11.resources import snapshot
        while True:
            memory=snapshot()
            if min(memory['RAM_available'],memory['Commit_available'])>=6*1024**3:break
            atomic(attempt/'progress.json',dict(phase='WAITING_NEW_SMOKE_MODEL_MEMORY_ADMISSION',memory=memory,healthy_workers_terminated=0,UTC=now()))
            time.sleep(5)
        if any(record(item['path'])!=item for item in recovery['fresh_artifacts'].values()):
            raise PermissionError('RESUME_FRESH_ARTIFACT_CHANGED_AFTER_RECOVERY')
        point,final,row=_trial(case,budget,output/'SHORT_FULL_MILP',validator=validator,seconds=seconds,
            point=point,strict=strict,unrestricted=True,
            numeric_parameters=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-8,NumericFocus=3,ScaleFlag=2))
        checked=_validate(case,point,output/'FINAL_DEVELOPMENT_FULL_POINT.npz',validator,budget,'FINAL_SOURCE_SMOKE_FULL_REPLAY')
        if checked is None or Fraction(checked['exact_Global_UB'])>Fraction(strict['exact_Global_UB']):raise ValueError('RESUME_SMOKE_UB_REGRESSION')
        if len(parent.calls)!=1 or not parent.calls[0]['entered_native'] or parent.inflight is not None or parent.native_used<=0:
            raise ValueError('RESUME_SINGLE_COMPLETED_NATIVE_SMOKE_REQUIRED')
        if source_files()!=sources or record(previous)!=prior_receipt:raise PermissionError('RESUME_SOURCE_OR_PREVIOUS_NATIVE0_LEDGER_DRIFT')
        smoke=dict(PASS=True,source_SHA=source_sha,native_execution_source_SHA=source_sha,
            construction_source_SHA=construction_request['source_SHA'],development_only=True,production_results_promoted=0,day=DAY,
            Native_Runtime=parent.native_used,effective_TimeLimit=row['effective_TimeLimit'],
            cumulative_native_budget_preserved=row['effective_TimeLimit']==min(seconds,1800.),native_limit_seconds=1800,
            native_budget_overshoot_seconds=max(0.,parent.native_used-seconds),FULL_feasible_certified=True,UB_nonregression=True,
            initial_UB=strict['Global_UB'],final_UB=checked['Global_UB'],original_model_identity=record(row['original_model_identity']['path']),
            native_ledger=record(parent.path),prior_native0_ledger=prior_receipt,
            initial_FULL_certificate=record(output/'INITIAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),
            final_FULL_certificate=record(output/'FINAL_DEVELOPMENT_FULL_POINT.REPLAY.json'),
            full_MILP_result=record(output/'SHORT_FULL_MILP/RESULT.json'),telemetry=row,memory=memory_observation(),
            final_source_equivalence=record(DEV/'ORIGINAL_EQUIVALENCE_VALIDATION_FINAL_SOURCE.json'),UTC=now())
        atomic(DEV/'RUNTIME_SMOKE.json',smoke)
        print(json.dumps(dict(source_SHA=source_sha,construction_source_SHA=construction_request['source_SHA'],Native_Runtime=parent.native_used,UB=checked['Global_UB'])))
        return smoke
    except Exception as error:
        atomic(attempt/'RESUME_VALIDATION_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),source_SHA=source_sha,UTC=now()))
        raise
    finally:_active.reset(token);current_authority.cache_clear()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--prepare-memory-refresh':prepare_memory_refresh()
    elif len(sys.argv)>1 and sys.argv[1]=='--refresh-memory':resume(float(sys.argv[2]) if len(sys.argv)>2 else 30.,True)
    elif len(sys.argv)>1 and sys.argv[1]=='--resume':resume(float(sys.argv[2]) if len(sys.argv)>2 else 30.)
    else:run(float(sys.argv[1]) if len(sys.argv)>1 else 30.)
