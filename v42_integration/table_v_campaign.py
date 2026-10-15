"""Four real Table V executors on the existing durable production date loop.

Public preparation is independent of permission to launch Heavy solvers. A
31-day wiring audit cannot grant a May31 launch or certify physical results.
"""
from copy import deepcopy
import gc
import importlib
import json
from pathlib import Path

from .a_engine import digest
from .m_engine import file_record, _write
from .table_v_dates import context_day, require_day

SCHEMA='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1'
ARMS=('B0','B1','B2','B3')
STAGES={'B0':(), 'B1':('A1',), 'B2':('M1',), 'B3':('A1','M1','A2','M2')}


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def executor_sources():
    from .table_v_run import adapters
    root=Path(__file__).resolve().parents[1]
    return adapters()+[file_record(Path(__file__).with_name('release_production_campaign.py'))]+[
        file_record(root/'tools'/name) for name in ('run_v42_table_v.py',
            'run_v42_production_campaign.py','run_v42_table_v_serial_arms.py')]


def describe_case(context,arm):
    """Inspect actual production callables and public inputs without building."""
    from .table_v_flex_planning import require_flex_context
    require_flex_context(context);day=context_day(context)
    if arm not in ARMS:raise ValueError('TABLE_V_ORIGINAL_FOUR_ARMS_REQUIRED')
    targets=dict(A='v42_integration.table_v_a:execute_current_a',
        M='v42_integration.table_v_mess:TableVMessStages',
        K48='v42_integration.table_v_k48:run_current_k48',
        ACTUAL=('v42_integration.tablev_fullflex_actual:run_fullflex_actual' if arm in ('B1','B3')
                else 'v42_integration.tablev_actual:run_tablev_actual'),
        FRESH='v42_integration.tablev_actual:run_tablev_fresh',
        ARM='v42_integration.table_v_run:run_arm')
    sources=[]
    for target in targets.values():
        module,name=target.split(':')
        loaded=importlib.import_module(module)
        if not callable(getattr(loaded,name,None)):
            raise ValueError('TABLE_V_REAL_EXECUTOR_MISSING:'+target)
        record=file_record(loaded.__file__)
        if record not in sources:sources.append(record)
    state=context['state'];manifest=context['manifest'];axis=manifest['time_axis']
    begin=state['begin_epoch_seconds']
    if (axis['evaluation_begin_seconds']!=begin or axis['evaluation_end_seconds']!=begin+86400
            or any(r['submit_seconds']>begin for k in ('running','pending') for r in state[k])):
        raise ValueError('TABLE_V_CAUSAL_INDEPENDENT_DATE_INPUT_REQUIRED')
    steps=[]
    for stage in STAGES[arm]:
        steps.append(stage)
        if stage.startswith('M'):steps.append('K48_'+stage)
    return dict(day=day,arm=arm,source_identity=deepcopy(manifest['identity']),source_sha=manifest['source_sha'],
        initial_state_sha=state['common_initial_state_sha'],input_sha=context['input_audit']['a_input_sha'],
        stages=steps+['ACTUAL96','FRESH_AC96'],executors=targets,executor_source_records=sources,
        real_executor='v42_integration.table_v_campaign.RealTableVExecutor',
        Computing='REFERENCE' if arm in ('B0','B2') else 'FULL_E1_FLEX30_R1',
        MESS='OFF_LITERAL_ZERO_PQ' if arm in ('B0','B1') else 'ORIGINAL_FULL_FOUR_MESS_PQ_SOC_ROUTE',
        final_AIDC_stage='REFERENCE' if arm in ('B0','B2') else STAGES[arm][-1] if arm=='B1' else 'A2',
        final_MESS_stage='OFF' if arm in ('B0','B1') else 'M1' if arm=='B2' else 'M2',
        B0_B2_shared_reference=True,B1_B3_shared_flex_contract=True,Known_and_Unknown_separate=True,
        future_Unknown_UIDs_in_planning=False,prior_day_state_imported=False,
        slots=96,slot_seconds=900,P2_calls=0,R2='HOLD',Worker=1,Threads=1,
        AIDC_algorithm='ORIGINAL_DW_PHASE_I_P1_AND_ORIGINAL_FULL_INTEGER_UB',
        MESS_algorithm='ORIGINAL_ADAPTIVE_BEAM_JOINT_MILP_AND_K16_K32_K48',
        physical_contract='ORIGINAL_11_SVR_7_REGCONTROL_SETTLED_FULL_NETWORK_96',
        physical_result_certified=False,Native_calls=0,model_builds=0,Actual_runs=0)


