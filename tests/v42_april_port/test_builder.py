"""Tiny TEST-only construction fixtures; no native May values or physical runs.

The provider deliberately predicts service unlike requested walltime. These
tests exercise the authority boundary, rather than establish scientific PASS.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from v42_april_port.builder import (
    B0_FLAGS, SCHEMA, axis, build_v42_day_input_bundle, freeze_common_reference,
    immutable_request, predict_causal_batch, require_b0_physical_presence,
)
from v42_april_b0_v2.contracts import ZERO_ACTIONS, digest, validate_controls
from v42_april_b0_v2.reference import QUEUE_RULE
from v42_final.common import MODEL


class TestOnlyFrozenProvider:
    """Frozen inference interface fake; no fitting, calibration, or native data."""

    __test__ = False

    def __init__(self, prediction=1800.0, available='2025-03-31T00:00:00Z'):
        self.available = datetime.fromisoformat(available.replace('Z', '+00:00'))
        self.prediction = prediction
        self.calls = []

    def predict_batch(self, records, *, submit_times, event_time):
        self.calls.append(deepcopy(dict(records=records, submissions=submit_times,
                                      event_time=event_time)))
        return [self.prediction for _ in records]


def fixture(day='2025-04-01'):
    """Identical April/May schema with freshly constructed synthetic timestamps."""
    issue, start, end = axis(day)
    known = [
        dict(job_uid='TEST_RUNNING', submit_time=(start-timedelta(hours=12)).isoformat(),
             state_at_D1_cutoff='RUNNING', elapsed_seconds=450,
             source_site='AIDC01', source_site_authority='TEST_ONLY_CURRENT_SITE'),
        dict(job_uid='TEST_PENDING', submit_time=(start-timedelta(hours=10)).isoformat(),
             state_at_D1_cutoff='PENDING', elapsed_seconds=0,
             source_site=None, source_site_authority=None),
    ]
    submissions = {j['job_uid']:j['submit_time'] for j in known}
    submissions.update(TEST_CARRYIN=(start-timedelta(hours=3)).isoformat(),
                       TEST_ARRIVAL=(start+timedelta(hours=1)).isoformat())
    gpus = dict(TEST_RUNNING=2, TEST_PENDING=4, TEST_CARRYIN=1, TEST_ARRIVAL=2)
    requests = {uid:[dict(submit_time=t, gpus_requested=gpus[uid], nodes_req=7,
                         processors_req=112, memory_req='1G', requested_seconds=86400,
                         array_pos=0, account_hash='TEST_ACCOUNT', qos='normal',
                         partition='TEST_H100', source_row=i,
                         source_member=f'TEST_ONLY/year={day[:4]}/month={int(day[5:7])}/jobs.parquet',
                         source_sha256='a'*64, request_version_verified=True)]
                for i,(uid,t) in enumerate(submissions.items())}
    observations = {
        'TEST_RUNNING':dict(start_time=(start-timedelta(hours=8)).isoformat(),
                            end_time=(start+timedelta(hours=3)).isoformat()),
        'TEST_PENDING':dict(start_time=(start+timedelta(hours=4)).isoformat(),
                            end_time=(end+timedelta(hours=3)).isoformat()),
        'TEST_CARRYIN':dict(start_time=(start-timedelta(hours=2)).isoformat(),
                            end_time=(start+timedelta(hours=1)).isoformat()),
        'TEST_ARRIVAL':dict(start_time=(start+timedelta(hours=2)).isoformat(),
                            end_time=(start+timedelta(hours=4)).isoformat()),
    }
    provider = TestOnlyFrozenProvider()
    return dict(day=day, known_snapshot=known, raw_requests=requests,
                actual_observations=observations, runtime_provider=provider,
                physical_authority=dict(capacities={'AIDC01':4, 'AIDC02':4},
                                        rack_compatibility={'AIDC01':[4], 'AIDC02':[4]},
                                        network_static_complete=True, electrical_adapter_bound=True,
                                        test_only=True),
                forecast_inputs=dict(complete=True, CC4_bound=True, test_only=True,
                                     load_mw=[1.0]*96, pv_mw=[0.2]*96),
                actual_inputs=dict(complete=True, test_only=True,
                                   load_mw=[1.1]*96, pv_mw=[0.1]*96))


def build(arguments):
    return build_v42_day_input_bundle(**arguments)


def by_uid(rows):
    return {j['job_uid']:j for j in rows}


def test_same_reusable_builder_constructs_april_and_test_only_may_schema():
    april = build(fixture('2025-04-01'))
    may = build(fixture('2025-05-01'))
    for a,b in zip(april[:3], may[:3]):
        assert set(a) == set(b)
    for result in (april, may):
        planning, actual, gate, _ = result
        assert gate['PASS'] is True
        assert planning['schema'] == actual['schema'] == SCHEMA
        assert planning['slots'] == actual['slots'] == 96
        assert planning['slot_seconds'] == actual['slot_seconds'] == 900
        assert planning['runtime_authority'] == actual['runtime_authority'] == MODEL
        assert gate['scientific_execution'] == 'NOT_RUN'
        assert actual['physical_arrays_generated'] is False
    assert set(april[0]['known_population'][0]) == set(may[0]['known_population'][0])
    assert set(april[1]['post_issue_arrivals'][0]) == set(may[1]['post_issue_arrivals'][0])


def test_april_axis_covers_all_30_dates_without_executing_science():
    first = datetime(2025, 4, 1)
    dates = [(first+timedelta(days=i)).date().isoformat() for i in range(30)]
    assert dates[-1] == '2025-04-30'
    for day in dates:
        planning, actual, gate, _ = build(fixture(day))
        issue, start, end = axis(day)
        assert start-issue == timedelta(hours=6)
        assert end-start == timedelta(days=1)
        assert planning['day'] == actual['day'] == gate['day'] == day
        assert gate['scientific_execution'] == 'NOT_RUN'


@pytest.mark.parametrize('missing', [None, float('nan'), 0, -1, 1.5, True])
def test_unresolved_known_gpu_is_retained_and_never_derived_from_nodes(missing):
    inputs = fixture()
    raw = inputs['raw_requests']['TEST_RUNNING'][0]
    raw.update(gpus_requested=missing, nodes_req=8, gpu_nodes_occupied=8,
               allocated_GPU=32)
    planning, actual, gate, recovery = build(inputs)
    known = by_uid(planning['known_population'])
    assert len(known) == 2
    assert known['TEST_RUNNING']['GPU_gang'] is None
    assert known['TEST_RUNNING']['service_slots'] == 2
    assert known['TEST_RUNNING']['runtime_authority'] == MODEL
    assert actual['known_immutable_GPU_map']['TEST_RUNNING'] is None
    assert gate['KNOWN_GPU_AUTHORITY_COMPLETE'] is False
    assert gate['ACTUAL_GPU_AUTHORITY_COMPLETE'] is False
    assert gate['runtime_authority_complete'] is True
    assert gate['no_synthetic_fill'] is True
    assert gate['rows_dropped'] == 0
    assert gate['PASS'] is False
    assert next(r for r in recovery if r['job_uid'] == 'TEST_RUNNING')['GPU_gang'] is None
    with pytest.raises(ValueError, match='INPUT_GATE_REQUIRED'):
        freeze_common_reference(planning, gate)


@pytest.mark.parametrize('missing', [None, 0, 2.5])
def test_unresolved_actual_gpu_has_separate_failing_authority_gate(missing):
    inputs = fixture()
    inputs['raw_requests']['TEST_ARRIVAL'][0]['gpus_requested'] = missing
    planning, actual, gate, _ = build(inputs)
    assert gate['KNOWN_GPU_AUTHORITY_COMPLETE'] is True
    assert gate['ACTUAL_GPU_AUTHORITY_COMPLETE'] is False
    assert gate['ARRIVAL_GPU_AUTHORITY_COMPLETE'] is False
    assert gate['PASS'] is False
    assert len(actual['post_issue_arrivals']) == 2
    assert by_uid(actual['post_issue_arrivals'])['TEST_ARRIVAL']['GPU_gang'] is None
    assert len(planning['known_population']) == 2


def test_positive_raw_request_uses_whole_gang_without_node_scaling():
    planning, actual, gate, _ = build(fixture())
    known = by_uid(planning['known_population'])
    assert known['TEST_RUNNING']['GPU_gang'] == 2
    assert known['TEST_PENDING']['GPU_gang'] == 4
    assert actual['known_immutable_GPU_map'] == {'TEST_RUNNING':2, 'TEST_PENDING':4}
    assert gate['missing_known_GPU'] == gate['missing_actual_GPU'] == 0


def test_same_request_identity_matches_equivalent_timestamp_offsets():
    inputs = fixture()
    raw = inputs['raw_requests']['TEST_RUNNING'][0]
    instant = datetime.fromisoformat(raw['submit_time'])
    raw['submit_time'] = instant.astimezone(timezone(timedelta(hours=-6))).isoformat()
    planning, _, gate, _ = build(inputs)
    assert gate['PASS'] is True
    assert by_uid(planning['known_population'])['TEST_RUNNING']['GPU_gang'] == 2


def test_same_uid_different_submission_cannot_supply_gpu_or_runtime():
    inputs = fixture()
    raw = inputs['raw_requests']['TEST_RUNNING'][0]
    raw['submit_time'] = (datetime.fromisoformat(raw['submit_time'])-timedelta(hours=1)).isoformat()
    planning, _, gate, recovery = build(inputs)
    row = by_uid(planning['known_population'])['TEST_RUNNING']
    assert row['GPU_gang'] is None and row['service_slots'] is None
    assert gate['PASS'] is False and gate['rows_dropped'] == 0
    record = next(r for r in recovery if r['job_uid'] == 'TEST_RUNNING')
    assert record['candidate_count'] == 0


@pytest.mark.parametrize('second_gpu', [2, 4, None])
def test_duplicate_exact_identity_requires_reconciliation_even_if_values_agree(second_gpu):
    inputs = fixture()
    records = inputs['raw_requests']['TEST_RUNNING']
    records.append(dict(records[0], gpus_requested=second_gpu, source_row=99))
    planning, _, gate, recovery = build(inputs)
    row = by_uid(planning['known_population'])['TEST_RUNNING']
    assert row['GPU_gang'] is None and row['service_slots'] is None
    assert gate['PASS'] is False and gate['rows_dropped'] == 0
    record = next(r for r in recovery if r['job_uid'] == 'TEST_RUNNING')
    assert record['status'] == 'AMBIGUOUS_SOURCE_MATCH'
    assert record['candidate_count'] == 2


def test_current_runtime_service_is_distinct_from_requested_walltime():
    inputs = fixture()
    planning, actual, gate, _ = build(inputs)
    known = by_uid(planning['known_population'])
    assert gate['runtime_authority'] == MODEL
    assert known['TEST_RUNNING']['Q50_total_seconds'] == 1800
    assert known['TEST_RUNNING']['nominal_remaining_seconds'] == 1350
    assert known['TEST_RUNNING']['service_slots'] == 2
    assert known['TEST_PENDING']['nominal_remaining_seconds'] == 1800
    assert known['TEST_PENDING']['service_slots'] == 2
    assert all(j['service_slots'] == 2 and j['runtime_authority'] == MODEL
               for j in actual['post_issue_arrivals'])
    for call in inputs['runtime_provider'].calls:
        for features in call['records']:
            assert features['requested_seconds'] == 86400
            assert features['requested_memory_mib'] == 1024
            assert not {'state', 'elapsed_seconds', 'start_time', 'end_time',
                        'actual_runtime', 'actual_remaining', 'voltage'}.intersection(features)


def test_raw_future_label_fields_do_not_become_runtime_predictor_features():
    inputs = fixture()
    inputs['raw_requests']['TEST_RUNNING'][0].update(
        end_time='2099-01-01T00:00:00Z', actual_runtime=1e20, voltage=0.1)
    build(inputs)
    assert all(not {'end_time', 'actual_runtime', 'voltage'}.intersection(r)
               for call in inputs['runtime_provider'].calls for r in call['records'])


def test_planning_population_and_forecast_do_not_depend_on_actual_observations():
    inputs = fixture()
    baseline = build(inputs)
    changed = deepcopy(inputs)
    changed['actual_observations'] = {'TEST_FUTURE':dict(start_time='2099-01-01T00:00:00Z')}
    changed['actual_inputs']['load_mw'] = [10000.0]*96
    changed['actual_inputs']['pv_mw'] = [5000.0]*96
    alternative = build(changed)
    assert baseline[0]['known_population'] == alternative[0]['known_population']
    assert baseline[0]['forecast_inputs'] == alternative[0]['forecast_inputs']
    assert baseline[0]['future_actual_arrival_IDs_present'] is False
    assert all(j['job_uid'] not in {'TEST_ARRIVAL', 'TEST_CARRYIN', 'TEST_FUTURE'}
               for j in alternative[0]['known_population'])
    assert baseline[1]['realized_inputs'] != alternative[1]['realized_inputs']


def test_unknown_arrivals_use_their_causal_submission_event_and_retain_carryin():
    _, actual, _, _ = build(fixture())
    arrivals = by_uid(actual['post_issue_arrivals'])
    assert set(arrivals) == {'TEST_CARRYIN', 'TEST_ARRIVAL'}
    assert arrivals['TEST_CARRYIN']['arrival_period'] == 'POST_ISSUE_PRE_DAY_CARRYIN'
    assert arrivals['TEST_ARRIVAL']['arrival_period'] == 'DDAY_ARRIVAL'
    assert all(j['runtime_inference_event_time'] == j['submit_time'] for j in arrivals.values())


def test_actual_observation_channel_does_not_publish_future_completion():
    _, actual, _, _ = build(fixture())
    observations = by_uid(actual['observed_known_episodes'])
    assert observations['TEST_PENDING']['end_observed_by_day_end'] is None
    assert observations['TEST_RUNNING']['end_observed_by_day_end'] is not None


@pytest.mark.parametrize('forbidden', ['start_time', 'end_time', 'actual_remaining',
                                     'voltage', 'line_loading', 'May_GPU'])
def test_planning_rejects_future_and_grid_fields(forbidden):
    inputs = fixture()
    inputs['known_snapshot'][0][forbidden] = 1
    with pytest.raises(ValueError, match='PLANNING_FUTURE_OR_GRID_FEATURE'):
        build(inputs)
    assert not inputs['runtime_provider'].calls


def test_known_future_submission_is_rejected_before_model_inference():
    inputs = fixture()
    issue, _, _ = axis(inputs['day'])
    inputs['known_snapshot'][0]['submit_time'] = (issue+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match='PLANNING_FUTURE_ARRIVAL'):
        build(inputs)
    assert not inputs['runtime_provider'].calls


def test_april_cannot_use_future_month_gpu_request_payload():
    inputs = fixture()
    inputs['raw_requests']['TEST_RUNNING'][0]['source_member'] = 'TEST/year=2025/month=5/jobs.parquet'
    with pytest.raises(ValueError, match='FUTURE_MONTH_VALUE_DONOR'):
        build(inputs)


def test_model_availability_is_checked_at_every_actual_arrival_not_batch_max():
    inputs = fixture()
    issue, _, _ = axis(inputs['day'])
    inputs['known_snapshot'] = []
    inputs['raw_requests'] = {k:v for k,v in inputs['raw_requests'].items()
                              if k in {'TEST_CARRYIN', 'TEST_ARRIVAL'}}
    inputs['raw_requests']['TEST_CARRYIN'][0]['submit_time'] = (issue+timedelta(hours=1)).isoformat()
    inputs['runtime_provider'].available = issue+timedelta(hours=2)
    with pytest.raises(ValueError, match='FROZEN_MODEL_NOT_AVAILABLE_AT_ROW_EVENT'):
        build(inputs)
    assert not inputs['runtime_provider'].calls


def test_model_availability_is_checked_at_d1_issue():
    inputs = fixture()
    issue, _, _ = axis(inputs['day'])
    inputs['runtime_provider'].available = issue+timedelta(seconds=1)
    with pytest.raises(ValueError, match='FROZEN_MODEL_NOT_AVAILABLE_AT_ROW_EVENT'):
        build(inputs)


@pytest.mark.parametrize('shift', [-1, 1])
def test_runtime_prediction_cardinality_must_match_exact_request_population(shift):
    inputs = fixture()
    raw = inputs['raw_requests']['TEST_RUNNING'][0]
    issue, _, _ = axis(inputs['day'])

    class WrongAxisProvider(TestOnlyFrozenProvider):
        def predict_batch(self, records, **kwargs):
            return [1800.0]*(len(records)+shift)

    with pytest.raises(ValueError, match='PREDICTION'):
        predict_causal_batch(WrongAxisProvider(), [raw], [raw['submit_time']], [issue])


def test_model_cannot_infer_before_individual_submission():
    inputs = fixture()
    raw = inputs['raw_requests']['TEST_RUNNING'][0]
    submitted = datetime.fromisoformat(raw['submit_time'])
    with pytest.raises(ValueError, match='PREDICTION_BEFORE_SUBMISSION'):
        predict_causal_batch(inputs['runtime_provider'], [raw], [submitted],
                             [submitted-timedelta(seconds=1)])


def test_immutable_gpu_map_does_not_change_with_runtime_or_realized_power_values():
    inputs = fixture()
    first = build(inputs)
    changed = deepcopy(inputs)
    changed['runtime_provider'] = TestOnlyFrozenProvider(prediction=9999)
    changed['actual_inputs']['load_mw'] = [1000.0]*96
    second = build(changed)
    assert first[1]['known_immutable_GPU_map'] == second[1]['known_immutable_GPU_map']
    assert {j['job_uid']:j['GPU_gang'] for j in first[1]['post_issue_arrivals']} == {
        j['job_uid']:j['GPU_gang'] for j in second[1]['post_issue_arrivals']}
    assert first[0]['known_population'][0]['service_slots'] != second[0]['known_population'][0]['service_slots']


@pytest.mark.parametrize('missing_authority', ['network_static_complete', 'electrical_adapter_bound'])
def test_unbound_physics_retains_input_inventory_but_cannot_freeze_reference(missing_authority):
    inputs = fixture()
    inputs['physical_authority'][missing_authority] = False
    planning, actual, gate, _ = build(inputs)
    assert gate['KNOWN_GPU_AUTHORITY_COMPLETE'] is True
    assert gate['ACTUAL_GPU_AUTHORITY_COMPLETE'] is True
    assert gate['PASS'] is False
    assert planning['status'] == actual['status'] == 'INCOMPLETE_NONEXECUTABLE'
    assert len(planning['known_population']) == len(actual['post_issue_arrivals']) == 2
    with pytest.raises(ValueError, match='INPUT_GATE_REQUIRED'):
        freeze_common_reference(planning, gate)


def test_archive_unique_identity_does_not_establish_request_version_causality():
    inputs = fixture()
    for records in inputs['raw_requests'].values():
        records[0].pop('request_version_verified')
    planning, _, gate, _ = build(inputs)
    assert gate['KNOWN_GPU_AUTHORITY_COMPLETE'] is True
    assert gate['ACTUAL_GPU_AUTHORITY_COMPLETE'] is True
    assert gate['request_version_authority_verified'] is False
    assert gate['D1_request_version_causality_PASS'] is None
    assert gate['PASS'] is False
    with pytest.raises(ValueError, match='INPUT_GATE_REQUIRED'):
        freeze_common_reference(planning, gate)


def test_grid_blind_common_reference_is_deterministic_under_input_reordering():
    inputs = fixture()
    planning, _, gate, _ = build(inputs)
    reference, frozen_sha = freeze_common_reference(planning, gate)
    reordered = deepcopy(inputs)
    reordered['known_snapshot'].reverse()
    reordered['raw_requests'] = dict(reversed(list(reordered['raw_requests'].items())))
    other_plan, _, other_gate, _ = build(reordered)
    other_reference, other_sha = freeze_common_reference(other_plan, other_gate)
    assert reference == other_reference and frozen_sha == other_sha == digest(reference)
    jobs = by_uid(reference)
    assert jobs['TEST_RUNNING']['reference_site'] == 'AIDC01'
    assert jobs['TEST_RUNNING']['reference_start'] == 0
    assert jobs['TEST_RUNNING']['fallback_used'] is False
    assert jobs['TEST_PENDING']['reference_site'] == 'AIDC02'
    assert jobs['TEST_PENDING']['fallback_used'] is True
    assert all(j['queue_rule'] == QUEUE_RULE for j in reference)
    assert {j['job_uid'] for j in reference} == {j['job_uid'] for j in inputs['known_snapshot']}


def test_q50_expired_running_remains_physical_and_is_not_fabricated_complete():
    inputs = fixture()
    inputs['known_snapshot'][0]['elapsed_seconds'] = 9999
    planning, _, gate, _ = build(inputs)
    reference, _ = freeze_common_reference(planning, gate)
    running = by_uid(reference)['TEST_RUNNING']
    assert running['service_slots'] == 0
    assert running['GPU_gang'] == 2
    assert running['physical_running_retained'] is True
    assert running['q50_expired_hard_occupancy'] is True
    assert running['synthetic_completion'] is False


def test_b0_uses_ml_with_workload_present_and_all_flex_mess_disabled():
    planning, actual, _, _ = build(fixture())
    for bundle in (planning, actual):
        flags = bundle['flags']
        assert flags['AIDC_PRESENT'] is flags['AIDC_WORKLOAD_PRESENT'] is flags['ML_RUNTIME_USED'] is True
        assert flags['AIDC_FLEX_OPTIMIZATION'] is flags['MESS_ACTIVE'] is False
        assert all(flags[k] is False for k in ('timeshift_optimization', 'migration_optimization',
            'prestart_relocation_optimization', 'grid_aware_site_allocation'))
        assert all(type(flags[k]) is int and flags[k] == 0 for k in ('P_MESS', 'Q_MESS', 'movement', 'MESS_optimization_calls'))
        assert all(flags[k] is False for k in ('B1_RUN', 'B2_RUN', 'B3_RUN', 'MAY_RUN',
            'M1_BENDERS_RUN', 'M1_PRODUCTION_RUN', 'A2_M2_PRODUCTION_RUN', 'FINAL_MARGIN_ACCEPTED'))
        validate_controls({k:flags[k] for k in ZERO_ACTIONS})
    assert planning['primary_voltage_band_pu'] == [0.95, 1.05]


def test_offline_da_diagnostic_never_becomes_operational_gate_or_actual_repair():
    flags = B0_FLAGS
    assert flags['OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY'] is True
    assert flags['DA_AC_OPERATIONAL_GATE'] is False
    controls = {k:flags[k] for k in ZERO_ACTIONS}
    assert controls['global_optimization'] == controls['local_p_repair'] == controls['local_q_repair'] == 0
    assert controls['route_repair'] == controls['schedule_repair'] == 0
    for forbidden in ('global_optimization', 'local_p_repair', 'local_q_repair', 'schedule_repair'):
        with pytest.raises(ValueError, match='B0_ACTION_FORBIDDEN'):
            validate_controls(dict(controls, **{forbidden:1}))


def positive_metrics():
    return dict(served_jobs=1, served_GPUh=0.25, AIDC_IT_energy_kWh=1.0,
                AIDC_PCC_energy_kWh=1.1, active_AIDC_slots=1)


def test_only_actual_nonzero_physical_metrics_establish_aidc_presence():
    assert require_b0_physical_presence(positive_metrics()) is True


@pytest.mark.parametrize('key', list(positive_metrics()))
@pytest.mark.parametrize('invalid', [0, -1, None, float('nan'), float('inf'), True])
def test_absent_zero_nonfinite_or_boolean_physical_metrics_do_not_establish_presence(key, invalid):
    values = positive_metrics()
    values[key] = invalid
    with pytest.raises(ValueError, match='B0_AIDC_PHYSICAL_PRESENCE_REQUIRED'):
        require_b0_physical_presence(values)


def test_missing_physical_metrics_do_not_pass_vacuously():
    with pytest.raises(ValueError, match='B0_AIDC_PHYSICAL_PRESENCE_REQUIRED'):
        require_b0_physical_presence({})
