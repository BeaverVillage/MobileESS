"""Pure scheduling decisions; preparation does not launch a campaign process."""
from .config import MAIN_ORDER,B2_ORDER,DAYS,policy
from .stages import CHAINS

TERMINAL={'COMPLETE','FAILED','BLOCKED','INPUT_NOT_READY'}


def assignments(cases,running):
    """Keep both B2 slots, with Main waiting until the B2 queue is drained."""
    busy={(r['day'],r['arm']) for r in running};slots={r['worker_slot'] for r in running if r['arm']=='B2'}
    b2=[(d,a) for d,a in B2_ORDER if cases.get((d,a),'READY') not in TERMINAL and (d,a) not in busy]
    if any(r['arm']!='B2' for r in running):return []
    if b2 or slots:
        return [dict(day=d,arm=a,worker_slot=slot,lane='B2')
            for slot,(d,a) in zip((s for s in (1,2) if s not in slots),b2)]
    for d,a in MAIN_ORDER:
        if cases.get((d,a),'READY') not in TERMINAL:
            return [dict(day=d,arm=a,worker_slot=1,lane='MAIN')]
    return []


def manifest():
    return dict(schema='V44_CAMPAIGN_SCHEDULER_V1',**policy(),
        Main_order=[dict(day=d,arm=a) for d,a in MAIN_ORDER],
        B2_queue=[dict(day=d,arm=a) for d,a in B2_ORDER],stage_dependencies=CHAINS,
        B2_reference='SAME_DAY_PR189_R0_Q50_NO_AIDC_OPTIMIZATION',
        B2_waits_for_B0_Actual_or_B1=False,B3_A1='EXACT_SAME_DAY_B1_A1',
        locks=dict(external='COORDINATOR_OWNS_ALL_LEGACY_SHARED_LOCKS',
            worker='MAIN_SLOT_1_OR_B2_SLOT_1_2_PLUS_DAY_ARM_OS_LOCK',PID_creation_verified=True,
            external_lock_bypass=False),
        resume='NEW_ATTEMPT_ONLY_AFTER_PID_CREATION_EXIT_OS_LOCK_AND_NATIVE_INFLIGHT_RECONCILIATION',
        timeout='FULL_VALIDATED_HEALTHY_M_INCUMBENT_MAY_CONTINUE_WITH_GAP_NOT_CERTIFIED;NO_FULL_BLOCKS_ONLY_DESCENDANTS',
        A2_acceptance='INDEPENDENT_ORIGINAL_FULL_AND_GLOBAL_GAP_LE_0.005',
        process_files='DAY/ARM/ATTEMPT/STAGE/{tmp,Native_ledgers,Native_logs};LEGACY_NODEFILES_IN_STAGE/tmp/gurobi',
        stages_timing=['Build','Native','Actual','Current_AC','Fresh'])
