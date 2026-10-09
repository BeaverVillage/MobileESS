"""Restricted-master Presolve0/current-start adapter; single30s solve retained.

Reuse the unchanged ExactRowModel and its raw-model scope/row/Pi transport.
The original budget remains the sole Runtime recorder and Native delegate.
This candidate has no lower-bound authority or performance qualification.
"""
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import math
import inspect
import weakref
import sys

import numpy as np
from v42_autonomous_b2 import dw_native
from v42_m1_hybrid import dw
from v42_b2_seed_recovery_v19 import budget as original_budget
from v42_b2_seed_recovery_v19 import execution as original_execution,numerical
from v42_autonomous_b2.worker import ReceiptDateBudget
from v42_autonomous_b2 import worker as deployment
import gurobipy as gp
from v42_may_campaign_native90 import execution
from v42_may_campaign_native90.a_routing import rebound

_ORIGINAL_BUILD=dw.build_master
_ORIGINAL_RUN=dw.run
_ORIGINAL_NATIVE_OPTIMIZE=original_budget.DateBudget.native_optimize
_ORIGINAL_RECEIPT_OPTIMIZE=ReceiptDateBudget.optimize
_ORIGINAL_INHERITED_OPTIMIZE=original_budget.OriginalBudget.optimize
_ORIGINAL_EXACT_OPTIMIZE=dw_native.ExactRowModel.optimize
_ORIGINAL_SCOPE=execution.native_scope
_ORIGINAL_SCOPE_GENERATOR=execution.native_scope.__wrapped__
_SCOPE_CLOSURE=tuple(cell.cell_contents for cell in _ORIGINAL_SCOPE.__closure__ or ())
_ORIGINAL_CURRENT=execution.current
_ORIGINAL_AUTHORIZE=execution.authorize
_ORIGINAL_GUARD=original_execution.guard
_ORIGINAL_PRECISION=numerical.set_precision
_RAW_MODEL_TYPE=gp.Model
_RAW_OPTIMIZE=inspect.getattr_static(gp.Model,'optimize')
_RAW_CODE=getattr(_RAW_OPTIMIZE,'__code__',None)
_ROOT=Path(__file__).resolve().parents[1]
_SOURCE_FUNCTION=deployment.sources
_REQUEST_VERIFIER=deployment.verify_request
_SOURCE_DIGEST=deployment.digest
_CODE_BINDINGS=tuple((f,f.__code__) for f in (
    _ORIGINAL_BUILD,_ORIGINAL_RUN,_ORIGINAL_NATIVE_OPTIMIZE,
    _ORIGINAL_RECEIPT_OPTIMIZE,_ORIGINAL_INHERITED_OPTIMIZE,_ORIGINAL_EXACT_OPTIMIZE,_ORIGINAL_SCOPE,_ORIGINAL_SCOPE_GENERATOR,
    _ORIGINAL_CURRENT,_ORIGINAL_AUTHORIZE,_ORIGINAL_GUARD,_ORIGINAL_PRECISION,
    dw.matrix_replay,dw.verify_decomposition,dw.sha,dw.vector_sha,
    _SOURCE_FUNCTION,_REQUEST_VERIFIER,_SOURCE_DIGEST))
_HELPERS=tuple((key,_ORIGINAL_BUILD.__globals__[key])
               for key in ('matrix_replay','verify_decomposition','sha','vector_sha'))
_ENTRY=ContextVar('V42_B2_RMP_PRESOLVE_ENTRY_V30',default=None)
PRECISION=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,NumericFocus=3,ScaleFlag=2)
LABEL='ONE_RESTRICTED_MASTER'


def _record(path):
    path=Path(path).resolve();h=sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):h.update(chunk)
    return dict(path=str(path),sha256=h.hexdigest(),bytes=path.stat().st_size)


def _read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def _method(obj,key,descriptor):
    bound=getattr(obj,key)
    if (getattr(bound,'__self__',None) is not obj
            or getattr(bound,'__func__',None) is not descriptor):
        raise PermissionError('RMP_PRESOLVE_OWN_ORIGINAL_DELEGATE_REQUIRED:'+key)


