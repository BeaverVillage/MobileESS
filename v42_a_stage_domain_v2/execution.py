"""Task authorization boundary, independent of Gurobi and domain generation.

The four diagnostic dates remain blocked outside a hash-verified permit. The
user's continuation authorizes exactly those dates only after every independent
static/exact gate passes. There is no environment variable, CLI flag or fixture
override. The other 27 dates cannot run under a stress permit.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json


STRESS_DATES = frozenset(('2025-05-10', '2025-05-12', '2025-05-17', '2025-05-19'))
BLOCK_REASON = 'STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED'
BLOCKED_ACTIONS = frozenset(('OPTIMIZE', 'P1', 'P2', 'FEASIBILITY_LP',
    'FEASIBILITY_MIP', 'A1', 'A2', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC'))
_native_day = ContextVar('v42_a_stage_authorized_native_day', default=None)
_stress_permit = ContextVar('v42_a_stage_verified_stress_run_permit', default=None)
_accepted_pipeline = ContextVar('v42_a_stage_accepted_pipeline_day', default=None)
STRESS_RUN_ORDER = ('2025-05-17','2025-05-19','2025-05-12','2025-05-10')
REQUIRED_STRESS_GATES = frozenset(('domain_authority_verification','pre_run_tests',
    'complete_stay','migration_equivalence','lex_stage_rebuild','migration_zero_projection',
    'shift_integrality','shift_strengthening','no_flex_nesting','may17_membership',
    'may19_membership','scientific_input_identity'))
REQUIRED_RUN_SOURCE_NAMES=('execution.py','solver_policy.py','stress_runner.py','telemetry.py','status.py')


def _file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


@dataclass(frozen=True)
class StressRunPermit:
    """Frozen receipt/code identities, never an environment-variable bypass."""
    canonical_json: str

    @property
    def document(self):
        return json.loads(self.canonical_json)

    def verify(self):
        doc=self.document
        if (doc.get('schema')!='A_STAGE_V2_STRESS4_VERIFIED_PERMIT_V1'
                or tuple(doc.get('run_order',()))!=STRESS_RUN_ORDER
                or set(doc.get('gate_receipts',{}))!=REQUIRED_STRESS_GATES
                or not doc.get('execution_sources')):
            raise PermissionError('STRESS4_VERIFIED_PERMIT_REQUIRED')
        required_sources={str((Path(__file__).parent/name).resolve()) for name in REQUIRED_RUN_SOURCE_NAMES}
        if not required_sources<=set(doc['execution_sources']):
            raise PermissionError('STRESS4_ALL_EXECUTION_GUARD_SOURCES_REQUIRED')
        for key,receipt in doc['gate_receipts'].items():
            if _file_sha(receipt['path'])!=receipt['sha256']:
                raise PermissionError('STRESS4_GATE_RECEIPT_DRIFT:'+key)
            if json.loads(Path(receipt['path']).read_text(encoding='utf-8-sig')).get('PASS') is not True:
                raise PermissionError('STRESS4_PRE_RUN_GATE_NOT_PASS:'+key)
        for path,sha in doc['execution_sources'].items():
            if _file_sha(path)!=sha:
                raise PermissionError('STRESS4_EXECUTION_SOURCE_DRIFT:'+path)
        return True


def create_stress_run_permit(gate_receipts, source_paths, *, output=None, base_identity=None):
    """Called by the preregistered runner only after every independent gate PASS."""
    if set(gate_receipts)!=REQUIRED_STRESS_GATES:
        raise PermissionError('STRESS4_ALL_PRE_RUN_GATES_REQUIRED')
    resolved={key:str(Path(path).resolve()) for key,path in gate_receipts.items()}
    if len(set(resolved.values()))!=len(resolved):
        raise PermissionError('STRESS4_DISTINCT_GATE_RECEIPTS_REQUIRED')
    receipts={key:dict(path=path,sha256=_file_sha(path)) for key,path in sorted(resolved.items())}
    sources={str(Path(path).resolve()):_file_sha(path) for path in source_paths}
    doc=dict(schema='A_STAGE_V2_STRESS4_VERIFIED_PERMIT_V1',run_order=list(STRESS_RUN_ORDER),
        gate_receipts=receipts,execution_sources=sources,base_identity=base_identity,
        other_27_dates_authorized=False,actual_reoptimization_authorized=False,
        pipeline_requires_full_integer_domain_acceptance=True)
    permit=StressRunPermit(json.dumps(doc,sort_keys=True,separators=(',',':')))
    permit.verify()
    if output is not None:
        target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('x',encoding='utf8') as stream:
            json.dump(doc,stream,ensure_ascii=False,indent=2);stream.write('\n')
    return permit


@contextmanager
def stress_run_scope(permit):
    if not isinstance(permit,StressRunPermit):
        raise PermissionError('STRESS4_VERIFIED_PERMIT_REQUIRED')
    permit.verify()
    token=_stress_permit.set(permit)
    try:
        yield permit
    finally:
        _stress_permit.reset(token)


@contextmanager
def accepted_pipeline_scope(day,domain_status):
    from .status import require_production_domain_accepted
    require_production_domain_accepted(domain_status)
    normalized=normalize_day(day)
    permit=_stress_permit.get()
    if permit is None or normalized not in STRESS_DATES:
        raise PermissionError('STRESS4_VERIFIED_PERMIT_REQUIRED')
    permit.verify()
    token=_accepted_pipeline.set(normalized)
    try:
        yield
    finally:
        _accepted_pipeline.reset(token)


def normalize_day(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Native timestamps use the date in their scientific source timezone.
        # Reject malformed dates rather than interpreting a system timezone.
        result = value[:10]
        try:
            if date.fromisoformat(result).isoformat() == result:
                return result
        except ValueError:
            pass
    raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')


def day_from_authority(value):
    """Read only explicit date metadata; never inspect scientific future data."""
    if isinstance(value, (date, datetime, str)):
        return normalize_day(value)
    if isinstance(value, Mapping):
        days = []
        for key in ('day', 'date', 'planning_day', 'target_day'):
            if key in value and value[key] is not None:
                days.append(normalize_day(value[key]))
        for key in ('bundle', 'identity', 'payload', 'request', 'plan'):
            if isinstance(value.get(key), Mapping):
                found = day_from_authority(value[key])
                if found is not None:
                    days.append(found)
        if len(set(days)) > 1:
            # A conflict may never hide a stress date behind another date.
            if set(days) & STRESS_DATES:
                raise PermissionError(BLOCK_REASON)
            raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')
        return days[0] if days else None
    request = getattr(value, 'request', None)
    if isinstance(request, Mapping):
        return day_from_authority(request)
    return None


def require_action_authorized(authority, action='OPTIMIZE', *, require_day=True):
    """Fail before model creation, optimization, freeze, or physical execution."""
    day = day_from_authority(authority)
    if day is None:
        day = _native_day.get()
    if day is None and require_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')
    from v42_may12_rescue.execution import current as may12_current, authorize as may12_authorize
    if may12_current() is not None:
        return may12_authorize(day, action)
    from v42_a_stage_acceptance.execution import current as continuation_current, authorize as continuation_authorize
    if continuation_current() is not None:
        return continuation_authorize(day, action)
    from v42_a_stage_cg.execution import current as cg_current, authorize as cg_authorize
    if cg_current() is not None:
        return cg_authorize(day, action)
    from v42_a_stage_lexcases.execution import current as cases_current, authorize as cases_authorize
    if cases_current() is not None:
        return cases_authorize(day, action)
    from v42_a_stage_lexrefine.execution import current as refine_current, authorize as refine_authorize
    if refine_current() is not None:
        return refine_authorize(day, action)
    from v42_a_stage_lexfull.execution import current as fulllex_current, authorize as fulllex_authorize
    if fulllex_current() is not None:
        return fulllex_authorize(day, action)
    from v42_a_stage_lex.execution import current as lex_current, authorize as lex_authorize
    if lex_current() is not None:
        return lex_authorize(day, action)
    from v42_a_stage_bnp.execution import current as bnp_current, authorize as bnp_authorize
    if bnp_current() is not None:
        return bnp_authorize(day, action)
    from v42_a_stage_practical.execution import current as practical_current, authorize as practical_authorize
    if practical_current() is not None:
        return practical_authorize(day, action)
    from v42_a_stage_compact_rowgen.execution import current as compact_current, authorize as compact_authorize
    if compact_current() is not None:
        return compact_authorize(day, action)
    from v42_a_stage_residual.execution import current as residual_current, authorize as residual_authorize
    if residual_current() is not None:
        return residual_authorize(day, action)
    from v42_a_stage_early.execution import current as early_current, authorize as early_authorize
    if early_current() is not None:
        return early_authorize(day, action)
    # The successor permit has narrower native model/phase authorization than
    # the preserved complete-STAY diagnostic permit.
    from .fast_execution import current_fast_permit, authorize_fast_action
    if current_fast_permit() is not None:
        return authorize_fast_action(day, action)
    permit=_stress_permit.get()
    if permit is not None:
        if day not in STRESS_DATES:
            raise PermissionError('OTHER_27_MAY_DATES_NOT_AUTHORIZED')
        permit.verify()
        if _accepted_pipeline.get() is not None and action not in ('PLANNING_FREEZE','ACTUAL','FRESH_AC'):
            raise PermissionError('ACTUAL_OR_FRESH_REOPTIMIZATION_FORBIDDEN')
        if action in ('PLANNING_FREEZE','ACTUAL','FRESH_AC') and _accepted_pipeline.get()!=day:
            raise PermissionError('PRODUCTION_DOMAIN_CLOSURE_REQUIRED')
    elif day in STRESS_DATES:
        raise PermissionError(BLOCK_REASON)
    return day


@contextmanager
def native_execution_scope(authority, action='OPTIMIZE'):
    day = require_action_authorized(authority, action)
    token = _native_day.set(day)
    try:
        yield day
    finally:
        _native_day.reset(token)


def tag_model_for_day(model, authority, *, require_day=True):
    """Static model construction is permitted; tag without authorizing a solve."""
    day = day_from_authority(authority)
    if day is None and require_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')
    if day is not None:
        original_day=getattr(model,'_v42_a_stage_day',None)
        if original_day is not None and original_day!=day:
            if original_day in STRESS_DATES or day in STRESS_DATES:
                raise PermissionError(BLOCK_REASON)
            raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')
        model._v42_a_stage_day = day
    return model


def guard_model_optimize(model):
    # Tagged native models are always guarded, including direct optimize calls.
    day = getattr(model, '_v42_a_stage_day', None)
    context_day = _native_day.get()
    effective_day=day if day is not None else context_day
    from v42_may12_rescue.execution import current as may12_current, guard as may12_guard
    if may12_current() is not None:
        may12_guard(model, effective_day)
        return
    from v42_a_stage_acceptance.execution import current as continuation_current, guard as continuation_guard
    if continuation_current() is not None:
        continuation_guard(model, effective_day)
        return
    from v42_a_stage_cg.execution import current as cg_current, guard as cg_guard
    if cg_current() is not None:
        cg_guard(model, effective_day)
        return
    from v42_a_stage_lexcases.execution import current as cases_current, guard as cases_guard
    if cases_current() is not None:
        cases_guard(model, effective_day)
        return
    from v42_a_stage_lexrefine.execution import current as refine_current, guard as refine_guard
    if refine_current() is not None:
        refine_guard(model, effective_day)
        return
    from v42_a_stage_lexfull.execution import current as fulllex_current, guard as fulllex_guard
    if fulllex_current() is not None:
        fulllex_guard(model, effective_day)
        return
    from v42_a_stage_lex.execution import current as lex_current, guard as lex_guard
    if lex_current() is not None:
        lex_guard(model, effective_day)
        return
    from v42_a_stage_bnp.execution import current as bnp_current, guard as bnp_guard
    if bnp_current() is not None:
        bnp_guard(model, effective_day)
        return
    from v42_a_stage_practical.execution import current as practical_current, guard as practical_guard
    if practical_current() is not None:
        practical_guard(model, effective_day)
        return
    from v42_a_stage_compact_rowgen.execution import current as compact_current, guard as compact_guard
    if compact_current() is not None:
        compact_guard(model, effective_day)
        return
    from v42_a_stage_residual.execution import current as residual_current, guard as residual_guard
    if residual_current() is not None:
        residual_guard(model, effective_day)
        return
    from v42_a_stage_early.execution import current as early_current, guard as early_guard
    if early_current() is not None:
        early_guard(model, effective_day)
        return
    from .fast_execution import current_fast_permit, guard_fast_model
    if current_fast_permit() is not None:
        guard_fast_model(model, effective_day)
        return
    if _stress_permit.get() is not None:
        require_action_authorized(effective_day,'OPTIMIZE')
    elif day in STRESS_DATES or context_day in STRESS_DATES:
        raise PermissionError(BLOCK_REASON)
    if day is not None and context_day is not None and day != context_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')


def guarded_optimize(model, authority, *args, **kwargs):
    guard_model_optimize(model)
    require_action_authorized(authority)
    tag_model_for_day(model, authority)
    guard_model_optimize(model)
    return model.optimize(*args, **kwargs)


def install_gurobi_backstop(gp):
    """Preserve the native class; guard optimize/copy/relax without solving.

    copy() and relax() return different native models. Date tags are explicitly
    propagated so feasibility LPs and copied MIPs cannot lose the boundary.
    This installer is idempotent and does not change settings or coefficients.
    """
    model_class = gp.Model
    if getattr(model_class, '_v42_stress_guard_installed', False):
        return
    original_optimize = model_class.optimize

    def optimize(self, *args, **kwargs):
        guard_model_optimize(self)
        return original_optimize(self, *args, **kwargs)

    model_class.optimize = optimize
    for method in ('copy', 'relax', 'presolve', 'fixed'):
        original = getattr(model_class, method, None)
        if original is None:
            continue

        def derived(self, *args, _original=original, _method=method, **kwargs):
            if _method == 'presolve':
                guard_model_optimize(self)
            result = _original(self, *args, **kwargs)
            day = getattr(self, '_v42_a_stage_day', None)
            if day is not None:
                result._v42_a_stage_day = day
            return result

        setattr(model_class, method, derived)
    model_class._v42_stress_guard_installed = True

