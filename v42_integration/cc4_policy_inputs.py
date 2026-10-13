"""Literal frozen CC4 inputs for offline conditional-policy evaluation.

This adapter exposes no fitting or forecast-correction API.  Q50 and Q90
remain separate hourly lifetime-GPUh scenarios; their convolution is a
scenario occupancy estimate, never an Actual occupancy reservation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from v42_final.workload import profile


MODEL_ID = 'LGBM_weighted_c1_s20260924'
DT_HOURS = .25


def record(path):
    path = Path(path)
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path.resolve()), sha256=value, bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _checked(descriptor, explicit_path=None):
    path = Path(explicit_path) if explicit_path is not None else Path(descriptor['path'])
    actual = record(path)
    if any(actual[key] != descriptor[key] for key in ('sha256', 'bytes')):
        raise ValueError('CC4_FROZEN_SOURCE_BYTES_DRIFT:' + str(path))
    return path, dict(actual, original_path=descriptor['path'], explicit_path_recovery=explicit_path is not None)


def _row(path, index):
    """Read only the authorized day row, as the original April/May producer."""
    with zipfile.ZipFile(path) as archive, archive.open('q.npy') as stream:
        version = np.lib.format.read_magic(stream)
        shape, fortran, dtype = np.lib.format._read_array_header(stream, version)
        if fortran or shape[1:] != (24, 2) or dtype != np.dtype('float64'):
            raise ValueError('CC4_ORIGINAL_ARRAY_SCHEMA')
        if not 0 <= index < shape[0]:
            raise ValueError('CC4_ORIGINAL_ROW_OUT_OF_RANGE')
        offset = stream.tell()
        stream.seek(offset + index * 48 * dtype.itemsize)
        selected = np.frombuffer(stream.read(48 * dtype.itemsize), dtype=dtype).copy().reshape(24, 2)
    return selected, shape


def _array_sha(values):
    return hashlib.sha256(np.asarray(values, dtype='<f8').tobytes(order='C')).hexdigest()


def load_frozen_cc4(binding_path, day_path, *, kernel_path=None,
                    runtime_integrity_path=None, planning_bundle_path=None):
    """Verify immutable sources and produce Q50/Q90 scenario vectors.

    Optional path recovery must identify byte-identical inputs.  A supplied
    Planning bundle is used only to compare C0 and the frozen Runtime receipt;
    no request, UID, future arrival or Actual field is interpreted.
    """
    binding, day = read(binding_path), read(day_path)
    interface = binding['interface']
    if interface['model'] != MODEL_ID:
        raise ValueError('CC4_ACTUAL_MAY_MODEL_ID_MISMATCH')
    if binding['forecast_modifications'] != 0 or binding['fit_calls'] != 0:
        raise ValueError('CC4_ORIGINAL_FORECAST_MODIFIED_OR_REFIT')
    paths, receipts = {}, [record(binding_path), record(day_path)]
    for name in ('prediction', 'ledger', 'selection'):
        paths[name], receipt = _checked(interface[name])
        receipts.append(dict(receipt, role=name))
    kernel_path, kernel_receipt = _checked(binding['kernel'], kernel_path)
    receipts.append(dict(kernel_receipt, role='TRAIN_EXECUTION_LAG_KERNEL'))
    index = day['prediction_index']
    if type(index) is not int or index not in binding['indices']:
        raise ValueError('CC4_UNBOUND_PREDICTION_INDEX')
    with paths['ledger'].open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if index >= len(rows) or any(str(rows[index][key]) != str(day[key]) for key in ('target_day', 'issue_time')):
        # Timestamp formatting can differ while identifying the same issue.
        from datetime import datetime
        if index >= len(rows) or rows[index]['target_day'] != day['target_day'] or (
            datetime.fromisoformat(rows[index]['issue_time']).timestamp() !=
            datetime.fromisoformat(day['issue_time']).timestamp()):
            raise ValueError('CC4_LEDGER_DATE_OR_ISSUE_DRIFT')
    q, shape = _row(paths['prediction'], index)
    if list(shape) != binding['array_shape']:
        raise ValueError('CC4_ORIGINAL_ARRAY_SHAPE_DRIFT')
    if np.any(~np.isfinite(q)) or np.any(q < 0) or np.any(q[:, 0] > q[:, 1]):
        raise ValueError('CC4_QUANTILE_ORDER_OR_FINITE')
    if not np.array_equal(q[:, 0], day['Q50_GPUh']) or not np.array_equal(q[:, 1], day['Q90_GPUh']):
        raise ValueError('CC4_DAY_NOT_LITERAL_ORIGINAL_PREDICTION_ROW')
    if day.get('future_job_ids', []) or day.get('unknown_profile_site_allocation_bound', False):
        raise ValueError('CC4_ANONYMOUS_AGGREGATE_SCOPE_REQUIRED')
    kernel_frame = pd.read_csv(kernel_path, usecols=['lag_slot', 'kappa'])
    if not np.array_equal(kernel_frame.lag_slot.to_numpy(), np.arange(len(kernel_frame))):
        raise ValueError('CC4_TRAIN_KERNEL_LAG_AXIS_DRIFT')
    kernel = kernel_frame.kappa.to_numpy(dtype=float)
    nominal, high = profile(q[:, 0], kernel), profile(q[:, 1], kernel)
    reserve = profile(q[:, 1] - q[:, 0], kernel)
    reconstruction = dict(
        nominal_max_absolute_delta=float(np.max(np.abs(nominal[:96] - np.asarray(day['nominal_unknown_GPU_96'])))),
        reserve_max_absolute_delta=float(np.max(np.abs(reserve[:96] - np.asarray(day['spread_headroom_GPU_96'])))))
    if max(reconstruction.values()) > 1e-8:
        raise ValueError('CC4_ORIGINAL_DAILY_CONVOLUTION_DRIFT')
    bundle = read(planning_bundle_path) if planning_bundle_path is not None else None
    runtime_receipt = None
    if bundle is not None:
        if not np.array_equal(bundle['C0_Q50'], q[:, 0]) or not np.array_equal(bundle['C0_Q90'], q[:, 1]):
            raise ValueError('CC4_PLANNING_C0_NOT_ORIGINAL_ROW')
        receipts.append(dict(record(planning_bundle_path), role='CURRENT_PLANNING_C0_BINDING'))
        if runtime_integrity_path is not None:
            _, runtime_receipt = _checked(bundle['runtime_provider'], runtime_integrity_path)
            receipts.append(dict(runtime_receipt, role='FROZEN_RUNTIME_PROVIDER_Q50'))
    elif runtime_integrity_path is not None:
        raise ValueError('CC4_RUNTIME_REQUIRES_ORIGINAL_PLANNING_PROVIDER_RECEIPT')
    result = dict(schema='FROZEN_CC4_POLICY_SCENARIO_INPUTS_V1',
        model_id=MODEL_ID, target_day=day['target_day'], issue_time=day['issue_time'], prediction_index=index,
        hourly_units='HOURLY_ARRIVAL_LIFETIME_GPUh', occupancy_units='GPU', dt_h=DT_HOURS,
        q50_hourly_GPUh=q[:, 0].tolist(), q90_hourly_GPUh=q[:, 1].tolist(), kernel=kernel.tolist(),
        q50_GPU=nominal.tolist(), q90_GPU=high.tolist(), q50_GPU_96=nominal[:96].tolist(),
        q90_GPU_96=high[:96].tolist(), reserve_delta_GPU=reserve.tolist(),
        prediction_sha=interface['prediction']['sha256'], kernel_sha=kernel_receipt['sha256'],
        runtime_sha=None if runtime_receipt is None else runtime_receipt['sha256'],
        original_selected_row_sha=_array_sha(q), source_receipts=receipts,
        convolution=dict(function='v42_final.workload.profile', impulses='hourly GPUh at slots 4*h',
            equation='GPU[t] = convolve(hourly_GPUh_impulses, TRAIN_kappa)[t] / 0.25',
            full_mass_Q50_GPUh=float(nominal.sum() * DT_HOURS), full_mass_Q90_GPUh=float(high.sum() * DT_HOURS),
            tail_Q50_GPUh=float(nominal[96:].sum() * DT_HOURS), tail_Q90_GPUh=float(high[96:].sum() * DT_HOURS),
            stored_daily_reconstruction=reconstruction),
        forecast_modifications=0, fit_calls=0, new_calibrator_calls=0, scaling_calls=0,
        clipping_calls=0, May_result_model_reselection=0, future_Actual_or_UID_inputs_used=False,
        scenario_is_Actual_occupancy=False, reserve_is_realized_load=False,
        selection_retrospective=binding['inherited_model_selection_retrospective'],
        historical_fit_ingestion_receipts_certified=not binding['unexported_fit_ingestion_receipts_not_certified'])
    return result


def validate_site_partition(packet, nominal_site_gpu, stress_site_gpu, *, source_receipt,
                            baseline_total_gpu=None, stress_total_gpu=None):
    """Validate explicitly sourced separate nominal and Q90 site scenarios.

    A-stage service timing may differ from the fixed-kernel reference.  In
    that case callers must supply both totals from its frozen timing artifact.
    The returned delta is relative to the existing nominal baseline and may
    be added only by an offline scenario scorer, never by an Actual engine.
    """
    if not source_receipt or len(source_receipt.get('sha256', '')) != 64:
        raise ValueError('CC4_SITE_PARTITION_SOURCE_RECEIPT_REQUIRED')
    if stress_site_gpu is None:
        raise ValueError('INSUFFICIENT_SOURCE_SITE_DISTRIBUTION')
    nominal, high = np.asarray(nominal_site_gpu, float), np.asarray(stress_site_gpu, float)
    if nominal.ndim != 2 or nominal.shape != high.shape or nominal.shape[0] != 96:
        raise ValueError('CC4_SITE_SCENARIO_AXIS')
    if any(np.any(~np.isfinite(x)) or np.any(x < 0) for x in (nominal, high)):
        raise ValueError('CC4_SITE_SCENARIO_FINITE_NONNEGATIVE')
    n = np.asarray(packet['q50_GPU_96'] if baseline_total_gpu is None else baseline_total_gpu, float)
    h = np.asarray(packet['q90_GPU_96'] if stress_total_gpu is None else stress_total_gpu, float)
    if n.shape != (96,) or h.shape != (96,) or not np.allclose(nominal.sum(axis=1), n, rtol=1e-10, atol=1e-8) or not np.allclose(high.sum(axis=1), h, rtol=1e-10, atol=1e-8):
        raise ValueError('CC4_SITE_SCENARIO_SERVICE_PARTITION_DRIFT')
    return dict(nominal_site_GPU=nominal.tolist(), high_site_GPU=high.tolist(),
        high_minus_existing_nominal_site_GPU=(high - nominal).tolist(), source_receipt=source_receipt,
        q90_added_twice=False, Actual_load_addition_authorized=False)


def validate_optimized_reserve(packet, nominal_site_gpu, reserve_site_gpu, *,
                               nominal_carryout_GPUh, stress_carryout_GPUh,
                               source_receipt, allocation_aidc_anchor,
                               full_row_validation):
    """Validate A-stage CDF-timed allocation without imposing kernel timing.

    The source A model conserves arrival-cohort GPUh while choosing a timing
    inside the unchanged TRAIN envelope.  Its reserve is a *difference*
    scenario allocation; it is not a second Q90 amount or an Actual load.
    """
    if not source_receipt or len(source_receipt.get('sha256', '')) != 64:
        raise ValueError('CC4_A_RESERVE_SOURCE_RECEIPT_REQUIRED')
    if (not full_row_validation.get('FULL_feasible') or
            full_row_validation.get('aidc_anchor') != allocation_aidc_anchor or
            len(allocation_aidc_anchor or '') != 64 or
            full_row_validation.get('FULL_max_residual', float('inf')) > 1e-5):
        raise ValueError('CC4_A_RESERVE_FULL_ANCHOR_NOT_VALIDATED')
    nominal, reserve = np.asarray(nominal_site_gpu, float), np.asarray(reserve_site_gpu, float)
    if nominal.ndim != 2 or nominal.shape != reserve.shape or nominal.shape[0] != 96:
        raise ValueError('CC4_A_RESERVE_SITE_AXIS')
    if any(np.any(~np.isfinite(x)) or np.any(x < 0) for x in (nominal, reserve)) or any(
            not np.isfinite(v) or v < 0 for v in (nominal_carryout_GPUh, stress_carryout_GPUh)):
        raise ValueError('CC4_A_RESERVE_NONNEGATIVE_FINITE')
    nominal_mass = float(nominal.sum() * DT_HOURS + nominal_carryout_GPUh)
    stress_mass = float(reserve.sum() * DT_HOURS + stress_carryout_GPUh)
    q50 = float(np.sum(packet['q50_hourly_GPUh']))
    delta = float(np.sum(np.asarray(packet['q90_hourly_GPUh']) - packet['q50_hourly_GPUh']))
    if not np.isclose(nominal_mass, q50, rtol=1e-10, atol=1e-8) or not np.isclose(stress_mass, delta, rtol=1e-10, atol=1e-8):
        raise ValueError('CC4_A_RESERVE_FULL_GPUH_MASS_DRIFT')
    return dict(stress_site_GPU=reserve.tolist(), stress_profile_GPU=reserve.sum(axis=1).tolist(),
        stress_carryout_GPUh=float(stress_carryout_GPUh), nominal_carryout_GPUh=float(nominal_carryout_GPUh),
        stress_allocation_source='A_STAGE_OPTIMIZED_RESERVE', allocation_aidc_anchor=allocation_aidc_anchor,
        allocation_receipt=source_receipt, original_CDF_model_rows_validated=True,
        kernel_slot_equality_required=False, reserve_is_realized_load=False,
        scenario_total='existing optimized Q50 nominal + optimized (Q90-Q50) reserve',
        q90_added_twice=False)


def audit_train_burst(kernel_audit_path, *, cohort_cdf_path=None):
    """Disclose existing TRAIN support without fabricating a burst profile."""
    audit = read(kernel_audit_path)
    if audit.get('PASS') is not True or audit.get('May_outcomes_used') is not False or audit.get('VALID_used') is not False:
        raise ValueError('CC4_TRAIN_PROVENANCE_NOT_CAUSAL')
    sources = [record(kernel_audit_path)]
    source = audit['TRAIN_source']
    available = Path(source['path']).is_file()
    verified = False
    if available:
        _, receipt = _checked(source)
        sources.append(receipt)
        verified = True
    columns = []
    if cohort_cdf_path is not None:
        sources.append(record(cohort_cdf_path))
        with Path(cohort_cdf_path).open(encoding='utf-8-sig', newline='') as stream:
            columns = next(csv.reader(stream))
    return dict(scenario='TRAIN_BURST_STRESS', status='INSUFFICIENT_SUPPORT', selected_burst=None,
        reasons=['No frozen burst-selection and workgroup/request provenance artifact was supplied.',
                 'Aggregate completed-cohort CDF and pooled lag kernel do not identify a verified burst workgroup.'],
        TRAIN_rows=audit['TRAIN_rows'], completed_execution_rows=audit['completed_execution_rows'],
        TRAIN_source_declared=source, TRAIN_source_available_at_declared_path=available,
        TRAIN_source_bytes_verified=verified, existing_cohort_cdf_columns=columns,
        TRAIN_cutoff=audit['cutoff'], May_future_inputs_used=False, invented_burst_values=False,
        source_receipts=sources)


def audit_signed_grid(certificate_path, thermal_path):
    """Replay the original signed-face normalization at its stored anchor.

    This is an algebra/source audit; no new coefficients, model, AC solve or
    certificate for a final A/M policy are produced.
    """
    certificate, thermal = read(certificate_path), read(thermal_path)
    coefficient_path, coefficient_receipt = _checked(certificate['outputs']['planning_coefficients'])
    with np.load(coefficient_path, allow_pickle=False) as source:
        names = tuple(map(str, source['branch_names']))
        controls = tuple(map(str, source['control_names']))
        p0, q0 = source['flow_p_constant'], source['flow_q_constant']
        pm, qm = source['flow_p_matrix'], source['flow_q_matrix']
        cc, cm = source['current_constant'], source['current_matrix'].transpose(0, 2, 1)
        anchor, limits = source['anchor_control'], source['branch_limits']
        ratings = source['rating_a']
        voltage_shape = source['voltage_matrix'].shape
    mapping = {row['branch_phase'].lower(): float(row['NormalAmps'])
               for row in thermal['rows'] + thermal['lines']}
    expected = np.asarray([mapping[name.lower()] for name in names])
    if not np.array_equal(ratings, expected):
        raise ValueError('CC4_POLICY_GRID_ORIGINAL_THERMAL_DENOMINATOR_DRIFT')
    if anchor.shape[0] != 96 or cm.shape != pm.shape or anchor.shape[1] != len(controls):
        raise ValueError('CC4_POLICY_GRID_FULL96_CONTROL_AXIS_DRIFT')
    angles = 2 * np.pi * np.arange(16) / 16
    cos, sin = np.cos(angles), np.sin(angles)
    ap = limits * np.cos(np.pi / 16)
    p = p0 + np.einsum('tbc,tc->tb', pm, anchor)
    q = q0 + np.einsum('tbc,tc->tb', qm, anchor)
    raw = (p[:, :, None] * cos + q[:, :, None] * sin) / ap[:, :, None]
    active = np.argmax(raw, axis=2)
    grad = (cos[active, None] * pm + sin[active, None] * qm) / ap[:, :, None]
    correction = cm - grad
    direct = cc + np.einsum('tbc,tc->tb', cm, anchor)
    bias = direct - raw.max(axis=2)
    face_at_anchor = raw + bias[:, :, None]
    anchor_error = float(np.max(np.abs(face_at_anchor.max(axis=2) - direct)))
    derivative_error = float(np.max(np.abs(grad + correction - cm)))
    # Both directions use a fixed original active face. Its derivative is
    # exactly the signed normalized-current derivative, not an absolute value.
    finite_error = 0.
    aidc_columns = [k for k, name in enumerate(controls) if name.startswith('aidc_load_kw[')]
    for k in aidc_columns:
        chosen = np.take_along_axis(raw, active[:, :, None], axis=2)[:, :, 0] + bias
        face_grad = (cos[active] * pm[:, :, k] + sin[active] * qm[:, :, k]) / ap + correction[:, :, k]
        for sign in (-1., 1.):
            after = chosen + sign * face_grad
            finite_error = max(finite_error, float(np.max(np.abs((after - chosen) - sign * cm[:, :, k]))))
    if max(anchor_error, derivative_error, finite_error) > 1e-10:
        raise ValueError('CC4_POLICY_GRID_SIGNED_FACE_ALGEBRA_MISMATCH')
    return dict(status='ORIGINAL_SIGNED_FACE_SOURCE_ALGEBRA_VALIDATED',
        coefficient_receipt=coefficient_receipt,
        source_receipts=[record(certificate_path), record(thermal_path), coefficient_receipt],
        slots=96, control_count=len(controls), branch_phase_count=len(names),
        transformer_phase_count=sum(n.lower().startswith('transformer.') for n in names),
        line_phase_count=sum(not n.lower().startswith('transformer.') for n in names),
        voltage_matrix_shape=list(voltage_shape), signed_face_count=16,
        current_denominators='EXACT_COMPILED_BRANCH_PHASE_NormalAmps',
        thermal_rating_bytes_equal=True, control_units='aidc_load_kw/mess_p_kw: kW; mess_q_kvar: kvar',
        voltage_units='squared per-unit', current_objective_units='dimensionless current/rating',
        line_objective='max over all original non-transformer phase faces and 96 slots',
        transformer_hard_guards=['normalized signed current <= 1', 'original winding 16-face kVA polygon'],
        anchor_loading_max_error=anchor_error, signed_derivative_max_error=derivative_error,
        plus_minus_1kW_fixed_face_max_error=finite_error,
        source_grid_function='v42_native.grid.add_grid',
        original_AIDC_PQ_axis='aidc_load_kw already changes coupled P and PF=.95 Q; do not add Q a second time',
        original_16_face_current_correction=True, absolute_value_sensitivity_used=False,
        original_certificate_validity=certificate.get('validity_scope'),
        original_sensitivity_semantics=certificate.get('sensitivity_semantics'),
        fresh_AC_run=False, final_A2_M2_policy_anchor_validated=False,
        new_coefficients_generated=False)