def _delegates(model,budget):
    if (any(f.__code__ is not code for f,code in _CODE_BINDINGS)
            or any(getattr(owner,key) is not f or f.__code__ is not code
                   for owner,key,f,code in _WARM_BINDINGS)):
        raise PermissionError('RMP_PRESOLVE_IMMUTABLE_ORIGINAL_CODE_REQUIRED')
    aliases=(
        (original_budget.DateBudget,'native_optimize',_ORIGINAL_NATIVE_OPTIMIZE),
        (ReceiptDateBudget,'optimize',_ORIGINAL_RECEIPT_OPTIMIZE),
        (original_budget.OriginalBudget,'optimize',_ORIGINAL_INHERITED_OPTIMIZE),
        (dw_native.ExactRowModel,'optimize',_ORIGINAL_EXACT_OPTIMIZE),
        (execution,'native_scope',_ORIGINAL_SCOPE),(execution,'current',_ORIGINAL_CURRENT),
        (execution,'authorize',_ORIGINAL_AUTHORIZE),(numerical,'set_precision',_ORIGINAL_PRECISION),
        *tuple((dw,key,value) for key,value in _HELPERS))
    if any(getattr(owner,key) is not expected for owner,key,expected in aliases):
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_SCOPE_OR_DELEGATE_ALIAS_DRIFT')
    if (type(budget) is not ReceiptDateBudget
            or _ORIGINAL_SCOPE.__wrapped__ is not _ORIGINAL_SCOPE_GENERATOR
            or tuple(cell.cell_contents for cell in _ORIGINAL_SCOPE.__closure__ or ())!=_SCOPE_CLOSURE):
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_BUDGET_OR_SCOPE_CLOSURE_DRIFT')
    globals_required=((_ORIGINAL_NATIVE_OPTIMIZE.__globals__,'native_scope',_ORIGINAL_SCOPE),
        (_ORIGINAL_NATIVE_OPTIMIZE.__globals__,'guard',_ORIGINAL_GUARD),
        (_ORIGINAL_GUARD.__globals__,'current',_ORIGINAL_CURRENT),
        (_ORIGINAL_GUARD.__globals__,'authorize',_ORIGINAL_AUTHORIZE),
        (_ORIGINAL_SCOPE_GENERATOR.__globals__,'authorize',_ORIGINAL_AUTHORIZE))
    if any(ns.get(key) is not expected for ns,key,expected in globals_required):
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_GUARD_GLOBALS_DRIFT')
    if type(model) is not _APPROVED_WRAPPER_TYPE or type(model._model) is not _RAW_MODEL_TYPE:
        raise PermissionError('RMP_PRESOLVE_EXACT_OWNED_MODEL_TYPES_REQUIRED')
    if (inspect.getattr_static(type(model),'optimize') is not _WRAPPER_OPTIMIZE
            or inspect.getattr_static(type(model._model),'optimize') is not _RAW_OPTIMIZE
            or _WRAPPER_OPTIMIZE.__code__ is not _WRAPPER_CODE
            or getattr(_RAW_OPTIMIZE,'__code__',None) is not _RAW_CODE):
        raise PermissionError('RMP_PRESOLVE_MODEL_OPTIMIZE_DESCRIPTOR_DRIFT')
    _method(model,'optimize',_WRAPPER_OPTIMIZE)
    _method(model._model,'optimize',_RAW_OPTIMIZE)
    _method(budget,'optimize',_ORIGINAL_RECEIPT_OPTIMIZE)
    _method(budget,'native_optimize',_ORIGINAL_NATIVE_OPTIMIZE)


class RunBinding:
    def __init__(self,run,build,wrapper,write):
        self.functions=tuple((f,f.__code__) for f in (run,build,wrapper))
        self.closures=tuple((f,tuple(c.cell_contents for c in f.__closure__ or ()))
                            for f in (run,build,wrapper))
        self.aliases=((run.__globals__,'build_master',wrapper),(run.__globals__,'write',write),
            *tuple((build.__globals__,key,function) for key,function in _HELPERS),
            *tuple((build.__globals__,key,build.__globals__[key])
                   for key in ('output_directory','write')))
        self.model_factory=build.__globals__['gp'];self.model_type=self.model_factory.Model
        self.warm_records=weakref.WeakKeyDictionary()
    def register_warm(self,model,plan):
        self.warm_records[model]=(weakref.ref(plan),plan.seal())
    def warm(self,model):
        recorded=self.warm_records.get(model)
        plan=getattr(model,'_rmp_warm_plan',None)
        if recorded is None or type(plan) is not WarmPlan or recorded[0]() is not plan:
            raise PermissionError('RMP_WARM_OWN_ORIGINAL_BUILD_PLAN_REQUIRED')
        for key in ('seal','verify','install'):_method(plan,key,_WARM_METHODS[key])
        plan.verify(recorded[1]);return plan
    def verify(self):
        _method(self,'warm',_RUN_WARM)
        _method(self,'register_warm',_RUN_REGISTER_WARM)
        if (any(f.__code__ is not code for f,code in self.functions)
                or any(ns.get(key) is not value for ns,key,value in self.aliases)
                or any(tuple(c.cell_contents for c in f.__closure__ or ())!=values for f,values in self.closures)
                or self.model_factory.Model is not self.model_type
                or self.functions[1][0].__globals__.get('gp') is not self.model_factory):
            raise PermissionError('RMP_PRESOLVE_ORIGINAL_REBOUND_CODE_OR_HELPER_DRIFT')


def _matrix_sha(matrix):
    matrix=matrix.tocsr();h=sha256(str(matrix.shape).encode())
    for key in ('indptr','indices','data'):
        array=np.ascontiguousarray(getattr(matrix,key));h.update(array.dtype.str.encode());h.update(memoryview(array).cast('B'))
    return h.hexdigest()


