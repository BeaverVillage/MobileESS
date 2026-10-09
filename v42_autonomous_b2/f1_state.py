"""Current-attempt F1 state for the original F1 and full-LP pipeline.

Call the original F1 and full-LP functions; neither Native solve is removed.
Only the original independent rational checker supplies lower-bound authority.
There is no API to import a saved state or another attempt's checkpoint.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import math
import re

import numpy as np
from scipy import sparse


F1_LABEL = 'CURRENT_DAY_STATIONARY_FULL_INTEGER_REPRESENTATIVE_BOUNDS'
LP_LABEL = 'CURRENT_DAY_FULL_LP_EXACT_DUAL'
PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9,
                 NumericFocus=3, ScaleFlag=2)
IDENTITY_KEYS = ('run_id', 'arm', 'day', 'worker_slot', 'attempt_id')
_ISSUER = object()


def _original_functions():
    from v42_b2_seed_recovery_v19.stationary_dispatch import validated_start
    from v42_may_campaign_native90.m_stage import _fresh_lp_dual
    from v42_m1_research.lb import repair_affine_equality_duals
    from v42_b2_seed_recovery_v18.certificate_box import check
    return dict(F1=validated_start,FULL_LP=_fresh_lp_dual,
                REPAIR=repair_affine_equality_duals,CHECKER=check)


_ORIGINAL_FUNCTIONS = _original_functions()


def _original_code(function, kind):
    # Capture before a future scoped hook changes the module's global alias.
    # The original code objects themselves remain the authority.
    if getattr(function,'__code__',None) is not _ORIGINAL_FUNCTIONS[kind].__code__:
        raise PermissionError('F1_ORIGINAL_CODE_OBJECT_REQUIRED:'+kind)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _digest(value):
    return sha256(_json(value)).hexdigest()


def _record(path):
    path = Path(path).resolve()
    h = sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=h.hexdigest())


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _array_digest(array):
    a = np.ascontiguousarray(array)
    h = sha256()
    h.update(_json(dict(dtype=a.dtype.str, shape=a.shape)))
    h.update(memoryview(a).cast('B'))
    return h.hexdigest()


def _canonical(matrix):
    a = sparse.csr_matrix(matrix, copy=True)
    a.sum_duplicates(); a.eliminate_zeros(); a.sort_indices()
    return a


def case_fingerprint(case):
    """Complete stored matrix/domain/row and column axes, including constant."""
    a = _canonical(case.A)
    return dict(case_sha=case.case_sha, matrix_shape=list(a.shape),
        matrix={k:_array_digest(getattr(a, k)) for k in ('indptr','indices','data')},
        domain={k:_array_digest(v) for k,v in sorted(case.d.items())})


def _same(left, right):
    return np.array_equal(np.asarray(left), np.asarray(right))


def _same_bounds(actual, expected):
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    # Preserve only already-unbounded original endpoints; never create a box.
    return bool(np.all((actual == expected)
        | (np.isposinf(expected) & (actual >= 1e100))
        | (np.isneginf(expected) & (actual <= -1e100))))


def verify_native_math(model, case, *, fixed=None):
    """A full Native matrix/domain/objective round trip, with no tolerances."""
    expected = _canonical(case.A); actual = _canonical(model.getA())
    if (actual.shape != expected.shape or any(not _same(getattr(actual,k),
            getattr(expected,k)) for k in ('indptr','indices','data'))):
        raise PermissionError('F1_NATIVE_MATRIX_DRIFT')
    d = case.d
    lo = np.asarray(d['lower'], dtype=float).copy()
    hi = np.asarray(d['upper'], dtype=float).copy()
    if fixed is not None:
        ids, values = fixed
        ids, values = np.asarray(ids), np.asarray(values, dtype=float)
        if (ids.ndim != 1 or ids.dtype.kind not in 'iu' or len(set(ids)) != len(ids)
                or values.shape != ids.shape or not np.isfinite(values).all()
                or np.any(ids < 0) or np.any(ids >= len(lo))
                or np.any(values < lo[ids]) or np.any(values > hi[ids])):
            raise PermissionError('F1_FIXED_REPRESENTATIVE_AXIS_DRIFT')
        lo[ids] = values; hi[ids] = values
    for key, expected in (('RHS',d['rhs']), ('Sense',d['sense']),
                          ('Obj',d['objective']), ('VarName',d['names'])):
        if not _same(model.getAttr(key), expected):
            raise PermissionError('F1_NATIVE_METADATA_DRIFT:'+key)
    if (not _same_bounds(model.getAttr('LB'),lo)
            or not _same_bounds(model.getAttr('UB'),hi)
            or float(model.ObjCon) != float(np.asarray(d['constant']).item())
            or any(t != 'C' for t in model.getAttr('VType'))):
        raise PermissionError('F1_NATIVE_DOMAIN_OR_OBJECTIVE_DRIFT')
    return dict(PASS=True, matrix_RHS_senses_original_bounds_objective_constant_exact=True,
                all_original_columns_continuous_for_this_LP=True,
                fixed_candidate_bounds_only=fixed is not None)


@dataclass(frozen=True)
class CapturedState:
    issuer: object
    scope_token: object
    binding: dict
    point: np.ndarray
    pi: object
    vbasis: object
    cbasis: object
    fixed_ids: np.ndarray
    fixed_values: np.ndarray
    array_shas: dict
    strict_receipt: dict
    native_call: dict
    native_index: int
    native_snapshot: dict
    packet: dict


def _freeze(array, dtype=None):
    if array is None:
        return None
    a = np.array(array, dtype=dtype, copy=True)
    a.setflags(write=False)
    return a


def _attributes(model, key, n, *, integer=False):
    try:
        raw = np.asarray(model.getAttr(key))
    except Exception:
        return None
    if raw.shape != (n,) or not np.isfinite(raw).all():
        return None
    if integer and (raw.dtype.kind not in 'iu' or not np.isin(raw,(-3,-2,-1,0)).all()):
        return None
    return _freeze(raw, dtype=np.int32 if integer else np.float64)


class Scope:
    """Request-local state and receipts.  Saved arrays are never admitted back."""
    def __init__(self, request, code_root, *, writer=None):
        self.request = copy.deepcopy(request)
        self.code_root = Path(code_root).resolve()
        self.token = object(); self.state = None; self.installed = False
        self.capture_entered = False
        self._state_digest = None
        self.writer = writer or self._default_writer
        self._authority = self._authority_now()

    @staticmethod
    def _default_writer(path, value):
        from v42_pr134_b1.common import atomic
        atomic(path,value)

    def _authority_now(self):
        r = self.request
        root = Path(r['root']).resolve()
        output = root/'dates/B2'/r['day']/'attempts'/r['attempt_id']/'output'
        if (r['arm'] != 'B2' or not re.fullmatch(r'2025-05-(0[1-9]|[12][0-9]|3[01])',r['day'])
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',r['attempt_id'])
                or type(r['worker_slot']) is not int or not 1 <= r['worker_slot'] <= 3
                or type(r['Threads']) is not int or r['Threads'] != 1 or r['P2_calls'] != 0
                or r['native_budget_seconds'] != 5400 or r['wall_budget_seconds'] is not None
                or r['target_gap'] != .03 or r.get('previous_attempts',[]) != []
                or Path(r['output']).resolve() != output
                or Path(r['manifest']).resolve().parent != root):
            raise PermissionError('F1_CURRENT_ATTEMPT_POLICY_REQUIRED')
        manifest = _read(r['manifest'])
        if (_record(r['manifest'])['sha256'] != r['manifest_SHA']
                or manifest['run_id'] != r['run_id']
                or manifest['initialization_native_limit_seconds'] != 5400
                or manifest['execution_SHA'] != r['implementation_SHA']
                or manifest.get('prior_attempts',{}).get(r['day']) is not None):
            raise PermissionError('F1_MANIFEST_IDENTITY_OR_PRIOR_STATE_FORBIDDEN')
        sources = dict(manifest['builder_original_sources'])
        for name, expected in manifest['execution_sources'].items():
            if name in sources and sources[name] != expected:
                raise PermissionError('F1_SOURCE_MAP_DISAGREEMENT')
            sources[name] = expected
        for name, expected in sources.items():
            path = (self.code_root/name).resolve()
            if not path.is_relative_to(self.code_root) or _record(path)['sha256'] != expected:
                raise PermissionError('F1_SOURCE_SHA_DRIFT:'+name)
        if _digest(manifest['execution_sources']) != manifest['execution_SHA']:
            raise PermissionError('F1_EXECUTION_SOURCE_DIGEST_DRIFT')
        return dict(identity={k:r[k] for k in IDENTITY_KEYS}, code_root=str(self.code_root),
            manifest=_record(r['manifest']), scientific_sources_sha=_digest(sources),
            implementation_SHA=r['implementation_SHA'], adapter_source=_record(__file__),
            previous_attempt_state_eligible=False)

    def _authority_check(self):
        if self._authority_now() != self._authority:
            raise PermissionError('F1_SCOPE_SOURCE_OR_REQUEST_CHANGED')

    def _owned(self, name):
        path = Path(self.request['output']).resolve()/name
        if not path.resolve().is_relative_to(Path(self.request['output']).resolve()):
            raise PermissionError('F1_OUTPUT_ESCAPE')
        path.parent.mkdir(parents=True,exist_ok=True)
        return path

    def write(self, name, value):
        self.writer(self._owned(name),value)

    def _ledger(self, budget, index=None, call=None):
        expected = Path(self.request['output']).resolve().parent/'NATIVE_RUNTIME_LEDGER.json'
        if (Path(budget.path).resolve() != expected or budget.native_limit != 5400
                or budget.wall_limit is not None or getattr(budget,'prior_attempt',None)
                or budget.inflight is not None):
            raise PermissionError('F1_OWN_KNOWN_NATIVE_LEDGER_REQUIRED')
        ledger = _read(expected)
        if (ledger['Native_ceiling_seconds'] != 5400 or ledger['wall_ceiling_seconds'] is not None
                or ledger.get('P2_calls') != 0 or ledger.get('inflight') is not None
                or ledger.get('historical_costs_reused') is not False
                or ledger['calls'] != budget.calls):
            raise PermissionError('F1_PERSISTED_NATIVE_LEDGER_DRIFT')
        runtimes = []
        for entry in ledger['calls']:
            runtime = entry.get('Native_Runtime')
            if (entry.get('entered_native') is not True or entry.get('runtime_unavailable') is not False
                    or isinstance(runtime,bool) or not isinstance(runtime,(float,int))
                    or not math.isfinite(runtime) or runtime < 0):
                raise PermissionError('F1_UNKNOWN_NATIVE_ACCOUNTING_FORBIDDEN')
            runtimes.append(runtime)
        if ledger['measured_Native_Runtime'] != sum(runtimes):
            raise PermissionError('F1_NATIVE_CUMULATIVE_RUNTIME_DRIFT')
        if index is not None and (index >= len(ledger['calls']) or ledger['calls'][index] != call):
            raise PermissionError('F1_CAPTURED_NATIVE_CALL_CHANGED')
        return ledger

    def capture(self, original, case, budget, progress=None, *, pattern=None):
        """Run original F1, read state before dispose, promote after FULL PASS."""
        _original_code(original,'F1')
        self._authority_check()
        if self.capture_entered:
            raise PermissionError('F1_ONE_CAPTURE_PER_CURRENT_ATTEMPT')
        self.capture_entered = True
        if Path(case.output).resolve() != Path(self.request['output']).resolve():
            raise PermissionError('F1_CASE_OUTPUT_MISMATCH')
        if pattern is None:
            from v42_b2_seed_recovery_v19.fixed_pattern import discrete_stationary
            pattern = discrete_stationary(case)
        fixed = (_freeze(pattern[0]),_freeze(pattern[1],np.float64))
        fingerprint = case_fingerprint(case)
        pending = {}
        calls_entered = [0]
        scope = self

        class Proxy:
            def __getattr__(self, name):
                return getattr(budget,name)

            def native_optimize(self, model, callback=None, **kwargs):
                if (kwargs.get('component'),kwargs.get('track'),kwargs.get('label')) != (
                        'FEASIBILITY_LP','M_START',F1_LABEL):
                    raise PermissionError('F1_ONLY_ORIGINAL_STATIONARY_CALL')
                if kwargs.get('requested_seconds') != 120. or calls_entered[0]:
                    raise PermissionError('F1_ORIGINAL_CALL_LIMIT_OR_CARDINALITY_DRIFT')
                scope._ledger(budget)
                before = len(budget.calls); calls_entered[0] += 1
                returned = budget.native_optimize(model,callback,**kwargs)
                if len(budget.calls) != before+1 or pending:
                    raise PermissionError('F1_ORIGINAL_CALL_LIMIT_OR_CARDINALITY_DRIFT')
                ledger = scope._ledger(budget)
                call = copy.deepcopy(budget.calls[-1])
                if (call.get('status') != 'FINISHED' or call.get('error') is not None
                        or call.get('component') != 'FEASIBILITY_LP' or call.get('track') != 'M_START'
                        or call.get('label') != F1_LABEL or call.get('requested_seconds') != 120.
                        or not 0 < call.get('effective_TimeLimit',0) <= 120.
                        or call.get('precision_parameters') != PRECISION
                        or call.get('Native_status') != 2
                        or model.Status != 2 or not model.SolCount):
                    return returned
                if (model.Params.Threads != 1 or model.Params.Method != 1
                        or float(model.Params.TimeLimit) != float(call['effective_TimeLimit'])
                        or float(model.Runtime) != call['Native_Runtime']
                        or {k:getattr(model.Params,k) for k in PRECISION} != PRECISION):
                    raise PermissionError('F1_ACTUAL_NATIVE_PARAMETERS_OR_RUNTIME_DRIFT')
                math_receipt = verify_native_math(model,case,fixed=fixed)
                nrow,ncol = case.A.shape
                x = _attributes(model,'X',ncol)
                if x is None:
                    return returned
                pending.update(point=x, pi=_attributes(model,'Pi',nrow),
                    vbasis=_attributes(model,'VBasis',ncol,integer=True),
                    cbasis=_attributes(model,'CBasis',nrow,integer=True),
                    native_index=before, native_call=call,
                    native_snapshot=dict(record=_record(budget.path),ledger=ledger),
                    math_receipt=math_receipt)
                return returned

        point = original(case,Proxy(),progress)
        self._authority_check()
        if case_fingerprint(case) != fingerprint:
            raise PermissionError('F1_ORIGINAL_CASE_MUTATED')
        if point is None or not pending:
            self.write('F1_STATE_ADMISSION.json',dict(status='NO_ADMITTED_STATE',
                original_F1_returned_valid_point=point is not None, Native_calls_added=0))
            return point
        strict_path = self._owned('STATIONARY_DISPATCH_REPLAY.json')
        strict = _read(strict_path)
        point_file = self._owned('STATIONARY_DISPATCH_RAW_POINT.npz')
        vector = sha256(np.ascontiguousarray(point,dtype='<f8').tobytes()).hexdigest()
        replay = strict.get('original_matrix_and_96_slot_physical_replay',{})
        if (strict.get('PASS') is not True or strict.get('case_sha') != case.case_sha
                or strict.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
                or replay.get('PASS') is not True or replay.get('case_sha') != case.case_sha
                or strict.get('point_vector_sha256') != vector
                or replay.get('point_sha256') != vector
                or Path(strict.get('point_path','')).resolve() != point_file
                or strict.get('point_file_sha256') != _record(point_file)['sha256']
                or not _same(point,pending['point'])):
            raise PermissionError('F1_ORIGINAL_FULL_REPLAY_REQUIRED')
        with np.load(point_file,allow_pickle=False) as archive:
            if not _same(archive['point'],point):
                raise PermissionError('F1_STRICT_RAW_POINT_FILE_DRIFT')
        self._ledger(budget,pending['native_index'],pending['native_call'])
        arrays = {k:pending[k] for k in ('point','pi','vbasis','cbasis') if pending[k] is not None}
        arrays.update(fixed_ids=fixed[0],fixed_values=fixed[1])
        array_shas = {k:_array_digest(v) for k,v in arrays.items()}
        packet_path = self._owned('F1_SAME_ATTEMPT_STATE.npz')
        # Never overwrite a historical or interrupted state packet.
        with packet_path.open('xb') as stream:
            np.savez_compressed(stream,**arrays)
        binding = dict(self._authority,case=fingerprint, arrays=array_shas,
                       original_math_roundtrip=pending['math_receipt'])
        self.state = CapturedState(_ISSUER,self.token,binding,pending['point'],pending['pi'],
            pending['vbasis'],pending['cbasis'],fixed[0],fixed[1],array_shas,
            _record(strict_path),pending['native_call'],pending['native_index'],
            pending['native_snapshot'],_record(packet_path))
        self._state_digest = self._state_metadata_digest(self.state)
        self.write('F1_STATE_ADMISSION.json',dict(status='ADMITTED_CURRENT_ATTEMPT_ONLY',
            binding=binding, strict_FULL_replay=self.state.strict_receipt,
            state_packet=self.state.packet, F1_completed_Native_receipt=self.state.native_call,
            native_index=self.state.native_index, native_snapshot=self.state.native_snapshot,
            warm_state_is_Global_LB=False, F1_Native_objective_is_Global_LB=False,
            existing_F1_native_calls=1, Native_calls_added=0, performance_benefit_claimed=False))
        return point

    @staticmethod
    def _state_metadata_digest(state):
        return _digest(dict(binding=state.binding,array_shas=state.array_shas,
            strict_receipt=state.strict_receipt,native_call=state.native_call,
            native_index=state.native_index,native_snapshot=state.native_snapshot,
            packet=state.packet))

    def verify_state(self, case, budget):
        self._authority_check()
        s = self.state
        if (s is None or s.issuer is not _ISSUER or s.scope_token is not self.token
                or s.binding['case'] != case_fingerprint(case)
                or self._state_metadata_digest(s) != self._state_digest):
            raise PermissionError('F1_LIVE_SAME_ATTEMPT_STATE_REQUIRED')
        for name in ('point','pi','vbasis','cbasis','fixed_ids','fixed_values'):
            value = getattr(s,name)
            if value is not None and _array_digest(value) != s.array_shas[name]:
                raise PermissionError('F1_CAPTURED_ARRAY_DRIFT:'+name)
        if _record(s.packet['path']) != s.packet or _record(s.strict_receipt['path']) != s.strict_receipt:
            raise PermissionError('F1_SEALED_ADMISSION_EVIDENCE_CHANGED')
        self._ledger(budget,s.native_index,s.native_call)
        return s

    def install(self, model, case, budget):
        """Apply computational starts to the unchanged original full LP only."""
        state = self.verify_state(case,budget)
        if self.installed:
            raise PermissionError('F1_ONE_FRESH_FULL_LP_START_ONLY')
        model.update()
        math_before = verify_native_math(model,case)
        if model.Params.Threads != 1:
            raise PermissionError('F1_ORIGINAL_THREADS_ONE_REQUIRED')
        old_precision = {k:getattr(model.Params,k) for k in PRECISION}
        model.Params.Method = 1
        vbasis = None
        reason = 'COMPLETE_BASIS_UNAVAILABLE'
        if (state.vbasis is not None and state.cbasis is not None
                and np.isin(state.cbasis,(-1,0)).all()):
            vbasis = np.array(state.vbasis,copy=True)
            lo,hi = np.asarray(case.d['lower']),np.asarray(case.d['upper'])
            for j,value in zip(state.fixed_ids,state.fixed_values):
                if vbasis[j] == 0:
                    continue
                if value == lo[j]:
                    vbasis[j] = -1
                elif value == hi[j]:
                    vbasis[j] = -2
                else:
                    reason = 'FORMER_FIXED_NONBASIC_INTERIOR_NO_INVENTED_BASIS'
                    vbasis = None; break
            # An unaffected nonbasic bound must exist.  A superbasic status
            # has no encoded primal value here, so prefer full start vectors.
            if vbasis is not None and (np.any(vbasis == -3)
                    or np.any((vbasis == -1)&~np.isfinite(lo))
                    or np.any((vbasis == -2)&~np.isfinite(hi))
                    or np.any((vbasis == -1)&(state.point != lo))
                    or np.any((vbasis == -2)&(state.point != hi))
                    or np.count_nonzero(vbasis == 0)+np.count_nonzero(state.cbasis == 0) != case.A.shape[0]):
                reason = 'BASIS_COUNT_BOUND_OR_SUPERBASIC_NOT_PROVEN'; vbasis = None
        receipt = dict(schema='V42_V27_CURRENT_ATTEMPT_F1_FULL_LP_START',
            PASS=True, case_sha=case.case_sha, binding=state.binding,
            original_math_roundtrip=math_before, Native_calls_added=0,
            original_full_LP_required_seconds=300., original_F1_required_seconds=120.,
            total_native_cap_seconds=5400, Threads=1, Method=1,
            original_precision_unchanged=True, original_full_LP_not_removed=True,
            no_historical_checkpoint_or_Native_budget_carry=True,
            performance_benefit_claimed=False)
        if vbasis is not None:
            model.setAttr('VBasis',model.getVars(),vbasis.tolist())
            model.setAttr('CBasis',model.getConstrs(),state.cbasis.tolist())
            receipt.update(mode='COMPLETE_SAME_ATTEMPT_BASIS',
                remapped_nonbasic_endpoints=int(np.count_nonzero(vbasis != state.vbasis)))
        elif state.pi is not None:
            model.setAttr('PStart',model.getVars(),state.point.tolist())
            model.setAttr('DStart',model.getConstrs(),state.pi.tolist())
            receipt.update(mode='COMPLETE_SAME_ATTEMPT_PRIMAL_DUAL_START',basis_fallback_reason=reason)
        else:
            receipt.update(mode='COLD_ORIGINAL_FULL_LP',basis_fallback_reason=reason,
                           missing_complete_dual_start=True)
        if receipt['mode'] != 'COLD_ORIGINAL_FULL_LP':
            model.Params.LPWarmStart = 2
            receipt.update(LPWarmStart=2,presolve_preserved_by_computational_start_transport=True)
        math_after = verify_native_math(model,case)
        if (math_after != math_before or model.Params.Method != 1
                or old_precision != {k:getattr(model.Params,k) for k in PRECISION}):
            raise PermissionError('F1_WARMSTART_CHANGED_ORIGINAL_MATH_OR_PRECISION')
        self.installed = True
        self.write('F1_FULL_LP_WARMSTART.json',receipt)
        return receipt

    def select(self, original_full_lp, case, budget, progress=None, *, checker=None, repair=None):
        """Always run original 300s LP, then select the best independent proof."""
        _original_code(original_full_lp,'FULL_LP')
        if checker is None:
            checker = _ORIGINAL_FUNCTIONS['CHECKER']
        if repair is None:
            repair = _ORIGINAL_FUNCTIONS['REPAIR']
        _original_code(checker,'CHECKER'); _original_code(repair,'REPAIR')
        before = len(budget.calls)
        full_dual, _ = original_full_lp(case,budget,progress)
        if len(budget.calls) != before+1:
            raise PermissionError('F1_ORIGINAL_FULL_LP_CALL_REQUIRED')
        full_call = budget.calls[-1]
        if (full_call.get('component') != 'P1' or full_call.get('track') != 'M_LB'
                or full_call.get('label') != LP_LABEL
                or not 0 < full_call.get('requested_seconds',0) <= 300.
                or not 0 < full_call.get('effective_TimeLimit',0) <= 300.
                or full_call.get('precision_parameters') != PRECISION):
            raise PermissionError('F1_ORIGINAL_FULL_LP_LIMIT_OR_PRECISION_DRIFT')
        self._ledger(budget)
        candidates = []
        for kind,dual in (('ORIGINAL_FULL_LP',full_dual),('ORIGINAL_ZERO_SIGNED_DUAL',{})):
            cert = checker(case.A,case.d,dual,case_sha=case.case_sha)
            if cert.get('PASS') is not True or cert.get('case_sha') != case.case_sha:
                raise PermissionError('F1_ORIGINAL_INDEPENDENT_CERTIFICATE_REQUIRED')
            candidates.append(dict(kind=kind,dual=dual,certificate=cert))
        f1_status = 'NO_ADMITTED_F1_STATE'
        if self.state is not None:
            state = self.verify_state(case,budget)
            if state.pi is not None:
                # Original d only: its infinite helpers use unchanged equality
                # implication proofs via certificate_box.check, not F1 bounds.
                try:
                    dual,repair_receipt = repair(case.A,case.d,state.pi)
                    cert = checker(case.A,case.d,dual,case_sha=case.case_sha)
                    if cert.get('PASS') is not True or cert.get('case_sha') != case.case_sha:
                        raise PermissionError('F1_FULL_DOMAIN_EXACT_CERTIFICATE_REQUIRED')
                    candidates.append(dict(kind='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI',dual=dual,
                        certificate=cert,affine_repair=repair_receipt))
                    f1_status = 'INDEPENDENT_ORIGINAL_DOMAIN_BOUND_AVAILABLE'
                except (ValueError,ArithmeticError) as exc:
                    f1_status = 'F1_CANDIDATE_NOT_CERTIFIABLE:'+str(exc)
            else:
                f1_status = 'FINITE_COMPLETE_F1_PI_UNAVAILABLE'
        selected = max(candidates,key=lambda item:Fraction(item['certificate']['exact_bound']))
        cert = dict(selected['certificate'],exact_Global_LB=selected['certificate']['exact_bound'],
            selected_candidate=selected['kind'],F1_Native_objective_used=False,
            F1_restricted_bounds_used=False,original_full_LP_completed_receipt=copy.deepcopy(full_call))
        if 'affine_repair' in selected:
            cert['affine_repair'] = selected['affine_repair']
        self.write('F1_FULL_DOMAIN_LB_SELECTION.json',dict(schema='V42_V27_F1_FULL_DOMAIN_LB',
            PASS=True,case_sha=case.case_sha,f1_status=f1_status,selected=selected['kind'],
            candidates=[dict(kind=c['kind'],certificate=c['certificate']) for c in candidates],
            maximum_exact_bound=cert['exact_bound'],Native_calls_added=0,
            original_full_LP_not_removed=True,performance_benefit_claimed=False))
        self.write('INITIAL_EXACT_ORIGINAL_DUAL.json',selected['dual'])
        self.write('INITIAL_EXACT_LB_CERTIFICATE.json',cert)
        return selected['dual'],cert

    def full_lp_adapter(self, original_full_lp, case, budget, progress=None):
        """Rebind only the original fresh-LP builder; preserve its code object."""
        from v42_may_campaign_native90.a_routing import rebound
        _original_code(original_full_lp,'FULL_LP')
        original_builder = original_full_lp.__globals__['_model']

        def build(current_case, continuous=False):
            model,identity = original_builder(current_case,continuous=continuous)
            if current_case is not case or continuous is not True:
                model.dispose()
                raise PermissionError('F1_ONLY_CURRENT_FULL_CONTINUOUS_LP_BUILDER')
            try:
                if self.state is not None:
                    self.install(model,case,budget)
            except BaseException:
                model.dispose(); raise
            return model,identity

        bound = rebound(original_full_lp,dict(original_full_lp.__globals__,_model=build))
        return self.select(bound,case,budget,progress)
