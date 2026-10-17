"""Dependency and admission contracts, independent of any solver import."""
import math
from .common import digest
from .config import require_day, A_GAP, M_GAP

CHAINS={
    'B0':('REFERENCE','ACTUAL','FRESH'),
    'B1':('A1','ACTUAL','FRESH'),
    'B2':('REFERENCE','K48_M1','M1','ACTUAL','FRESH'),
    'B3':('A1_REUSE','K48_M1','M1','A2','K48_M2','M2','ACTUAL','FRESH'),
}


def case_key(day,arm,stage):
    require_day(day)
    if arm not in CHAINS or stage not in CHAINS[arm]:raise ValueError('CASE_STAGE_AXIS')
    return '/'.join((day,arm,stage))


def require_parent(parent,*,day,arm,stage,source_sha=None):
    require_day(day)
    if any(parent.get(k)!=v for k,v in dict(day=day,arm=arm,stage=stage).items()):
        raise ValueError('CROSS_DATE_ARM_STAGE_PARENT')
    if source_sha is not None and parent.get('source_sha')!=source_sha:raise ValueError('PARENT_SOURCE_DRIFT')
    if parent.get('error') or parent.get('implementation_errors') or not parent.get('finished_UTC'):
        raise ValueError('INCOMPLETE_OR_FAILED_PARENT')
    return parent


def m_outcome(result):
    """Consume the original FULL validator, never a restricted pool verdict."""
    full=(result.get('FULL_feasible') is True and result.get('upper',{}).get('FULL_validated') is True)
    healthy=(result.get('M_stage_execution_PASS') is True and not result.get('error')
        and not result.get('implementation_errors') and bool(result.get('finished_UTC')))
    lb=result.get('global_LB');ub=result.get('global_UB')
    valid_lb=(result.get('independent_Global_LB_validated') is True and result.get('LB_origin')=='K48_INDEPENDENT_GLOBAL'
        and isinstance(lb,(int,float)) and math.isfinite(lb))
    gap=None
    if valid_lb and isinstance(ub,(int,float)) and math.isfinite(ub) and lb<=ub:
        gap=(ub-lb)/max(abs(ub),1e-12)
    certified=bool(full and healthy and gap is not None and gap<=M_GAP)
    timed=result.get('timeout') is True
    status=('IMPLEMENTATION_FAILURE_BEST_FULL_PRESERVED' if not healthy and full else
        'IMPLEMENTATION_FAILURE' if not healthy else
        'TIME_LIMIT_NO_FULL_FEASIBLE_INCUMBENT' if not full and timed else
        'NO_FULL_FEASIBLE_INCUMBENT' if not full else 'GLOBAL_GAP_PASS' if certified else
        'TIME_LIMIT_FULL_FEASIBLE_GAP_NOT_CERTIFIED' if timed else 'FULL_FEASIBLE_GAP_NOT_CERTIFIED')
    return dict(status=status,allow_downstream=full and healthy,FULL_feasible=full,
        Global_Gap=gap,global_gap_certified=certified,
        LB_status='VALID_INDEPENDENT_GLOBAL_LB' if valid_lb else 'GLOBAL_LB_NOT_CERTIFIED',
        restricted_ObjBound_is_Global_LB=False,incumbent_preserved=full)


def require_a2(result,day):
    require_parent(result,day=day,arm='B3',stage='A2')
    gap=result.get('certified_gap')
    if (result.get('PASS') is not True or result.get('FULL_feasible') is not True
            or result.get('P2_calls')!=0 or not isinstance(gap,(int,float))
            or not math.isfinite(gap) or not 0<=gap<=A_GAP
            or result.get('independent_Global_LB_validated') is not True):
        raise ValueError('A2_INDEPENDENT_FULL_AND_HALF_PERCENT_GAP_REQUIRED')
    return result


def require_m1(result,day):
    """Keep the V43 FULL plan checks; generalize only the dated parent."""
    require_parent(result,day=day,arm='B3',stage='M1')
    if not m_outcome(result)['allow_downstream']:raise ValueError('A2_REQUIRES_HEALTHY_FULL_M1')
    plan=result.get('MESS_plan',{})
    if (plan.get('case_sha')!=result.get('case_sha') or not result.get('case_sha')
            or digest({k:v for k,v in plan.items() if k!='plan_sha'})!=plan.get('plan_sha')):
        raise ValueError('A2_M1_PLAN_SHA_OR_CASE_DRIFT')
    if plan.get('P_sign')!='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch' or plan.get('time_axis')!=list(range(96)):
        raise ValueError('A2_ORIGINAL_MESS_SIGN_AXIS_REQUIRED')
    binding=plan.get('case_binding',{})
    if any(binding.get(k)!=v for k,v in dict(case_sha=result['case_sha'],arm='B3',stage='M1',day=day).items()):
        raise ValueError('A2_M1_PHYSICAL_CASE_BINDING_REQUIRED')
    parent=result.get('fixed_AIDC',{})
    if (parent.get('arm'),parent.get('stage'),parent.get('day'),parent.get('reused_exact_A1'))!=('B1','A1',day,True):
        raise ValueError('A2_SAME_DAY_B1_A1_REUSE_REQUIRED')
    return plan


def next_stage(day,arm,completed,*,b1_a1=None):
    """A failure blocks this case's descendants only."""
    require_day(day)
    for stage in CHAINS[arm]:
        if stage not in completed:
            if stage=='A1_REUSE' and b1_a1 is None:return dict(status='WAIT_SAME_DAY_B1_A1',stage=stage)
            return dict(status='READY',stage=stage)
        row=completed[stage]
        if stage in ('M1','M2'):
            if not m_outcome(row)['allow_downstream']:return dict(status='BLOCKED_DEPENDENCY',stage=stage)
        elif row.get('PASS') is not True:return dict(status='BLOCKED_DEPENDENCY',stage=stage)
        if stage=='A2':require_a2(row,day)
    return dict(status='COMPLETE',stage=None)