def _array_sha(value):
    array=np.ascontiguousarray(value);h=sha256(str(array.shape).encode())
    h.update(array.dtype.str.encode());h.update(array.tobytes());return h.hexdigest()


def _case_sha(case,decomp):
    # The hint belongs to this live case/decomposition, never a past point.
    h=sha256(_matrix_sha(case.A).encode())
    for key in ('names','lower','upper','types','objective','rhs','sense','row_names','constant'):
        h.update(key.encode());h.update(_array_sha(np.asarray(case.d[key])).encode())
    for block in (*decomp.units.values(),decomp.nonunit_block):
        h.update(str(block.unit).encode());h.update(_matrix_sha(block.A).encode())
        for key in ('original_rows','original_columns'):
            h.update(_array_sha(getattr(block,key)).encode())
        for key in ('names','lower','upper','types','objective','rhs','sense','row_names','constant'):
            h.update(_array_sha(np.asarray(block.d[key])).encode())
    h.update(_array_sha(decomp.coupling_rows).encode())
    h.update(_array_sha(decomp.column_owner).encode())
    return h.hexdigest()


def _point(case):
    value=getattr(case,'point',None)
    if value is None:return None
    try:return np.asarray(value,dtype=np.float64).copy()
    except (TypeError,ValueError):return None


def _residual(matrix,rhs,sense,point):
    residual=np.asarray(matrix@point,dtype=np.float64)-rhs
    if not np.isfinite(residual).all():return dict(finite=False)
    violation=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
    return dict(finite=True,residual_sha256=_array_sha(residual),
        maximum_absolute_residual=float(np.max(abs(residual),initial=0)),
        maximum_row_violation=max(0.,float(np.max(violation,initial=0))))


