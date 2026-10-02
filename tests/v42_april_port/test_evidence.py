"""Check persisted authority against code and retained April populations.

These checks never open May workload/coefficient/outcome payloads or invoke a
producer, Runtime fit, optimizer, or OpenDSS engine. Code hashes identify the
construction blueprint; April input receipts do not certify executed physics.
"""
import ast
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from v42_april_port.builder import BASE, MODEL, SCHEMA, axis, immutable_request, timestamp


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/v42_april_port_from_may_pipeline'
PRIOR = ROOT / 'docs/v42_april_b0_voltage_margin_calibration_v2'
DAYS = tuple((date(2025, 4, 1) + timedelta(days=i)).isoformat() for i in range(30))
STAGES = {
    'RAW_WORKLOAD_SOURCE', 'CANONICAL_JOB_IDENTITY', 'D1_KNOWN_POPULATION',
    'GPU_REQUEST_AND_GANG', 'RUNTIME_AND_SERVICE', 'STATE_AND_RESIDUAL_SERVICE',
    'SITE_RACK_COMPATIBILITY', 'FACILITY_CAPACITY', 'AIDC_IT_POWER',
    'AIDC_PCC_POWER', 'LOAD_PV_WEATHER', 'CC4_COMMON_FORECAST',
    'GRID_NETWORK_AND_PLANNING_INPUT', 'PLANNING_BUNDLE_AND_FREEZE',
    'ACTUAL_REALIZED_POPULATION', 'ACTUAL_PHYSICAL_BUNDLE', 'OPENDSS_INPUT',
}
FIELDS = {
    'job_uid', 'submission_time', 'state', 'GPU_gang', 'immutable_GPU_request',
    'service_slots', 'remaining_service', 'Q50_total_seconds', 'runtime_authority',
    'requested_walltime', 'elapsed_seconds', 'site', 'reference_start',
    'compatible_sites', 'rack_authority', 'facility_capacity', 'P_IT', 'P_PCC',
    'Q_PCC', 'PUE', 'load_forecast', 'load_actual', 'PV_forecast', 'PV_actual',
    'weather_forecast', 'weather_actual', 'network_grid', 'alpha_BG',
    'CC4_Q50_Q90', 'J_known', 'J_actual', 'actual_occupancy', 'MESS_initial_state',
    'frozen_plan', 'DA_diagnostic', 'D_Day_Actual',
}
REQUIRED_GATE_FIELDS = (
    'KNOWN_GPU_AUTHORITY_COMPLETE', 'ACTUAL_GPU_AUTHORITY_COMPLETE',
    'runtime_authority_complete', 'compatibility_complete',
    'capacity_authority_complete', 'forecast_complete', 'actual_grid_complete',
    'network_static_authority_complete', 'april_electrical_adapter_bound',
    'CC4_forecast_bound', 'request_version_authority_verified',
    'workload_population_present',
)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def positive_gpu(value):
    return type(value) is int and value > 0


@pytest.mark.parametrize('source_member', (
    'synthetic-fixture/year=2025/month=5/requests.csv',
    'synthetic-fixture/year=2026/month=1/requests.csv',
    'synthetic-fixture/year=2026/month=4/requests.csv',
))
def test_exact_identity_cannot_use_a_future_month_or_year_donor(source_member):
    # Synthetic descriptors only: a perfect UID/submission match does not
    # authorize reading a later partition as an earlier-day value authority.
    submission = '2025-03-31T00:00:00+00:00'
    target = dict(job_uid='synthetic-exact-identity', submit_time=submission)
    request = dict(target, gpus_requested=2, source_member=source_member)
    with pytest.raises(ValueError, match='^FUTURE_MONTH_VALUE_DONOR$'):
        immutable_request(target, {target['job_uid']: [request]},
                          event_time='2025-03-31T08:00:00+00:00', target_day='2025-04-01')


