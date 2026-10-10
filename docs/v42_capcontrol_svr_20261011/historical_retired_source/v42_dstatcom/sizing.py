"""Offline development-only engineering sizing and forecast-error receipts.

No Actual controller or planning optimizer calls this module. Linear estimates
are screening results, never physical PASS or proof of a global cost minimum.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .siting import receipt, write_csv, write_json


def modular_rating(required_phase_kvar, *, site_id, safety_factor=1.5,
                   module_kvar=750., loss_kw_per_phase=0., operating_fraction=.95):
    required = np.asarray(required_phase_kvar, dtype=float)
    if required.shape != (3,) or not np.isfinite(required).all() or safety_factor < 1 or not 0 < operating_fraction <= 1:
        raise ValueError("VALID_THREE_PHASE_COMPENSATION_AND_RESERVE_REQUIRED")
    apparent = np.hypot(required, float(loss_kw_per_phase))
    # Each 750kvar module has three independent 250kvar phase modules.
    # BOTH total device kVA and the largest phase must meet the safety factor.
    requirement = max(float(apparent.sum()), 3*float(apparent.max())) * safety_factor / operating_fraction
    minimum = 1500. if site_id == "STA08" else 750.
    rating = max(minimum, module_kvar * math.ceil(requirement/module_kvar))
    return dict(site_id=site_id, required_phase_Q_kvar=required.tolist(),
        required_phase_apparent_kva=apparent.tolist(), max_required_total_apparent_kva=float(apparent.sum()),
        safety_factor=safety_factor, operating_fraction=operating_fraction,
        selected_candidate_rating_kvar=rating, module_count=int(rating/module_kvar),
        independent_phase_rating_kvar=rating/3, peak_phase_rating_utilization=float(apparent.max()/(rating/3)),
        peak_total_rating_utilization=float(apparent.sum()/rating),
        phase_safety_factor=float((rating/3)*operating_fraction/apparent.max()) if apparent.max() else None,
        device_safety_factor=float(rating*operating_fraction/apparent.sum()) if apparent.sum() else None,
        physical_approval=False, status="SIZING_ESTIMATE_REQUIRES_PHYSICAL_AC_AND_CONTROLLER_VERIFICATION")


def local_coupled_requirement(voltage_pu, sensitivity, *, lower_target=.955, upper_target=1.045):
    voltage = np.asarray(voltage_pu, dtype=float)
    matrix = np.asarray(sensitivity, dtype=float)
    if voltage.shape != (3,) or matrix.shape != (3,3) or not np.isfinite(voltage).all() or not np.isfinite(matrix).all():
        raise ValueError("FINITE_LOCAL_PHASE_COUPLING_MATRIX_REQUIRED")
    if np.linalg.cond(matrix) > 1e8:
        raise ValueError("UNRELIABLE_ILL_CONDITIONED_Q_RESPONSE")
    target = np.clip(voltage, lower_target, upper_target)
    q = np.linalg.solve(matrix, target-voltage)
    return dict(original_phase_voltage_pu=voltage.tolist(), target_phase_voltage_pu=target.tolist(),
        sensitivity_pu_per_kvar=matrix.tolist(), signed_required_phase_Q_kvar=q.tolist(),
        maximum_linear_reconstruction_error_pu=float(np.abs(voltage+matrix@q-target).max()),
        phase_coupling_used=True, global_network_physical_PASS=False,
        interpretation="Linear screening at a conditional operating point; nonlinear and control verification required.")


def coupled_droop_stability(sensitivity, phase_rating_kva, *,
                            target_fraction=.18, active_span_pu=.01, damping=.025):
    """Conditional fixed-tap small-signal test, including off-diagonal phases.

    Q injection is positive. Absorbing droop has dQ/dV=-G, hence the
    simultaneous damped update has J=(1-alpha)I-alpha*G*S. This is not a
    proof for tap events, saturation, hysteresis, or a full AC trajectory.
    """
    matrix = np.asarray(sensitivity, dtype=float)
    rating = np.asarray(phase_rating_kva, dtype=float)
    if (rating.ndim != 1 or matrix.shape != (len(rating), len(rating))
            or not np.isfinite(matrix).all() or not np.isfinite(rating).all()
            or np.any(rating <= 0) or not 0 < target_fraction <= 1
            or active_span_pu <= 0 or not 0 < damping <= 1):
        raise ValueError("FINITE_COMPLETE_COUPLED_DROOP_CONTRACT_REQUIRED")
    gain = rating * target_fraction / active_span_pu
    feedback = gain[:, None] * matrix
    eigenvalues = np.linalg.eigvals(feedback)
    shifted = 1 + eigenvalues
    radius = float(np.max(np.abs(1 - damping * shifted)))
    # Any nonpositive shifted real part forbids a positive stable step.
    bound = (float(np.min(2 * shifted.real / np.abs(shifted)**2))
             if np.all(shifted.real > 0) else 0.)
    return dict(phase_count=len(rating), target_fraction_of_phase_nameplate=target_fraction,
        active_span_pu=active_span_pu, damping=damping,
        droop_gain_kvar_per_pu=gain.tolist(),
        feedback_GS_spectral_radius=float(np.max(np.abs(eigenvalues))),
        feedback_GS_eigenvalue_real_min=float(eigenvalues.real.min()),
        feedback_GS_eigenvalue_real_max=float(eigenvalues.real.max()),
        feedback_GS_eigenvalue_imaginary_max_abs=float(np.abs(eigenvalues.imag).max()),
        iteration_Jacobian_spectral_radius=radius,
        maximum_linear_stable_damping_bound=bound,
        conditional_fixed_tap_small_signal_PASS=radius < 1,
        nonlinear_96_slot_physical_PASS=None,
        limitations=["Original settled-tap small-Q response only.",
            "Tap transitions, active-set changes, losses and nonlinear response require full physical replay."])


def _resolved(raw):
    from v42_capacity.common import resolve
    path = resolve(raw)
    if isinstance(raw, dict) and raw.get("sha256") and receipt(path)["sha256"] != raw["sha256"]:
        raise ValueError("FORECAST_DEVELOPMENT_SOURCE_SHA_DRIFT")
    return path


def audit_forecast_uncertainty(output, *, code_root=None, include_may01=True,
                               include_may28=False):
    """Read explicitly authorized development dates; never other May dates.

    May28 is opt-in because it was not authorized in the first design fit.
    Original evidence and prior fit outputs remain unchanged.
    """
    import pandas as pd
    from v42_regcontrol.runner import background
    code_root = Path(code_root or Path(__file__).resolve().parents[1])
    rows, day_records = [], []
    days = [f"2025-04-{day:02d}" for day in range(1,31)] + (["2025-05-01"] if include_may01 else [])
    days += ["2025-05-28"] if include_may28 else []
    for day in days:
        if day.startswith("2025-04-"):
            prov_path = code_root / "docs/v42_april_modelable_population_b0/BUNDLE" / ("DAY_"+day.replace("-","")) / "SOURCE_PROVENANCE.json"
            prov = json.loads(prov_path.read_text(encoding="utf-8-sig"))
            forecast_path = _resolved(prov["daily_sources"]["aemo_forecast.json"])
            actual_path = _resolved(prov["daily_sources"]["aemo_actual.parquet"])
        elif day == "2025-05-01":
            from .sensitivity import OLD_OPERATIONS
            physical = json.loads((OLD_OPERATIONS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json").read_text(encoding="utf8"))
            actual_path = _resolved(physical["Actual_exogenous"])
            attempt_request = json.loads((OLD_OPERATIONS.parents[1] / "REQUEST.json").read_text(encoding="utf8"))
            ops_path = Path(attempt_request["input_folder"]) / "OPERATIONS.json"
            ops = json.loads(ops_path.read_text(encoding="utf8"))
            forecast_path = ops_path
            prov_path = OLD_OPERATIONS / "FRESH/RAW_PHYSICAL_INPUT_LOG.json"
        else:
            baseline = Path("D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01/dates/B1/2025-05-28/attempts/recovery_v9_01")
            prov_path = baseline / "output/OPERATIONS/FRESH/RAW_PHYSICAL_INPUT_LOG.json"
            physical = json.loads(prov_path.read_text(encoding="utf8"))
            actual_path = _resolved(physical["Actual_exogenous"])
            attempt_request = json.loads((baseline / "request.json").read_text(encoding="utf8"))
            if attempt_request["day"] != day:
                raise ValueError("OBSERVED_MAY28_DEVELOPMENT_DATE_MISMATCH")
            forecast_path = Path(attempt_request["input_folder"]) / "OPERATIONS.json"
        forecast = json.loads(forecast_path.read_text(encoding="utf-8-sig"))
        if day.startswith("2025-05-"): forecast = forecast["forecast_inputs"]["AEMO"]
        actual = pd.read_parquet(actual_path)
        stamps = [pd.Timestamp(value).tz_convert("Etc/GMT-10").isoformat() for value in actual.ts_fixed_aest_end]
        if len(stamps) != 96 or not pd.DatetimeIndex(stamps).tz_convert("UTC").equals(pd.DatetimeIndex(forecast["timestamps_96"]).tz_convert("UTC")):
            raise ValueError("DEVELOPMENT_FORECAST_ACTUAL_96_SLOT_TIME_MISMATCH")
        forecast_demand = np.asarray(forecast["demand_mw_96"], dtype=float)
        forecast_pv = np.asarray(forecast["pv_mw_96"], dtype=float)
        actual_demand = actual.demand_mw.to_numpy(float)
        actual_pv = actual.rooftop_pv_mw.to_numpy(float)
        if any(array.shape != (96,) or not np.isfinite(array).all() for array in (forecast_demand,forecast_pv,actual_demand,actual_pv)):
            raise ValueError("FINITE_DEVELOPMENT_FORECAST_ARRAY_REQUIRED")
        fbg = background(stamps, forecast_demand.tolist(), forecast_pv.tolist())
        abg = background(stamps, actual_demand.tolist(), actual_pv.tolist())
        for slot in range(96):
            sumrow = lambda bg, key: float(sum(getattr(bg,key)[slot].values()))
            fp,fq,fsolar = [sumrow(fbg,key) for key in ("gross_p_kw_96","gross_q_kvar_96","pv_generation_kw_96")]
            ap,aq,asolar = [sumrow(abg,key) for key in ("gross_p_kw_96","gross_q_kvar_96","pv_generation_kw_96")]
            rows.append(dict(day=day, split="OBSERVED_DEVELOPMENT", independent_holdout=False,
                slot0=slot, timestamp_interval_end_aest=stamps[slot],
                national_forecast_demand_mw=forecast_demand[slot], national_actual_demand_mw=actual_demand[slot],
                national_demand_error_actual_minus_forecast_mw=actual_demand[slot]-forecast_demand[slot],
                national_forecast_PV_mw=forecast_pv[slot], national_actual_PV_mw=actual_pv[slot],
                national_PV_error_actual_minus_forecast_mw=actual_pv[slot]-forecast_pv[slot],
                feeder_forecast_gross_P_kw=fp, feeder_actual_gross_P_kw=ap, feeder_gross_P_error_kw=ap-fp,
                feeder_forecast_gross_Q_kvar=fq, feeder_actual_gross_Q_kvar=aq, feeder_gross_Q_error_kvar=aq-fq,
                feeder_forecast_PV_kw=fsolar, feeder_actual_PV_kw=asolar, feeder_PV_error_kw=asolar-fsolar,
                feeder_net_P_error_kw=(ap-asolar)-(fp-fsolar),
                feeder_mapping="ORIGINAL_FROZEN_BACKGROUND_AUTHORITY_ALPHA_BG_1.15_PV_UNSCALED"))
        day_records.append(dict(day=day, split="OBSERVED_DEVELOPMENT", source_receipts=[receipt(prov_path),receipt(forecast_path),receipt(actual_path)],
            forecast_cutoff=forecast.get("cutoff_fixed_aest"), actual_future_Planning_input=False))
    output = Path(output)
    write_csv(output / "DSTATCOM_FORECAST_UNCERTAINTY_AUDIT.csv", rows)
    error_keys = [key for key in rows[0] if "error" in key]
    summary = {key:dict(min=float(min(row[key] for row in rows)),max=float(max(row[key] for row in rows)),
        max_absolute=float(max(abs(row[key]) for row in rows)),
        p95_absolute=float(np.quantile([abs(row[key]) for row in rows],.95))) for key in error_keys}
    proof = dict(schema="V42_DSTATCOM_DEVELOPMENT_FORECAST_UNCERTAINTY_V1", development_days=days,
        April_days=30, May01_explicit_observed_development=include_may01,
        May28_previously_observed_not_blind=True, May28_not_used_by_this_error_fit=not include_may28,
        May28_explicit_observed_development=include_may28,
        independent_May_Actual_days_read=[], control_or_Planning_future_information_input=False,
        Native_calls=0, OpenDSS_solve_calls=0, background_authority_unchanged=True,
        error_envelope=summary, development_sources=day_records,
        limitations=["National MW errors are not directly equated with local PCC kW.",
            "Background electrical allocation is original; AIDC operating-plan uncertainty and MESS movement require separate physical development stress tests.",
            "Error envelope screening alone does not approve a device rating or prove a voltage guarantee."],
        artifact=receipt(output / "DSTATCOM_FORECAST_UNCERTAINTY_AUDIT.csv"))
    write_json(output / "DSTATCOM_FORECAST_UNCERTAINTY_RECEIPTS.json", proof)
    return proof


def screen_ratings(output, *, inventory_path, matrix_paths, inputs=None):
    """Screen all36 endpoints, preserving incomplete-design state explicitly."""
    import pandas as pd
    from .sensitivity import original_development_inputs
    from .settings import ControllerSettings
    settings=ControllerSettings()
    inputs = inputs or original_development_inputs()
    inventory_path = Path(inventory_path)
    inventory = json.loads(inventory_path.read_text(encoding="utf8"))
    sites = inventory["sites"]
    matrix = pd.concat([pd.read_csv(path) for path in matrix_paths],ignore_index=True)
    matrix = matrix[(matrix.perturbation_kvar==1.) & (matrix.control_mode=="FIXED_SETTLED_TAPS")]
    names = list(inputs["ac"]["node_names"].astype(str))
    node_axis = {name:index for index,name in enumerate(names)}
    rows = []
    column_vectors = []
    all_pcc_nodes = [site["pcc_bus"]+"."+str(phase) for site in sites for phase in site["phases"]]
    for site in sites:
        pcc_nodes = [site["pcc_bus"]+"."+str(phase) for phase in site["phases"]]
        columns = []
        for phase in site["phases"]:
            source = matrix[(matrix.injection_bus==site["pcc_bus"]) & (matrix.injection_phase=="ABC"[phase-1])]
            if len(source) != len(names) or len(source.measured_node.unique()) != len(names):
                raise ValueError("COMPLETE_REAL_PHASE_COUPLING_COLUMN_REQUIRED:"+site["device_id"])
            source = source.set_index("measured_node")
            columns.append(source.loc[pcc_nodes,"dV_dQ_central_pu_per_kvar"].to_numpy(float))
            column_vectors.append(source.loc[all_pcc_nodes,"dV_dQ_central_pu_per_kvar"].to_numpy(float))
        local = np.asarray(columns).T
        volts = inputs["ac"]["voltage_pu"][:,[node_axis[name] for name in pcc_nodes]]
        requirements = [np.asarray(local_coupled_requirement(v,local)["signed_required_phase_Q_kvar"]) for v in volts]
        apparent = np.abs(np.asarray(requirements))
        worst = np.max(apparent,axis=0)
        rating = modular_rating(worst,site_id=site["site_id"],operating_fraction=.90,
                                loss_kw_per_phase=site["initial_design_rating_kvar"]/3*.002)
        rows.append(dict(site_id=site["site_id"],endpoint_id=site["endpoint_id"],device_id=site["device_id"],
            pcc_bus=site["pcc_bus"], service_transformer_kva=site["service_transformer_kva"],
            **{key:value for key,value in rating.items() if key!="site_id"},
            measured_max_abs_Q_A_kvar=float(worst[0]),measured_max_abs_Q_B_kvar=float(worst[1]),measured_max_abs_Q_C_kvar=float(worst[2]),
            development_upper_voltage_max_pu=float(volts.max()),development_lower_voltage_min_pu=float(volts.min()),
            minimum_signed_Q_kvar=np.asarray(requirements).min(axis=0).tolist(), maximum_signed_Q_kvar=np.asarray(requirements).max(axis=0).tolist(),
            known_May01_linear_1_5_reserve_PASS=rating["phase_safety_factor"] is None or rating["phase_safety_factor"]>=1.5,
            forecast_physical_stress_complete=False, future_MESS_location_stress_complete=False,
            original_and_dedicated_current_kva_validation_complete=False, closed_loop_96_slot_development_complete=False,
            installation_selected=False, sizing_approved=False,
            scope="Observed May01 originalplan conditional fixedtap linear screen; no independentMayActualread",
            cost_objective_included=False))
    global_matrix = np.asarray(column_vectors).T
    gain = np.asarray([.9*row["selected_candidate_rating_kvar"]/3/.02 for row in rows for _phase in (1,2,3)])
    GS = gain[:,None]*global_matrix
    eigenvalues = np.linalg.eigvals(GS)
    J = np.eye(len(gain))-settings.damping*(np.eye(len(gain))+GS)
    spectral_radius = float(np.abs(np.linalg.eigvals(J)).max())
    bound = min(2*complex(1+value).real/abs(1+value)**2 for value in eigenvalues if abs(1+value)>0)
    stable = spectral_radius < 1
    output = Path(output)
    write_csv(output / "DSTATCOM_RATING_AND_RESERVE.csv", rows)
    np.savez_compressed(output / "DSTATCOM_ALL_ENDPOINT_COUPLING_STABILITY.npz",
        pcc_nodes=np.asarray(all_pcc_nodes), sensitivity=global_matrix, droop_gain=gain,
        droop_feedback_eigenvalues=eigenvalues, iteration_Jacobian=J,damping=settings.damping)
    proof = dict(schema="V42_DSTATCOM_PRELIMINARY_36_ENDPOINT_RATING_V1",logical_sites=24,physical_endpoint_count=36,
        hypothetical_candidate_total_kvar=sum(row["selected_candidate_rating_kvar"] for row in rows),
        hypothetical_candidate_total_MVAr=sum(row["selected_candidate_rating_kvar"] for row in rows)/1000,
        total_750_kvar_modules=sum(row["module_count"] for row in rows),installed_devices=0,
        economic_objective_or_cost_study=False,physical_design_approved=False,
        known_May01_linear_phase_reserve_PASS=all(row["known_May01_linear_1_5_reserve_PASS"] for row in rows),
        linear_108_phase_all_active_stability=dict(conditional_fixed_tap_and_small_Q=True,
            droop_gain_kvar_per_pu=gain.tolist(),damping_tested=settings.damping,
            feedback_GS_spectral_radius=float(np.abs(eigenvalues).max()),
            feedback_GS_eigenvalue_real_min=float(eigenvalues.real.min()),
            feedback_GS_eigenvalue_real_max=float(eigenvalues.real.max()),
            feedback_GS_eigenvalue_imaginary_max_abs=float(np.abs(eigenvalues.imag).max()),
            iteration_Jacobian_spectral_radius=spectral_radius,linear_local_stability_PASS=stable,
            maximum_linear_stable_damping_bound=float(bound),
            rejected_damping_0_10_Jacobian_spectral_radius=float(np.abs(np.linalg.eigvals(np.eye(len(gain))-.10*(np.eye(len(gain))+GS))).max()),
            all_active_droop_screen_not_full_nonlinear_autonomous_control_proof=True),
        frozen_candidate_controller_settings=settings.to_dict(),
        input_receipts=inputs["receipts"]+[receipt(inventory_path)]+[receipt(path) for path in matrix_paths],
        missing_required_design_gates=["PhysicalAprilForecastErrorStress","PotentialFutureMESSMovementAcrossAll24Sites",
            "ActualNonlinear36DeviceController96SlotsAndTapCoordination","OriginalAndDedicatedCurrentKvaAndLosses"],
        artifacts=[receipt(output / "DSTATCOM_RATING_AND_RESERVE.csv"),receipt(output / "DSTATCOM_ALL_ENDPOINT_COUPLING_STABILITY.npz")])
    write_json(output / "DSTATCOM_PRELIMINARY_RATING_AND_STABILITY.json",proof)
    return proof
