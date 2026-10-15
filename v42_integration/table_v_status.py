"""Evidence based A-stage status; a missing certificate never means zero gap."""
import math


def classify_a_result(result):
    if not result:
        return 'NOT_RUN'
    native = result.get('Native_call') or result.get('reused_native_call') or {}
    status = result.get('Gurobi_Status', result.get('solver_status', native.get('status')))
    feasible = result.get('FULL_feasible') is True and result.get('FULL_point_replay', {}).get('PASS') is True
    dw = result.get('DW') or {}
    lb = result.get('AIDC_Global_LB')
    ub = result.get('AIDC_Global_UB')
    certified = dw.get('LB_certified') is True and dw.get('full_domain_pricing_complete') is True
    finite = lambda v: type(v) in (int, float) and math.isfinite(v)
    if feasible and certified and finite(lb) and finite(ub) and ub > 0 and lb <= ub:
        gap = max(0., (ub-lb)/ub)
        return 'P1_GLOBAL_GAP_TARGET_MET' if gap <= .005 else 'DW_GLOBAL_LB_CERTIFIED'
    if feasible:
        return 'FULL_FEASIBLE_OPTIMALITY_UNPROVEN'
    if status == 3:
        return 'INFEASIBLE_REPORTED_CURRENT_MATRIX'
    if status == 9:
        return 'TIME_LIMIT_NO_FEASIBLE'
    if status == 11:
        return 'INTERRUPTED_NO_FEASIBLE'
    if dw.get('phase_I_status') not in (None, 'PASS', 'CERTIFIED', 'PHI_ZERO_CERTIFIED'):
        return 'DW_PHASE_I_NOT_CERTIFIED'
    if dw and not certified:
        return 'DW_PRICING_INCOMPLETE'
    if certified and finite(lb):
        return 'DW_GLOBAL_LB_CERTIFIED'
    return result.get('status') or 'NOT_CERTIFIED'


def failed_stage_status(stages, stage):
    result = stages.get(stage, {}).get('result') or {}
    return classify_a_result(result) if stage.startswith('A') and result else result.get('status', 'NOT_CERTIFIED')
