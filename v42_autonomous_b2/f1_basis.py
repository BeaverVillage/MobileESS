"""Current-attempt original basis / primal simplex computational start.

Inherit the unchanged V27 source, FULL promotion, Native receipts and
independent checker. Only a proved complete original basis selects
Method0/LPWarmStart2 at the exact original Native call. Installation keeps
Method1/LPWarmStart1 until that entry; fallback retains Method1 and 300s.
"""
import copy
import math

import numpy as np
from v42_autonomous_b2 import f1_state as v27


def transport_basis(*, vbasis, cbasis, point, lower, upper, types,
                    fixed_ids, fixed_values, rows):
    """Keep original basic columns/slacks; remap exact nonbasic endpoints.

    The original solved F1 returned the nonsingular basis. Bound relaxation
    leaves its basis matrix unchanged. A narrowly free, unfixed continuous
    superbasic column at exact zero retains its zero RHS contribution. This
    computational start is not a feasibility, optimum, or lower-bound proof.
    """
    fail = lambda reason: dict(eligible=False, reason=reason)
    if vbasis is None or cbasis is None:
        return fail('COMPLETE_BASIS_UNAVAILABLE')
    v, c = np.asarray(vbasis), np.asarray(cbasis)
    x, lo, hi, t = map(np.asarray, (point, lower, upper, types))
    ids, values = np.asarray(fixed_ids), np.asarray(fixed_values)
    n = len(lo)
    if (v.shape != (n,) or c.shape != (rows,) or x.shape != (n,)
            or hi.shape != (n,) or t.shape != (n,)
            or v.dtype.kind not in 'iu' or c.dtype.kind not in 'iu'
            or not np.isin(v, (-3,-2,-1,0)).all()
            or not np.isin(c, (-1,0)).all() or not np.isfinite(x).all()
            or np.isnan(lo).any() or np.isnan(hi).any() or np.any(lo > hi)
            or ids.ndim != 1 or ids.dtype.kind not in 'iu'
            or values.shape != ids.shape or not np.isfinite(values).all()
            or len(set(ids)) != len(ids) or np.any(ids < 0) or np.any(ids >= n)):
        return fail('INCOMPLETE_OR_INVALID_AXIS_STATUS')
    out = v.copy()
    for j, value in zip(ids, values):
        if x[j] != value or value < lo[j] or value > hi[j]:
            return fail('FIXED_POINT_OR_ORIGINAL_BOUND_DRIFT')
        # A fixed original continuous column is not eligible for the narrow
        # superbasic exception even when its old fixed value happened to be0.
        if v[j] == -3:
            return fail('FIXED_SUPERBASIC_NOT_ELIGIBLE')
        if v[j] == 0:
            continue
        if value == lo[j]:
            out[j] = -1
        elif value == hi[j]:
            out[j] = -2
        else:
            return fail('FORMER_FIXED_NONBASIC_INTERIOR_NO_INVENTED_BASIS')
    free = out == -3
    fixed = np.zeros(n, dtype=bool); fixed[ids] = True
    if np.any(free & (~np.isneginf(lo) | ~np.isposinf(hi) | (t != 'C')
                      | (x != 0.) | fixed)):
        return fail('SUPERBASIC_NOT_UNFIXED_ORIGINAL_FREE_CONTINUOUS_EXACT_ZERO')
    if (np.any((out == -1) & (~np.isfinite(lo) | (x != lo)))
            or np.any((out == -2) & (~np.isfinite(hi) | (x != hi)))):
        return fail('NONBASIC_EXACT_ORIGINAL_FINITE_ENDPOINT_REQUIRED')
    if np.count_nonzero(out == 0) + np.count_nonzero(c == 0) != rows:
        return fail('COMPLETE_ORIGINAL_BASIS_COUNT_REQUIRED')
    if not np.array_equal(np.flatnonzero(out == 0),np.flatnonzero(v == 0)):
        return fail('ORIGINAL_BASIC_COLUMNS_CHANGED')
    return dict(eligible=True, vbasis=out, cbasis=c.copy(),
        remapped_nonbasic_endpoints=int(np.count_nonzero(v != out)),
        free_continuous_exact_zero_superbasics_retained=int(free.sum()),
        original_basic_columns_and_slacks_unchanged=True,
        basis_nonsingularity_inherited_from_completed_original_F1=True,
        computational_start_only=True, Global_LB_authority=False)


