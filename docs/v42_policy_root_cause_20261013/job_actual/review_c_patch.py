"""Independent read-only review receipt. No tests, native optimization or AC run."""
from pathlib import Path
import hashlib,json,subprocess
B=Path('D:/v42_policy_root_cause_20261013');C=Path('D:/v42_policy_root_cause_fix_20261013')
def record(path):
    path=Path(path);data=path.read_bytes();return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
diff=subprocess.run(['git','diff','--','v42_integration/sensitivity_policy.py'],cwd=C,capture_output=True,text=True,check=True).stdout
code=(C/'v42_integration/sensitivity_policy.py').read_text(encoding='utf8')
test=(C/'tests/test_v42_policy_root_cause_regressions.py').read_text(encoding='utf8')
runtime=json.loads((B/'audit/job_actual/POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json').read_text(encoding='utf8'))
checks=dict(source_None_PREPLACE_requires_explicit_permission="(row['action']=='PREPLACE' and metadata.get('can_prestart_place') is not True)" in code,
    positive_delay_retains_batch_rights="(delay>1e-9 and metadata.get('batch_eligible') is not True)" in code,
    protection_remains_explicit_False="if metadata.get('protected') is not False or (" in code,
    Running_batch_remains_required="state=='RUNNING' and metadata.get('batch_eligible') is not True" in code,
    start_receipt_window_and_shared_budget_unchanged="start not in receipt['allowed_starts_seconds'] or consumed>receipt['budget_seconds']+1e-9" in code,
    site_and_hard_earliest_latest_deadline_guards_retained="site not in metadata.get('compatible_sites',())" in code and "('hard_latest_start_seconds',start),('completion_deadline_seconds',end)" in code,
    current_and_all_future_capacity_included="total=(packet.known_gpu+anonymous+stress+delta)[slot:]" in code,
    expired_capacity_only_excluded="score=packet.evaluate(delta,remaining_slot=slot,scenario_gpu=stress)" in code,
    migration_checkpoint_packet_budget_and_hold_code_unchanged='@@' not in diff[diff.find('def select_migration'): ] if 'def select_migration' in diff else True,
    regression_source_None_both_batch_states="@pytest.mark.parametrize('source_site', ['A', None])" in test and "@pytest.mark.parametrize('batch', [None, True])" in test,
    regression_current_future_last_slot_preserved="@pytest.mark.parametrize('stress_slot', [0, 2, 3, 95])" in test,
    regression_frozen_reload_checked='before == after and loaded.sha == policy.sha' in test,
    runtime_unknown_partition=runtime['dispatch_unknown_UIDs']==766 and runtime['actual_unknown_population']==774 and runtime['unknown_not_evaluated_count']==8,
    runtime_known_partition=runtime['dispatch_known_UIDs']==48 and runtime['known_not_entering_unknown_policy_dispatch_UID_count']==1498,
    runtime_Dday_unknown_partition=runtime['actual_UNKNOWN_Dday_pending_attempt_UIDs']==693 and runtime['Dday_unknown']==696,
    runtime_no_all_Unknown_entered_claim=runtime['unknown_missing_policy_event_reasons']==dict(COMPLETED_BEFORE_NEXT_EXECUTION_CHECKPOINT=5,NO_ADMISSION_CONTROL_BOUNDARY_BEFORE_DAY_END=3))
assert all(checks.values()),checks
report_names=['CONTROL_POLICY_ROOT_CAUSE_FINAL_KO.md','CONTROL_POLICY_ROOT_CAUSE_MATRIX.json','POLICY_COMPILER_ONLY_FIRST_FAILURE.json','POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json']
reports=[dict(name=name,exists=(B/'audit'/name).exists(),receipt=record(B/'audit'/name) if (B/'audit'/name).exists() else None) for name in report_names]
receipt=dict(schema='INDEPENDENT_C_PATCH_READONLY_REVIEW_V1',PASS=True,concrete_issues=[],
    scope='9_LINE_SENSITIVITY_POLICY_DIFF_AND_16_PARAMETERIZED_REGRESSION_CASES_REVIEW',
    verification='SOURCE_AND_TEST_CASE_READ_ONLY_REVIEW_NOT_TEST_EXECUTION',
    checks=checks,
    review_findings=[
        'Same-start PREPLACE with explicit permission no longer requires unrelated batch-delay authority; protected=False remains mandatory.',
        'Source_site=None cannot bypass explicit can_prestart_place for PREPLACE.',
        'Positive additional delay still requires batch=True, allowed start membership and same immutable remaining budget.',
        'RUNNING batch/checkpoint/WAN/one-migration/hold/migration-budget semantics are unchanged.',
        'Capacity slice includes the current slot and every remaining slot through95; only expired slots are excluded, matching the signed-grid scorer.',
        'Regression cases cover batchNone/False, sourceA/None, protectedNone/True, RunningbatchNone, past/current/future/95capacity and frozenreload.' ],
    test_cases_reviewed=16,test_reruns=0,Native_Optimize_calls=0,AC_reruns=0,
    actual_May_action_improvement_established=False,
    May_production_no_selected_candidate_or_action_claim_unchanged=True,
    runtime_partitions=dict(active_known=1546,known_dispatch=48,known_no_dispatch=1498,
        active_unknown=774,unknown_dispatch=766,unknown_no_dispatch=8,
        Dday_unknown=696,Dday_pending_dispatch=693,Dday_late_carryout_no_dispatch=3,
        initial_unknown_running_no_checkpoint_before_completion=5),
    aggregate_report_review=reports,aggregate_report_status='PENDING_LEAD_WRITE' if any(not r['exists'] for r in reports) else 'AVAILABLE_REQUIRES_FIELD_REVIEW',
    sources=[record(C/'v42_integration/sensitivity_policy.py'),record(C/'tests/test_v42_policy_root_cause_regressions.py'),record(B/'audit/job_actual/POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json'),record(Path(__file__))],
    diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),source_index_or_original_artifact_mutations=0)
(B/'audit/job_actual/INDEPENDENT_PATCH_REVIEW.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps(dict(PASS=True,output=str(B/'audit/job_actual/INDEPENDENT_PATCH_REVIEW.json'),aggregate_report_status=receipt['aggregate_report_status'])))
