import csv
import json

import numpy as np
import pandas as pd
import pytest

from v42_integration.cc4_policy_inputs import (
    MODEL_ID, audit_train_burst, load_frozen_cc4, record, validate_site_partition,
    validate_optimized_reserve)
from v42_final.workload import profile


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf8')
    return path


def source_fixture(tmp_path):
    q = np.zeros((2, 24, 2))
    q[1, :, 0] = np.arange(1., 25.)
    q[1, :, 1] = q[1, :, 0] * 2
    prediction = tmp_path / 'original.npz'
    np.savez(prediction, q=q)
    ledger = tmp_path / 'ledger.csv'
    with ledger.open('w', newline='', encoding='utf8') as stream:
        out = csv.DictWriter(stream, fieldnames=['target_day', 'issue_time'])
        out.writeheader()
        out.writerow(dict(target_day='2025-04-30', issue_time='2025-04-29T08:00:00+00:00'))
        out.writerow(dict(target_day='2025-05-01', issue_time='2025-04-30T08:00:00+00:00'))
    selection = write(tmp_path / 'selection.json', dict(selected=MODEL_ID))
    kernel_path = tmp_path / 'kernel.csv'
    kernel = np.zeros(100)
    kernel[0], kernel[99] = .5, .5
    pd.DataFrame(dict(lag_slot=np.arange(100), kappa=kernel)).to_csv(kernel_path, index=False)
    runtime = write(tmp_path / 'runtime.json', dict(frozen=True))
    bundle = write(tmp_path / 'bundle.json', dict(C0_Q50=q[1, :, 0].tolist(), C0_Q90=q[1, :, 1].tolist(),
                                                runtime_provider=record(runtime)))
    binding = write(tmp_path / 'binding.json', dict(interface=dict(model=MODEL_ID,
        prediction=record(prediction), ledger=record(ledger), selection=record(selection)), kernel=record(kernel_path),
        indices=[1], array_shape=[2, 24, 2], forecast_modifications=0, fit_calls=0,
        inherited_model_selection_retrospective=True, unexported_fit_ingestion_receipts_not_certified=True))
    day = write(tmp_path / 'day.json', dict(target_day='2025-05-01', issue_time='2025-04-30T08:00:00+00:00',
        prediction_index=1, Q50_GPUh=q[1, :, 0].tolist(), Q90_GPUh=q[1, :, 1].tolist(), future_job_ids=[],
        nominal_unknown_GPU_96=profile(q[1, :, 0], kernel)[:96].tolist(),
        spread_headroom_GPU_96=profile(q[1, :, 1] - q[1, :, 0], kernel)[:96].tolist(),
        unknown_profile_site_allocation_bound=False))
    return binding, day, kernel_path, runtime, bundle, prediction


def load(fixture):
    binding, day, kernel, runtime, bundle, _ = fixture
    return load_frozen_cc4(binding, day, kernel_path=kernel, runtime_integrity_path=runtime, planning_bundle_path=bundle)


def test_lifetime_mass_convolution_preserves_long_tail_and_separate_scenarios(tmp_path):
    packet = load(source_fixture(tmp_path))
    assert packet['convolution']['full_mass_Q50_GPUh'] == 300.
    assert packet['convolution']['full_mass_Q90_GPUh'] == 600.
    assert packet['convolution']['tail_Q50_GPUh'] == 150.
    assert np.allclose(packet['q90_GPU'], np.asarray(packet['q50_GPU']) * 2)
    assert np.allclose(packet['reserve_delta_GPU'], packet['q50_GPU'])
    assert not packet['scenario_is_Actual_occupancy']
    assert not packet['historical_fit_ingestion_receipts_certified']
    assert packet['runtime_sha'] and packet['forecast_modifications'] == packet['fit_calls'] == 0


def test_archive_byte_drift_rejects_even_when_selected_row_unchanged(tmp_path):
    fixture = source_fixture(tmp_path)
    with fixture[-1].open('ab') as stream:
        stream.write(b'drift')
    with pytest.raises(ValueError, match='FROZEN_SOURCE_BYTES_DRIFT'):
        load(fixture)