class Scope(v27.Scope):
    def _authority_now(self):
        return dict(super()._authority_now(),
            computational_basis_adapter_source=v27._record(__file__))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._primal_model = None
        self._primal_basis = None
        self._primal_receipt = None
        self._full_lp_entered = False

    def install(self, model, case, budget):
        state = self.verify_state(case,budget)
        if self.installed:
            raise PermissionError('F1_ONE_FRESH_FULL_LP_START_ONLY')
        decision = transport_basis(vbasis=state.vbasis, cbasis=state.cbasis,
            point=state.point,lower=case.d['lower'],upper=case.d['upper'],
            types=case.d['types'],fixed_ids=state.fixed_ids,
            fixed_values=state.fixed_values,rows=case.A.shape[0])
        if not decision['eligible']:
            return super().install(model,case,budget)
        model.update()
        before = v27.verify_native_math(model,case)
        if model.Params.Threads != 1:
            raise PermissionError('F1_ORIGINAL_THREADS_ONE_REQUIRED')
        precision = {k:getattr(model.Params,k) for k in v27.PRECISION}
        # Original fresh-LP bytecode sets Method1 after its builder returns.
        # Method0 is selected only at its exact scoped Native call entry.
        model.Params.Method = 1
        model.setAttr('VBasis',model.getVars(),decision['vbasis'].tolist())
        model.setAttr('CBasis',model.getConstrs(),decision['cbasis'].tolist())
        model.Params.LPWarmStart = 1
        model.update()
        if (before != v27.verify_native_math(model,case)
                or precision != {k:getattr(model.Params,k) for k in v27.PRECISION}
                or model.Params.Threads != 1 or model.Params.Method != 1
                or model.Params.LPWarmStart != 1):
            raise PermissionError('F1_V28_BASIS_INSTALL_MATH_OR_PRECISION_DRIFT')
        receipt = dict(schema='V42_V31_CURRENT_ATTEMPT_ORIGINAL_BASIS_PRESOLVED_PRIMAL',
            PASS=True,case_sha=case.case_sha,binding=state.binding,
            original_math_roundtrip=before,mode='COMPLETE_SAME_ATTEMPT_ORIGINAL_BASIS',
            LPWarmStart=1,Method_at_builder_return=1,Method_at_approved_Native_entry=0,
            LPWarmStart_at_builder_return=1,LPWarmStart_at_approved_Native_entry=2,
            Threads=1,original_precision_unchanged=True,
            original_F1_required_seconds=120.,original_full_LP_required_seconds=300.,
            total_native_cap_seconds=5400,Native_calls_added=0,
            original_full_LP_not_removed=True,performance_benefit_claimed=False,
            F1_Native_objective_is_Global_LB=False,
            original_unpresolved_basis_computational_start=False,
            original_basis_installed_before_Native_entry=True,
            original_basis_to_presolved_start_transport_planned=True,
            presolved_basis_identity_unchanged_claimed=False,
            **{k:val for k,val in decision.items() if k not in ('vbasis','cbasis','eligible')})
        self.installed = True
        self._primal_model = model
        self._primal_basis = decision
        self.write('F1_FULL_LP_WARMSTART.json',receipt)
        self._primal_receipt = v27._record(self._owned('F1_FULL_LP_WARMSTART.json'))
        return receipt

    def _budget_proxy(self, case, budget):
        scope = self
        class Proxy:
            def __getattr__(self, name):
                return getattr(budget,name)

            def native_optimize(self, model, callback=None, **kwargs):
                # Validate exact original one-call location BEFORE delegation.
                requested = kwargs.get('requested_seconds')
                if (scope._full_lp_entered or budget.inflight is not None
                        or set(kwargs) != {'component','track','label','requested_seconds'}
                        or callback is not None
                        or kwargs.get('component') != 'P1' or kwargs.get('track') != 'M_LB'
                        or kwargs.get('label') != v27.LP_LABEL
                        or isinstance(requested,bool) or not isinstance(requested,(int,float))
                        or not math.isfinite(requested) or not 0 < requested <= 300.
                        or requested != min(300.,budget.remaining(reserve=budget.final_reserve))):
                    raise PermissionError('F1_V28_EXACT_ORIGINAL_FULL_LP_CALL_REQUIRED')
                scope._authority_check()
                scope._ledger(budget)
                scope._full_lp_entered = True
                before = len(budget.calls)
                if scope._primal_model is not None:
                    if model is not scope._primal_model:
                        raise PermissionError('F1_V28_INSTALLED_CURRENT_MODEL_REQUIRED')
                    state = scope.verify_state(case,budget)
                    if (v27._record(scope._owned('F1_FULL_LP_WARMSTART.json')) != scope._primal_receipt
                            or model.Params.Threads != 1 or model.Params.Method != 1
                            or model.Params.LPWarmStart != 1):
                        raise PermissionError('F1_V28_ORIGINAL_RESET_OR_RECEIPT_DRIFT')
                    v27.verify_native_math(model,case)
                    # Reconstruct from sealed original state every time. The
                    # cached mutable decision is never authority for a basis.
                    d = transport_basis(vbasis=state.vbasis,cbasis=state.cbasis,
                        point=state.point,lower=case.d['lower'],upper=case.d['upper'],
                        types=case.d['types'],fixed_ids=state.fixed_ids,
                        fixed_values=state.fixed_values,rows=case.A.shape[0])
                    if (not d['eligible']
                            or not np.array_equal(model.getAttr('VBasis'),d['vbasis'])
                            or not np.array_equal(model.getAttr('CBasis'),d['cbasis'])):
                        raise PermissionError('F1_V28_INSTALLED_BASIS_CHANGED')
                    # The original budget applies these exact original policy
                    # values again. No precision or per-call cap is increased.
                    for key,val in v27.PRECISION.items():
                        setattr(model.Params,key,val)
                    model.Params.TimeLimit = min(float(requested),budget.remaining())
                    # Use the verified original basis to derive/crush starts
                    # on the presolved FULL LP. Gurobi may construct a new
                    # presolved basis; its identity is not claimed unchanged.
                    model.Params.LPWarmStart = 2
                    model.Params.Method = 0
                    actual = dict(Method=int(model.Params.Method),LPWarmStart=int(model.Params.LPWarmStart),
                        Threads=int(model.Params.Threads),TimeLimit=float(model.Params.TimeLimit),
                        precision={k:getattr(model.Params,k) for k in v27.PRECISION})
                    if (actual['Method'] != 0 or actual['LPWarmStart'] != 2 or actual['Threads'] != 1
                            or actual['precision'] != v27.PRECISION
                            or not 0 < actual['TimeLimit'] <= requested <= 300.):
                        raise PermissionError('F1_V28_ACTUAL_COMPUTATIONAL_PARAMETERS_DRIFT')
                    scope.write('F1_FULL_LP_COMPUTATIONAL_ENTRY.json',dict(
                        schema='V42_V31_APPROVED_FULL_LP_PRESOLVED_NATIVE_ENTRY',status='ABOUT_TO_DELEGATE',
                        Native_call_completed=False,call_index=before,original_call=kwargs,
                        actual_parameters=actual,original_math_roundtrip=v27.verify_native_math(model,case),
                        basis_start_receipt=scope._primal_receipt,state_packet=state.packet,
                        Native_calls_added=0,performance_benefit_claimed=False))
                returned = budget.native_optimize(model,callback,**kwargs)
                if len(budget.calls) != before + 1 or budget.inflight is not None:
                    raise PermissionError('F1_V28_EXACTLY_ONE_COMPLETED_FULL_LP_CALL_REQUIRED')
                if scope._primal_model is not None:
                    call = copy.deepcopy(budget.calls[-1])
                    if (model.Params.Method != 0 or model.Params.LPWarmStart != 2
                            or model.Params.Threads != 1
                            or {k:getattr(model.Params,k) for k in v27.PRECISION} != v27.PRECISION
                            or call.get('effective_TimeLimit') != model.Params.TimeLimit
                            or call.get('precision_parameters') != v27.PRECISION):
                        raise PermissionError('F1_V28_COMPLETED_CALL_PARAMETER_DRIFT')
                    scope._ledger(budget)
                    entry = v27._read(scope._owned('F1_FULL_LP_COMPUTATIONAL_ENTRY.json'))
                    entry.update(status='COMPLETED',Native_call_completed=True,
                        completed_original_Native_call=call)
                    scope.write('F1_FULL_LP_COMPUTATIONAL_ENTRY.json',entry)
                return returned
        return Proxy()

    def full_lp_adapter(self, original_full_lp, case, budget, progress=None):
        from v42_may_campaign_native90.a_routing import rebound
        v27._original_code(original_full_lp,'FULL_LP')
        builder = original_full_lp.__globals__['_model']
        def build(current_case, continuous=False):
            model,identity = builder(current_case,continuous=continuous)
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
        return self.select(bound,case,self._budget_proxy(case,budget),progress)
