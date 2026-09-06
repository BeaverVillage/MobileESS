"""One recursive case validator used by completion, day and resume paths."""
from pathlib import Path
import math
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40a.invariants import digest
from dayahead.v40g_segments.canonical import identities
from .identity import SCHEMA, CASES, require, verify_file, validate_identity, immutable_write, file_record, IntegrityError, verify_bound_files

ROLES = ('Planning', 'Fresh', 'Actual', 'physical_gates', 'objective', 'DA_decision', 'AIDC_decision',
         'MESS_trajectory', 'input_authority', 'final_executed_joint')


def validate_completed_case(certificate_reference, expected, *, day, case, campaign_root, actual_required=True):
    root = Path(campaign_root).resolve()
    verify_bound_files(expected)
    cert_path = verify_file(certificate_reference, root=root)
    cert = read(cert_path)
    require(cert.get('schema') == SCHEMA and cert.get('status') == 'COMPLETE_CURRENT_IDENTITY', 'OLD_OR_INCOMPLETE_CASE_CERTIFICATE')
    require((cert.get('day'), cert.get('case')) == (day, case), 'CASE_IDENTITY')
    validate_identity(cert['execution_identity'], expected)
    checkpoint_path = verify_file(cert['checkpoint'], root=root)
    checkpoint = read(checkpoint_path)
    require(checkpoint.get('schema') == SCHEMA and checkpoint.get('status') == 'COMPLETE_CURRENT_IDENTITY', 'CHECKPOINT_NOT_COMPLETE_CURRENT')
    require((checkpoint['day'], checkpoint['case']) == (day, case), 'CHECKPOINT_CASE_IDENTITY')
    validate_identity(checkpoint['execution_identity'], expected)
    leaves = checkpoint['files']; require(len({r['relative_path'] for r in leaves}) == len(leaves), 'DUPLICATE_CHECKPOINT_FILE')
    by_path = {r['relative_path']: verify_file(r, root=root) for r in leaves}
    roles = checkpoint['roles']; needed = set(ROLES) - (set() if actual_required else {'Actual'})
    require(needed.issubset(roles) and set(roles.values()).issubset(by_path), 'MISSING_CASE_SCIENTIFIC_LEAF')
    documents = {role: read(by_path[path]) for role, path in roles.items()}
    for role in ('Planning', 'Fresh') + (('Actual',) if actual_required else ()):
        result = documents[role]
        require((result['day'], result['case']) == (day, case), role + '_IDENTITY')
        require(result['status'] == 'PASS' and not result.get('physical_violation'), role + '_PHYSICAL_FAIL')
        if role != 'Planning': require(result['convergence_count'] == 96, role + '_COVERAGE')
        require(result['execution_identity_SHA'] == expected['identity_SHA'], role + '_AUTHORITY_BINDING')
        require(math.isfinite(float(result['rho_max'])) and float(result['rho_max']) >= 0, role + '_INVALID_OBJECTIVE')
    gates = documents['physical_gates']
    for role in ('Planning', 'Fresh') + (('Actual',) if actual_required else ()):
        require(gates[role]['status'] == 'PASS' and all(gates[role][k] == 0 for k in
            ('voltage_violation_count', 'current_violation_count', 'transformer_violation_count')), 'CASE_PHYSICAL_GATES')
    objective = documents['objective']
    require((objective['day'], objective['case']) == (day, case), 'OBJECTIVE_CASE')
    require(objective['primary'] == 'MIN_RHO_MAX' and objective['rho_max'] == documents['Planning']['rho_max'], 'OBJECTIVE_RESULT_BINDING')
    da = documents['DA_decision']; aidc = documents['AIDC_decision']; mess = documents['MESS_trajectory']
    require(da['decision_SHA'] == digest(da['decision']), 'DA_DECISION_CONTENT')
    seg = identities(aidc['jobs'])
    require(aidc['segment_identity'] == seg, 'AIDC_SEGMENT_CONTENT')
    require(aidc['decision_SHA'] == digest(aidc['jobs']), 'AIDC_DECISION_CONTENT')
    require(mess['trajectory_SHA'] == digest(mess['trajectory']), 'MESS_TRAJECTORY_CONTENT')
    require(da['decision']['AIDC_decision_SHA'] == aidc['decision_SHA'] and da['decision']['MESS_trajectory_SHA'] == mess['trajectory_SHA'], 'DA_JOINT_CHILD_BINDING')
    inputs = documents['input_authority']; validate_identity(inputs['execution_identity'], expected)
    for record in inputs['files']: verify_file(record)
    joint = documents['final_executed_joint']
    require(joint['final_executed_joint_SHA'] == digest(joint['payload']), 'EXECUTED_JOINT_SHA')
    bindings = {'DA_decision_SHA': da['decision_SHA'], 'AIDC_decision_SHA': aidc['decision_SHA'],
        'AIDC_segment_SHA': seg['segment_and_event_SHA'], 'MESS_trajectory_SHA': mess['trajectory_SHA'],
        'execution_identity_SHA': expected['identity_SHA']}
    require(all(joint['payload'].get(k) == v for k, v in bindings.items()), 'EXECUTED_JOINT_BINDING')
    for role in ('Planning', 'Fresh') + (('Actual',) if actual_required else ()):
        require(documents[role]['final_executed_joint_SHA'] == joint['final_executed_joint_SHA'], role + '_EXECUTED_DECISION_BINDING')
    require(checkpoint['bindings'] == cert['bindings'] == {**bindings, 'final_executed_joint_SHA': joint['final_executed_joint_SHA']}, 'CHECKPOINT_CERTIFICATE_BINDINGS')
    return {'status': 'COMPLETE_CURRENT_IDENTITY', 'certificate': certificate_reference,
        'leaf_count': len(leaves), 'day': day, 'case': case, 'bindings': bindings}


