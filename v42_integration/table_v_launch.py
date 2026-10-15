"""One release/source/policy/budget authority gate for every public launcher."""
import json
from pathlib import Path
import subprocess

from .a_engine import digest
from .m_engine import file_record


def checked_json(record):
    if file_record(record['path'])!=record:raise ValueError('LAUNCH_AUTHORITY_DOCUMENT_BYTES_DRIFT')
    return json.loads(Path(record['path']).read_text(encoding='utf8'))


def release_identity():
    from .table_v_campaign import executor_sources
    root=Path(__file__).resolve().parents[1]
    records=executor_sources()
    # Pin the unchanged original algorithms as well as their new adapters.
    # Checking tracked Python bytes also covers imports routed dynamically by
    # the original source bridges; no module or research scenario is executed.
    paths=subprocess.check_output(['git','ls-files','-z','--','*.py'],cwd=root).decode('utf8').split('\0')
    pinned={r['path']:r for r in records}
    for relative in paths:
        if relative and (root/relative).is_file():
            record=file_record(root/relative);pinned[record['path']]=record
    records=[pinned[path] for path in sorted(pinned)]
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    return dict(release_sha=digest(records),release_sources=records,release_git_sha=revision)


def validate_launch_identity(plan,gate):
    """No boolean or CLI scope can mint authority for a changed release."""
    from .table_v_budget import require_authorization
    from .table_v_flex_planning import require_flex_case
    from .table_v_dates import require_day
    if plan.get('execution_scope')=='PREPARED_ONLY':raise PermissionError('PREPARED_ONLY_NO_HEAVY_LAUNCH')
    dates=plan.get('dates',[])
    arms=plan.get('run_arms',['B0','B1','B2','B3'])
    if (plan.get('schema')!='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1' or not dates
            or len(dates)!=len(set(dates)) or plan.get('Worker')!=1 or plan.get('Threads')!=1
            or plan.get('P2_calls')!=0 or plan.get('R2')!='HOLD'
            or plan.get('automatic_start') is not False or plan.get('actual_slots',96) not in (16,96)
            or not arms or len(arms)!=len(set(arms)) or any(a not in ('B0','B1','B2','B3') for a in arms)):
        raise PermissionError('ORIGINAL_SERIAL_TABLE_V_PRODUCTION_POLICY_REQUIRED')
    for day in dates:require_day(day)
    roots=[Path(plan['execution_roots'][day]).resolve() for day in dates]
    if len(roots)!=len(set(roots)):
        raise PermissionError('INDEPENDENT_DATE_EXECUTION_ROOTS_REQUIRED')
    scope=plan.get('execution_scope')
    from .table_v_b2_gate import B2_SCOPES,validate_b2_scope,validate_b2_reference
    b2_scope=scope in B2_SCOPES
    if b2_scope:validate_b2_scope(plan)
    if scope not in ('MAY01_VALIDATION','REPRESENTATIVE_CANARY16_APPROVED','MAY31_APPROVED')+B2_SCOPES:
        raise PermissionError('EXPLICIT_TABLE_V_EXECUTION_SCOPE_REQUIRED')
    if scope=='REPRESENTATIVE_CANARY16_APPROVED' and (
            plan.get('actual_slots')!=16 or any(day not in ('2025-05-02','2025-05-10','2025-05-12') for day in dates)):
        raise PermissionError('EXACT_REPRESENTATIVE_DATE_CANARY16_SCOPE_REQUIRED')
    if scope=='MAY31_APPROVED' and plan.get('actual_slots',96)!=96:
        raise PermissionError('MAY31_FULL96_REQUIRED')
    current=release_identity()
    if any(plan.get(k)!=v for k,v in current.items()):
        raise PermissionError('CURRENT_RELEASE_SOURCE_OR_GIT_SHA_REQUIRED')
    approval=checked_json(gate['launch_authorization'])
    if (approval.get('schema')!='TABLE_V_EXPLICIT_RELEASE_LAUNCH_APPROVAL_V1'
            or approval.get('approved') is not True or not approval.get('human_approval_reference')
            or approval.get('approved_plan_sha')!=digest(plan) or approval.get('dates')!=plan['dates']
            or approval.get('execution_scope')!=scope or approval.get('approved_release_sha')!=current['release_sha']
            or approval.get('approved_release_git_sha')!=current['release_git_sha']
            or approval.get('approved_policy_bindings_sha')!=digest(plan.get('policy_bindings'))
            or approval.get('approved_budget_bindings_sha')!=digest(plan.get('budget_authorizations'))):
        raise PermissionError('EXACT_RELEASE_POLICY_BUDGET_AND_HUMAN_LAUNCH_APPROVAL_REQUIRED')
    if scope=='MAY01_VALIDATION' and plan['dates']!=['2025-05-01']:
        raise PermissionError('MAY01_VALIDATION_CANNOT_LAUNCH_OTHER_DATES')
    for day in plan['dates']:
        root=Path(plan['execution_roots'][day]).resolve()
        manifest=require_flex_case(json.loads((root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text(encoding='utf8')))
        expected=dict(day=day,source_sha=manifest['source_sha'],source_identity=manifest['identity'])
        policy=json.loads((root/'INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json').read_text(encoding='utf8'))['spec']
        if (manifest['day']!=day or plan['case_bindings'].get(day)!=expected
                or policy!=manifest['science_derivation']['policy']
                or plan['policy_bindings'].get(day)!=digest(policy)):
            raise PermissionError('CURRENT_DATE_SCIENCE_CASE_SOURCE_POLICY_SHA_REQUIRED')
        if b2_scope:
            validate_b2_reference(root,expected,manifest,
                actual_policy_sha=plan.get('actual_policy_bindings',{}).get(day,{}).get('B2'))
        for kind in ('PLANNING','K48'):
            record=plan['budget_authorizations'][day][kind]
            if Path(record['path']).resolve()!=root/(kind+'_AUTHORIZATION.json'):
                raise PermissionError('ONE_EXACT_DATE_BUDGET_AUTHORIZATION_DOCUMENT_REQUIRED')
            authority=require_authorization(checked_json(record))
            if b2_scope and authority.get('authorized_arm_stages')!=[
                    'B2:M1' if kind=='PLANNING' else 'B2:K48_M1']:
                raise PermissionError('B2_SCOPE_EXACT_AUTHORIZED_ARM_STAGE_REQUIRED')
            ledger_path=root/(kind+'_NATIVE_LEDGER.json')
            if (Path(authority['authorized_ledger_path']).resolve()!=ledger_path
                    or authority['source_cases']!=[expected]):
                raise PermissionError('CURRENT_DATE_APPROVED_BUDGET_SOURCE_CASE_REQUIRED')
            ledger=json.loads(ledger_path.read_text(encoding='utf8'))
            if (ledger.get('authorization_document')!=authority
                    or ledger.get('release_identity',{}).get('authorization_sha')!=digest(authority)
                    or ledger.get('inflight') is not None or ledger.get('active_stage_context') is not None):
                raise PermissionError('CURRENT_BUDGET_AUTHORITY_OR_UNRECONCILED_NATIVE_STATE')
    return approval
