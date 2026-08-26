import pytest
import pandas as pd
from types import SimpleNamespace

from pfr.methods import ElectricalStressMethod, ExperimentAuthority, MethodFactory
from pfr.optimization import FastOptimizationContext, GurobiFastControlOptimizer
from pfr.persistent_bounded_milp import (
    PersistentBoundedMilpPlanner,
    _WorkloadOption,
)
from pfr.runtime import (
    CausalExperimentFrame,
    MESS_CANONICAL_STAGING,
    MESS_IDS,
    MutableMethodState,
    OperationalTrainingJob,
    RuntimeJobState,
    RuntimeContractError,
    _schedule_capacity_feasible_queued_jobs,
    _synchronize_planned_rack_assignments,
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
        state=None,
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
            state=None,
            config=config,
            frame=None,
            migration_authority=None,
            evaluation_steps_remaining=54,
        )
    assert planner.candidate_limit == 4