def preflight_table_v_plan(plan,gate=None):
    """Read public manifests only; launch blockers stay separate from wiring."""
    from .table_v_flex_planning import require_flex_case
    blockers=[];dates=plan.get('dates',[]);bindings=[]
    if (plan.get('schema')!=SCHEMA or not dates or len(dates)!=len(set(dates))
            or plan.get('Worker')!=1 or plan.get('Threads')!=1 or plan.get('P2_calls')!=0
            or plan.get('R2')!='HOLD' or plan.get('automatic_start') is not False):
        blockers.append('EXPLICIT_SERIAL_FOUR_ARM_MAY_PLAN_REQUIRED')
    roots=[]
    for day in dates:
        try:
            require_day(day)
            root=Path(plan['execution_roots'][day]).resolve();roots.append(root)
            manifest=require_flex_case(_read(root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json'))
            expected=dict(day=day,source_sha=manifest['source_sha'],source_identity=manifest['identity'])
            if manifest['day']!=day or plan['case_bindings'].get(day)!=expected:
                raise ValueError('EXACT_INDEPENDENT_DATE_SOURCE_CASE_BINDING_REQUIRED')
            bindings.append(expected)
        except (ValueError,KeyError,OSError,TypeError) as error:
            blockers.append(day+':'+str(error))
    if len(roots)!=len(set(roots)):blockers.append('DATE_EXECUTION_ROOTS_MUST_BE_INDEPENDENT')
    if len({r['source_identity']['case_sha'] for r in bindings})!=len(bindings):
        blockers.append('DATE_CASE_SHA_MUST_NOT_BE_COPIED')
    launch=[]
    if plan.get('execution_scope')=='PREPARED_ONLY':launch.append('PREPARED_ONLY_NO_HEAVY_LAUNCH')
    if not plan.get('release_sha') or not (gate or {}).get('launch_authorization'):
        launch.append('CURRENT_RELEASE_SHA_AND_EXPLICIT_LAUNCH_APPROVAL_MISSING')
    if not plan.get('budget_authorizations'):launch.append('CURRENT_DATE_APPROVED_NATIVE_BUDGET_BINDINGS_MISSING')
    if any(day!='2025-05-01' for day in dates):
        launch.append('MAY01_FOUR_ARM_FULL96_AND_REPRESENTATIVE_CANARY_APPROVAL_REQUIRED')
    return dict(status='PASS_NATIVE0_WIRING' if not blockers else 'NOT_CERTIFIED',
        blockers=blockers,launch_blockers=launch,dates=bindings,case_count=4*len(bindings),
        Native_calls=0,model_builds=0,Actual_runs=0,P2_calls=0,R2='HOLD',
        production_executor='v42_integration.table_v_campaign.RealTableVExecutor',
        stage_checkpoint_engine='v42_integration.release_production_campaign._date_loop',
        wiring_is_physical_or_launch_certificate=False)


def _checked(record):
    if file_record(record['path'])!=record:raise ValueError('TABLE_V_CAMPAIGN_GATE_BYTES_DRIFT')
    return _read(record['path'])


def validate_arm_full96(record,expected,arm,*,expected_policy_sha):
    """The public evidence API uses the same strict verifier as launch."""
    from .table_v_launch_evidence import validate_arm_full96 as verify
    return verify(record,expected,arm,expected_policy_sha=expected_policy_sha)


def _launch_gate(plan,gate):
    from .table_v_launch import validate_launch_identity
    validate_launch_identity(plan,gate)
    if plan['execution_scope']=='MAY01_VALIDATION':return
    for arm in ARMS:
        expected=plan['case_bindings']['2025-05-01']
        validate_arm_full96(gate['May01_four_arm_Full96'][arm],expected,arm,
            expected_policy_sha=plan['actual_policy_bindings']['2025-05-01'][arm])
    if plan['execution_scope']=='REPRESENTATIVE_CANARY16_APPROVED':
        return
    for day in ('2025-05-02','2025-05-10','2025-05-12'):
        approved=_checked(gate['representative_canary_approvals'][day])
        if (approved.get('day')!=day or approved.get('approved') is not True
                or not approved.get('human_approval_reference')
                or approved.get('source_case')!=plan['case_bindings'].get(day)
                or approved.get('release_sha')!=plan['release_sha']
                or approved.get('release_git_sha')!=plan['release_git_sha']
                or approved.get('policy_sha')!=plan['policy_bindings'].get(day)):
            raise PermissionError('CURRENT_REPRESENTATIVE_DATE_CANARY_APPROVAL_REQUIRED')
        arm=approved.get('arm')
        if arm not in ARMS or not approved.get('actual_policy_sha') or not approved.get('physical_evidence'):
            raise PermissionError('CURRENT_REPRESENTATIVE_SETTLED_CANARY_RAW_REQUIRED')
        from .table_v_launch_evidence import validate_arm_canary16
        validate_arm_canary16(approved['physical_evidence'],plan['case_bindings'][day],arm,
            expected_policy_sha=approved['actual_policy_sha'])


class RealTableVExecutor:
    """Calls the same real arm engine used by May01; no injectable executor."""
    def __init__(self,plan,gate=None):self.plan,self.gate=plan,gate or {}

    def __call__(self,*,day,stage,previous,output):
        from .table_v_run import run_arm,verify_adapters
        root=Path(self.plan['execution_roots'][day]);verify_adapters(root)
        if stage not in ARMS or previous is not None:raise ValueError('ONE_ARM_PER_DURABLE_DATE_STREAM_REQUIRED')
        attempt=self.plan.get('attempts',{}).get(day,{}).get(stage)
        result=run_arm(stage,root,attempt=attempt,actual_slots=self.plan.get('actual_slots',96),
            launch_authority=dict(plan=self.plan,gate=self.gate))
        folder=root/stage if attempt is None else root/stage/attempt
        saved=_read(folder/'ARM_OUTCOME.json')
        if result!=saved or saved.get('day')!=day or saved.get('arm')!=stage:
            raise ValueError('CURRENT_REAL_ARM_OUTCOME_BINDING_REQUIRED')
        status='FULL_PASS' if saved['status']=='FULL_PASS' else 'NOT_CERTIFIED'
        records=[file_record(p) for p in sorted(folder.rglob('*')) if p.is_file()]
        return dict(status=status,result=dict(day=day,arm=stage,status=saved['status'],
            outcome=file_record(folder/'ARM_OUTCOME.json'),source_case=self.plan['case_bindings'][day]),
            raw_records=records,acceptance=None)

    def restore(self,day,stage,row):
        if row['result'].get('source_case')!=self.plan['case_bindings'][day]:
            raise ValueError('TABLE_V_RESUME_DIFFERENT_DATE_SOURCE_CASE')
        records=row.get('raw_records',[])
        outcome=row['result'].get('outcome')
        if (not records or outcome not in records
                or len({r['path'] for r in records})!=len(records)):
            raise ValueError('TABLE_V_RESUME_COMPLETE_RAW_AND_OUTCOME_REQUIRED')
        for record in records:
            if set(record)!={'path','sha256','bytes'}:
                raise ValueError('TABLE_V_RESUME_EXACT_FILE_DESCRIPTOR_REQUIRED')
            if file_record(record['path'])!=record:raise ValueError('TABLE_V_RESUME_RAW_BYTES_DRIFT')
            path=Path(record['path'])
            if path.suffix.lower()=='.json':
                value=_read(path)
                if not isinstance(value,(dict,list)):raise ValueError('TABLE_V_RESUME_JSON_STRUCTURE_REQUIRED')
                if path.name=='ARM_OUTCOME.json' and (not isinstance(value,dict)
                        or value.get('day')!=day or value.get('arm')!=stage
                        or value.get('status')!=row['result'].get('status')):
                    raise ValueError('TABLE_V_RESUME_ARM_OUTCOME_STRUCTURE_DRIFT')

    def release_day(self,day):gc.collect()


def run_table_v_production(plan,*,authorization,gate,folder,budget_ledger,**injected):
    """Launch only after explicit authority; May02–31 remain gated by evidence."""
    from .release_production_campaign import _date_loop
    from .table_v_run import budget
    if injected:raise ValueError('PRODUCTION_INJECTED_OR_DUMMY_EXECUTORS_FORBIDDEN')
    ready=preflight_table_v_plan(plan,gate)
    if ready['blockers']:raise ValueError(';'.join(ready['blockers']))
    _launch_gate(plan,gate)
    for day in plan['dates']:
        for kind in ('PLANNING','K48'):
            current=budget(Path(plan['execution_roots'][day]),kind)
            if (current.authorization!=authorization[day][kind]
                    or Path(budget_ledger[day][kind]).resolve()!=current.path.resolve()):
                raise PermissionError('EXACT_DATE_NATIVE_LEDGER_AND_AUTHORIZATION_REQUIRED')
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    identity=dict(plan_sha=digest(plan),authorization_sha=digest(authorization),gate_sha=digest(gate),
        source_records=executor_sources(),evidence_scope='REAL_PRODUCTION',P2_calls=0)
    executor=RealTableVExecutor(plan,gate);reports=[]
    for day in plan['dates']:
        for arm in plan.get('run_arms',ARMS):
            # Independent streams preserve B2 execution after B1 failure. The
            # arm engine stops immediately at its first failed planning stage.
            reports+=_date_loop(dates=[day],folder=root/arm,identity=identity,dispatch=executor,
                restore=executor.restore,evidence_scope='REAL_PRODUCTION',stages=(arm,),close_day=executor.release_day)
    if identity['source_records']!=executor_sources():raise ValueError('TABLE_V_CAMPAIGN_EXECUTED_SOURCE_DRIFT')
    result=dict(status='EXECUTED_RECORDED_DATE_ARM_STATUSES',reports=reports,
        P2_calls=0,Worker=1,Threads=1,R2='HOLD',prior_results_overwritten=False)
    _write(root/'TABLE_V_CAMPAIGN_RESULT.json',result)
    return result
