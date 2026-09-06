"""Corrected namespace only. No legacy launcher/matrix import exists here."""
from pathlib import Path
from dayahead.paper_analysis.storage import read
from .identity import SCHEMA, CAMPAIGN, CASES, require, validate_matrix, validate_identity
from .certification import validate_completed_case, certified_day, recovery_state


def prelaunch(repo, matrix_path, expected_builder):
    repo = Path(repo).resolve(); root = (repo / CAMPAIGN).resolve(); path = Path(matrix_path).resolve()
    require(path.is_relative_to(root) and path.name == 'CORRECTED_MAY_EXECUTION_MATRIX.json', 'OBSOLETE_EXECUTION_MATRIX_FORBIDDEN')
    expected = expected_builder(); matrix = validate_matrix(read(path), expected)
    require(read(root / 'EXECUTION_AUTHORIZATION.json').get('MAY_31DAY_AUTHORIZED') == 'YES', 'MAY_31DAY_NOT_AUTHORIZED')
    require(read(root / 'EXECUTION_AUTHORIZATION.json').get('B2_B3_AUTHORIZED') == 'YES', 'B2_B3_NOT_AUTHORIZED')
    from .freeze import verify_scientific_freeze, expected_campaign
    verify_scientific_freeze(repo)
    validate_identity(expected, expected_campaign(repo, require_outputs=True))
    return root, expected, matrix


def run_day(repo, day, matrix_path, expected_builder, execute_new_case):
    """Injected current producer receives the frozen identity; never old results."""
    root, expected, matrix = prelaunch(repo, matrix_path, expected_builder)
    results = {}
    for case in CASES:
        row = next(r for r in matrix['rows'] if (r['day'], r['case']) == (day, case))
        state = recovery_state(row.get('certificate'), expected, day=day, case=case, campaign_root=root)
        if state['status'] == 'COMPLETE_CURRENT_IDENTITY': results[case] = state; continue
        produced = execute_new_case(day, case, expected, root / 'days' / day / case)
        results[case] = validate_completed_case(produced, expected_builder(), day=day, case=case, campaign_root=root)
    from dayahead.paper_analysis.storage import write_json
    from .identity import file_record
    day_path = root / 'days' / day / 'DAY_CERTIFICATE.json'
    write_json(day_path, {'schema': SCHEMA, 'day': day, 'execution_identity': expected,
                        'cases': {case: value['certificate'] for case, value in results.items()}})
    return certified_day(file_record(day_path, root=root), expected_builder(), day=day, campaign_root=root)