def certified_day(day_reference, expected, *, day, campaign_root):
    path = verify_file(day_reference, root=campaign_root); value = read(path)
    require(value.get('schema') == SCHEMA and value.get('day') == day, 'DAY_CERTIFICATE_IDENTITY')
    validate_identity(value['execution_identity'], expected)
    require(set(value['cases']) == set(CASES), 'DAY_FOUR_CASES_REQUIRED')
    cases = {c: validate_completed_case(value['cases'][c], expected, day=day, case=c,
                                       campaign_root=campaign_root) for c in CASES}
    return {'status': 'COMPLETE_CURRENT_IDENTITY', 'day': day, 'cases': cases, 'ALL_4_CASE_LEAF_ARTIFACTS_VALID_NOW': True}


def recovery_state(receipt, expected, *, day, case, campaign_root):
    if receipt is None: return {'status': 'PARTIAL_CURRENT_IDENTITY', 'skip_computation': False}
    try:
        result = validate_completed_case(receipt, expected, day=day, case=case, campaign_root=campaign_root)
        return {**result, 'skip_computation': True}
    except (IntegrityError, OSError, KeyError, TypeError, ValueError) as error:
        stale = 'STALE_DIFFERENT_IDENTITY' in str(error) or 'OLD_OR_INCOMPLETE' in str(error) or 'OUTSIDE_CURRENT' in str(error)
        return {'status': 'STALE_DIFFERENT_IDENTITY' if stale else 'INVALID', 'skip_computation': False, 'reason': str(error)}


def certify_case(checkpoint_path, expected, *, day, case, campaign_root):
    root = Path(campaign_root); checkpoint = read(checkpoint_path)
    path = Path(checkpoint_path).parent / 'CASE_CERTIFICATE.json'
    certificate = {'schema': SCHEMA, 'status': 'COMPLETE_CURRENT_IDENTITY', 'day': day, 'case': case,
        'execution_identity': expected, 'checkpoint': file_record(checkpoint_path, root=root), 'bindings': checkpoint['bindings']}
    # Validate with the sole validator before publishing a completion receipt.
    draft = path.with_name('CASE_CERTIFICATE.validation.json')
    immutable_write(draft, certificate)
    validate_completed_case(file_record(draft, root=root), expected, day=day, case=case, campaign_root=root)
    immutable_write(path, certificate)
    return file_record(path, root=root)
