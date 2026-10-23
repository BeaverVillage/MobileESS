"""May01-only execution HOLD and exact original stage/budget contracts."""
from .may01_common import *
from v44.stages import CHAINS

def request(day,arm):
    if day!='2025-05-01':raise PermissionError('ONLY_MAY01_NEW_EXECUTION_ALLOWED')
    if arm not in CHAINS:raise ValueError('ORIGINAL_B0_B1_B2_B3_REQUIRED')
    return list(CHAINS[arm])

def plan():
    from v44 import config
    old=read(OLD/'CAMPAIGN_EXECUTION_HOLD.json')
    return put('MAY01_B0_B1_B2_B3_STAGE_READINESS.json',dict(
        experiment='V2_add',PR=236,day='2025-05-01',status='PRESTART_BLOCKED_WITH_EVIDENCE',
        original_source=SOURCE,base=BASE,chains={a:request('2025-05-01',a) for a in CHAINS},
        budgets=old['budgets'],runtime_settings=old['original_r043_overlay'],
        worker_policy=old['current_worker_policy'],official_campaign_executed=False,
        May02_to_07_new_execution_allowed=False,
        stage_bindings=dict(B0='Exact original FCFS replay and fresh finite AC evidence',
            A1='Original FULL option generator retained; IEEE8500 variable-AIDC grid/policy binding unresolved',
            M1='Sealed fixed-B0 M1 + literal original-row delayed master with on-demand auxiliaries + independent original-coordinate oracle, Native0 only',
            A2='Original fixed-M1 handoff and FULL variable-AIDC case not bound',
            M2='Original same-date A2 freeze and full optimizer case not bound',
            K48='Original current-case physical metadata/pricing/global-LB proof interface not bound',
            Adaptive_Beam='Original source preserved; same-case delayed-master adapter not certified',
            Direct_Joint='Original source budget/gap retained; no optimizer run or certified Global Bound',
            Actual='Native CommonClock TIME with all original delays; physical voltage FAIL',
            Fresh='Independent contexts; finite-schedule results only'),
        final_hardware_frozen=False,arm_hardware_policy_must_be_identical=True,
        official_campaign_command_runnable=False,
        preparation_commands=['python -m v2_add_preflight.may01_execution plan',
            'python -m v2_add_preflight.may01_exact_native','python -m v2_add_preflight.may01_verify'],
        future_campaign_command='python -m v2_add_preflight.may01_execution campaign --approval <explicit-user-approval.json>',
        SCIENTIFIC_SIMULATION_READY=False,FIELD_INSTALLATION_UNVERIFIED=True,
        field_certification_is_not_the_scientific_blocker=True))

def campaign(approval):
    # Read the gate before approval IO; neither a forged readiness file nor an
    # old IEEE123 Worker can activate the unbound production stage handlers.
    p=OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json'
    if not p.exists() or read(p).get('status')!='READY_FOR_MAY01_CAMPAIGN_APPROVAL':
        raise PermissionError('PRESTART_BLOCKED_WITH_EVIDENCE')
    raise PermissionError('ORIGINAL_FULL_STAGE_HANDLERS_AND_SEPARATE_EXPLICIT_USER_APPROVAL_REQUIRED')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','campaign']);p.add_argument('--approval');args=p.parse_args()
    plan() if args.mode=='plan' else campaign(args.approval)