def test_scaled_daily_values_and_future_uid_are_never_accepted(tmp_path):
    fixture = source_fixture(tmp_path)
    day = json.loads(fixture[1].read_text())
    day['Q50_GPUh'][0] *= .9
    write(fixture[1], day)
    with pytest.raises(ValueError, match='NOT_LITERAL'):
        load(fixture)
    fixture = source_fixture(tmp_path)
    day = json.loads(fixture[1].read_text())
    day['future_job_ids'] = ['not-yet-submitted']
    write(fixture[1], day)
    with pytest.raises(ValueError, match='ANONYMOUS_AGGREGATE_SCOPE'):
        load(fixture)


def test_site_scenario_requires_source_partition_and_rejects_double_q90(tmp_path):
    packet = load(source_fixture(tmp_path))
    nominal = np.column_stack([packet['q50_GPU_96'], np.zeros(96)])
    high = np.column_stack([np.zeros(96), packet['q90_GPU_96']])
    receipt = dict(sha256='a' * 64)
    with pytest.raises(ValueError, match='INSUFFICIENT_SOURCE_SITE_DISTRIBUTION'):
        validate_site_partition(packet, nominal, None, source_receipt=receipt)
    with pytest.raises(ValueError, match='SERVICE_PARTITION_DRIFT'):
        validate_site_partition(packet, nominal, high + nominal, source_receipt=receipt)
    result = validate_site_partition(packet, nominal, high, source_receipt=receipt)
    delta = np.asarray(result['high_minus_existing_nominal_site_GPU'])
    assert delta[0, 0] < 0 and delta[0, 1] > 0
    assert not result['Actual_load_addition_authorized'] and not result['q90_added_twice']


def test_planning_c0_and_runtime_source_cannot_be_rebound(tmp_path):
    fixture = source_fixture(tmp_path)
    bundle = json.loads(fixture[4].read_text())
    bundle['C0_Q90'][2] += 1.
    write(fixture[4], bundle)
    with pytest.raises(ValueError, match='PLANNING_C0_NOT_ORIGINAL_ROW'):
        load(fixture)
    fixture = source_fixture(tmp_path)
    write(fixture[3], dict(refitted=True))
    with pytest.raises(ValueError, match='FROZEN_SOURCE_BYTES_DRIFT'):
        load(fixture)


def test_optimized_cdf_timing_preserves_mass_without_false_kernel_slot_requirement(tmp_path):
    packet = load(source_fixture(tmp_path))
    # Original A may move service inside its TRAIN CDF domain. This mass-only
    # adapter requires a FULL source-row certificate for that timing choice.
    nominal = np.zeros((96, 2))
    reserve = np.zeros_like(nominal)
    nominal[7, 0], reserve[11, 1] = 600., 600.
    kwargs = dict(nominal_carryout_GPUh=150., stress_carryout_GPUh=150.,
        source_receipt=dict(sha256='b' * 64), allocation_aidc_anchor='c' * 64,
        full_row_validation=dict(FULL_feasible=True, aidc_anchor='c' * 64, FULL_max_residual=1e-9))
    result = validate_optimized_reserve(packet, nominal, reserve, **kwargs)
    assert not result['kernel_slot_equality_required']
    assert result['stress_site_GPU'][11][1] == 600.
    reserve[11, 1] *= 2
    with pytest.raises(ValueError, match='FULL_GPUH_MASS_DRIFT'):
        validate_optimized_reserve(packet, nominal, reserve, **kwargs)
    kwargs['full_row_validation']['FULL_feasible'] = False
    with pytest.raises(ValueError, match='FULL_ANCHOR_NOT_VALIDATED'):
        validate_optimized_reserve(packet, nominal, reserve, **kwargs)


def test_no_selected_train_burst_never_manufactures_values_and_rejects_may_provenance(tmp_path):
    audit = dict(PASS=True, May_outcomes_used=False, VALID_used=False, TRAIN_rows=10,
        completed_execution_rows=9, cutoff='2024-10-18T00:00:00+00:00',
        TRAIN_source=dict(path=str(tmp_path / 'missing_train.parquet'), sha256='a' * 64, bytes=100))
    path = write(tmp_path / 'audit.json', audit)
    result = audit_train_burst(path)
    assert result['status'] == 'INSUFFICIENT_SUPPORT' and result['selected_burst'] is None
    assert not result['invented_burst_values'] and not result['May_future_inputs_used']
    audit['May_outcomes_used'] = True
    write(path, audit)
    with pytest.raises(ValueError, match='TRAIN_PROVENANCE_NOT_CAUSAL'):
        audit_train_burst(path)
