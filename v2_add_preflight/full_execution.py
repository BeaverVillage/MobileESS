"""V2_add execution HOLD, source-budget contract and safe preparation commands."""
from .full_common import *
from v44.stages import CHAINS

def plan():
    init()
    # Read original constants/overlay, without constructing a permit, touching
    # a Worker ledger, or routing any stage into the IEEE123 campaign.
    from v44 import config
    import ast
    tree=ast.parse((ROOT/'v44/q250_m4.py').read_text(encoding='utf-8'))
    overlay=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='overlay')
    result=next(n for n in ast.walk(overlay) if isinstance(n,ast.Return)).value
    literal={k.arg:ast.literal_eval(k.value) for k in result.keywords if isinstance(k.value,(ast.Constant,ast.List,ast.Tuple))}
    hold=dict(experiment_id='V2_add',status='PRESTART_BLOCKED_WITH_EVIDENCE',
        ready_for_user_campaign_approval=False,SCIENTIFIC_SIMULATION_READY=False,FIELD_INSTALLATION_UNVERIFIED=True,
        source=SOURCE,baseline=BASE,original_chains={a:list(v) for a,v in CHAINS.items()},
        candidate=dict(feeder='IEEE8500 Balanced',beta_BG=2.,Planning='S0 original Reg12/Cap9',Actual='S1_03 original Reg12 plus3 serial banks',
            AIDC=12,STA=12,mobile_service_locations=24,GPU=780,MESS=8,initial=INITIAL),
        budgets=dict(A1=config.A_SECONDS,A2=config.A_SECONDS,K48_M1=config.K48_SECONDS,K48_M2=config.K48_SECONDS,
            M1=config.JOINT_SECONDS,M2=config.JOINT_SECONDS,A_gap=config.A_GAP,M_gap=config.M_GAP,
            effective_r043_Joint_single_call_cap=literal['Joint_call_cap']),
        original_r043_overlay={k:literal[k] for k in ('Workers','M_Threads','A_Threads','Actual_Workers','Root_Method','K48_Threads','K48_Method','K48_total','Joint_total','Joint_call_cap')},
        runtime=str(RUN/'official_may01_07_HOLD'),Python=str(RUNTIME/'.venv/Scripts/python.exe'),
        preparation_commands=['python -m v2_add_preflight.full_execution plan','python -m v2_add_preflight.full_grid',
            'python -m v2_add_preflight.full_native','python -m v2_add_preflight.full_pack','python -m v2_add_preflight.full_days','python -m v2_add_preflight.full_verify'],
        future_campaign_command_template='python -m v2_add_preflight.full_execution campaign --approval <explicit-user-approval.json>',
        campaign_command_runnable=False,official_campaign_executed=False,optimization_calls=0,
        current_worker_policy=dict(isolated_preparation_processes=True,heavy_Native_workers=0,below_normal_priority=True,
            own_affinity_only=[12,13],Native0_RSS_limit_GiB=4,system_available_reserve_GiB=5,protected_workers_not_modified=True),
        stage_bindings=dict(REFERENCE='Original R0/Q50+CC4 and original daily C1, finite diagnostic certified',
            ACTUAL='Original B0 FCFS and exact C1; no official controller or Worker run',FRESH='New DSS TIME contexts, finite diagnostics',
            A1='Original complete-option builder/acceptance; whole8500 AIDC-variable grid not bound',
            M1='Original8 mobility plus complete96 fixed-B0 affine matrix/domain pack; monolithic resource gate and original solver-case interface unresolved',
            A2='Requires independent A2 fixed-M1 FULL case',M2='Requires original FULL M2 and same-date A2 anchor',
            K48='Original independent Global-LB interface needs complete current FULL CSR/domain/physical metadata',
            Adaptive_Beam='Original method needs same FULL case and independent validator',Direct_Joint='Original method needs same FULL case and original call caps'),
        checkpoints='Existing fail-closed Scheduler: source/input/scenario/acceptance/artifact hashes, no in-flight budget reset, OS lease; real optimizer handlers remain unbound',
        readiness_excludes_field_certification=True,
        blocking_reasons=['causal initial TIME voltage, Planning TIME and new IDC LV event voltage','campaign AIDC FULL/policy/Current-AC integration',
            'monolithic resource clearance and original current-case K48/Beam/Joint binding','all seven dated whole120 physical PASS and remaining dated optimizer coefficient preparation'],
        no_Golden414_acceptance=True,no_arbitrary_source_or_rating_or_beta_or_route_changes=True)
    return put('CAMPAIGN_EXECUTION_HOLD.json',hold)

def require_campaign(approval):
    cert=read(OUT/'FINAL_INTEGRATION_CERTIFICATION.json')
    if cert.get('status')!='READY_FOR_USER_CAMPAIGN_APPROVAL':raise PermissionError('PRESTART_BLOCKED_WITH_EVIDENCE')
    # No real FULL stage adapters are installed by this preparation-only module.
    # A forged JSON readiness label cannot activate the original IEEE123 worker.
    raise PermissionError('CERTIFIED_REAL_IEEE8500_FULL_HANDLERS_AND_EXPLICIT_USER_APPROVAL_REQUIRED')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','campaign']);p.add_argument('--approval');a=p.parse_args()
    if a.mode=='plan':plan()
    else:require_campaign(a.approval)