class WarmPlan:
    """Current original seed projection, exclusively a model-local LP hint."""
    def __init__(self,case,decomp,result,point,case_structure,request,output):
        self.case=case;self.decomp=decomp;self.model=result[0];self.identity=result[3]
        self.request=copy.deepcopy(request);self.case_structure=case_structure
        self.case_identity=(case.case_sha,decomp.case_sha)
        self.point=point;self.point_sha=None if point is None else _array_sha(point)
        self.identity_sha=sha256(json.dumps(self.identity,sort_keys=True,allow_nan=False).encode()).hexdigest()
        self.pstart=None;self.dstart=None;self.seed_receipts=[]
        self.original_lpwarmstart=int(self.model.Params.LPWarmStart)
        self.original_crossover=int(self.model.Params.Crossover)
        self.diagnostic=dict(eligible=False,reason='CURRENT_FULL_POINT_MISSING_PARTIAL_OR_NONFINITE',
            original_method=1,computational_zero_DStart_is_Native_Pi=False,
            start_is_basis_or_feasibility_or_dual_or_UB_or_Global_LB_authority=False,
            Native_after_start_setters_or_updates_allowed=False,
            owned_model_disposed_by_original_run_finally=True)
        current=_point(case)
        if (_case_sha(case,decomp)!=case_structure or case.case_sha!=decomp.case_sha
                or (point is None)!=(current is None)
                or point is not None and _array_sha(current)!=self.point_sha):
            raise PermissionError('RMP_WARM_CURRENT_BUILD_CASE_OR_POINT_DRIFT')
        if point is not None:point.flags.writeable=False
        if (point is not None and point.shape==(case.A.shape[1],) and np.isfinite(point).all()
                and not np.any(point==gp.GRB.UNDEFINED)
                and np.isfinite(case.A@point).all()):
            replay=dw.matrix_replay(case.A,case.d,point,tolerance=1e-9,
                bound_tolerance=1e-9,integer_tolerance=0.)
            self.diagnostic.update(current_full_matrix_replay=replay,current_point_sha256=self.point_sha)
            if not (replay['PASS'] and replay['integer_pattern_exact'] and replay['exact_binary_0_1']):
                self.diagnostic['reason']='CURRENT_FULL_POINT_NOT_STRICTLY_REPLAYED_COLD_ORIGINAL_METHOD1'
            else:
                nonunit=np.asarray(decomp.nonunit_columns)
                rows=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
                identity=self.identity;catalog=identity['catalog'];n=len(nonunit)
                if (identity.get('PASS') is not True or identity['case_sha']!=case.case_sha
                        or not np.array_equal(identity['nonunit_columns'],nonunit)
                        or not np.array_equal(identity['source_rows'],rows)
                        or identity['columns']!=n+len(catalog)
                        or identity['rows']!=len(rows)+4):
                    raise PermissionError('RMP_WARM_ORIGINAL_CATALOG_AXES_DRIFT')
                primal=np.r_[point[nonunit],np.zeros(len(catalog))]
                for unit,block in decomp.units.items():
                    positions=[j for j,item in enumerate(catalog) if item['unit']==unit]
                    if not positions:raise PermissionError('RMP_WARM_OWN_CURRENT_SEED_MISSING')
                    j=positions[0];item=catalog[j];seed=point[block.original_columns]
                    expected=(Path(output)/(unit+'_MASTER_SEED_COLUMN.npz')).resolve()
                    record=_record(expected)
                    if (Path(item['point_path']).resolve()!=expected
                            or item['point_file_sha256']!=record['sha256']
                            or item['point_vector_sha256']!=_ORIGINAL_BUILD.__globals__['vector_sha'](seed)
                            or not np.array_equal(item['original_columns'],block.original_columns)
                            or item['local_replay'].get('PASS') is not True
                            or item['local_replay'].get('integer_pattern_exact') is not True
                            or item['local_replay'].get('exact_binary_0_1') is not True):
                        raise PermissionError('RMP_WARM_CURRENT_SEED_FILE_VECTOR_OR_AXIS_DRIFT')
                    with np.load(expected,allow_pickle=False) as saved:
                        if (not np.array_equal(saved['original_columns'],block.original_columns)
                                or _array_sha(np.asarray(saved['point'],dtype=np.float64))!=_array_sha(seed)):
                            raise PermissionError('RMP_WARM_CURRENT_SEED_CONTENT_DRIFT')
                    primal[n+j]=1.;self.seed_receipts.append(record)
                if not np.isfinite(primal).all():raise PermissionError('RMP_WARM_FINITE_PROJECTED_VECTOR_REQUIRED')
                dual=np.zeros(self.model.NumConstrs,dtype=np.float64)
                primal.flags.writeable=False;dual.flags.writeable=False
                self.pstart=primal;self.dstart=dual
                original=self.model.getA();rhs=np.asarray(self.model.getAttr('RHS'));sense=np.asarray(self.model.getAttr('Sense'))
                native=self.model._model.getA();native_rhs=np.asarray(self.model._model.getAttr('RHS'))
                self.diagnostic.update(eligible=True,reason='OWN_CURRENT_STRICT_FULL_SEED_PROJECTION',
                    PStart_sha256=_array_sha(primal),DStart_sha256=_array_sha(dual),
                    PStart_variables=len(primal),DStart_rows=len(dual),
                    DStart_policy='ALL_FINITE_COMPUTATIONAL_ZERO_NO_NATIVE_DUAL_AUTHORITY',
                    own_first_seed_files=self.seed_receipts,
                    original_RMP_residual=_residual(original,rhs,sense,primal),
                    Native_scaled_RMP_residual=_residual(native,native_rhs,sense,primal),
                    original_RMP_matrix_sha256=_matrix_sha(original),
                    Native_scaled_RMP_matrix_sha256=_matrix_sha(native),
                    LPWarmStart_planned=2,Presolve_planned=0,
                    presolved_model_or_crushed_start_claimed=False)
                if not (self.diagnostic['original_RMP_residual']['finite']
                        and self.diagnostic['Native_scaled_RMP_residual']['finite']):
                    self.diagnostic.update(eligible=False,reason='NONFINITE_RMP_RESIDUAL_COLD_ORIGINAL_METHOD1')
                    self.pstart=None;self.dstart=None
        self.diagnostic_json=json.dumps(self.diagnostic,sort_keys=True,allow_nan=False)

    def seal(self):
        return (id(self.case),id(self.decomp),id(self.model),id(self.identity),self.case_structure,
            self.case_identity,self.point_sha,self.identity_sha,self.original_lpwarmstart,
            self.original_crossover,self.diagnostic_json)

    def verify(self,sealed):
        if self.seal()!=sealed:raise PermissionError('RMP_WARM_SEALED_PLAN_DRIFT')
        current=_point(self.case)
        if (execution.current() is None or execution.current()['request']!=self.request
                or (self.case.case_sha,self.decomp.case_sha)!=self.case_identity
                or _case_sha(self.case,self.decomp)!=self.case_structure
                or (current is None)!=(self.point is None)
                or current is not None and _array_sha(current)!=self.point_sha
                or self.point is not None and (self.point.flags.writeable or _array_sha(self.point)!=self.point_sha)
                or sha256(json.dumps(self.identity,sort_keys=True,allow_nan=False).encode()).hexdigest()!=self.identity_sha
                or json.dumps(self.diagnostic,sort_keys=True,allow_nan=False)!=self.diagnostic_json):
            raise PermissionError('RMP_WARM_CURRENT_CASE_CATALOG_OR_REQUEST_DRIFT')
        for value,key in ((self.pstart,'PStart_sha256'),(self.dstart,'DStart_sha256')):
            if self.diagnostic['eligible'] and (value is None or value.flags.writeable
                    or _array_sha(value)!=self.diagnostic[key]):
                raise PermissionError('RMP_WARM_READONLY_START_VECTOR_DRIFT')
            if not self.diagnostic['eligible'] and value is not None:
                raise PermissionError('RMP_WARM_COLD_PLAN_HAS_UNAPPROVED_START')
        if any(_record(r['path'])!=r for r in self.seed_receipts):
            raise PermissionError('RMP_WARM_CURRENT_SEED_FILE_DRIFT')
        self.model.getA();self.model.getAttr('RHS')

    def install(self):
        if (self.model.Params.LPWarmStart!=self.original_lpwarmstart
                or self.model.Params.Crossover!=self.original_crossover):
            raise PermissionError('RMP_WARM_PRE_NATIVE_ORIGINAL_PARAMETER_DRIFT')
        if not self.diagnostic['eligible']:return False
        variables=self.model.getVars();rows=self.model.getConstrs()
        if len(variables)!=len(self.pstart) or len(rows)!=len(self.dstart):
            raise PermissionError('RMP_WARM_NATIVE_START_AXIS_DRIFT')
        self.model.setAttr('PStart',variables,self.pstart.tolist())
        self.model.setAttr('DStart',rows,self.dstart.tolist())
        self.model.Params.LPWarmStart=2;self.model.update()
        if (self.model.Params.LPWarmStart!=2
                or _array_sha(np.asarray(self.model.getAttr('PStart'),dtype=np.float64))!=self.diagnostic['PStart_sha256']
                or _array_sha(np.asarray(self.model.getAttr('DStart'),dtype=np.float64))!=self.diagnostic['DStart_sha256']):
            raise PermissionError('RMP_WARM_EXACT_PRE_NATIVE_START_READBACK_REQUIRED')
        return True


