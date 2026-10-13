"""Read completed C artifacts; never execute an Actual or grid model."""
from pathlib import Path
import bisect
import collections
import gzip
import hashlib
import itertools
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit/control/FINAL_FLEX_COMPARISON'
EXPECTED_SOURCE = 'c4b59fb3898da7f3bed6b3b6818890165c74f7f1f90e4cd2470fa3abd5c56c0a'
D_RESULT = Path('D:/v42_q90_service_recourse_20261014/audit/final/SOURCE_ONLY_CORRECTED_ACTUAL_FULL96.json.gz')


def read(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def read_result(path):
    with gzip.open(path, 'rt', encoding='utf-8-sig') as stream:
        return json.load(stream)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_baseline(path, expected):
    data = read_result(path)
    rules = data['rule_consumption_receipt']
    reasons = collections.Counter(row.get('reason') for row in rules)
    assert dict(reasons) == expected, 'BASELINE_FIRST_GUARD_COUNT_DRIFT'
    missing = [row['time_seconds'] for row in rules
               if row.get('reason') == 'NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY']
    return dict(path=str(path), SHA256=sha(path), dispatch_events=len(rules),
        earliest_guard_reason_counts=dict(reasons),
        end_boundary_missing_support_events=len(missing),
        missing_support_observed_seconds_min=min(missing),
        missing_support_observed_seconds_max=max(missing),
        lookup_count_scope='SOURCE_BRANCH_RECONSTRUCTION;NOT_A_RAW_PROFILER_COUNTER',
        actual_receipt=data['receipt'], new_assumed_contracts=False,
        Actual_Maximum_Line_Loading=None, Fresh_AC='NOT_RUN')


def audit_case(folder, cell=None):
    receipt = read(folder / 'EXECUTION_RECEIPT.json')
    assert receipt['source_freeze_sha'] == EXPECTED_SOURCE
    assert receipt['Full96'] and receipt['slots'] == 96
    result_path = folder / 'CONDITIONAL_ACTUAL_RESULT.json.gz'
    assert sha(result_path) == receipt['result_sha256']
    data = read_result(result_path)
    assert data['conditional_case']['case_sha'] == receipt['case_sha']
    assert data['conditional_case']['source_freeze_sha'] == EXPECTED_SOURCE
    audit = data['experimental_candidate_audit']
    state = data['carryout']['controller']
    budgets = data['qos_budget_ledger']
    active = {row['job_uid'] for row in data['queue_ledger']}
    generated = collections.Counter()
    evaluated = collections.Counter()
    q50_hard_pass_actions = collections.Counter()
    rejected = collections.Counter()
    for event in audit:
        generated.update(event.get('generated_action_counts', {}))
        evaluated.update(event.get('evaluated_action_counts', {}))
        q50_hard_pass_actions.update('DELAY' if row['action'].startswith('DELAY') else row['action']
            for row in event.get('q50_scores', []) if row['hard'])
        rejected.update(row['reason'] for row in event.get('rejected', []))
    starts = [event for event in data['job_event_ledger'] if event['event'] == 'RUNNING']
    started_uids = {event['uid'] for event in starts}
    start_actions = {event['uid']: event['action'] for event in starts}
    admitted_uids = {row['job_uid'] for row in data['queue_ledger'] if row.get('admitted_time') is not None}
    episode_started_uids = {uid for uid, row in state['episode_jobs'].items() if row.get('start_time') is not None}
    initial_running_uids = episode_started_uids - started_uids
    never_started_uids = active - admitted_uids
    assert admitted_uids == episode_started_uids
    assert len(initial_running_uids) + len(started_uids) + len(never_started_uids) == len(active)
    late = []
    no_window = []
    for event in starts:
        decision = state['decisions'][event['uid']]
        window = decision.get('execution_window_receipt')
        if window is None:
            no_window.append(event['uid'])
        elif (event['time_seconds'] > window['latest_start_seconds']
              or event['time_seconds'] not in window['allowed_starts_seconds']):
            late.append(dict(uid=event['uid'], start=event['time_seconds'],
                deadline=window['latest_start_seconds']))
    violations = [row['uid'] for row in data['qos_ledger']
                  if row['total_intentional_burden_seconds'] > row['budget_seconds'] + 1e-7]
    protected = [uid for uid in active if budgets[uid]['source_observed_metadata'].get('protected') is True
        or str(budgets[uid]['source_observed_metadata'].get('qos', '')).lower() in {'high', 'urgent'}
        or budgets[uid]['source_observed_metadata'].get('batch_eligible') is False]
    protection_failures = [uid for uid in protected if budgets[uid]['budget_seconds'] != 0
                           or budgets[uid]['eligible_for_contract']]
    refs = collections.defaultdict(list)
    advances = []
    for row in data['experimental_reference_audit']:
        if row['event'] == 'CAUSAL_REFERENCE_FROZEN':
            refs[row['uid']].append(row)
        elif row['event'] == 'OBSERVED_PHYSICAL_REFERENCE_ADVANCE':
            advances.append(row)
    for uid in refs:
        refs[uid].sort(key=lambda row: row['proof']['observed_at_seconds'])
    advance_proof_violations = []
    for row in advances:
        prior = [ref for ref in refs[row['uid']]
                 if ref['reference_start_seconds'] == row['old_reference_start_seconds']
                 and ref['proof']['observed_at_seconds'] <= row['proof']['observed_at_seconds']]
        if not prior:
            advance_proof_violations.append(dict(uid=row['uid'], reason='NO_PRIOR_REFERENCE'))
            continue
        ref = prior[-1]
        proof = row['proof']
        deadline = ref['reference_start_seconds'] + budgets[row['uid']]['budget_seconds'] - ref['intentional_burden_at_reference_seconds']
        if (proof['old_reference_start_seconds'] != row['old_reference_start_seconds']
            or proof['observed_at_seconds'] < row['old_reference_start_seconds']
            or proof['observed_at_seconds'] > deadline
            or row['new_reference_start_seconds'] <= row['old_reference_start_seconds']
            or row['immutable_budget_renewed'] or row['intentional_spend_refunded']
            or not proof.get('observed_GPU') or not proof.get('public_resource_sha')
            or (row['wait_class'] == 'GRID_REQUIRED_WAIT' and not proof.get('original_grid_violations'))):
            advance_proof_violations.append(dict(uid=row['uid'], reason='INVALID_OR_LATE_OBSERVED_ADVANCE_PROOF'))
    expired = []
    other_empty = []
    for event in audit:
        if event.get('terminal_status') != 'EMPTY_EXPERIMENTAL_EXECUTION_WINDOW':
            continue
        uid = event['uid']
        history = refs[uid]
        index = bisect.bisect_right([r['proof']['observed_at_seconds'] for r in history],
                                   event['time_seconds']) - 1
        assert index >= 0
        ref = history[index]
        # PENDING has no prior migration: once started this engine never returns
        # an episode to PENDING. Source hard/representation emptiness is separate.
        deadline = ref['reference_start_seconds'] + budgets[uid]['budget_seconds'] - ref['intentional_burden_at_reference_seconds']
        (expired if event['time_seconds'] > deadline else other_empty).append(uid)
    risks = data['experimental_pending_contract_risk']
    risk_uids = {row['uid'] for row in risks}
    frozen_reference_uids = set(state['experimental_runtime_state']['references'])
    no_R0_pending_uids = never_started_uids - frozen_reference_uids
    assert len(risks) == len(risk_uids)
    assert risk_uids == never_started_uids & frozen_reference_uids
    actual = data['receipt']
    cc4 = data['cc4_depletion_ledger']
    cc4_uids = {row['uid'] for row in cc4}
    assert len(cc4) == len(cc4_uids) == 696
    assert all(row['depletion_count'] == 1 for row in cc4)
    positive = {uid for uid in active if budgets[uid]['budget_seconds'] > 0}
    response = dict(case_sha=receipt['case_sha'], source_sha=EXPECTED_SOURCE,
        scenario=receipt['scenario'], participation=receipt['participation'], algorithm=receipt['algorithm'],
        result_SHA256=receipt['result_sha256'],
        lookup_events=len(audit), lookup_unique_UIDs=len({r['uid'] for r in audit}),
        lookup_definition='DYNAMIC_BOUNDED_SELECTOR_ENTRY;NOT_FROZEN_TABLE_MATCH',
        generated_candidates=sum(r['generated'] for r in audit),
        evaluated_candidates=sum(r['physically_and_grid_evaluated'] for r in audit),
        Q50_hard_pass_candidates=sum(r['q50_hard_pass'] for r in audit),
        approved_candidate_occurrences=sum(r['approved'] for r in audit),
        generated_action_counts=dict(generated), evaluated_action_counts=dict(evaluated),
        Q50_hard_pass_action_counts=dict(q50_hard_pass_actions),
        evaluated_candidates_are_scored_occurrences_not_necessarily_hard_approved=True,
        rejection_reason_occurrences=dict(rejected),
        selected_action_occurrences=dict(collections.Counter(r['selected_action'] for r in audit)),
        selected_action_count_scope='OCCURRENCES;RETRY_SELECTIONS_MAY_NOT_EXECUTE',
        executed_start_actions=dict(collections.Counter(r['action'] for r in starts)),
        executed_start_unique_UIDs=len({r['uid'] for r in starts}),
        initial_running_UID_count=len(initial_running_uids),
        never_started_UID_count=len(never_started_uids),
        never_started_UIDs=sorted(never_started_uids),
        public_initial_plus_new_start_plus_never_start_population_count=len(initial_running_uids)+len(started_uids)+len(never_started_uids),
        executed_migrations=len(data['migration_receipts']),
        source_explicit_protected_high_urgent_nonbatch_jobs=len(protected),
        source_protection_authority_violations=protection_failures,
        source_raw_QoS_labels_active=dict(collections.Counter(budgets[uid]['source_observed_metadata'].get('qos') for uid in active)),
        source_missing_protection_jobs=sum(budgets[uid]['source_observed_metadata'].get('protected') is None for uid in active),
        source_missing_batch_eligibility_jobs=sum(budgets[uid]['source_observed_metadata'].get('batch_eligible') is None for uid in active),
        positive_assumed_contract_active_jobs=len(positive),
        committed_intentional_delay_seconds=sum(r['intentional_start_delay_seconds'] for r in data['qos_ledger']),
        committed_intentional_delay_seconds_started_UIDs=sum(r['intentional_start_delay_seconds'] for r in data['qos_ledger'] if r['uid'] in started_uids),
        committed_intentional_delay_seconds_never_started_UIDs=sum(r['intentional_start_delay_seconds'] for r in data['qos_ledger'] if r['uid'] not in started_uids),
        committed_delay_by_executed_start_action={action:sum(r['intentional_start_delay_seconds'] for r in data['qos_ledger'] if start_actions.get(r['uid']) == action) for action in set(start_actions.values())},
        committed_delay_is_not_the_same_as_executed_DELAY_action_count=True,
        intentional_shared_budget_violation_UIDs=violations,
        legacy_original_issuer_latest_start_excess_jobs=sum(row['latest_start_excess_seconds']>1e-7 for row in data['qos_ledger']),
        legacy_latest_excess_is_separate_from_new_causal_R0_contract_compliance=True,
        late_start_outside_frozen_research_window=late,
        executed_starts_missing_research_window_UIDs=no_window,
        queued_after_window_expiry_event_count=len(expired),
        queued_after_window_expiry_unique_UIDs=len(set(expired)),
        empty_other_source_hard_or_representation_window_events=len(other_empty),
        observed_physical_reference_advance_count=len(advances),
        physical_reference_advance_wait_classes=dict(collections.Counter(r['wait_class'] for r in advances)),
        physical_reference_advance_seconds_by_class={key:sum(r['new_reference_start_seconds']-r['old_reference_start_seconds']
            for r in advances if r['wait_class'] == key) for key in {r['wait_class'] for r in advances}},
        current_physical_proof_is_required_not_future_Q50_or_clock_only=True,
        invalid_or_late_observed_reference_advance_proofs=advance_proof_violations,
        selected_Q90_CDF_timing_status_counts=dict(collections.Counter(event['selected_Q90_risk']['CDF_timing_status'] for event in audit if event.get('selected_Q90_risk'))),
        selected_Q90_mass_conservation_failures=sum(not event['selected_Q90_mass']['conservation_PASS'] for event in audit if event.get('selected_Q90_mass')),
        selected_Q90_physical_hard_failures=sum(not event['selected_Q90_risk']['hard_feasible'] for event in audit if event.get('selected_Q90_risk')),
        pending_never_started_risk_UID_count=len(risks),
        pending_first_R0_risk_record_count=len(risks),
        pending_risk_scope='ONLY_NEVER_STARTED_WITH_FROZEN_FIRST_R0;NOT_TOTAL_NEVER_STARTED_POPULATION',
        never_started_without_frozen_R0_UIDs=sorted(no_R0_pending_uids),
        never_started_without_frozen_R0_positive_budget_jobs=sum(uid in positive for uid in no_R0_pending_uids),
        no_R0_pending_contract_overdue_assessment=None,
        pending_positive_assumed_contract_overdue_jobs=sum(r['uid'] in positive and r['contract_overdue_at_end'] for r in risks),
        pending_grid_required_wait_seconds=sum(r['grid_required_wait_seconds'] for r in risks),
        pending_observed_resource_wait_seconds=sum(r['physical_resource_wait_seconds'] for r in risks),
        whole_observed_job_SLA_certified=False,
        total_queue_wait_is_not_equated_with_intentional_delay_or_capacity_wait=True,
        actual_receipt=actual, actual_capacity_violations=actual['capacity_violations'],
        dropped_jobs=actual['dropped_jobs'], private_future_controller_reads=actual['future_duration_controller_reads']+actual['future_completion_controller_reads'],
        retrospective_service_mass_audit=receipt['retrospective_service_audit'],
        CC4_observed_future_submission_depletion_events=len(cc4),
        CC4_observed_future_submission_unique_UIDs=len(cc4_uids),
        CC4_once_PASS=True,
        affine_current_and_Q50_guard='ORIGINAL_FROZEN_SIGNED_GRID_ROWS;UNAVOIDABLE_RUNNING_NOT_EVICTED',
        actual_electrical_safety_certified=False, Actual_Maximum_Line_Loading=None, Fresh_AC='NOT_RUN')
    assert not violations and not protection_failures and not late and not no_window and not advance_proof_violations
    assert response['selected_Q90_mass_conservation_failures'] == response['selected_Q90_physical_hard_failures'] == 0
    assert actual['capacity_violations'] == actual['dropped_jobs'] == response['private_future_controller_reads'] == 0
    if cell:
        assert cell['case_sha'] == response['case_sha'] and cell['source_sha'] == EXPECTED_SOURCE
        assert cell['generated_candidates'] == response['generated_candidates']
        assert cell['policy_lookup_events'] == response['lookup_events']
    return response


def main():
    manifest = read(OUT / 'CASE_MANIFEST.json')
    detail = read(OUT / 'COMPARISON_DETAIL.json')
    assert manifest['source_sha'] == detail['source_sha'] == EXPECTED_SOURCE
    expected = set(itertools.product(('E1', 'E2'), ('FLEX20', 'FLEX30', 'FLEX40'),
                                    ('FIXED', 'GREEDY', 'GRID_SENSITIVITY_AWARE')))
    assert {tuple(c[k] for k in ('scenario', 'participation', 'algorithm')) for c in manifest['cases']} == expected
    cells = {c['case_sha']: c for c in detail['cells'] if c['scenario'] != 'E0'}
    assert len(cells) == 18
    physical_review_path = ROOT / 'audit/independent_review/C_COMPLETED_CASE_VALIDATION.json'
    physical_review = read(physical_review_path)
    assert physical_review['source_sha'] == EXPECTED_SOURCE
    assert physical_review['complete'] and physical_review['completed_cases'] == 18 and physical_review['all_completed_PASS']
    physical_cases = {row['name']: row for row in physical_review['cases']}
    assert len(physical_cases) == 18
    responses = []
    for case in manifest['cases']:
        name = '_'.join(case[k] for k in ('scenario', 'participation', 'algorithm'))
        folder = OUT / name
        response = audit_case(folder, cells[case['case_sha']])
        checked = physical_cases[name]
        assert checked['PASS'] and all(checked['checks'].values())
        assert checked['source_sha'] == EXPECTED_SOURCE and checked['case_sha'] == response['case_sha']
        assert checked['result_file_sha'] == response['result_SHA256']
        arrays = checked['physical_array_validation']
        assert arrays['PASS'] and sha(Path(arrays['path'])) == arrays['sha256']
        response['all96_physical_array_evidence'] = arrays
        response['physical_evidence_scope'] = 'INDEPENDENT_MONITOR_JSON_VS_NPZ_AND_SOURCE_CAPS_REVIEW_REBOUND_TO_EXACT_RESULT_AND_ARRAY_HASH;NOT_NEW_PHYSICS_OR_AC'
        response['public_DDay_queue_wait_audit'] = cells[case['case_sha']]['DDay_queue_wait_audit']
        response['historical_issue_and_day_queue_wait_seconds'] = cells[case['case_sha']]['historical_issue_and_day_queue_wait_seconds']
        response['physical_start_delta_vs_final_causal_reference_seconds'] = cells[case['case_sha']]['physical_start_minus_final_causal_reference_seconds']
        response['physical_start_delta_is_not_persistent_charged_obligation'] = True
        assert cells[case['case_sha']]['physical_never_started_jobs'] == response['never_started_UID_count']
        assert cells[case['case_sha']]['pending_first_reference_risk_unique_jobs'] == response['pending_first_R0_risk_record_count']
        responses.append(response)
        print(json.dumps(dict(audited_case=name, completed=len(responses), total=18,
            never_started=response['never_started_UID_count'], risk_R0_records=response['pending_first_R0_risk_record_count'],
            executed=response['executed_start_actions'], migrations=response['executed_migrations'])), flush=True)
    report = dict(schema='CONTROL_RESOURCE_GUARD_BEFORE_AFTER_V1', status='PASS', source_sha=EXPECTED_SOURCE,
        E0=source_baseline(ROOT/'audit/control/FINAL_E0_STRICT_BASELINE_FULL96/CONDITIONAL_ACTUAL_RESULT.json.gz',
            {'OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT':5763,'NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY':53}),
        D_source_only=source_baseline(D_RESULT,
            {'ACTION_QOS_AUTHORITY_UNCONFIRMED':4128,'OFF_GRID_CHECKPOINT_OUTSIDE_FROZEN_SCORE_TEMPLATE':1635,'NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY':53}),
        C_cases=responses, C_independent_full96_executions=18, E0_nine_cells_are_one_execution_aliases=True,
        all18_independent_physical_validation_file=dict(path=str(physical_review_path), sha256=sha(physical_review_path)),
        comparison_detail_file=dict(path=str(OUT/'COMPARISON_DETAIL.json'),sha256=sha(OUT/'COMPARISON_DETAIL.json')),
        all18_budget_window_and_observed_R0_proofs_PASS=True,
        all18_capacity_drop_private_CC4_and_service_mass_PASS=True,
        all18_first_R0_risk_scope_is_not_all_never_started=True,
        comparison_scope='C_ADDS_DECLARED_ASSUMED_CONTRACTS_AND_DYNAMIC_CURRENT_HARD_GUARDS;NOT_ONLY_A_SUPPORT_BOX_PATCH',
        removed_blanket_forecast_box_veto=True, physical_GPU_rack_WAN_and_original_signed_grid_relaxation=False,
        affine_guard_is_not_Fresh_AC_certificate=True, observed_whole_SLA_PASS_claim=False,
        Native_runs_by_auditor=0, Actual_runs_by_auditor=0, Fresh_AC_runs_by_auditor=0)
    target=ROOT/'audit/CONTROL_RESOURCE_GUARD_BEFORE_AFTER.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',cases=18,target=str(target))))


if __name__ == '__main__':
    main()
