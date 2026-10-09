"""Original stationary dispatch, fixing FULL integer representatives by bounds.

No floating point is rounded or repaired. A new raw LP point must pass the
unchanged literal integer, FULL rows and 96-slot physical gate.
"""
import numpy as np
from v42_may_campaign_native90 import m_stage as original
from .fixed_pattern import discrete_stationary
from .common import atomic

def validated_start(case,budget,progress):
    ids,values=discrete_stationary(case)
    model,identity=original._model(case,continuous=True)
    try:
        variables=model.getVars();low=np.asarray(model.getAttr('LB'));high=np.asarray(model.getAttr('UB'))
        if np.any(values<low[ids]) or np.any(values>high[ids]):raise ValueError('STATIONARY_PATTERN_OUTSIDE_ORIGINAL_BOUNDS')
        low[ids]=values;high[ids]=values
        model.setAttr('LB',variables,low.tolist());model.setAttr('UB',variables,high.tolist())
        model.Params.Method=1;model.update()
        atomic(case.output/'STATIONARY_DISPATCH_MODEL_IDENTITY.json',dict(identity,
            fixed_FULL_integer_representatives=len(ids),original_rows_and_objective_retained=True,
            domain_restriction_applies_only_to_candidate=True,point_rounding=False))
        if progress:progress(dict(phase='M_CURRENT_DAY_STATIONARY_DISPATCH_FEASIBILITY'))
        budget.native_optimize(model,component='FEASIBILITY_LP',track='M_START',
            label='CURRENT_DAY_STATIONARY_FULL_INTEGER_REPRESENTATIVE_BOUNDS',requested_seconds=120.)
        if model.Status!=2 or not model.SolCount:
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(PASS=False,
                reason='NO_OPTIMAL_CONTINUOUS_WITNESS',Native_status=int(model.Status)));return None
        point=np.asarray(model.getAttr('X'),dtype=np.float64)
        packet=case.output/'STATIONARY_DISPATCH_RAW_POINT.npz';np.savez_compressed(packet,point=point)
        try:
            with budget.cost('integer_physical_validation','stationary_dispatch_original_FULL_replay'):
                receipt=original._strict_ub(case,packet,{})
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(receipt,case_sha=case.case_sha));return point
        except ValueError as exc:
            atomic(case.output/'STATIONARY_DISPATCH_REPLAY.json',dict(PASS=False,reason=str(exc),
                case_sha=case.case_sha,invalid_start_not_supplied=True));return None
    finally:model.dispose()