def _source(request):
    if (Path(deployment.ROOT).resolve()!=_ROOT or deployment.sources is not _SOURCE_FUNCTION
            or deployment.verify_request is not _REQUEST_VERIFIER or deployment.digest is not _SOURCE_DIGEST):
        raise PermissionError('RMP_PRESOLVE_OWN_IMMUTABLE_SOURCE_ROOT_REQUIRED')
    observed=_SOURCE_FUNCTION()
    manifest=_REQUEST_VERIFIER(request)
    if (_record(request['manifest'])['sha256']!=request['manifest_SHA']
            or manifest['execution_SHA']!=request['implementation_SHA']
            or manifest['run_id']!=request['run_id']
            or manifest['execution_sources']!=observed
            or _SOURCE_DIGEST(observed)!=manifest['execution_SHA']):
        raise PermissionError('RMP_PRESOLVE_SOURCE_REQUEST_MANIFEST_DRIFT')
    own_relative=Path(__file__).resolve().relative_to(_ROOT).as_posix()
    own=_record(__file__)
    package_files=sorted(p.relative_to(_ROOT).as_posix() for p in (_ROOT/'v42_autonomous_b2').glob('*.py'))
    declared_package=sorted(k for k in manifest['execution_sources']
                            if k.startswith('v42_autonomous_b2/') and k.endswith('.py') and k.count('/')==1)
    if (manifest['execution_sources'].get(own_relative)!=own['sha256']
            or package_files!=declared_package):
        raise PermissionError('RMP_PRESOLVE_OWN_DECLARED_SOURCE_OR_PACKAGE_LIST_DRIFT')
    maps=dict(manifest['builder_original_sources'])
    for key,value in manifest['execution_sources'].items():
        if key in maps and maps[key]!=value:raise PermissionError('RMP_PRESOLVE_SOURCE_MAP_CONFLICT')
        maps[key]=value
    sources={}
    for relative,module in [('v42_m1_hybrid/dw.py',dw),('v42_autonomous_b2/dw_native.py',dw_native),
                            ('v42_b2_seed_recovery_v19/budget.py',original_budget),
                            ('v42_b2_seed_recovery_v19/execution.py',original_execution),
                            ('v42_b2_seed_recovery_v19/numerical.py',numerical),
                            ('v42_may_campaign_native90/execution.py',execution),
                            ('v42_autonomous_b2/worker.py',deployment)]:
        receipt=_record(module.__file__)
        if receipt['path']!=str((_ROOT/relative).resolve()) or maps.get(relative)!=receipt['sha256']:
            raise PermissionError('RMP_PRESOLVE_ORIGINAL_SOURCE_PATH_OR_SHA_DRIFT:'+relative)
        sources[relative]=receipt
    return dict(manifest=_record(request['manifest']),sources=sources,
        computational_adapter_source=own,execution_SHA=request['implementation_SHA'],
        complete_declared_execution_source_count=len(observed),
        complete_declared_execution_sources_checked=True,
        exact_declared_package_files=package_files,immutable_code_root=str(_ROOT))


