import pytest
import pandas as pd
from types import SimpleNamespace

from pfr.methods import ElectricalStressMethod, ExperimentAuthority, MethodFactory
from pfr.optimization import FastOptimizationContext, GurobiFastControlOptimizer
from pfr.persistent_bounded_milp import (
    BURST_PLANNER_WALL_BUDGET_SECONDS,
    BURST_VISIBLE_QUEUE_THRESHOLD,
    PersistentBoundedMilpPlanner,
    _PersistentMilpModel,
    _WorkloadOption,
    _effective_workload_groups,
    _resident_candidate_axis_capacity,
    _resident_job_slot_capacity,
    _workload_option_effective_signature,
)
from pfr.runtime import (
    CausalExperimentFrame,
    MESS_CANONICAL_STAGING,
    MESS_IDS,
    IDC_FACILITY_POWER_FACTOR,
    IDC_FACILITY_PUE,
    IDC_FACILITY_TANPHI,
    MutableMethodState,
    NativeGridControlDecision,
    OperationalTrainingJob,
    RuntimeJobState,
    RuntimeContractError,
    _PhysicalVerifierAdapter,
    _facility_power,
    _schedule_capacity_feasible_queued_jobs,
    _synchronize_planned_rack_assignments,
)
from pfr.slow_fast import FastControl, FastLayerLimits, FastLayerState, SlowDiscretePlan


def test_burst_watchdog_retains_half_control_interval_topology_margin() -> None:
    assert BURST_VISIBLE_QUEUE_THRESHOLD == 128
    assert BURST_PLANNER_WALL_BUDGET_SECONDS == 150.0


@pytest.mark.parametrize(
    ("visible_queue", "expected_capacity"),
    [
        (0, 16),
        (16, 16),
        (17, 32),
        (32, 32),
        (33, 64),
        (265, 288),
        (1024, 1024),
        (2048, 1024),
    ],
)
def test_resident_job_slots_grow_in_bounded_blocks(
    visible_queue: int,
    expected_capacity: int,
) -> None:
    assert _resident_job_slot_capacity(visible_queue) == expected_capacity


@pytest.mark.parametrize(
    ("job_slots", "active_k", "expected_k"),
    [
        (16, 4, 64),
        (128, 4, 64),
        (129, 4, 4),
        (288, 4, 4),
        (288, 8, 8),
        (288, 16, 16),
    ],
)
def test_candidate_superset_axis_is_bounded_for_burst_queues(
    job_slots: int,
    active_k: int,
    expected_k: int,
) -> None:
    assert _resident_candidate_axis_capacity(
        job_slots=job_slots,
        active_candidate_k=active_k,
        adaptive_candidate_max_k=64,
    ) == expected_k


def test_workload_symmetry_signature_clips_only_beyond_h54() -> None:
    def option(duration: int) -> _WorkloadOption:
        return _WorkloadOption(
            destination="IDC04",
            rack="IDC04_LP01",
            start_offset=2,
            duration_steps=duration,
            it_power_kw=0.70625,
            requested_gpu=1,
            wan_schedule_gb=(0.0,) * 54,
            wan_required_bytes=0,
            remote=False,
            generation_score=(0.1, 0.2, 0.0, "IDC04", "IDC04_LP01"),
        )

    assert _workload_option_effective_signature((option(54),)) == (
        _workload_option_effective_signature((option(200),))
    )
    assert _workload_option_effective_signature((option(51),)) != (
        _workload_option_effective_signature((option(54),))
    )


def test_effective_workload_groups_preserve_first_seen_class_order() -> None:
    def option(duration: int, *, destination: str = "IDC01") -> _WorkloadOption:
        return _WorkloadOption(
            destination=destination,
            rack=f"{destination}-R01",
            start_offset=0,
            duration_steps=duration,
            it_power_kw=0.70625,
            requested_gpu=1,
            wan_schedule_gb=(),
            wan_required_bytes=0,
            remote=False,
            generation_score=(0.0, 0.0, 0.0, destination, f"{destination}-R01"),
        )

    assert _effective_workload_groups(
        ((option(54),), (option(3),), (option(200),), (option(3),))
    ) == ((0, 2), (1, 3))


def test_fresh_ac_facility_inputs_match_h54_pue_and_power_factor() -> None:
    facility_p, facility_q = _PhysicalVerifierAdapter._facility_ac_inputs(
        (100.0, 0.0)
    )

    assert IDC_FACILITY_PUE == pytest.approx(1.30)
    assert IDC_FACILITY_POWER_FACTOR == pytest.approx(0.95)
    assert facility_p == pytest.approx((130.0, 0.0))
    assert facility_q == pytest.approx(
        (130.0 * IDC_FACILITY_TANPHI, 0.0)
    )
    assert facility_p[0] / (facility_p[0] ** 2 + facility_q[0] ** 2) ** 0.5 == pytest.approx(
        IDC_FACILITY_POWER_FACTOR
    )


