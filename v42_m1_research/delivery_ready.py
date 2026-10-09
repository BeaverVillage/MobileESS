"""Post-commit readiness including the explicitly authorized May01 research."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .case import REPORTS
from v42_unified.audit import ROOT, git, write
from v42_unified.delivery import ready as integration_ready
from v42_unified.storage import sha


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ready():
    """Keep integration and research costs, authorities and acceptance separate."""
    result = integration_ready()
    research = read(REPORTS / 'FINAL_RESEARCH_STATUS.json')
    joint = read(REPORTS / 'JOINT_LB_UB_GAP.json')
    tests = read(REPORTS / 'ZERO_NATIVE_COMMON_TESTS.json')
    preservation = read(REPORTS / 'EXECUTION_PRESERVATION_AUDIT.json')
    admission = read(REPORTS / 'FINAL_ADMISSION_VIEW.json')
    manifest = read(REPORTS / 'SHA256_MANIFEST.json')
    if not all(value['PASS'] for value in (research, joint, tests, preservation, admission)):
        raise ValueError('FINAL_RESEARCH_EVIDENCE_REQUIRED')
    if len({value['case_sha'] for value in (research, joint, admission, manifest)}) != 1:
        raise ValueError('FINAL_RESEARCH_CASE_DRIFT')
    for name, digest in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha(path) != digest:
            raise ValueError('FINAL_MANIFEST_DRIFT:' + name)
    remote = git('ls-remote', 'origin', 'refs/heads/v42').decode().split()
    if not remote or remote[0] != result['integration_HEAD']:
        raise ValueError('FINAL_REMOTE_HEAD_NOT_IDENTICAL')
    counts = dict(passed=len(tests['passed']), skipped=len(tests['skipped']), failed=len(tests['failed']))
    result['schema'] = 'V42_INTEGRATION_AND_AUTHORIZED_M1_RESEARCH_READY_V2'
    result['original_integration_phase'] = dict(
        native_optimize_calls=result['native_optimize_calls'],
        large_new_M1_runs=result['large_new_M1_runs'],
        test_counts=result['test_counts'], tests=result['tests'],
        preserved_receipts=True)
    result['native_optimize_calls'] = joint['independent_native_accounting']['checked_native_calls']
    result['large_new_M1_runs'] = 1
    result['native_execution_scope'] = 'Explicitly authorized bounded May01/1499-job M1 research only'
    result['test_counts'] = counts
    state = result['scientific_state']
    state['historical_M188_global_gap_percent'] = state.pop('current_M1_global_gap_percent')
    state['production_evidence_backend_preserves_historical_M188_state'] = True
    state['new_May01_research'] = dict(
        case_sha=joint['case_sha'],
        independently_certified_Global_LB=joint['independently_certified_Global_LB'],
        independently_validated_integer_Global_UB=joint['independently_validated_integer_Global_UB'],
        certified_Global_Gap_percent_upper=joint['certified_Global_Gap_percent_upper'],
        M1_P1_GAP_CERTIFIED=joint['M1_P1_GAP_CERTIFIED'], M1_ACCEPTED=False,
        P2_certificate=None, production_default_promoted=False,
        May12_1782_job_anchor_transfer=False)
    result['research'] = dict(
        execution_completed=True, scientific_goal_completed=joint['M1_P1_GAP_CERTIFIED'],
        run=admission['original_run'], final_replay_view=admission['read_only_replay_view'],
        classification=research['classification'], Native_Runtime=research['Native_Runtime'],
        Native_Work=research['Native_Work'], runner_wall_seconds=research['runner_wall_seconds'],
        research_through_final_review_wall_seconds=research['research_through_final_review_wall_seconds'],
        through_review_90_minute_practicality_PASS=research['through_review_90_minute_practicality_PASS'],
        post_run_independent_checker_wall_seconds=research['post_run_independent_checker_wall_seconds'],
        tests=counts, tests_Native_optimize_calls=0,
        preserved_original_capture_pool_strict_PASS=False,
        strict_Native_final_RAW_admitted_without_repair=True,
        evidence={name: dict(path=str(REPORTS / name), sha256=sha(REPORTS / name))
                  for name in ('FINAL_RESEARCH_STATUS.json', 'JOINT_LB_UB_GAP.json',
                               'FINAL_ADMISSION_VIEW.json', 'ZERO_NATIVE_COMMON_TESTS.json',
                               'EXECUTION_PRESERVATION_AUDIT.json', 'SHA256_MANIFEST.json')})
    result['M_handoff']['additional_contract'] = str(REPORTS / 'M_RESEARCH_HANDOFF_KO.md')
    result['M_handoff']['external_M_completion_claimed'] = False
    result['final_M_work_completed'] = False
    result['remote_v42_HEAD'] = remote[0]
    result['generated_utc'] = datetime.now(timezone.utc).isoformat()
    result['delivery_elapsed_after_research_results_seconds'] = max(
        0., datetime.now(timezone.utc).timestamp() - (Path(admission['original_run']) / 'RESEARCH_TRACK_RESULTS.json').stat().st_mtime)
    result['coding_and_Git_delivery_are_not_Native_Runtime'] = True
    write(ROOT / 'V42_INTEGRATION_READY.json', result)
    return result


if __name__ == '__main__':
    receipt = ready()
    print('V42_INTEGRATION_AND_RESEARCH_READY', receipt['integration_HEAD'], receipt['test_counts'])