def _known_ledger(budget, request, *, inflight=False):
    expected=Path(request['output']).resolve().parent/'NATIVE_RUNTIME_LEDGER.json'
    if (Path(budget.path).resolve()!=expected or budget.native_limit!=5400
            or budget.wall_limit is not None):raise PermissionError('RMP_PRESOLVE_OWN_ORIGINAL_NATIVE_LEDGER_REQUIRED')
    persisted=_read(expected)
    recorded_inflight=persisted.get('inflight')
    live_inflight=budget.inflight
    # Original v19 persists the mandatory inflight admission before adding
    # this optional diagnostic to the same live row (budget.py:85-88).
    # Admit only that exact original RMP addition; every persisted key and
    # every other live key must still match. No ledger field is rewritten.
    if inflight and isinstance(recorded_inflight,dict) and isinstance(live_inflight,dict):
        comparable=dict(live_inflight)
        if ('Native_objective_basis' not in recorded_inflight
                and comparable.get('Native_objective_basis')=='ORIGINAL_OBJECTIVE'):
            comparable.pop('Native_objective_basis')
    else:comparable=live_inflight
    if (persisted['Native_ceiling_seconds']!=5400 or persisted['wall_ceiling_seconds'] is not None
            or persisted['P2_calls']!=0 or persisted['calls']!=budget.calls
            or recorded_inflight!=comparable
            or (budget.inflight is not None)!=inflight):
        raise PermissionError('RMP_PRESOLVE_PERSISTED_NATIVE_LEDGER_DRIFT')
    values=[]
    for row in persisted['calls']:
        value=row.get('Native_Runtime')
        if (row.get('runtime_unavailable') is not False or isinstance(value,bool)
                or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):
            raise PermissionError('RMP_PRESOLVE_UNKNOWN_NATIVE_RUNTIME_FORBIDDEN')
        values.append(value)
    # The original budget constructor validates any measured prior receipt.
    # Preserve its accounting; this computational policy neither resets nor
    # imports previous points. Unknown/conservative prefixes stay unknown.
    prior=budget.prior_attempt or {}
    carried=prior.get('Native_Runtime',0.)
    if (persisted.get('prior_attempt')!=budget.prior_attempt or isinstance(carried,bool)
            or not isinstance(carried,(int,float)) or not math.isfinite(carried) or carried<0
            or prior.get('actual_cumulative_Native_Runtime')=='UNKNOWN'
            or sum(values)+carried!=persisted['measured_Native_Runtime']
            or sum(values)+carried!=budget.used() or sum(values)+carried>5400):
        raise PermissionError('RMP_PRESOLVE_NATIVE_ACCOUNTING_DRIFT')
    return dict(receipt=_record(expected),ledger=persisted)


class Entry:
    def __init__(self,model,budget,kwargs,write,binding=None):
        context=execution.current()
        if context is None:raise PermissionError('RMP_PRESOLVE_WORKER_SCOPE_REQUIRED')
        self.request=copy.deepcopy(context['request']);r=self.request
        _delegates(model,budget)
        if (r['arm']!='B2' or r['Threads']!=1 or r['P2_calls']!=0 or r['native_budget_seconds']!=5400
                or r['wall_budget_seconds'] is not None or r['target_gap']!=.03):
            raise PermissionError('RMP_PRESOLVE_ORIGINAL_REQUEST_POLICY_REQUIRED')
        output=Path(model._rmp_output).resolve()
        if not output.is_relative_to(Path(r['output']).resolve()):raise PermissionError('RMP_PRESOLVE_OUTPUT_ESCAPE')
        self.model=model;self.budget=budget;self.kwargs=dict(kwargs);self.write=write;self.output=output
        if binding is None or getattr(model,'_rmp_build_binding',None) is not binding:
            raise PermissionError('RMP_PRESOLVE_ORIGINAL_REBOUND_BUILD_REQUIRED')
        self.raw_model=model._model;self.binding=binding
        binding.verify()
        self.warm=binding.warm(model);self.warm_installed=False
        self.sources=_source(r);self.before=len(budget.calls);self.entered=False;self.committed=False
        self.before_ledger=_known_ledger(budget,r)
        self.matrix_sha=_matrix_sha(model.getA());self.rhs=np.array(model.getAttr('RHS'),copy=True)
        self.original_row_transport=copy.deepcopy(model._receipt)

    def verify(self):
        _delegates(self.model,self.budget)
        if self.model._model is not self.raw_model:raise PermissionError('RMP_PRESOLVE_OWN_RAW_MODEL_CHANGED')
        if self.binding is not None:self.binding.verify()
        if execution.current() is None or execution.current()['request']!=self.request or _source(self.request)!=self.sources:
            raise PermissionError('RMP_PRESOLVE_SAME_LIVE_REQUEST_SOURCE_REQUIRED')
        if (_matrix_sha(self.model.getA())!=self.matrix_sha
                or not np.array_equal(self.model.getAttr('RHS'),self.rhs)
                or self.model._receipt!=self.original_row_transport):
            raise PermissionError('RMP_PRESOLVE_ORIGINAL_ROW_TRANSPORT_MATH_DRIFT')
        if self.binding.warm(self.model) is not self.warm:
            raise PermissionError('RMP_WARM_OWN_ENTRY_PLAN_DRIFT')
        if self.model.Params.Crossover!=self.warm.original_crossover:
            raise PermissionError('RMP_WARM_ORIGINAL_CROSSOVER_DRIFT')

    def receipt(self,**values):
        result=dict(schema='V42_B2_RMP_PRESOLVE0_CURRENT_START_COMPUTATIONAL_ENTRY_V34',
            identity={k:self.request[k] for k in ('run_id','arm','day','worker_slot','attempt_id')},
            source=self.sources,original_row_transport=self.original_row_transport,
            Native_calls_added=0,original_RMP_call_required_seconds=30,
            original_total_Native_cap_seconds=5400,original_RMP_not_removed=True,
            restricted_master_objective_is_Global_LB=False,
            computational_performance_or_Global_LB_improvement_proved=False,**values)
        result['current_attempt_warm_start']=dict(self.warm.diagnostic,
            installed=self.warm_installed,
            exact_complete_start_readback_before_Native=self.warm_installed,
            backend_actual_start_use_or_basis_proved=False)
        self.write(self.output/'RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json',result)


