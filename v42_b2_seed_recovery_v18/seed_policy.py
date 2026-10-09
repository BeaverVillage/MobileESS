"""B2-only seed stopping policy, retaining the original strict FULL verifier."""
from v42_may_campaign_native90 import m_stage as original
from .common import atomic, record, now
import numpy as np

VERSION = 'B2_SEED_GAP_3_PERCENT_REQUEST_CAP_V1'
SEED_GAP = .03


def seed_model(case, continuous=False):
    model, identity = original._model(case, continuous=continuous)
    if not continuous:
        model.Params.MIPGap = SEED_GAP
        identity = dict(identity, solver_parameters=dict(identity['solver_parameters'], MIPGap=SEED_GAP),
                        seed_policy=VERSION, final_acceptance='ORIGINAL_EXACT_UB_LB_ONLY')
    return model, identity


def seed_integer(case, budget, progress):
    from .execution import current
    context = current()
    start = None
    # prepare() already exhausted candidate LPs. Reaching this function means
    # no independently valid case.point exists. Do not repeat candidate solves.
    model, identity = seed_model(case)
    try:
        model.Params.MIPFocus=1
        model.Params.SolutionLimit=1
        identity.update(initialization_only=True,MIPFocus=1,SolutionLimit=1,
            first_feasible_exit_still_requires_original_FULL_replay=True)
        atomic(case.output/'SAME_DAY_SEED_MODEL_IDENTITY.json',identity)
        if start is not None:
            model.setAttr('Start',model.getVars(),start.tolist())
        if progress:
            progress(dict(phase='M_SAME_DAY_P1_INTEGER_SEED',day=case.bundle['day'],arm='B2'))
        # The requested seed allowance is 900, also after a carried prior attempt.
        budget.native_optimize(model,component='P1',track='M_SEED',
            label='CURRENT_DAY_UNRESTRICTED_P1_SEED',requested_seconds=900.)
        if not model.SolCount and start is None:
            point, receipt = None, dict(status='INCONCLUSIVE' if model.Status==3 else 'TIME_LIMIT_NO_VALID_INCUMBENT',
                reason='NO_SAME_DAY_ORIGINAL_VALID_INTEGER_SEED',Native_status=int(model.Status))
        else:
            raw = np.asarray(model.getAttr('X'),dtype=np.float64) if model.SolCount else start
            packet = case.output/'SAME_DAY_NATIVE_SEED_RAW_POINT.npz'
            np.savez_compressed(packet,point=raw)
            try:
                with budget.cost('integer_physical_validation','M_seed_physical_replay'):
                    receipt = original._strict_ub(case,packet,{})
                atomic(case.output/'SAME_DAY_NATIVE_SEED_STRICT_REPLAY.json',dict(receipt,case_sha=case.case_sha,
                    start_used=start is not None,Native_SolCount=int(model.SolCount),policy=VERSION))
                point = raw
            except ValueError as exc:
                point,receipt = None,dict(status='PHYSICAL_FAILURE',reason=str(exc),replay=original.validate_candidate(case,raw))
    finally:
        model.dispose()
    if point is not None:
        return point, receipt  # Original _strict_ub has already replayed FULL.
    row = dict(receipt, UTC=now(), case_sha=case.case_sha, policy=VERSION,
        accepted=False, PASS=False, certified_UB=None, certified_LB=None, certified_gap=None,
        completed_Native_Runtime=budget.used(), remaining_Native_seconds=budget.remaining(),
        native_ledger=record(budget.path), automatic_retry=False,
        recovery='SEALED_SAME_DATE_NEW_ATTEMPT_WITH_CUMULATIVE_NATIVE_CARRY_REQUIRED',
        runtime_reset_allowed=False, historical_point_or_bound_transfer_allowed=False)
    if receipt.get('status') == 'TIME_LIMIT_NO_VALID_INCUMBENT':
        row['reason'] = 'B2_SEED_CALL_ENDED_WITHOUT_ORIGINAL_VALID_INTEGER_INCUMBENT'
    atomic(case.output / 'B2_SEED_FAILURE_AND_RECOVERY.json', row)
    if progress:
        progress(dict(phase='M_SEED_FAILED_REQUIRES_EXPLICIT_RECOVERY', seed_failure=row))
    return None, row
