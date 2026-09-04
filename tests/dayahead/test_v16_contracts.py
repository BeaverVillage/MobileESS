import math

import pytest

from dayahead.aidc_admission_contract import ForecastCohortAdmission, validate_admission_record
from dayahead.aidc_labels import SPLIT_CONTRACT, historical_label_eligible
from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE, audit_kappa, corrected_incremental_kw
from dayahead.aidc_realized_decomposition import realized_replay
from dayahead.aidc_reference_delta import facility_power_and_reactive, map_system_reference, planning_residual, reconstruct_da
from dayahead.aidc_resource_coupling import Direct96Architecture, PositiveTargetScaler, monotone_quantiles
from dayahead.aidc_service_contract import active_gpus, active_nodes, flexible_power_kw, require_terminal_reference_parity
from dayahead.authority import CURRENT_FROZEN_DIMENSIONS
from dayahead.reference_baseline_fidelity import fidelity_metrics, validate_access
from dayahead.reference_compute import build_reference_schedule
from dayahead.opendss_qsts import QSTSResult, classify_g13
from dayahead.realized_compute_replay import replay_compute
from dayahead.realized_mess_replay import replay_mess
from dayahead.result_schema import independent_recalculate
from dayahead.science_firewall import PRE_FREEZE_TOKEN
from dayahead.solver_equivalence import run_equivalence


def test_historical_eligibility_and_sharing_semantics_are_label_only() -> None:
    row = {"partition": "gpu-h100", "state_simple": "COMPLETED", "runtime_hours": 1.0,
           "gpu_nodes_occupied": 4, "gpus_requested": 16, "shared_job_count": None,
           "nodes_shared": None, "jobs_shared": None}
    assert historical_label_eligible(row)
    assert not historical_label_eligible({**row, "shared_job_count": 1})


def test_d1_admission_is_forecast_cohort_only_and_denies_expost_fields() -> None:
    ForecastCohortAdmission("C", (0.0,) * 96).validate()
    with pytest.raises(ValueError, match="D1_ADMISSION_CAUSALITY"):
        validate_admission_record({"cohort_id": "C", "state_simple": "COMPLETED"})
    with pytest.raises(ValueError, match="B_B1_ZERO"):
        ForecastCohortAdmission("C", (0.0,) * 96, initial_backlog_nodeh=1).validate()


def test_split_is_v16_and_locked_periods_require_a_complete_token() -> None:
    assert SPLIT_CONTRACT["phase_a_train_end"] == "2025-03-31"
    assert SPLIT_CONTRACT["primary_locked_test_start"] == "2025-05-01"
    with pytest.raises(PermissionError, match="LOCKED_PRIMARY"):
        PRE_FREEZE_TOKEN.require_locked_access("PRIMARY_2025MAY")


def test_corrected_kappa_is_package_only_and_matches_frozen_values() -> None:
    assert audit_kappa(KAPPA_KW_PER_ACTIVE_H100_NODE)["status"] == "PASS"
    value = corrected_incremental_kw(nodes=1, gpu_measured_w=4 * 72.5 + 2100, cpu_package_measured_w=2 * 64.1 + 100)
    assert value == pytest.approx(2.2)


def test_positive_scaling_and_monotone_quantile_head() -> None:
    scaler = PositiveTargetScaler(10.0)
    assert scaler.inverse(scaler.transform((0.0, 12.0))) == pytest.approx((0.0, 12.0))
    q10, q50, q90 = monotone_quantiles(-3, 0, 2)
    assert 0 <= q10 <= q50 <= q90
    with pytest.raises(ValueError):
        PositiveTargetScaler(1.0, mean_subtraction=1.0).validate()


def test_direct96_architecture_and_vanilla_delta_are_exact() -> None:
    proposed = Direct96Architecture(672, 8, 64, 2, 4, 0.1, True).contract()
    vanilla = Direct96Architecture(672, 8, 64, 2, 4, 0.1, False).contract()
    assert proposed["decoder_latent_shape"] == [96, 64]
    assert proposed["gpu_to_power_gated_residual"] and not vanilla["gpu_to_power_gated_residual"]
    assert proposed["causal_decoder_mask"] is False


def test_h100_node_hour_dimensions_apply_dt_exactly_once() -> None:
    assert active_nodes(0.5) == 2.0
    assert active_gpus(0.5) == 8.0
    assert flexible_power_kw(0.5, 2.0) == 4.0