class PresolveFreeRMP(dw_native.ExactRowModel):
    """Change only computational Presolve at the admitted original RMP entry."""
    def optimize(self,callback=None):
        entry=_ENTRY.get();scope=execution._model.get()
        if (entry is None or entry.model is not self or entry.entered or scope is None
                or scope.get('model') is not self or scope.get('component')!='P1' or scope.get('track')!='RMP'):
            raise PermissionError('RMP_PRESOLVE_ONE_APPROVED_MODEL_ENTRY_REQUIRED')
        entry.verify();_known_ledger(entry.budget,entry.request,inflight=True)
        row=entry.budget.inflight
        if (any(row.get(k)!=v for k,v in entry.kwargs.items())
                or row.get('effective_TimeLimit')!=self.Params.TimeLimit
                or row.get('precision_parameters')!=PRECISION
                or self.Params.Threads!=1 or self.Params.Method!=1
                or not 0<self.Params.TimeLimit<=30
                or {k:getattr(self.Params,k) for k in PRECISION}!=PRECISION):
            raise PermissionError('RMP_PRESOLVE_ACTUAL_ORIGINAL_CAP_PRECISION_OR_LABEL_DRIFT')
        entry.entered=True
        self.Params.Presolve=0
        if self.Params.Presolve!=0:raise PermissionError('RMP_PRESOLVE_ZERO_NOT_APPLIED')
        entry.warm_installed=entry.warm.install()
        entry.verify()
        entry.receipt(status='ABOUT_TO_DELEGATE',Native_call_completed=False,
            actual_parameters=dict(Presolve=0,Method=1,Threads=1,TimeLimit=float(self.Params.TimeLimit),precision=PRECISION,
                LPWarmStart=int(self.Params.LPWarmStart),Crossover=int(self.Params.Crossover)),
            ledger_before=entry.before_ledger)
        # ExactRowModel carries only this wrapper's model scope to its owned
        # raw delegate. Original guards/callbacks/Runtime accounting remain.
        return super().optimize(callback)


class BudgetProxy:
    def __init__(self,budget,write,binding=None):
        self._budget=budget;self._write=write;self._binding=binding;self._attempted=False
    def __getattr__(self,key):return getattr(self._budget,key)

    def optimize(self,model,*,track,label,requested_seconds,callback=None):
        if (self._attempted or _ENTRY.get() is not None or not isinstance(model,PresolveFreeRMP)
                or track!='RMP' or label!=LABEL or isinstance(requested_seconds,bool)
                or requested_seconds!=30 or model.Params.Method!=1 or callback is not None):
            raise PermissionError('RMP_PRESOLVE_EXACT_ORIGINAL_ONE_30_SECOND_CALL_REQUIRED')
        self._attempted=True
        entry=Entry(model,self._budget,dict(component='P1',track=track,label=label,requested_seconds=requested_seconds),self._write,self._binding)
        token=_ENTRY.set(entry)
        original_progress=self._budget.progress
        progress_verified=False
        def progress(value):
            nonlocal progress_verified
            returned=original_progress(value)
            # v19's first progress notification follows mandatory inflight
            # persistence and precedes its original guard/Native delegate.
            # Inspect there as well: mutated wrapper code must not bypass
            # the checks contained in the wrapper method itself.
            if not progress_verified:
                progress_verified=True
                entry.verify()
            return returned
        self._budget.progress=progress
        try:
            returned=self._budget.optimize(model,track=track,label=label,
                requested_seconds=requested_seconds,callback=callback)
            entry.verify();known=_known_ledger(self._budget,entry.request)
            if (not entry.entered or len(self._budget.calls)!=entry.before+1
                    or self._budget.calls[-1].get('label')!=LABEL
                    or self._budget.calls[-1].get('track')!='RMP'
                    or self._budget.calls[-1].get('component')!='P1'
                    or self._budget.calls[-1].get('precision_parameters')!=PRECISION
                    or not 0<self._budget.calls[-1].get('effective_TimeLimit',0)<=30
                    or model.Params.Presolve!=0 or model.Params.Method!=1 or model.Params.Threads!=1
                    or model.Params.LPWarmStart!=(2 if entry.warm_installed else entry.warm.original_lpwarmstart)
                    or {k:getattr(model.Params,k) for k in PRECISION}!=PRECISION):
                raise PermissionError('RMP_PRESOLVE_ORIGINAL_SINGLE_COMPLETED_NATIVE_RECEIPT_REQUIRED')
            entry.committed=True
            entry.receipt(status='COMPLETED',Native_call_completed=True,
                completed_original_Native_call=copy.deepcopy(self._budget.calls[-1]),
                actual_parameters=dict(Presolve=0,Method=1,Threads=1,TimeLimit=float(model.Params.TimeLimit),precision=PRECISION,
                    LPWarmStart=int(model.Params.LPWarmStart),Crossover=int(model.Params.Crossover)),
                ledger_after=known)
            return returned
        except BaseException as exc:
            entry.receipt(status='FAILED',Native_call_completed=entry.committed,error=repr(exc),
                own_original_ledger=_record(self._budget.path),Native_policy_scope_closed=True)
            raise
        finally:
            self._budget.progress=original_progress
            _ENTRY.reset(token)


