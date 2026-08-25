import pytest

from pfr.methods import ElectricalStressMethod, ExperimentAuthority, MethodFactory
from pfr.optimization import FastOptimizationContext, GurobiFastControlOptimizer
from pfr.runtime import (
    CausalExperimentFrame,
    MESS_CANONICAL_STAGING,
    MESS_IDS,
    MutableMethodState,
    OperationalTrainingJob,
    RuntimeJobState,
    _schedule_capacity_feasible_queued_jobs,
)
from pfr.slow_fast import FastControl, FastLayerLimits, FastLayerState, SlowDiscretePlan


def _case(*, deadline: int, remaining: float, nominal_rate: float = 0.0):
    state = FastLayerState(
        issue=10,
        mess_soc={"m1": 0.5},
        remaining_work_gpu_hours={"j1": remaining},
    )
    limits = FastLayerLimits(
        step_minutes=5,
        mess_energy_capacity_kwh={"m1": 100.0},
        mess_charge_limit_kw={"m1": 50.0},
        mess_discharge_limit_kw={"m1": 50.0},
        mess_pcs_kva={"m1": 50.0},
        mess_soc_min={"m1": 0.1},
        mess_soc_max={"m1": 0.9},
        job_gpu_count={"j1": 2},
        site_throughput_limit={"IDC01": 1.0},
    )
    nominal = FastControl(
        mess_charge_kw={"m1": 0.0},
        mess_discharge_kw={"m1": 0.0},
        mess_q_kvar={"m1": 30.0},
        job_compute_rate_fraction={"j1": nominal_rate},
        site_throughput_fraction={"IDC01": 1.0},
    )
    context = FastOptimizationContext(
        issue=10,
        current_price_aud_per_mwh=-1000.0,
        horizon_price_median_aud_per_mwh=5000.0,
        job_destination={"j1": "IDC01"},
        job_deadline_step={"j1": deadline},
        site_gpu_capacity={"IDC01": 2},
        mess_operational_enabled=True,
        compute_modulation_enabled=True,
    )
    return state, limits, nominal, context


def test_fast_recourse_enforces_deadline_feasibility_independent_of_price() -> None:
    state, limits, nominal, context = _case(
        deadline=11, remaining=2.0 / 12.0
    )
    result = GurobiFastControlOptimizer().optimize(
        nominal=nominal, state=state, limits=limits, context=context
    )
    assert result.control.job_compute_rate_fraction["j1"] == pytest.approx(1.0)
    assert "ELECTRICAL_STRESS_OBJECTIVE_V1" in (
        result.certificate.objective_authority
    )


def test_fast_recourse_preserves_joint_planner_q_setpoint_and_pcs_circle() -> None:
    state, limits, nominal, context = _case(
        deadline=12, remaining=2.0 / 12.0, nominal_rate=1.0
    )
    result = GurobiFastControlOptimizer().optimize(
        nominal=nominal, state=state, limits=limits, context=context
    )
    assert result.control.mess_q_kvar["m1"] == pytest.approx(30.0)
    p = (
        result.control.mess_discharge_kw["m1"]
        - result.control.mess_charge_kw["m1"]
    )
    assert p * p + result.control.mess_q_kvar["m1"] ** 2 <= 50.0**2 + 1e-9


def test_dispatcher_honors_h54_temporal_start_decision() -> None:
    source = OperationalTrainingJob(
        job_uid="job-1",
        origin_idc="IDC01",
        arrival_step=100,
        latest_start_step=104,
        deadline_step=120,
        requested_gpu=8,
        runtime_seconds_source=3600.0,
        cpu_request_share_kw=1.0,
        input_bytes=0,
        source_record_id="source-1",
    )
    runtime_job = RuntimeJobState(
        source=source,
        destination_idc="IDC01",
        logical_rack_id="IDC01:RACK:job-1",
        gang_membership=tuple(f"IDC01:GPU:{index}" for index in range(8)),
        remaining_work_gpu_hours=8.0,
    )
    plan = SlowDiscretePlan(
        plan_id="B02-100-1",
        valid_from_issue=100,
        mess_destination=dict(MESS_CANONICAL_STAGING),
        mess_native_route_rank={mid: 1 for mid in MESS_IDS},
        job_idc_placement={"job-1": "IDC01"},
        checkpoint_migration={"job-1": None},
        gpu_gang_allocation={"job-1": runtime_job.gang_membership},
        job_start_issue={"job-1": 102},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_discharging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_reactive_kvar={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    state = MutableMethodState(
        issue=100,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={"job-1": runtime_job},
        active_plan=plan,
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B02)

    def frame(issue: int) -> CausalExperimentFrame:
        return CausalExperimentFrame(
            issue=issue,
            current_price_aud_per_mwh=0.0,
            horizon_price_median_aud_per_mwh=0.0,
            q50_background_p_kw=0.0,
            q50_background_q_kvar=0.0,
            arrivals=(),
            exogenous_sha256="b" * 64,
        )

    waiting = _schedule_capacity_feasible_queued_jobs(state, config, frame(100))
    assert runtime_job.lifecycle == "QUEUED"
    assert waiting["plan_scheduled_wait_jobs"] == 1
    started = _schedule_capacity_feasible_queued_jobs(state, config, frame(102))
    assert runtime_job.lifecycle == "RUNNING"
    assert started["started_jobs"] == 1