def test_reference_schedule_v2_is_deterministic_and_starts_empty() -> None:
    racks = CURRENT_FROZEN_DIMENSIONS.rack_ids
    capacities = {rack: 1.0 for rack in racks}
    arrivals = {"C1": (2.0,) + (0.0,) * 95}
    first = build_reference_schedule(CURRENT_FROZEN_DIMENSIONS, None, production=True, cohort_arrivals=arrivals, rack_capacity_nodeh_per_slot=capacities)
    second = build_reference_schedule(CURRENT_FROZEN_DIMENSIONS, None, production=True, cohort_arrivals=arrivals, rack_capacity_nodeh_per_slot=capacities)
    assert first.authority_id == "REFERENCE_COMPUTE_SCHEDULE_V2"
    assert first.workload_by_rack_slot == second.workload_by_rack_slot
    assert sum(first.workload_by_rack_slot[rack, 0] for rack in racks) == 2.0


def test_reference_delta_identity_and_nonnegative_gate() -> None:
    mapped = map_system_reference((100.0,) * 96, (0.5, 0.5))
    flex_ref = ((10.0, 20.0),) * 96
    residual = planning_residual(mapped, flex_ref)
    da = reconstruct_da(residual, ((15.0, 25.0),) * 96)
    assert sum(da[0]) == pytest.approx(100.0 + 40.0 - 30.0)
    with pytest.raises(ValueError, match="FAIL_REFERENCE"):
        planning_residual(mapped, ((60.0, 20.0),) * 96)


def test_reference_matched_terminal_service_has_no_deadline_slack() -> None:
    arrivals = (1.0,) + (0.0,) * 95
    da, ref = require_terminal_reference_parity(arrivals, (1.0,) + (0.0,) * 95, (1.0,) + (0.0,) * 95)
    assert da[0] == ref[0] == 0 and da[-1] == ref[-1] == 0


def test_planning_pue_pf_applied_once_after_it_reconstruction() -> None:
    p, q = facility_power_and_reactive(100.0)
    assert p == 130.0
    assert q == pytest.approx(130.0 * math.tan(math.acos(0.95)))


def test_realized_remove_then_add_prevents_double_count_and_fails_negative() -> None:
    result = realized_replay((100.0,) * 96, (20.0,) * 96, ((5.0, 10.0),) * 96, (0.5, 0.5))
    assert result["rack_residual"][0] == (40.0, 40.0)
    assert result["rack_replay"][0] == (45.0, 50.0)
    assert result["solver_call_count"] == 0
    with pytest.raises(ValueError, match="FAIL_REALIZED"):
        realized_replay((10.0,) * 96, (20.0,) * 96, ((0.0, 0.0),) * 96, (0.5, 0.5))


def test_reference_fidelity_is_diagnostic_only_and_locked() -> None:
    metrics = fidelity_metrics((1.0, 2.0), (1.0, 1.0))
    assert metrics["acceptance_threshold"] is None and metrics["tuning_authority"] is False
    with pytest.raises(PermissionError):
        validate_access("PRIMARY_2025MAY")


def test_controlled_monolithic_standard_and_cl_mc_bd_are_equivalent() -> None:
    pytest.importorskip("gurobipy")
    report=run_equivalence()
    assert report["status"] == "PASS"
    assert report["standard"]["gap"] <= 1e-3 and report["cl_mc_bd"]["gap"] <= 1e-3


def test_g14_independent_recalculator_has_zero_external_calls() -> None:
    result=independent_recalculate({"planning_line_loading":[0.1,0.8],"opendss_line_loading":[0.2,0.9],"opendss_voltage":[0.97,1.03]})
    assert result["solver_call_count"] == result["opendss_call_count"] == 0


def test_fixed_schedule_compute_replay_never_reassigns_or_processes_future_arrival() -> None:
    reserved={("C","R",slot):(1.0 if slot==0 else 0.0) for slot in range(96)}
    result=replay_compute(reserved,{"C":(0.5,)+(0.0,)*95},{("R",slot):1.0 for slot in range(96)})
    assert result["executed"]["C","R",0] == 0.5
    assert result["solver_call_count"] == result["reassignment_count"] == 0


def test_fixed_mess_replay_zeroes_missed_command_without_shifting() -> None:
    commands=tuple({"p_kw":10.0 if slot==0 else 0.0,"q_kvar":0.0} for slot in range(96))
    result=replay_mess(commands,(False,)+ (True,)*95)
    assert result["executed"][0]["p_kw"] == 0 and result["missed_command_slots"] == (0,)
    assert result["shifted_command_count"] == result["solver_call_count"] == 0


def test_g13_distinguishes_release_fail_from_benchmark_infeasible() -> None:
    result=QSTSResult("FORECAST_PLANNING","a"*64,{}, {}, {}, {"rho_max_AC":1.01,"Vmin":0.96,"Vmax":1.04,"transformer_loading_max":0.8})
    assert classify_g13("B3_JOINT_PROPOSED",result) == "RELEASE_FAIL"
    assert classify_g13("B0_NO_FLEXIBILITY",result) == "BENCHMARK_INFEASIBLE"