def test_all_lineage_stages_have_provenance_units_and_causal_boundary():
    manifest = read(OUT / 'MAY_PIPELINE/MAY_V42_PIPELINE_MANIFEST.json')
    assert manifest['base'] == BASE
    assert manifest['lineage_forensic_complete'] is True
    stages = manifest['pipeline_stages']
    assert len(stages) == len(STAGES) == 17
    assert {row['stage'] for row in stages} == STAGES
    for row in stages:
        assert row['code'] and row['source_artifacts']
        assert row['authoritative_fields'] and row['derived_fields']
        assert row['units'] and row['timezone'] and row['temporal_resolution']
        assert row['causal_cutoff'] and row['April_action']
        for source in row['source_artifacts']:
            assert len(source['sha256']) == 64
            assert set(source['sha256']) <= set('0123456789abcdef')
    current_actual = next(row for row in stages if row['stage'] == 'ACTUAL_PHYSICAL_BUNDLE')
    assert current_actual['status'] == 'CODE_LINEAGE_RESOLVED_CONCRETE_NATIVE_ADAPTER_NOT_PRESENT'
    assert manifest['scientific_bundle_PASS'] is False


def test_lineage_function_references_match_actual_code_without_importing_it():
    manifest = read(OUT / 'MAY_PIPELINE/MAY_V42_PIPELINE_MANIFEST.json')
    unique = {}
    for stage in manifest['pipeline_stages']:
        for reference in stage['code']:
            unique.setdefault(reference['path'], []).append(reference)
    assert len(unique) == 32
    for path, references in unique.items():
        source = Path(path)
        assert source.suffix == '.py'
        raw = source.read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        tree = ast.parse(raw.decode('utf-8-sig'))
        definitions = {
            (node.name, node.lineno, node.end_lineno)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        for reference in references:
            assert reference['sha256'] == observed
            assert reference['read_scope'] == 'SOURCE_CODE_ONLY'
            assert (reference['symbol'].split('.')[-1], reference['start_line'], reference['end_line']) in definitions


def test_crosswalk_distinguishes_current_rules_from_historical_exclusions():
    rows = csv_rows(OUT / 'PORT/MAY_TO_APRIL_SCHEMA_CROSSWALK.csv')
    assert len(rows) == 36
    by_field = {row['field']: row for row in rows}
    assert set(by_field) == FIELDS
    for row in rows:
        assert all(row.values())
        assert row['same_semantics'] in ('true', 'false')
    assert by_field['GPU_gang']['same_semantics'] == 'false'
    assert by_field['GPU_gang']['action'] == 'SUPERSEDE_HISTORICAL_DROP_NO_IMPUTE'
    assert by_field['J_actual']['action'] == 'SUPERSEDE_KNOWN_ONLY_ACTUAL'
    assert by_field['service_slots']['action'] == 'KEEP_CURRENT_RUNTIME'
    assert by_field['requested_walltime']['action'] == 'NEVER_PROMOTE_AS_SERVICE'
    assert by_field['network_grid']['action'] == 'MAY_COEFFICIENT_ARRAY_COPY_FORBIDDEN'
    assert by_field['DA_diagnostic']['action'] == 'NEVER_OPERATIONAL_GATE'


def test_may_blueprint_is_not_a_scientific_value_donor():
    manifest = read(OUT / 'MAY_PIPELINE/MAY_V42_PIPELINE_MANIFEST.json')
    assert manifest['MAY_PIPELINE_USED_AS_BLUEPRINT'] is True
    for flag in ('MAY_SCIENTIFIC_OUTCOMES_USED_FOR_APRIL', 'MAY_USED_FOR_MARGIN_CALIBRATION',
                 'May_job_value_donation'):
        assert manifest[flag] is False
    for count in ('May_voltages_read', 'May_Actual_result_reads', 'May_policy_result_reads',
                  'May_calibration_result_reads', 'May_optimization_calls', 'May_OpenDSS_calls'):
        assert manifest[count] == 0
    runtime = read(OUT / 'MAY_PIPELINE/MAY_RUNTIME_AUTHORITY.json')
    power = read(OUT / 'MAY_PIPELINE/MAY_POWER_CONVERSION_AUDIT.json')
    assert runtime['May_outcomes_read'] is False
    assert power['May_scientific_outcomes_read'] is False
    for evidence in (runtime, power):
        assert evidence['May_optimization_calls'] == evidence['May_OpenDSS_calls'] == 0
    assert power['grid']['May_numerical_coefficients_as_April_donor'] is False


def test_current_runtime_and_capacity_are_retained_for_b0():
    runtime = read(OUT / 'MAY_PIPELINE/MAY_RUNTIME_AUTHORITY.json')
    power = read(OUT / 'MAY_PIPELINE/MAY_POWER_CONVERSION_AUDIT.json')
    assert runtime['MODEL'] == MODEL
    assert runtime['ML_RUNTIME_USED'] is True
    assert runtime['requested_walltime_service_authority'] is False
    provider = runtime['provider']
    assert provider['quantile'] == .5
    assert provider['family'] == 'ISOTONIC' and provider['mode'] == 'ROLLING14'
    assert provider['fitting_calls'] == provider['calibration_fitting_calls'] == 0
    assert timestamp(provider['max_completion_used']) < timestamp(provider['available_at'])
    assert power['capacity']['site_GPU'] == [80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80]
    assert sum(power['capacity']['site_GPU']) == power['capacity']['total_GPU'] == 780
    assert power['PCC']['PF_AIDC'] == .95


def test_gpu_blueprint_answers_all_authority_questions_with_exact_code_evidence():
    audit = read(OUT / 'MAY_PIPELINE/MAY_GPU_AUTHORITY_AUDIT.json')
    assert audit['forensic_complete'] is True
    assert audit['status'] == 'MAY_GPU_CONSTRUCTION_RULE_RESTORED'
    assert {answer['number'] for answer in audit['answers']} == set(range(1, 9))
    assert len(audit['lineage']) == 7
    for row in audit['lineage']:
        assert row['field_in'] and row['field_out'] and row['evidence']
    controls = audit['inspection_controls']
    for name in ('May_job_payloads_parsed', 'May_scientific_outcome_payloads_read',
                 'May_row_numeric_reproduction_performed', 'May_code_executed',
                 'external_raw_modified', 'historical_requested_walltime_service_fallback'):
        assert controls[name] is False
    assert controls['optimizer_calls'] == controls['OpenDSS_calls'] == 0
    assert controls['current_runtime_service_authority'] == MODEL
    contract = audit['permissible_april_transformation_frozen']
    assert contract['contract'] == 'EXACT_SOURCE_GPU_REQUEST_CANONICALIZATION_RETAIN_FAIL_CLOSED_V1'
    assert contract['new_missing_GPU_derivation_discovered'] is False
    assert any(row['old'] == 'EXCLUDE_MISSING_GPU' and row['new'] == 'RETAIN_FAIL_CLOSED'
               for row in audit['superseded_rules'])
    matches = audit['common_receipt_hash_matches']
    assert len(matches) == 8 and all(row['sha256_and_bytes_match'] is True for row in matches)
    for source in audit['code_sources'].values():
        path = Path(source['path'])
        assert path.suffix == '.py'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
    for answer in audit['answers']:
        assert answer['question'] and answer['answer'] and answer['evidence']
        for source in answer['evidence']:
            assert len(source['sha256']) == 64
            assert 0 < source['line_start'] <= source['line_end']


def test_holdout_guard_explicitly_disallows_values_and_scientific_outcomes():
    guard = read(OUT / 'MAY_HOLDOUT_GUARD.json')
    assert guard['MAY_USED_AS_IMPLEMENTATION_BLUEPRINT'] is True
    assert guard['MAY_PIPELINE_USED_AS_BLUEPRINT'] is True
    assert guard['MAY_USED_FOR_MARGIN_CALIBRATION'] is False
    assert guard['MAY_SCIENTIFIC_OUTCOMES_USED_FOR_APRIL'] is False
    assert guard['May_job_values_as_donor'] is False
    assert guard['May_scientific_outcome_files_read'] == guard['May_request_payload_members_read'] == []
    assert guard['May_optimizer_calls'] == guard['May_OpenDSS_calls'] == 0


@pytest.mark.parametrize('day', DAYS)
def test_each_april_day_retains_populations_runtime_and_immutable_gpu(day):
    folder = OUT / 'APRIL' / ('DAY_' + day.replace('-', ''))
    old_folder = PRIOR / 'APRIL_V42_INPUT_BUNDLE' / folder.name
    planning = read(folder / 'PLANNING_INPUT_BUNDLE.json')
    actual = read(folder / 'ACTUAL_INPUT_BUNDLE.json')
    prior_planning = read(old_folder / 'PLANNING_INPUT_BUNDLE.json')
    prior_actual = read(old_folder / 'ACTUAL_INPUT_BUNDLE.json')
    provenance = read(folder / 'INPUT_PROVENANCE.json')
    issue, start, end = axis(day)
    assert planning['schema'] == actual['schema'] == SCHEMA
    assert planning['day'] == actual['day'] == day
    assert planning['slots'] == actual['slots'] == 96
    assert planning['slot_seconds'] == actual['slot_seconds'] == 900
    assert planning['runtime_authority'] == actual['runtime_authority'] == MODEL
    assert planning['primary_voltage_band_pu'] == [.95, 1.05]
    assert planning['future_actual_arrival_IDs_present'] is False
    known = {row['job_uid']: row for row in planning['known_population']}
    arrivals = {row['job_uid']: row for row in actual['post_issue_arrivals']}
    old_known = {row['job_uid']: row for row in prior_planning['known_population']}
    old_arrivals = {row['job_uid']: row for row in prior_actual['post_issue_arrivals']}
    assert len(known) == len(planning['known_population'])
    assert len(arrivals) == len(actual['post_issue_arrivals'])
    assert set(known) == set(old_known) and set(arrivals) == set(old_arrivals)
    assert set(known).isdisjoint(arrivals)
    for rows, previous in ((known, old_known), (arrivals, old_arrivals)):
        for uid, row in rows.items():
            assert row['GPU_gang'] == previous[uid]['GPU_gang']
            assert row['GPU_gang'] is None or positive_gpu(row['GPU_gang'])
            assert row['runtime_authority'] == previous[uid]['runtime_authority'] == MODEL
            assert row['service_slots'] == previous[uid]['service_slots']
            assert type(row['service_slots']) is int and row['service_slots'] >= 0
            assert row['Q50_total_seconds'] == pytest.approx(previous[uid]['Q50_total_seconds'], rel=1e-12, abs=1e-8)
            assert row['request_version_history'] == 'UNVERIFIED_SOURCE_PROXY'
            assert row['gpu_source_field'] == 'gpus_requested'
            assert row['source_member'].find('year=2025/month=5/') == -1
    for row in known.values():
        assert timestamp(row['submit_time']) <= timestamp(issue)
        assert timestamp(row['runtime_inference_event_time']) == timestamp(issue)
        assert 'start_time' not in row and 'end_time' not in row
    for row in arrivals.values():
        assert timestamp(issue) < timestamp(row['submit_time']) < timestamp(end)
        assert timestamp(row['runtime_inference_event_time']) == timestamp(row['submit_time'])
        for field in ('start_observed_by_day_end', 'end_observed_by_day_end'):
            if row[field] is not None:
                assert timestamp(row[field]) <= timestamp(end)
    assert actual['known_immutable_GPU_map'] == {uid: row['GPU_gang'] for uid, row in known.items()}
    assert {row['job_uid']: row['GPU_gang'] for row in actual['observed_known_episodes']} == actual['known_immutable_GPU_map']
    assert actual['physical_arrays_generated'] is False
    assert actual['actual_occupancy_reconstructed'] is False
    assert actual['IT_recomputed_from_actual_occupancy'] is None
    assert provenance['May_request_payload_members_read'] == provenance['May_scientific_results_read'] == []
    assert provenance['actual_observations_in_Planning'] is False
    assert provenance['Runtime_fit_calls'] == 0


def test_thirty_day_gate_is_conjunction_and_reconciles_all_retained_rows():
    manifest = read(OUT / 'APRIL/APRIL_INPUT_MANIFEST.json')
    summary = read(OUT / 'APRIL/APRIL_GPU_AUTHORITY_SUMMARY.json')
    assert tuple(manifest['date_axis']) == DAYS
    assert tuple(record['day'] for record in manifest['days']) == DAYS
    csv_gate = csv_rows(OUT / 'APRIL/APRIL_DAY_INPUT_GATE.csv')
    assert tuple(row['day'] for row in csv_gate) == DAYS
    for record, persisted in zip(manifest['days'], csv_gate):
        gate = record['gate']
        assert gate['PASS'] == all(gate[key] for key in REQUIRED_GATE_FIELDS)
        assert persisted['PASS'] == str(gate['PASS'])
        assert gate['ACTUAL_GPU_AUTHORITY_COMPLETE'] == (
            gate['KNOWN_GPU_AUTHORITY_COMPLETE'] and gate['ARRIVAL_GPU_AUTHORITY_COMPLETE'])
        assert gate['rows_dropped'] == 0
        assert gate['source_population_reconciliation_PASS'] is True
        assert gate['historical_missing_exclusion_ported'] is False
        assert gate['submission_cutoff_PASS'] is True
        assert gate['D1_request_version_causality_PASS'] is None
        assert gate['scientific_execution'] == 'NOT_RUN'
    assert manifest['complete_days'] == summary['complete_days'] == sum(record['gate']['PASS'] for record in manifest['days']) == 0
    assert summary['known_jobs'] == sum(record['gate']['known_jobs'] for record in manifest['days']) == 29350
    assert summary['actual_post_issue_jobs'] == sum(record['gate']['actual_post_issue_jobs'] for record in manifest['days']) == 82323
    assert summary['rows_dropped'] == 0 and summary['synthetic_fill'] is False
    assert summary['May_job_values_used'] is False


def test_gpu_reprocessing_preserves_missing_requests_instead_of_filling_them():
    summary = read(OUT / 'APRIL/APRIL_GPU_AUTHORITY_SUMMARY.json')
    ledger = csv_rows(OUT / 'APRIL/APRIL_GPU_AUTHORITY_REPROCESS_LEDGER.csv')
    assert summary['initial_known_missing'] == summary['known_unresolved'] == 5173
    assert summary['initial_Actual_missing'] == 16284
    assert summary['Actual_unresolved'] == 20459
    assert summary['recovered'] == summary['ambiguous'] == 0
    assert summary['unresolved'] == summary['expanded_missing_observations'] == len(ledger) == 25632
    assert summary['expanded_unique_jobs'] == len({row['job_uid'] for row in ledger}) == 16574
    assert summary['source_field_absent'] == 25632
    assert {row['status'] for row in ledger} == {'SOURCE_FIELD_ABSENT'}
    assert {row['source_field'] for row in ledger} == {'gpus_requested'}
    assert {row['parser_rule'] for row in ledger} == {'POSITIVE_INTEGER_RAW_REQUEST_NO_NODE_DERIVATION'}
    assert all(row['GPU_gang'] == '' for row in ledger)


def test_incomplete_inputs_do_not_become_reference_or_executed_science():
    reference = read(OUT / 'REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json')
    assert reference['status'] == 'NOT_GENERATED_INPUT_GATE_FAIL'
    assert reference['generated_days'] == 0
    assert reference['same_B0_B1_B2_B3_reference'] is True
    assert reference['missing_historical_mapping_is_STOP_condition'] is False
    assert reference['historical_GPU_missing_exclusion_ported'] is False
    assert csv_rows(OUT / 'REFERENCE/V42_COMMON_REFERENCE_SCHEDULE.csv') == []
    for day in DAYS:
        execution = read(OUT / 'B0' / ('DAY_' + day.replace('-', '')) / 'EXECUTION_STATUS.json')
        assert execution['status'] == 'NOT_RUN'
        for key in ('Planning_calls', 'OpenDSS_calls', 'full_reoptimization',
                    'P_repair', 'Q_repair', 'route_repair', 'schedule_repair'):
            assert execution[key] == 0
        for key in ('V_PLAN', 'V_DA_AC', 'V_DDAY_AC', 'physical_PASS', 'served_jobs',
                    'served_GPUh', 'AIDC_IT_energy_kWh', 'AIDC_PCC_energy_kWh', 'active_AIDC_slots'):
            assert execution[key] is None
        flags = execution['flags']
        assert flags['AIDC_PRESENT'] is True and flags['AIDC_WORKLOAD_PRESENT'] is True
        assert flags['ML_RUNTIME_USED'] is True
        assert flags['AIDC_FLEX_OPTIMIZATION'] is False and flags['MESS_ACTIVE'] is False
        assert flags['OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY'] is True
        assert flags['DA_AC_OPERATIONAL_GATE'] is False
        assert flags['FINAL_MARGIN_ACCEPTED'] is False
        for key in ('B1_RUN', 'B2_RUN', 'B3_RUN', 'MAY_RUN', 'M1_BENDERS_RUN',
                    'M1_PRODUCTION_RUN', 'A2_M2_PRODUCTION_RUN'):
            assert flags[key] is False


def test_prior_983_test_receipt_and_scientific_boundary_are_preserved():
    verification = read(PRIOR / 'VERIFICATION.json')
    assert verification['tests'] == dict(tests=983, failures=0, errors=0, skipped=0)
    assert verification['PR118_files_preserved'] == 2144
    assert verification['physical_execution_verified'] is False
    assert verification['scientific_calibration_complete'] is False


def test_nonexecution_has_no_residual_samples_quantiles_or_coverage():
    calibration = OUT / 'CALIBRATION'
    assert csv_rows(calibration / 'APRIL_B0_RESIDUALS.csv') == []
    for name, aggregation in (('POINTWISE_QUANTILES.csv', 'pointwise'),
                              ('DAY_WORST_QUANTILES.csv', 'day-worst')):
        quantiles = csv_rows(calibration / name)
        assert [float(row['q']) for row in quantiles] == [.9, .95, .975, .99]
        for row in quantiles:
            assert row['aggregation'] == aggregation
            assert row['n'] == '0'
            assert row['FINAL_MARGIN_ACCEPTED'] == 'False'
            for field in ('delta_up', 'delta_down', 'lower_candidate',
                          'upper_candidate', 'nonempty_band'):
                assert row[field] == ''
    coverage = read(calibration / 'CURRENT_005_COVERAGE.json')
    assert coverage['status'] == 'NOT_MEASURED_INPUT_GATE_FAIL'
    assert coverage['n'] == coverage['evaluated_days'] == 0
    assert coverage['margin_up'] == coverage['margin_down'] == .005
    for field in ('pointwise_empirical_coverage', 'day_coverage', 'exceedance_days',
                  'worst_exceedance', 'worst_node_phase_slot'):
        assert coverage[field] is None
    candidates = read(calibration / 'CANDIDATE_BANDS.json')
    assert candidates['status'] == 'NOT_MEASURED_INPUT_GATE_FAIL'
    assert candidates['n'] == 0 and candidates['candidates'] == []
    assert candidates['primary_voltage_pu'] == [.95, 1.05]
    assert candidates['FINAL_MARGIN_ACCEPTED'] is False


def test_final_verdict_does_not_promote_input_inventory_to_physical_pass():
    flags = read(OUT / 'FINAL_FLAGS.json')
    verdict = read(OUT / 'FINAL_VERDICT.json')
    assert verdict['status'] == 'BLOCKED_AFTER_FULL_MAY_FORENSIC_AND_APRIL_REPROCESSING'
    assert flags['CURRENT_RUNTIME_INFERENCE_USED'] is True
    assert flags['current_runtime_authority'] == MODEL
    for key in ('SCIENTIFIC_EXECUTED_DAYS', 'COMMON_REFERENCE_GENERATED_DAYS',
                'APRIL_INPUT_BUNDLE_COMPLETE_DAYS'):
        assert flags[key] == 0
    assert flags['AIDC_PRESENT'] is True and flags['AIDC_WORKLOAD_PRESENT'] is True
    assert flags['AIDC_physical_presence_verified'] is False
    assert flags['AIDC_FLEX_OPTIMIZATION'] is False and flags['MESS_ACTIVE'] is False
    assert flags['FINAL_MARGIN_ACCEPTED'] is False
    assert verdict['scientific_calibration_complete'] is False
    assert verdict['input_inventory_is_executable_bundle'] is False
    assert verdict['user_requested_scientific_execution_completed'] is False
    assert verdict['rows_dropped'] == 0 and verdict['GPU_imputed'] is False
    assert verdict['B0_executed_days'] == verdict['physical_pass_evaluated_days'] == 0
    assert verdict['DDay_physical_pass_days'] is None
    for key in ('served_jobs', 'served_GPUh', 'AIDC_IT_energy_kWh',
                'AIDC_PCC_energy_kWh', 'active_AIDC_slots', 'Q95_upper',
                'Q95_down', 'Q99_upper', 'Q99_down', 'current_005_coverage', 'candidate_band'):
        assert verdict[key] is None
    assert verdict['V_PLAN_generated'] is False
    assert verdict['V_DA_AC_generated'] is False
    assert verdict['V_DDAY_AC_generated'] is False
    assert verdict['FINAL_MARGIN_ACCEPTED'] is False