def test_native_selector_receives_h54_facility_pq_not_unity_pf() -> None:
    class Backend:
        selected = None

        def select_native_control(self, **kwargs):
            self.selected = kwargs
            return NativeGridControlDecision(
                states={},
                raw_metrics={"status": "TEST"},
                fresh_instance=True,
                common_to_all_methods=True,
            )

    source = OperationalTrainingJob(
        job_uid="facility-pq",
        origin_idc="IDC01",
        arrival_step=0,
        latest_start_step=0,
        deadline_step=10,
        requested_gpu=1,
        runtime_seconds_source=3600.0,
        cpu_request_share_kw=0.0,
        input_bytes=0,
        source_record_id="facility-pq",
    )
    job = RuntimeJobState(
        source=source,
        destination_idc="IDC01",
        logical_rack_id="IDC01:RACK:facility-pq",
        gang_membership=("IDC01:GPU:0",),
        remaining_work_gpu_hours=1.0,
        lifecycle="RUNNING",
    )
    backend = Backend()
    verifier = _PhysicalVerifierAdapter(
        backend=backend,
        issue=0,
        jobs={source.job_uid: job},
        power_curve=SimpleNamespace(
            gang_power_kw=lambda gpu_count, fraction: 100.0
        ),
        mess_location=tuple(MESS_CANONICAL_STAGING.values()),
        mess_in_transit=(False,) * len(MESS_IDS),
        robust_background_p_kw=(),
        robust_background_q_kvar=(),
        robust_pv_available_kw=(),
        native_forecast_background_p_kw=(),
        native_forecast_background_q_kvar=(),
        native_forecast_pv_available_kw=(),
    )
    verifier.select_native_control(
        control=FastControl(
            mess_charge_kw={mid: 0.0 for mid in MESS_IDS},
            mess_discharge_kw={mid: 0.0 for mid in MESS_IDS},
            mess_q_kvar={mid: 0.0 for mid in MESS_IDS},
            job_compute_rate_fraction={source.job_uid: 1.0},
            site_throughput_fraction={"IDC01": 1.0},
        )
    )

    assert backend.selected is not None
    facility_p = backend.selected["facility_p_kw"]
    facility_q = backend.selected["facility_q_kvar"]
    assert facility_p[0] == pytest.approx(100.0 * IDC_FACILITY_PUE)
    assert facility_q[0] == pytest.approx(
        facility_p[0] * IDC_FACILITY_TANPHI
    )
    assert facility_p[1:] == pytest.approx((0.0,) * (len(facility_p) - 1))
    assert facility_q[1:] == pytest.approx((0.0,) * (len(facility_q) - 1))


def test_planner_and_fresh_facility_pq_use_canonical_job_sum_order() -> None:
    power_by_gpu = {1: 500.0, 2: 4e-14, 3: 4e-14}
    curve = SimpleNamespace(
        gang_power_kw=lambda gpu_count, fraction: power_by_gpu[gpu_count]
    )

    def runtime_job(uid: str, gpu: int) -> RuntimeJobState:
        source = OperationalTrainingJob(
            job_uid=uid,
            origin_idc="IDC01",
            arrival_step=0,
            latest_start_step=0,
            deadline_step=10,
            requested_gpu=gpu,
            runtime_seconds_source=3600.0,
            cpu_request_share_kw=0.0,
            input_bytes=0,
            source_record_id=uid,
        )
        return RuntimeJobState(
            source=source,
            destination_idc="IDC01",
            logical_rack_id=f"IDC01:RACK:{uid}",
            gang_membership=(f"IDC01:GPU:{gpu}",),
            remaining_work_gpu_hours=1.0,
            lifecycle="RUNNING",
            compute_rate_fraction=1.0,
        )

    # Deliberately reverse the state insertion order relative to the control.
    jobs = {
        uid: runtime_job(uid, gpu)
        for uid, gpu in (("job-c", 3), ("job-b", 2), ("job-a", 1))
    }
    verifier = SimpleNamespace(jobs=jobs, power_curve=curve)
    control = FastControl(
        mess_charge_kw={},
        mess_discharge_kw={},
        mess_q_kvar={},
        job_compute_rate_fraction={
            "job-a": 1.0,
            "job-b": 1.0,
            "job-c": 1.0,
        },
        site_throughput_fraction={},
    )

    facility_it_p, _, _ = _PhysicalVerifierAdapter._physical_inputs(
        verifier, control
    )
    fresh_pq = _PhysicalVerifierAdapter._facility_ac_inputs(facility_it_p)
    planner_pq = _facility_power(jobs.values(), curve)

    assert fresh_pq == planner_pq


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


