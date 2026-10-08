"""Exact clean/pushed HEAD readiness after independently checked hybrid pilot."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from v42_unified.audit import ROOT, git, write
from v42_unified.delivery import ready as integration_ready
from v42_unified import delivery as integration_delivery
from v42_unified.storage import sha
from .case import BASE_HEAD, CASE_SHA, REPORTS
from .report import read


def ready():
    # The integration helper validates clean Git/source/old receipts. Publish
    # current readiness only after every additional hybrid check succeeds.
    with patch.object(integration_delivery, 'write', lambda *args, **kwargs: None):
        result = integration_ready()
    final = read(REPORTS / 'FINAL_RESEARCH_STATUS.json')
    independent = read(REPORTS / 'INDEPENDENT_FINAL_VERIFICATION.json')
    tests = read(REPORTS / 'ZERO_NATIVE_REGRESSION.json')
    preservation = read(REPORTS / 'SOURCE_PRESERVATION_AUDIT.json')
    manifest = read(REPORTS / 'SHA256_MANIFEST.json')
    if not all(r['PASS'] for r in (final, independent, tests, preservation, manifest)):
        raise ValueError('CHECKED_HYBRID_DELIVERY_EVIDENCE_REQUIRED')
    if tests['failed'] or final['M1_ACCEPTED'] or final['P2_certificate'] is not None:
        raise ValueError('REGRESSION_OR_P2_ACCEPTANCE_DRIFT')
    if {r['case_sha'] for r in (final, independent, manifest)} != {CASE_SHA}:
        raise ValueError('SAME_ORIGINAL_MAY01_CASE_REQUIRED')
    required = set()
    for folder in (ROOT / 'v42_m1_hybrid', REPORTS):
        for path in folder.rglob('*'):
            if path.is_file() and path.name != 'SHA256_MANIFEST.json' and '__pycache__' not in path.parts:
                required.add(path.relative_to(ROOT).as_posix())
    required.update(path.relative_to(ROOT).as_posix()
                    for path in (ROOT / 'tests').glob('test_v42_m1_hybrid*.py'))
    required.update({'README.md', '.gitattributes', 'Start-V42-M1-Hybrid.ps1'})
    if set(manifest['files']) != required:
        raise ValueError('HYBRID_MANIFEST_COMPLETE_FILE_SET_REQUIRED')
    for name, digest in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha(path) != digest:
            raise ValueError('HYBRID_MANIFEST_DRIFT:' + name)
    remote = git('ls-remote', 'origin', 'refs/heads/v42').decode().split()
    if not remote or remote[0] != result['integration_HEAD']:
        raise ValueError('PUSHED_V42_HEAD_MUST_BE_IDENTICAL')
    original = dict(native_optimize_calls=result['native_optimize_calls'],
        test_counts=result['test_counts'], tests=result['tests'])
    result.update(schema='V42_INTEGRATION_AND_FAST_CERTIFIED_HYBRID_READY_V3',
        original_integration_phase=original, native_optimize_calls=final['Native_optimize_calls'],
        native_execution_scope='new bounded May01/1499-job hybrid pilot; historical calls separately preserved',
        large_new_M1_runs=1, test_counts=final['tests'], remote_v42_HEAD=remote[0],
        research_target_policy=dict(A1=.005, A2=.005, M1=.05, M2=.05,
            production_policy_modified=False), generated_utc=datetime.now(timezone.utc).isoformat())
    state = result['scientific_state']
    state['historical_M188_global_gap_percent'] = state.pop('current_M1_global_gap_percent')
    state['production_evidence_backend_preserves_historical_M188_state'] = True
    state['new_May01_fast_hybrid'] = dict(case_sha=CASE_SHA,
        exact_Global_LB=final['exact_Global_LB'], exact_Global_UB=final['exact_Global_UB'],
        independently_certified_Global_LB=final['independently_certified_Global_LB'],
        independently_validated_integer_Global_UB=final['independently_validated_Global_UB'],
        certified_Global_Gap_percent=final['certified_Global_Gap_percent'],
        research_gap_5_percent_certified=final['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED'],
        M1_ACCEPTED=False, P2_certificate=None, production_default_promoted=False,
        May12_1782_jobs_or_A2_M2_performance_transfer=False)
    previous = read(ROOT / 'docs/v42_m1_joint_gap_research/FINAL_RESEARCH_STATUS.json')
    result['historical_completed_May01_research'] = dict(completed_HEAD=BASE_HEAD,
        case_sha=CASE_SHA, historical_reports_and_ledgers_preserved=True,
        Native_optimize_calls=7,
        Native_Runtime=previous['Native_Runtime'], Native_Work=previous['Native_Work'],
        fresh_exact_LB=.5675886811427069, strict_UB=.6063186498423855,
        certified_Global_Gap_percent=6.387725119414779, budget_reset=False)
    result['Native_call_accounting_by_scope'] = dict(original_integration=0,
        historical_completed_May01_research=7, new_fast_hybrid_pilot=final['Native_optimize_calls'],
        all_preserved_authorized_May01_research=7+final['Native_optimize_calls'])
    result['fast_hybrid_research'] = dict(execution_completed=True,
        scientific_goal_completed=final['gap_5_percent_and_90_minutes_PASS'],
        classification=final['classification'], completed_baseline_HEAD=BASE_HEAD,
        run_id=final['run_id'], Runtime=final['Native_Runtime'], Work=final['Native_Work'],
        wall_through_final_verification_seconds=final['research_through_final_verification_wall_seconds'],
        wall_90_minutes_PASS=final['stage_wall_90_minutes_PASS'],
        speed_60_minutes_PASS=final['speed_wall_60_minutes_PASS'],
        exact_LB_improvement=final['exact_LB_improvement'], strict_UB_improvement=final['strict_UB_improvement'],
        tests=final['tests'], tests_Native_optimize_calls=0,
        evidence={name: dict(path=str(REPORTS / name), sha256=sha(REPORTS / name))
            for name in ('FINAL_RESEARCH_STATUS.json', 'INDEPENDENT_FINAL_VERIFICATION.json',
                         'COST_BREAKDOWN.json', 'ZERO_NATIVE_REGRESSION.json',
                         'SOURCE_PRESERVATION_AUDIT.json', 'SHA256_MANIFEST.json')})
    result['M_handoff']['additional_contract'] = str(REPORTS / 'HYBRID_HANDOFF_KO.md')
    result['M_handoff']['external_M_completion_claimed'] = False
    result['final_M_work_completed'] = False
    result['coding_and_Git_delivery_are_not_Native_Runtime'] = True
    result['delivery_elapsed_after_final_scientific_verification_seconds'] = max(0.,
        datetime.now(timezone.utc).timestamp() - (REPORTS / 'FINAL_RESEARCH_STATUS.json').stat().st_mtime)
    write(ROOT / 'V42_INTEGRATION_READY.json', result)
    return result


if __name__ == '__main__':
    receipt = ready()
    print('V42_FAST_HYBRID_READY', receipt['integration_HEAD'], receipt['test_counts'])