_APPROVED_WRAPPER_TYPE=PresolveFreeRMP
_WRAPPER_OPTIMIZE=PresolveFreeRMP.optimize
_WRAPPER_CODE=PresolveFreeRMP.optimize.__code__


def scoped_runner(original_run,output_directory,write):
    """Rebound original run/builder code; restore all dynamic scopes finally."""
    original_codes=dict(_CODE_BINDINGS)
    context=execution.current()
    if context is None:raise PermissionError('RMP_PRESOLVE_WORKER_SCOPE_REQUIRED')
    _source(context['request'])
    if original_run.__code__ is not original_codes[_ORIGINAL_RUN]:
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_RUN_CODE_REQUIRED')
    builder=original_run.__globals__['build_master']
    # It may be the existing row-transport scoped wrapper. Peel only that
    # known wrapper to retain the original builder's exact source bytecode.
    original_builder=getattr(builder,'original_builder',builder)
    if original_builder.__code__ is not original_codes[_ORIGINAL_BUILD]:
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_BUILD_CODE_REQUIRED')
    if any(original_builder.__globals__.get(key) is not value for key,value in _HELPERS):
        raise PermissionError('RMP_PRESOLVE_ORIGINAL_BUILDER_HELPERS_REQUIRED')
    namespace=dict(original_builder.__globals__,gp=SimpleNamespace(Model=PresolveFreeRMP),
                   output_directory=output_directory,write=write)
    checked_build=rebound(original_builder,namespace)
    build_owner=SimpleNamespace(binding=None)
    def build(case,decomp,columns,output):
        point=_point(case);case_structure=_case_sha(case,decomp)
        result=checked_build(case,decomp,columns,output)
        model=result[0]
        try:
            object.__setattr__(model,'_rmp_output',output_directory(output))
            object.__setattr__(model,'_rmp_build_binding',build_owner.binding)
            plan=WarmPlan(case,decomp,result,point,case_structure,context['request'],model._rmp_output)
            object.__setattr__(model,'_rmp_warm_plan',plan);build_owner.binding.register_warm(model,plan)
            write(output_directory(output)/'RMP_NATIVE_ROW_SCALING.json',model._receipt)
            return result
        except BaseException:
            # Original run has not entered its model-disposal finally yet.
            model.dispose();raise
    original=rebound(original_run,dict(original_run.__globals__,build_master=build,write=write))
    binding=RunBinding(original,checked_build,build,write)
    build_owner.binding=binding
    def run(case,decomp,columns,ledger,output,*,seconds=30):
        binding.verify()
        return original(case,decomp,columns,BudgetProxy(ledger,write,binding),output,seconds=seconds)
    run.original_run=original;run.original_build=checked_build;run.binding=binding
    return run


_WARM_BINDINGS=tuple((owner,key,getattr(owner,key),getattr(owner,key).__code__)
    for owner,keys in ((sys.modules[__name__],('_array_sha','_case_sha','_point','_residual')),
                       (WarmPlan,('__init__','seal','verify','install')),
                       (RunBinding,('register_warm','warm')))
    for key in keys)
_WARM_METHODS={key:getattr(WarmPlan,key) for key in ('seal','verify','install')}
_RUN_WARM=RunBinding.warm
_RUN_REGISTER_WARM=RunBinding.register_warm
