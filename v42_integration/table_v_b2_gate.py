"""Independent B2 launch scopes with the original strict physical evidence.

No B1 outcome, solver, model construction, or synthetic pass is used here.
Completed outcomes need a separate immutable current-release approval because
the historical ARM_OUTCOME format does not itself bind the executed release.
"""
from pathlib import Path
import json

from .a_engine import digest
from .table_v_launch_evidence import REFERENCE_POLICY

B2_SCOPES = ('B2_MAY01_FULL96', 'B2_REPRESENTATIVE_CANARY16_APPROVED', 'B2_MAY31_APPROVED')
REPRESENTATIVES = ('2025-05-02', '2025-05-10', '2025-05-12')
MAY_DATES = tuple(f'2025-05-{day:02d}' for day in range(1, 32))


def validate_b2_scope(plan):
    scope = plan.get('execution_scope')
    if scope not in B2_SCOPES:
        raise PermissionError('EXPLICIT_B2_EXECUTION_SCOPE_REQUIRED')
    if plan.get('run_arms') != ['B2']:
        raise PermissionError('B2_SCOPE_EXACT_SINGLE_ARM_REQUIRED')
    dates, slots = plan.get('dates', []), plan.get('actual_slots', 96)
    valid = (scope == B2_SCOPES[0] and dates == ['2025-05-01'] and slots == 96
             or scope == B2_SCOPES[1] and bool(dates) and len(dates) == len(set(dates))
             and all(day in REPRESENTATIVES for day in dates) and slots == 16
             or scope == B2_SCOPES[2] and dates == list(MAY_DATES) and slots == 96)
    if not valid:
        raise PermissionError('EXACT_B2_DATE_AND_16_OR_96_SCOPE_REQUIRED')


def validate_b2_reference(root, expected, manifest, *, actual_policy_sha):
    from .table_v_launch_evidence import _source, _reference
    if actual_policy_sha != digest(REFERENCE_POLICY):
        raise PermissionError('B2_ORIGINAL_REFERENCE_ACTUAL_POLICY_REQUIRED')
    _source(expected, manifest)
    return _reference(Path(root), expected, manifest)


def _approved_evidence(plan, record, day, *, physical_evidence=None):
    from .table_v_launch import checked_json
    approved = checked_json(record)
    policy = plan.get('actual_policy_bindings', {}).get(day, {}).get('B2')
    if (approved.get('day') != day or approved.get('arm') != 'B2'
            or approved.get('approved') is not True or not approved.get('human_approval_reference')
            or approved.get('source_case') != plan.get('case_bindings', {}).get(day)
            or not approved.get('source_case') or not plan.get('policy_bindings', {}).get(day)
            or approved.get('release_sha') != plan['release_sha']
            or approved.get('release_git_sha') != plan['release_git_sha']
            or approved.get('policy_sha') != plan['policy_bindings'][day]
            or policy != digest(REFERENCE_POLICY) or approved.get('actual_policy_sha') != policy
            or not approved.get('physical_evidence')
            or physical_evidence is not None and approved['physical_evidence'] != physical_evidence):
        raise PermissionError('CURRENT_B2_RELEASE_SOURCE_POLICY_AND_PHYSICAL_APPROVAL_REQUIRED')
    from .table_v_launch_evidence import _root
    root = _root(Path(approved['physical_evidence']['path']).resolve().parent)
    manifest = json.loads((root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text(encoding='utf8'))
    if digest(manifest.get('science_derivation', {}).get('policy')) != approved['policy_sha']:
        raise PermissionError('B2_COMPLETED_EVIDENCE_FROZEN_SCIENCE_POLICY_REQUIRED')
    return approved


def validate_b2_launch_evidence(plan, gate):
    """Only the scope's B2 ancestors can authorize the next execution step."""
    from .table_v_launch_evidence import validate_arm_full96, validate_arm_canary16
    validate_b2_scope(plan)
    if plan['execution_scope'] == B2_SCOPES[0]:
        return
    day = '2025-05-01'
    approved = _approved_evidence(plan, gate['B2_May01_release'], day,
        physical_evidence=gate['B2_May01_Full96'])
    validate_arm_full96(approved['physical_evidence'], plan['case_bindings'][day], 'B2',
        expected_policy_sha=approved['actual_policy_sha'])
    if plan['execution_scope'] == B2_SCOPES[1]:
        return
    for day in REPRESENTATIVES:
        approved = _approved_evidence(plan, gate['B2_representative_canary_approvals'][day], day)
        validate_arm_canary16(approved['physical_evidence'], plan['case_bindings'][day], 'B2',
            expected_policy_sha=approved['actual_policy_sha'])
