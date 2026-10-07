"""Source-bound fast qualification permits and LP-before-MILP backstop.

Import and model construction grant no native execution. Old stress permits and
receipts remain separate. A fast scope permits only its current model and phase.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math

from .execution import STRESS_DATES, STRESS_RUN_ORDER, REQUIRED_STRESS_GATES, _file_sha

CANARY_DATES = ('2025-05-17', '2025-05-19')
REQUIRED_FAST_GATES = (REQUIRED_STRESS_GATES - {'complete_stay'}) | frozenset((
    'complete_physical_domain', 'active_pool_partition', 'initial_active_support',
    'exact_pricing_authority', 'fast_pre_run_tests'))
REQUIRED_FAST_SOURCES = ('execution.py', 'fast_execution.py', 'fast_runner.py',
    'fast_status.py', 'solver_policy.py', 'fast_telemetry.py', 'telemetry.py')
SCHEMA = 'A_STAGE_FAST_ACTIVE_DOMAIN_PERMIT_V1'
_permit = ContextVar('v42_fast_permit', default=None)
_native = ContextVar('v42_fast_native_model_phase', default=None)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode('utf8')).hexdigest()


def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _checked_receipt(record, label):
    if _file_sha(record['path']) != record['sha256']:
        raise PermissionError('FAST_RECEIPT_DRIFT:' + label)
    return json.loads(Path(record['path']).read_text(encoding='utf-8-sig'))


@dataclass(frozen=True)
class FastRunPermit:
    canonical_json: str

    @property
    def document(self):
        return json.loads(self.canonical_json)

    @property
    def identity(self):
        return canonical_hash(self.document)

    def verify(self):
        doc = self.document
        mode = doc.get('mode')
        if (doc.get('schema') != SCHEMA or mode not in ('CANARY', 'PRODUCTION')
                or set(doc.get('gate_receipts', {})) != REQUIRED_FAST_GATES
                or tuple(doc.get('run_order', ())) != (CANARY_DATES if mode == 'CANARY' else STRESS_RUN_ORDER)
                or doc.get('other_27_dates_authorized') is not False):
            raise PermissionError('FAST_VERIFIED_PERMIT_REQUIRED')
        required = {str((Path(__file__).parent / name).resolve()) for name in REQUIRED_FAST_SOURCES}
        if not required <= set(doc.get('execution_sources', {})):
            raise PermissionError('FAST_ALL_EXECUTION_SOURCES_REQUIRED')
        for name, record in doc['gate_receipts'].items():
            if _checked_receipt(record, name).get('PASS') is not True:
                raise PermissionError('FAST_PRE_RUN_GATE_NOT_PASS:' + name)
        for path, expected in doc['execution_sources'].items():
            if _file_sha(path) != expected:
                raise PermissionError('FAST_EXECUTION_SOURCE_DRIFT:' + path)
        policy = _checked_receipt(doc['solver_policy'], 'solver_policy')
        from .solver_policy import validate_frozen_policy
        validate_frozen_policy(policy)
        active = _checked_receipt(doc['activation_policy'], 'activation_policy')
        if active.get('PASS') is not True or active.get('scientific_domain_cap') is not False:
            raise PermissionError('PREREGISTERED_ENGINEERING_ACTIVATION_POLICY_REQUIRED')
        budget = doc.get('native_budget_seconds')
        if not isinstance(budget, (int, float)) or isinstance(budget, bool) or not math.isfinite(budget):
            raise PermissionError('FAST_FINITE_CUMULATIVE_BUDGET_REQUIRED')
        if not 0 < budget <= (300 if mode == 'CANARY' else 3600):
            raise PermissionError('FAST_CUMULATIVE_BUDGET_EXCEEDED')
        if mode == 'PRODUCTION':
            speed = _checked_receipt(doc['speed_gate'], 'speed_gate')
            if (speed.get('classification') != 'SPEED_GATE_PASS' or speed.get('PASS') is not True
                    or speed.get('execution_sources_sha256') != canonical_hash(doc['execution_sources'])
                    or speed.get('solver_policy_sha256') != doc['solver_policy']['sha256']
                    or speed.get('activation_policy_sha256') != doc['activation_policy']['sha256']
                    or speed.get('canary_source_bound') is not True):
                raise PermissionError('ACTUAL_SOURCE_BOUND_SPEED_GATE_PASS_REQUIRED')
            for label in ('may17_canary', 'may19_canary'):
                canary = _checked_receipt(doc[label], label)
                if (canary.get('mode') != 'CANARY' or canary.get('global_scientific_stop') is True
                        or canary.get('domain_status', {}).get('LP_PRICING_CLOSED') is not True
                        or canary.get('execution_sources_sha256') != canonical_hash(doc['execution_sources'])
                        or canary.get('solver_policy_sha256') != doc['solver_policy']['sha256']
                        or canary.get('activation_policy_sha256') != doc['activation_policy']['sha256']):
                    raise PermissionError('CURRENT_SOURCE_CANARY_REQUIRED:' + label)
            if _checked_receipt(doc['may19_canary'], 'may19_canary').get('root_completed') is not True:
                raise PermissionError('MAY19_CANARY_ROOT_COMPLETION_REQUIRED')
        return True


def create_fast_run_permit(gate_receipts, source_paths, solver_policy_path, activation_policy_path,
        *, mode='CANARY', native_budget_seconds=300, output=None, speed_gate=None,
        may17_canary=None, may19_canary=None, checkpoint=None):
    if set(gate_receipts) != REQUIRED_FAST_GATES:
        raise PermissionError('FAST_ALL_PRE_RUN_GATES_REQUIRED')
    def record(path):
        path = str(Path(path).resolve())
        return dict(path=path, sha256=_file_sha(path))
    gates = {name: record(path) for name, path in sorted(gate_receipts.items())}
    if len({r['path'] for r in gates.values()}) != len(gates):
        raise PermissionError('FAST_DISTINCT_GATE_RECEIPTS_REQUIRED')
    sources = {str(Path(path).resolve()): _file_sha(path) for path in source_paths}
    doc = dict(schema=SCHEMA, mode=mode,
        run_order=list(CANARY_DATES if mode == 'CANARY' else STRESS_RUN_ORDER),
        native_budget_seconds=native_budget_seconds, gate_receipts=gates, execution_sources=sources,
        solver_policy=record(solver_policy_path), activation_policy=record(activation_policy_path),
        checkpoint=checkpoint, other_27_dates_authorized=False,
        canary_is_production_result=False, LP_pricing_is_integer_closure=False)
    if mode == 'PRODUCTION':
        if any(p is None for p in (speed_gate, may17_canary, may19_canary)):
            raise PermissionError('ACTUAL_SPEED_GATE_AND_CANARY_RECEIPTS_REQUIRED')
        doc.update(speed_gate=record(speed_gate), may17_canary=record(may17_canary), may19_canary=record(may19_canary))
    permit = FastRunPermit(json.dumps(doc, sort_keys=True, separators=(',', ':'), allow_nan=False))
    permit.verify()
    if output is not None:
        target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf8') as stream:
            json.dump(doc, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return permit


def current_fast_permit():
    return _permit.get()


@contextmanager
def fast_run_scope(permit):
    if not isinstance(permit, FastRunPermit):
        raise PermissionError('FAST_VERIFIED_PERMIT_REQUIRED')
    permit.verify()
    token = _permit.set(permit)
    try:
        yield permit
    finally:
        _permit.reset(token)


def authorize_fast_action(day, action):
    permit = _permit.get()
    if permit is None:
        raise PermissionError('FAST_VERIFIED_PERMIT_REQUIRED')
    permit.verify()
    allowed = CANARY_DATES if permit.document['mode'] == 'CANARY' else STRESS_DATES
    if day not in allowed:
        raise PermissionError('FAST_DATE_NOT_AUTHORIZED')
    if action in ('PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC'):
        raise PermissionError('FAST_FULL_DOMAIN_ACCEPTANCE_AND_PIPELINE_PERMIT_REQUIRED')
    if action in ('OPTIMIZE', 'FEASIBILITY_MIP') and _native.get() is None:
        raise PermissionError('FAST_EXPLICIT_NATIVE_MODEL_PHASE_REQUIRED')
    return day


@contextmanager
def fast_native_scope(model, day, phase, *, pricing_proof=None):
    permit = _permit.get()
    if permit is None or phase not in ('LP', 'MILP'):
        raise PermissionError('FAST_EXPLICIT_NATIVE_MODEL_PHASE_REQUIRED')
    authorize_fast_action(day, 'A1')
    if phase == 'MILP':
        from .fast_status import require_current_lp_pricing_closed
        require_current_lp_pricing_closed(pricing_proof)
        if pricing_proof['day'] != day:
            raise PermissionError('FAST_PRICING_PROOF_DATE_CONFLICT')
        if permit.document['mode'] == 'CANARY' and day == '2025-05-19':
            raise PermissionError('MAY19_CANARY_LP_ONLY')
    token = _native.set((model, day, phase))
    try:
        guard_fast_model(model, day)
        yield
    finally:
        _native.reset(token)


def guard_fast_model(model, day):
    authorize_fast_action(day, 'A1')
    if getattr(model,'_v42_a_stage_day',None)!=day:
        raise PermissionError('FAST_NATIVE_MODEL_DATE_CONFLICT')
    native = _native.get()
    if native is None or native[0] is not model or native[1] != day:
        raise PermissionError('FAST_EXPLICIT_NATIVE_MODEL_PHASE_REQUIRED')
    if native[2] == 'LP' and getattr(model, 'NumIntVars', None) != 0:
        raise PermissionError('FAST_LP_PHASE_REQUIRES_CONTINUOUS_MODEL')


def require_may19_tractable(receipt, permit):
    """May12/10 cannot proceed after an unresolved or catastrophic May19 root."""
    doc = permit.document
    if (not isinstance(receipt, dict) or receipt.get('day') != '2025-05-19'
            or receipt.get('mode') != 'PRODUCTION' or receipt.get('root_completed') is not True
            or receipt.get('catastrophic_root_behavior') is not False
            or receipt.get('may19_tractability_PASS') is not True
            or receipt.get('permit_sha256') != permit.identity
            or receipt.get('execution_sources_sha256') != canonical_hash(doc['execution_sources'])
            or receipt.get('solver_policy_sha256') != doc['solver_policy']['sha256']
            or receipt.get('activation_policy_sha256') != doc['activation_policy']['sha256']
            or receipt.get('global_scientific_stop') is True):
        raise PermissionError('CURRENT_MAY19_TRACTABILITY_PASS_REQUIRED')
    return True