def test_dispatcher_keeps_late_capacity_queue_out_of_fast_recourse() -> None:
    source = OperationalTrainingJob(
        job_uid="late-job",
        origin_idc="IDC01",
        arrival_step=100,
        latest_start_step=101,
        deadline_step=105,
        requested_gpu=1,
        runtime_seconds_source=1800.0,
        cpu_request_share_kw=0.1,
        input_bytes=0,
        source_record_id="late-source",
    )
    job = RuntimeJobState(
        source=source,
        destination_idc="IDC01",
        logical_rack_id="IDC01_LP01",
        gang_membership=("IDC01_LP01:PFR-GPU:late-job:0",),
        remaining_work_gpu_hours=0.5,
    )
    plan = SlowDiscretePlan(
        plan_id="B02-103-1",
        valid_from_issue=103,
        mess_destination=dict(MESS_CANONICAL_STAGING),
        mess_native_route_rank={mid: 1 for mid in MESS_IDS},
        job_idc_placement={"late-job": "IDC01"},
        checkpoint_migration={"late-job": None},
        gpu_gang_allocation={"late-job": job.gang_membership},
        job_start_issue={"late-job": 103},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_discharging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_reactive_kvar={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    state = MutableMethodState(
        issue=103,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={"late-job": job},
        active_plan=plan,
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B02)
    frame = CausalExperimentFrame(
        issue=103,
        current_price_aud_per_mwh=0.0,
        horizon_price_median_aud_per_mwh=0.0,
        q50_background_p_kw=0.0,
        q50_background_q_kvar=0.0,
        arrivals=(),
        exogenous_sha256="b" * 64,
    )

    audit = _schedule_capacity_feasible_queued_jobs(state, config, frame)

    assert job.lifecycle == "QUEUED"
    assert audit["started_jobs"] == 0
    assert audit["deadline_blocked_jobs"] == 1


def test_h54_physical_rack_assignment_is_materialized_for_running_state() -> None:
    source = OperationalTrainingJob(
        job_uid="job-rack",
        origin_idc="IDC01",
        arrival_step=100,
        latest_start_step=104,
        deadline_step=120,
        requested_gpu=2,
        runtime_seconds_source=3600.0,
        cpu_request_share_kw=1.0,
        input_bytes=0,
        source_record_id="source-rack",
    )
    job = RuntimeJobState(
        source=source,
        destination_idc="IDC01",
        logical_rack_id="IDC01:PFR-H100-LOGICAL-POOL",
        gang_membership=("IDC01:PFR-GPU:job-rack:0", "IDC01:PFR-GPU:job-rack:1"),
        remaining_work_gpu_hours=2.0,
        lifecycle="RUNNING",
    )
    physical_gang = (
        "IDC01_LP02:PFR-GPU:job-rack:0",
        "IDC01_LP02:PFR-GPU:job-rack:1",
    )
    plan = SlowDiscretePlan(
        plan_id="B07-100-1",
        valid_from_issue=100,
        mess_destination=dict(MESS_CANONICAL_STAGING),
        mess_native_route_rank={mid: 1 for mid in MESS_IDS},
        job_idc_placement={"job-rack": "IDC01"},
        checkpoint_migration={"job-rack": None},
        gpu_gang_allocation={"job-rack": physical_gang},
        job_start_issue={"job-rack": 100},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_discharging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_reactive_kvar={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    state = MutableMethodState(
        issue=101,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={"job-rack": job},
        active_plan=plan,
    )

    _synchronize_planned_rack_assignments(state)

    assert job.logical_rack_id == "IDC01_LP02"
    assert job.gang_membership == physical_gang

    job.logical_rack_id = "IDC01_LP01"
    with pytest.raises(RuntimeContractError, match="cannot change physical rack"):
        _synchronize_planned_rack_assignments(state)


def test_prestaged_spatial_admission_uses_remote_physical_rack_without_wan() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._initialize = lambda: None
    planner.scope = {
        "cap": pd.DataFrame(
            [
                {
                    "rack_pool_id": "IDC01_LP01",
                    "idc_id": "IDC01",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
                {
                    "rack_pool_id": "IDC02_LP01",
                    "idc_id": "IDC02",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
            ]
        ),
        "domains": {},
        "pmap": {},
        "wan_map": {},
    }
    jobs = {}
    for index in range(2):
        uid = f"burst-{index}"
        source = OperationalTrainingJob(
            job_uid=uid,
            origin_idc="IDC01",
            arrival_step=100,
            latest_start_step=105,
            deadline_step=120,
            requested_gpu=1,
            runtime_seconds_source=3600.0,
            cpu_request_share_kw=0.1,
            input_bytes=None,
            source_record_id=uid,
        )
        jobs[uid] = RuntimeJobState(
            source=source,
            destination_idc="IDC01",
            logical_rack_id="IDC01:PFR-H100-LOGICAL-POOL",
            gang_membership=(f"IDC01:PFR-GPU:{uid}:0",),
            remaining_work_gpu_hours=1.0,
        )
        planner.scope["domains"][uid] = [
            {
                "destination_IDC_id": "IDC01",
                "rack_pool_id": "IDC01_LP01",
            },
            {
                "destination_IDC_id": "IDC02",
                "rack_pool_id": "IDC02_LP01",
            },
        ]
        planner.scope["pmap"][uid] = {
            "arrival_step": 100,
            "latest_start_step": 105,
            "latest_completion_step_exclusive": 120,
            "requested_gpu": 1,
            "IT_power_kW": 1.0,
            "duration_steps": 12,
        }
    state = MutableMethodState(
        issue=100,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs=jobs,
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B07)

    audit = planner.materialize_runtime_rack_assignments(state, config)

    assert audit["assigned_jobs"] == 2
    assert {job.destination_idc for job in jobs.values()} == {"IDC01", "IDC02"}
    remote = next(job for job in jobs.values() if job.destination_idc == "IDC02")
    assert remote.migration_state == "PRESTART_PLACED_DATASET_PRESTAGED"
    assert remote.logical_rack_id == "IDC02_LP01"
    assert remote.prestart_wan_required_bytes == 0


def test_restart_rack_materialization_preserves_migration_destination() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._initialize = lambda: None
    uid = "restarting-job"
    planner.scope = {
        "cap": pd.DataFrame(
            [
                {
                    "rack_pool_id": "IDC01_LP01",
                    "idc_id": "IDC01",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
                {
                    "rack_pool_id": "IDC02_LP01",
                    "idc_id": "IDC02",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
            ]
        ),
        "domains": {
            uid: [
                {
                    "destination_IDC_id": "IDC01",
                    "rack_pool_id": "IDC01_LP01",
                },
                {
                    "destination_IDC_id": "IDC02",
                    "rack_pool_id": "IDC02_LP01",
                },
            ]
        },
        "pmap": {
            uid: {
                "arrival_step": 100,
                "latest_start_step": 105,
                "latest_completion_step_exclusive": 120,
                "requested_gpu": 1,
                "IT_power_kW": 1.0,
                "duration_steps": 12,
            }
        },
        "wan_map": {},
    }
    source = OperationalTrainingJob(
        job_uid=uid,
        origin_idc="IDC01",
        arrival_step=100,
        latest_start_step=105,
        deadline_step=120,
        requested_gpu=1,
        runtime_seconds_source=3600.0,
        cpu_request_share_kw=0.1,
        input_bytes=None,
        source_record_id=uid,
    )
    job = RuntimeJobState(
        source=source,
        destination_idc="IDC02",
        logical_rack_id="IDC02:PFR-H100-LOGICAL-POOL",
        gang_membership=(f"IDC02:PFR-GPU:{uid}:0",),
        remaining_work_gpu_hours=1.0,
        lifecycle="RESTARTING",
        restart_remaining_steps=1,
    )
    state = MutableMethodState(
        issue=106,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={uid: job},
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B08)

    planner.materialize_runtime_rack_assignments(state, config)

    assert job.destination_idc == "IDC02"
    assert job.logical_rack_id == "IDC02_LP01"


def test_active_migration_keeps_source_rack_until_transfer_completes() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._initialize = lambda: None
    uid = "migrating-job"
    planner.scope = {
        "cap": pd.DataFrame(
            [
                {
                    "rack_pool_id": "IDC01_LP01",
                    "idc_id": "IDC01",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
                {
                    "rack_pool_id": "IDC02_LP01",
                    "idc_id": "IDC02",
                    "deliverable_active_gpu_capacity": 1.0,
                    "rack_power_cap_kw": 10.0,
                },
            ]
        ),
        "domains": {
            uid: [
                {
                    "destination_IDC_id": "IDC01",
                    "rack_pool_id": "IDC01_LP01",
                },
                {
                    "destination_IDC_id": "IDC02",
                    "rack_pool_id": "IDC02_LP01",
                },
            ]
        },
        "pmap": {
            uid: {
                "arrival_step": 100,
                "latest_start_step": 105,
                "latest_completion_step_exclusive": 120,
                "requested_gpu": 1,
                "IT_power_kW": 1.0,
                "duration_steps": 12,
            }
        },
        "wan_map": {},
    }
    source = OperationalTrainingJob(
        job_uid=uid,
        origin_idc="IDC01",
        arrival_step=100,
        latest_start_step=105,
        deadline_step=120,
        requested_gpu=1,
        runtime_seconds_source=3600.0,
        cpu_request_share_kw=0.1,
        input_bytes=None,
        source_record_id=uid,
    )
    job = RuntimeJobState(
        source=source,
        destination_idc="IDC01",
        logical_rack_id="IDC01_LP01",
        gang_membership=(f"IDC01_LP01:PFR-GPU:{uid}:0",),
        remaining_work_gpu_hours=1.0,
        lifecycle="MIGRATING",
        compute_rate_fraction=0.0,
        migration_source_idc="IDC01",
        migration_destination_idc="IDC02",
        migration_payload_remaining_bytes=1_000_000,
    )
    state = MutableMethodState(
        issue=106,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={uid: job},
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B07)

    audit = planner.materialize_runtime_rack_assignments(state, config)

    assert audit["assigned_jobs"] == 0
    assert audit["migrating_destination_rack_reservations"] == 1
    assert audit["occupied_gpu_by_rack"] == {
        "IDC01_LP01": 0.0,
        "IDC02_LP01": 1.0,
    }
    assert audit["occupied_power_kw_by_rack"] == {
        "IDC01_LP01": 0.0,
        "IDC02_LP01": 1.0,
    }
    assert job.destination_idc == "IDC01"
    assert job.logical_rack_id == "IDC01_LP01"
    assert job.migration_destination_idc == "IDC02"


def test_restarting_job_reserves_full_power_after_fixed_racks() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._initialize = lambda: None
    fixed_uid = "fixed-running"
    restarting_uid = "restarting"
    planner.scope = {
        "cap": pd.DataFrame(
            [
                {
                    "rack_pool_id": "IDC11_LP01",
                    "idc_id": "IDC11",
                    "deliverable_active_gpu_capacity": 2.0,
                    "rack_power_cap_kw": 15.0,
                },
                {
                    "rack_pool_id": "IDC11_LP04",
                    "idc_id": "IDC11",
                    "deliverable_active_gpu_capacity": 2.0,
                    "rack_power_cap_kw": 15.0,
                },
            ]
        ),
        "domains": {
            uid: [
                {
                    "destination_IDC_id": "IDC11",
                    "rack_pool_id": rack,
                }
                for rack in ("IDC11_LP01", "IDC11_LP04")
            ]
            for uid in (fixed_uid, restarting_uid)
        },
        "pmap": {
            fixed_uid: {
                "arrival_step": 100,
                "latest_start_step": 105,
                "latest_completion_step_exclusive": 140,
                "requested_gpu": 1,
                "IT_power_kW": 10.0,
            },
            restarting_uid: {
                "arrival_step": 100,
                "latest_start_step": 101,
                "latest_completion_step_exclusive": 120,
                "requested_gpu": 1,
                "IT_power_kW": 10.0,
            },
        },
        "wan_map": {},
    }

    def source(uid: str, *, latest_start: int, deadline: int) -> OperationalTrainingJob:
        return OperationalTrainingJob(
            job_uid=uid,
            origin_idc="IDC11",
            arrival_step=100,
            latest_start_step=latest_start,
            deadline_step=deadline,
            requested_gpu=1,
            runtime_seconds_source=3600.0,
            cpu_request_share_kw=0.1,
            input_bytes=None,
            source_record_id=uid,
        )

    fixed = RuntimeJobState(
        source=source(fixed_uid, latest_start=105, deadline=140),
        destination_idc="IDC11",
        logical_rack_id="IDC11_LP01",
        gang_membership=(f"IDC11_LP01:PFR-GPU:{fixed_uid}:0",),
        remaining_work_gpu_hours=1.0,
        lifecycle="RUNNING",
    )
    restarting = RuntimeJobState(
        source=source(restarting_uid, latest_start=101, deadline=120),
        destination_idc="IDC11",
        logical_rack_id="IDC11:PFR-H100-LOGICAL-POOL",
        gang_membership=(f"IDC11:PFR-GPU:{restarting_uid}:0",),
        remaining_work_gpu_hours=1.0,
        lifecycle="RESTARTING",
        restart_remaining_steps=1,
    )
    state = MutableMethodState(
        issue=106,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={fixed_uid: fixed, restarting_uid: restarting},
    )
    config = MethodFactory(
        ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    ).create_electrical_stress(ElectricalStressMethod.B07)

    audit = planner.materialize_runtime_rack_assignments(state, config)

    assert fixed.logical_rack_id == "IDC11_LP01"
    assert restarting.logical_rack_id == "IDC11_LP04"
    assert audit["occupied_gpu_by_rack"] == {
        "IDC11_LP01": 1.0,
        "IDC11_LP04": 1.0,
    }
    assert audit["occupied_power_kw_by_rack"] == {
        "IDC11_LP01": 10.0,
        "IDC11_LP04": 10.0,
    }


def test_migration_candidate_requires_one_feasible_destination_rack() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._initialize = lambda: None
    candidate_uid = "candidate"
    occupant_uid = "occupant"
    planner.scope = {
        "cap": pd.DataFrame(
            [
                {
                    "rack_pool_id": "IDC01_LP01",
                    "idc_id": "IDC01",
                    "deliverable_active_gpu_capacity": 2.0,
                    "rack_power_cap_kw": 20.0,
                },
                {
                    "rack_pool_id": "IDC02_LP01",
                    "idc_id": "IDC02",
                    "deliverable_active_gpu_capacity": 2.0,
                    "rack_power_cap_kw": 20.0,
                },
            ]
        ),
        "domains": {
            candidate_uid: [
                {
                    "destination_IDC_id": "IDC01",
                    "rack_pool_id": "IDC01_LP01",
                },
                {
                    "destination_IDC_id": "IDC02",
                    "rack_pool_id": "IDC02_LP01",
                },
            ],
            occupant_uid: [
                {
                    "destination_IDC_id": "IDC02",
                    "rack_pool_id": "IDC02_LP01",
                }
            ],
        },
        "pmap": {
            candidate_uid: {
                "arrival_step": 100,
                "latest_start_step": 105,
                "latest_completion_step_exclusive": 140,
                "requested_gpu": 2,
                "IT_power_kW": 10.0,
            },
            occupant_uid: {
                "arrival_step": 100,
                "latest_start_step": 105,
                "latest_completion_step_exclusive": 140,
                "requested_gpu": 1,
                "IT_power_kW": 10.0,
            },
        },
        "wan_map": {},
    }

    def runtime_job(uid: str, origin: str, gpu: int) -> RuntimeJobState:
        source = OperationalTrainingJob(
            job_uid=uid,
            origin_idc=origin,
            arrival_step=100,
            latest_start_step=105,
            deadline_step=140,
            requested_gpu=gpu,
            runtime_seconds_source=3600.0,
            cpu_request_share_kw=0.1,
            input_bytes=None,
            source_record_id=uid,
        )
        return RuntimeJobState(
            source=source,
            destination_idc=origin,
            logical_rack_id=f"{origin}_LP01",
            gang_membership=tuple(f"{origin}:GPU:{index}" for index in range(gpu)),
            remaining_work_gpu_hours=float(gpu),
            lifecycle="RUNNING",
        )

    state = MutableMethodState(
        issue=106,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
        jobs={
            candidate_uid: runtime_job(candidate_uid, "IDC01", 2),
            occupant_uid: runtime_job(occupant_uid, "IDC02", 1),
        },
    )
    planned_racks = {
        candidate_uid: "IDC01_LP01",
        occupant_uid: "IDC02_LP01",
    }

    assert not planner._migration_candidate_rack_feasible(
        state=state,
        candidate_uid=candidate_uid,
        destination="IDC02",
        planned_racks=planned_racks,
    )


def test_periodic_persistent_refresh_resets_without_rebuilding() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    calls = []
    planner._master_models = {
        "B07": SimpleNamespace(
            model=SimpleNamespace(reset=lambda: calls.append("master"))
        )
    }
    planner._recourse_models = {
        "B07": SimpleNamespace(
            model=SimpleNamespace(reset=lambda: calls.append("recourse"))
        )
    }

    reset_count = planner._reset_method_model_solutions("B07")

    assert reset_count == 2
    assert calls == ["master", "recourse"]
    assert set(planner._master_models) == {"B07"}
    assert set(planner._recourse_models) == {"B07"}


def test_periodic_persistent_refresh_accepts_recourse_only_forced_domain() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    calls = []
    planner._master_models = {}
    planner._recourse_models = {
        "B00": SimpleNamespace(
            model=SimpleNamespace(reset=lambda: calls.append("recourse"))
        )
    }

    reset_count = planner._periodic_reset_method_models("B00")

    assert reset_count == 1
    assert calls == ["recourse"]
    assert planner._master_models == {}
    assert set(planner._recourse_models) == {"B00"}


def test_periodic_persistent_refresh_rejects_master_only_state() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner._master_models = {
        "B00": SimpleNamespace(model=SimpleNamespace(reset=lambda: None))
    }
    planner._recourse_models = {}

    with pytest.raises(RuntimeContractError, match="exact recourse"):
        planner._periodic_reset_method_models("B00")


def test_shared_watchdog_transfers_unused_master_time_to_exact_recourse() -> None:
    total = 30.0

    master_budget = PersistentBoundedMilpPlanner._shared_watchdog_budgets(total)
    recourse_budget = PersistentBoundedMilpPlanner._shared_watchdog_budgets(
        total,
        master_elapsed_seconds=16.5,
    )

    assert master_budget == pytest.approx(30.0)
    assert recourse_budget == pytest.approx(13.5)
    assert 16.5 + recourse_budget == pytest.approx(total)


def test_shared_watchdog_fails_before_recourse_when_master_consumes_total() -> None:
    with pytest.raises(RuntimeContractError, match="exhausted the shared"):
        PersistentBoundedMilpPlanner._shared_watchdog_budgets(
            30.0,
            master_elapsed_seconds=30.0,
        )


def test_persistent_model_refresh_disposes_both_hierarchical_stages() -> None:
    class FakeGurobiModel:
        def __init__(self) -> None:
            self.disposed = False

        def dispose(self) -> None:
            self.disposed = True

    class FakeStage:
        def __init__(self) -> None:
            self.model = FakeGurobiModel()

    planner = object.__new__(PersistentBoundedMilpPlanner)
    master = FakeStage()
    recourse = FakeStage()
    planner._master_models = {"B07": master}
    planner._recourse_models = {"B07": recourse}

    planner._dispose_method_models("B07")

    assert master.model.disposed
    assert recourse.model.disposed
    assert planner._master_models == {}
    assert planner._recourse_models == {}


def test_candidate_truncation_infeasibility_expands_k_until_feasible() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 16
    planner.candidate_limit_frozen = False
    planner._master_models = {}
    planner._recourse_models = {}
    planner._model_solve_generation_by_method = {}
    sentinel_plan = object()

    def solve_current(**_kwargs):
        if planner.candidate_limit < 16:
            raise RuntimeContractError(
                "hierarchical slow_master multiobjective solve failed to "
                "complete all priorities: status=INFEASIBLE"
            )
        return sentinel_plan, {"candidate_limit_k": planner.candidate_limit}

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(
        comparison_method_id=SimpleNamespace(value="B07")
    )

    plan, certificate = planner.solve(
        state=SimpleNamespace(jobs={}),
        config=config,
        frame=None,
        migration_authority=None,
        evaluation_steps_remaining=54,
    )

    assert plan is sentinel_plan
    assert certificate["candidate_limit_attempts"] == [4, 8, 16]
    assert certificate["candidate_limit_adaptive_expansion_used"] is True
    assert certificate["candidate_limit_infeasible_attempt_count"] == 2
    assert certificate["candidate_limit_expansion_reason"] == (
        "BASE_DOMAIN_SLOW_MASTER_INFEASIBLE"
    )


def test_capacity_deferral_expands_k_before_accepting_visible_queue() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 16
    planner.candidate_limit_frozen = False
    planner._master_models = {}
    planner._recourse_models = {}
    planner._model_solve_generation_by_method = {}
    sentinel_plan = object()

    def solve_current(**_kwargs):
        return sentinel_plan, {
            "candidate_limit_k": planner.candidate_limit,
            "optimized_deferred_job_count": int(planner.candidate_limit < 16),
            "capacity_admission_gate": float(planner.candidate_limit < 16),
        }

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(comparison_method_id=SimpleNamespace(value="B07"))

    plan, certificate = planner.solve(
        state=SimpleNamespace(
            jobs={"queued": SimpleNamespace(lifecycle="QUEUED")}
        ),
        config=config,
        frame=None,
        migration_authority=None,
        evaluation_steps_remaining=54,
    )

    assert plan is sentinel_plan
    assert certificate["candidate_limit_attempts"] == [4, 8, 16]
    assert certificate["candidate_limit_deferred_attempt_count"] == 2
    assert certificate["candidate_limit_expansion_reason"] == (
        "BASE_DOMAIN_CAPACITY_DEFERRAL"
    )
    assert certificate["candidate_limit_admission_screen_attempts"] == [4, 8, 16]


def test_intermediate_candidate_uses_admission_screen_before_full_solve() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 16
    planner.candidate_limit_frozen = False
    planner._master_models = {}
    planner._recourse_models = {}
    planner._model_solve_generation_by_method = {}
    sentinel_plan = object()
    calls = []
    ceilings = []
    admission_optima = []
    disposed = []
    planner._dispose_method_models = lambda method: disposed.append(method)

    def solve_current(**kwargs):
        screen = bool(kwargs.get("admission_screen_only", False))
        calls.append((planner.candidate_limit, screen))
        ceilings.append(kwargs.get("admission_ceiling_deferred_count"))
        admission_optima.append(
            kwargs.get("admission_ceiling_objective_value")
        )
        deferred = int(planner.candidate_limit < 8)
        return (None if screen else sentinel_plan), {
            "candidate_limit_k": planner.candidate_limit,
            "optimized_deferred_job_count": deferred,
            "capacity_admission_gate": float(deferred),
            "workload_domain_reduction": {"no_bounded_option_jobs": 0},
            "admission_gate_solve_seconds": 0.25 if screen else 0.0,
            "admission_screen_total_seconds": 0.5 if screen else 0.0,
            "admission_screen_model_build_seconds": 0.1 if screen else 0.0,
        }

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(comparison_method_id=SimpleNamespace(value="B07"))

    plan, certificate = planner.solve(
        state=SimpleNamespace(
            jobs={"queued": SimpleNamespace(lifecycle="QUEUED")}
        ),
        config=config,
        frame=None,
        migration_authority=None,
        evaluation_steps_remaining=54,
    )

    assert plan is sentinel_plan
    assert calls == [(4, True), (8, True), (8, False)]
    assert ceilings == [None, None, 0]
    assert admission_optima == [None, None, 0.0]
    assert disposed == []
    assert certificate["candidate_limit_attempts"] == [4, 8]
    assert certificate["candidate_limit_admission_screen_attempts"] == [4, 8]
    assert certificate["candidate_limit_admission_screen_solve_seconds"] == 0.5
    assert certificate["candidate_limit_admission_screen_total_seconds"] == 1.0
    assert (
        certificate["candidate_limit_admission_screen_model_build_seconds"]
        == 0.2
    )


def test_no_visible_queue_skips_duplicate_admission_screen() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 16
    planner.candidate_limit_frozen = False
    sentinel_plan = object()
    calls = []

    def solve_current(**kwargs):
        calls.append(bool(kwargs.get("admission_screen_only", False)))
        return sentinel_plan, {
            "candidate_limit_k": planner.candidate_limit,
            "optimized_deferred_job_count": 0,
            "workload_domain_reduction": {"no_bounded_option_jobs": 0},
        }

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(comparison_method_id=SimpleNamespace(value="B07"))

    plan, certificate = planner.solve(
        state=SimpleNamespace(
            jobs={"running": SimpleNamespace(lifecycle="RUNNING")}
        ),
        config=config,
        frame=None,
        migration_authority=None,
        evaluation_steps_remaining=54,
    )

    assert plan is sentinel_plan
    assert calls == [False]
    assert certificate["candidate_limit_attempts"] == [4]
    assert certificate["candidate_limit_admission_screen_attempts"] == []
    assert certificate["candidate_limit_admission_screen_total_seconds"] == 0.0
    assert certificate["candidate_limit_admission_screen_skipped_reason"] == (
        "NO_VISIBLE_QUEUED_JOBS"
    )


def test_unavoidable_capacity_deferral_does_not_expand_candidate_domain() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 64
    planner.candidate_limit_frozen = False
    planner._master_models = {}
    planner._recourse_models = {}
    planner._model_solve_generation_by_method = {}
    sentinel_plan = object()

    def solve_current(**_kwargs):
        return sentinel_plan, {
            "candidate_limit_k": planner.candidate_limit,
            "optimized_deferred_job_count": 75,
            "capacity_admission_gate": 75.0,
            "workload_domain_reduction": {
                "no_bounded_option_jobs": 75,
            },
        }

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(comparison_method_id=SimpleNamespace(value="B01"))

    plan, certificate = planner.solve(
        state=SimpleNamespace(
            jobs={"queued": SimpleNamespace(lifecycle="QUEUED")}
        ),
        config=config,
        frame=None,
        migration_authority=None,
        evaluation_steps_remaining=54,
    )

    assert plan is sentinel_plan
    assert certificate["candidate_limit_attempts"] == [4]
    assert certificate["candidate_limit_adaptive_expansion_used"] is False
    assert certificate["candidate_limit_deferred_attempt_count"] == 0
    assert certificate["candidate_limit_unavoidable_deferred_job_count"] == 75
    assert certificate["candidate_limit_expansion_avoided_reason"] == (
        "ONLY_EXACT_INFEASIBLE_WORKLOADS_DEFERRED"
    )


def test_slow_master_accepts_explicit_deferred_queue_decision() -> None:
    stage = object.__new__(_PersistentMilpModel)
    stage.model_role = "slow_master"
    stage.model = SimpleNamespace(SolCount=1)
    stage.domain = SimpleNamespace(
        route_options={"MESS01": (object(),), "MESS02": (object(),)},
        job_options=((),),
    )
    stage.route = {
        ("MESS01", 0): SimpleNamespace(X=1.0),
        ("MESS02", 0): SimpleNamespace(X=1.0),
    }
    stage.job = {}
    stage.defer_job = {0: SimpleNamespace(X=1.0)}

    route, jobs = stage.selected_domain_decisions()

    assert route == {"MESS01": 0, "MESS02": 0}
    assert jobs == {0: None}


def test_slow_master_expands_aggregate_option_counts_to_individual_jobs() -> None:
    stage = object.__new__(_PersistentMilpModel)
    stage.model_role = "slow_master"
    stage.model = SimpleNamespace(SolCount=1)
    stage.domain = SimpleNamespace(
        route_options={"MESS01": (object(),)},
        job_options=((object(), object()),) * 3,
    )
    stage.route = {("MESS01", 0): SimpleNamespace(X=1.0)}
    stage.job = {
        (0, 0): SimpleNamespace(X=1.0),
        (0, 1): SimpleNamespace(X=1.0),
    }
    stage.defer_job = {
        0: SimpleNamespace(X=0.0),
        1: SimpleNamespace(X=1.0),
        2: SimpleNamespace(X=0.0),
    }
    stage._job_groups = ((0, 1, 2),)

    route, jobs = stage.selected_domain_decisions()

    assert route == {"MESS01": 0}
    assert jobs == {0: 0, 1: None, 2: 1}


def test_workload_truncation_preserves_destination_and_time_diversity() -> None:
    options = []
    for destination_number in range(1, 13):
        destination = f"IDC{destination_number:02d}"
        for offset in range(6):
            for rack_number in range(2):
                options.append(
                    _WorkloadOption(
                        destination=destination,
                        rack=f"{destination}-R{rack_number}",
                        start_offset=offset,
                        duration_steps=1,
                        it_power_kw=1.0,
                        requested_gpu=1,
                        wan_schedule_gb=(),
                        wan_required_bytes=0,
                        remote=False,
                        generation_score=(
                            float(destination_number),
                            float(offset),
                            float(offset),
                            destination,
                            f"R{rack_number}",
                        ),
                    )
                )

    selected_16 = PersistentBoundedMilpPlanner._select_diverse_workload_options(
        options,
        16,
    )
    selected_64 = PersistentBoundedMilpPlanner._select_diverse_workload_options(
        options,
        64,
    )

    assert len({option.destination for option in selected_16}) == 12
    assert len(
        {(option.destination, option.start_offset) for option in selected_16}
    ) == 16
    assert len({option.destination for option in selected_64}) == 12
    assert len(
        {(option.destination, option.start_offset) for option in selected_64}
    ) == 64


def test_workload_truncation_round_robins_racks_after_site_time_coverage() -> None:
    options = [
        _WorkloadOption(
            destination="IDC01",
            rack=f"R{rack_number}",
            start_offset=0,
            duration_steps=1,
            it_power_kw=1.0,
            requested_gpu=1,
            wan_schedule_gb=(),
            wan_required_bytes=0,
            remote=False,
            generation_score=(0.0, 0.0, 0.0, "IDC01", f"R{rack_number}"),
        )
        for rack_number in range(8)
    ]

    selected = PersistentBoundedMilpPlanner._select_diverse_workload_options(
        options,
        4,
    )

    assert [option.rack for option in selected] == ["R0", "R1", "R2", "R3"]


def test_resilient_superset_keeps_legacy_top16_as_exact_prefix() -> None:
    options = [
        _WorkloadOption(
            destination=f"IDC{destination:02d}",
            rack=f"R{rack}",
            start_offset=offset,
            duration_steps=1,
            it_power_kw=1.0,
            requested_gpu=1,
            wan_schedule_gb=(),
            wan_required_bytes=0,
            remote=False,
            generation_score=(
                float(destination),
                float(offset),
                float(offset),
                f"IDC{destination:02d}",
                f"R{rack}",
            ),
        )
        for destination in range(1, 13)
        for offset in range(6)
        for rack in range(2)
    ]
    legacy = sorted(options, key=lambda option: option.generation_score)
    superset = PersistentBoundedMilpPlanner._select_resilient_workload_options(
        options,
        64,
    )

    assert superset[:16] == legacy[:16]
    assert len(superset) == 64
    assert len({option.destination for option in superset}) > len(
        {option.destination for option in legacy[:64]}
    )


def test_candidate_expansion_does_not_mask_non_infeasibility_failures() -> None:
    planner = object.__new__(PersistentBoundedMilpPlanner)
    planner.base_candidate_limit = 4
    planner.candidate_limit = 4
    planner.adaptive_candidate_max = 16
    planner.candidate_limit_frozen = False
    planner._master_models = {}
    planner._recourse_models = {}
    planner._model_solve_generation_by_method = {}

    def solve_current(**_kwargs):
        raise RuntimeContractError(
            "hierarchical slow_master multiobjective solve failed to complete "
            "all priorities: status=TIME_LIMIT"
        )

    planner._solve_current_candidate_limit = solve_current
    config = SimpleNamespace(
        comparison_method_id=SimpleNamespace(value="B07")
    )

    with pytest.raises(RuntimeContractError, match="status=TIME_LIMIT"):
        planner.solve(
            state=SimpleNamespace(jobs={}),
            config=config,
            frame=None,
            migration_authority=None,
            evaluation_steps_remaining=54,
        )
    assert planner.candidate_limit == 4
