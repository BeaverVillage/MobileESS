"""Acceptance boundaries; a necessary-condition pass is not a native plan."""
from .common import require


def require_a1(resource):
    require(resource.get('PASS') is True and resource.get('full_A1_authorized_after_this_PASS') is True,
            'NECESSARY_RESOURCE_FAILURE_STOP_BEFORE_A1')


def require_next(stage, receipts):
    order=('A1','M1','A2','M2')
    require(stage in order,'CANONICAL_STAGE')
    for prior in order[:order.index(stage)]:
        require(receipts.get(prior,{}).get('accepted_native_plan') is True,'PRIOR_NATIVE_STAGE_NOT_ACCEPTED')


def require_kernel(plan, fresh_ac, upstream):
    require(plan.get('stage')=='M2' and plan.get('accepted_native_plan') is True,'FINAL_NATIVE_M2_REQUIRED')
    require(fresh_ac.get('PASS') is True and fresh_ac.get('plan_sha')==plan.get('sha256')
            and len(str(plan.get('sha256','')))==64
            and fresh_ac.get('execution_layer')=='DDAY_ACTUAL','FRESH_AC_FINAL_PLAN_REQUIRED')
    require(set(upstream)=={'workload','placement','runtime','MESS_PQ','grid_anchor'}
            and all(isinstance(s,str) and len(s)==64 for s in upstream.values()),'KERNEL_UPSTREAM_SHA_BINDING')
    return True
