"""Checkpoint-aware batch AI-training job primitives for PFR2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import isclose
from typing import Mapping


class TrainingStateError(ValueError):
    pass


class JobLifecycle(str, Enum):
    NOT_ARRIVED = "NOT_ARRIVED"
    QUEUED = "QUEUED"
    PREFETCHING = "PREFETCHING"
    READY = "READY"
    RUNNING = "RUNNING"
    CHECKPOINT_READY = "CHECKPOINT_READY"
    MIGRATING = "MIGRATING"
    RESTARTING = "RESTARTING"
    COMPLETED = "COMPLETED"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    FAILED = "FAILED"


class WorkUnit(str, Enum):
    H100_EQUIVALENT_GPU_HOUR = "H100_EQUIVALENT_GPU_HOUR"


class PowerState(str, Enum):
    OFF = "OFF"
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"


class ParameterAuthority(str, Enum):
    KESTREL_MEASURED = "KESTREL_MEASURED"
    EXTERNAL_MEASURED = "EXTERNAL_MEASURED"
    SOURCE_DERIVED = "SOURCE_DERIVED"
    MODELED = "MODELED"
    UNRESOLVED = "UNRESOLVED"


class PreemptibilityMode(str, Enum):
    CHECKPOINT_ONLY = "CHECKPOINT_ONLY"
    NON_PREEMPTIBLE = "NON_PREEMPTIBLE"


@dataclass(frozen=True)
class TrainingParameterization:
    total_work: float
    checkpoint_eligible: bool
    checkpoint_interval_steps: int | None
    checkpoint_state_bytes: int | None
    eligible_sites: tuple[str, ...]
    min_compute_rate_per_hour: float
    max_compute_rate_per_hour: float
    power_authority_id: str
    model_family: str | None
    authority_by_field: Mapping[str, ParameterAuthority]
    eligible_gpu_type: str = "H100"
    preemptibility_mode: PreemptibilityMode = PreemptibilityMode.CHECKPOINT_ONLY

    def validate(self) -> None:
        if self.total_work <= 0:
            raise TrainingStateError("total effective compute work must be positive")
        if not self.eligible_sites:
            raise TrainingStateError("at least one eligible site is required")
        if self.checkpoint_interval_steps is not None and self.checkpoint_interval_steps <= 0:
            raise TrainingStateError("checkpoint interval must be positive")
        if self.checkpoint_state_bytes is not None and self.checkpoint_state_bytes < 0:
            raise TrainingStateError("checkpoint state bytes must be nonnegative")
        if not 0 <= self.min_compute_rate_per_hour <= self.max_compute_rate_per_hour:
            raise TrainingStateError("invalid compute-rate envelope")
        if self.model_family is not None:
            authority = self.authority_by_field.get("model_family")
            if authority is ParameterAuthority.KESTREL_MEASURED:
                raise TrainingStateError("Kestrel cannot provide a measured model-family label")
        if not self.eligible_gpu_type:
            raise TrainingStateError("eligible GPU type is required")
        if self.checkpoint_eligible != (
            self.preemptibility_mode is PreemptibilityMode.CHECKPOINT_ONLY
        ):
            raise TrainingStateError(
                "checkpoint eligibility and preemptibility mode disagree"
            )


def baseline_compute_work_gpu_hours(job: "KestrelOperationalJob") -> float:
    """Source-derived normalized progress, not FLOP or token ground truth."""

    if job.requested_gpu_count <= 0 or job.runtime_seconds_source <= 0:
        raise TrainingStateError("baseline GPU count and runtime must be positive")
    return job.requested_gpu_count * job.runtime_seconds_source / 3600.0


@dataclass(frozen=True)
class KestrelOperationalJob:
    """Only fields actually carried by the Kestrel operational backbone."""

    job_uid: str
    arrival_step: int
    deadline_step: int
    requested_gpu_count: int
    runtime_seconds_source: float
    input_bytes: int | None
    source_record_id: str

    def to_training_state(
        self, parameterization: TrainingParameterization
    ) -> "TrainingJobModelState":
        parameterization.validate()
        if self.arrival_step < 0 or self.deadline_step <= self.arrival_step:
            raise TrainingStateError("invalid operational arrival/deadline")
        if self.requested_gpu_count <= 0:
            raise TrainingStateError("GPU gang size must be positive")
        if parameterization.authority_by_field.get("total_work") is ParameterAuthority.SOURCE_DERIVED:
            expected_work = baseline_compute_work_gpu_hours(self)
            if not isclose(parameterization.total_work, expected_work):
                raise TrainingStateError(
                    "source-derived total work must equal gang size times baseline runtime"
                )
        return TrainingJobModelState(
            job_uid=self.job_uid,
            arrival_step=self.arrival_step,
            deadline_step=self.deadline_step,
            required_gpu_gang_size=self.requested_gpu_count,
            eligible_gpu_type=parameterization.eligible_gpu_type,
            current_site=None,
            current_logical_rack=None,
            gang_membership=(),
            eligible_sites=parameterization.eligible_sites,
            baseline_runtime_hours=self.runtime_seconds_source / 3600.0,
            total_work=parameterization.total_work,
            remaining_work=parameterization.total_work,
            work_unit=WorkUnit.H100_EQUIVALENT_GPU_HOUR,
            resource_gpuh=0.0,
            checkpoint_eligible=parameterization.checkpoint_eligible,
            checkpoint_interval_steps=parameterization.checkpoint_interval_steps,
            steps_since_checkpoint=0,
            checkpoint_state_bytes=parameterization.checkpoint_state_bytes,
            preemptibility_mode=parameterization.preemptibility_mode,
            migration_destination=None,
            migration_source=None,
            migration_payload_remaining_bytes=0,
            restart_remaining_steps=0,
            current_compute_rate_per_hour=0.0,
            min_compute_rate_per_hour=parameterization.min_compute_rate_per_hour,
            max_compute_rate_per_hour=parameterization.max_compute_rate_per_hour,
            power_state=PowerState.OFF,
            power_authority_id=parameterization.power_authority_id,
            source_identities=("KESTREL_F30", self.source_record_id),
            authority_by_field=dict(parameterization.authority_by_field),
            lifecycle=JobLifecycle.NOT_ARRIVED,
        )


@dataclass(frozen=True)
class TrainingJobModelState:
    job_uid: str
    arrival_step: int
    deadline_step: int
    required_gpu_gang_size: int
    eligible_gpu_type: str
    current_site: str | None
    current_logical_rack: str | None
    gang_membership: tuple[str, ...]
    eligible_sites: tuple[str, ...]
    baseline_runtime_hours: float
    total_work: float
    remaining_work: float
    work_unit: WorkUnit
    resource_gpuh: float
    checkpoint_eligible: bool
    checkpoint_interval_steps: int | None
    steps_since_checkpoint: int
    checkpoint_state_bytes: int | None
    preemptibility_mode: PreemptibilityMode
    migration_destination: str | None
    migration_source: str | None
    migration_payload_remaining_bytes: int
    restart_remaining_steps: int
    current_compute_rate_per_hour: float
    min_compute_rate_per_hour: float
    max_compute_rate_per_hour: float
    power_state: PowerState
    power_authority_id: str
    source_identities: tuple[str, ...]
    authority_by_field: Mapping[str, ParameterAuthority]
    lifecycle: JobLifecycle

    def validate(self) -> None:
        if self.required_gpu_gang_size <= 0:
            raise TrainingStateError("GPU gang size must be positive")
        if not self.eligible_gpu_type or self.baseline_runtime_hours <= 0:
            raise TrainingStateError("GPU type and baseline runtime are required")
        if self.current_site is not None and self.current_site not in self.eligible_sites:
            raise TrainingStateError("current site is not eligible")
        if self.migration_destination is not None and self.migration_destination not in self.eligible_sites:
            raise TrainingStateError("migration destination is not eligible")
        if self.total_work <= 0 or not 0 <= self.remaining_work <= self.total_work:
            raise TrainingStateError("remaining work must lie in [0, total work]")
        if self.resource_gpuh < 0:
            raise TrainingStateError("resource GPUh must be nonnegative")
        if self.migration_payload_remaining_bytes < 0:
            raise TrainingStateError("migration payload remaining must be nonnegative")
        if self.steps_since_checkpoint < 0 or self.restart_remaining_steps < 0:
            raise TrainingStateError("lifecycle timers must be nonnegative")
        if not 0 <= self.min_compute_rate_per_hour <= self.max_compute_rate_per_hour:
            raise TrainingStateError("invalid compute-rate envelope")
        if self.lifecycle is JobLifecycle.RUNNING:
            if not self.min_compute_rate_per_hour <= self.current_compute_rate_per_hour <= self.max_compute_rate_per_hour:
                raise TrainingStateError("current compute rate is outside its frozen envelope")
        elif self.current_compute_rate_per_hour != 0.0:
            raise TrainingStateError("non-running jobs must have zero compute rate")
        if self.lifecycle is JobLifecycle.COMPLETED and not isclose(self.remaining_work, 0.0):
            raise TrainingStateError("completed jobs cannot retain work")
        if self.lifecycle is JobLifecycle.RUNNING:
            if len(self.gang_membership) != self.required_gpu_gang_size:
                raise TrainingStateError("RUNNING requires the complete GPU gang")
            if len(set(self.gang_membership)) != len(self.gang_membership):
                raise TrainingStateError("GPU gang membership must be unique")


def arrive(state: TrainingJobModelState, *, prefetch_required: bool = False) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.NOT_ARRIVED:
        raise TrainingStateError("only NOT_ARRIVED jobs may arrive")
    target = JobLifecycle.PREFETCHING if prefetch_required else JobLifecycle.QUEUED
    return replace(state, lifecycle=target, power_state=PowerState.OFF)


def start_prefetch(state: TrainingJobModelState) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.QUEUED:
        raise TrainingStateError("prefetch starts from QUEUED")
    return replace(state, lifecycle=JobLifecycle.PREFETCHING)


def mark_ready(state: TrainingJobModelState) -> TrainingJobModelState:
    if state.lifecycle not in {JobLifecycle.QUEUED, JobLifecycle.PREFETCHING}:
        raise TrainingStateError("READY requires QUEUED or PREFETCHING")
    return replace(state, lifecycle=JobLifecycle.READY, power_state=PowerState.IDLE)


def start_running(
    state: TrainingJobModelState,
    *,
    site: str,
    logical_rack: str,
    gang_membership: tuple[str, ...],
) -> TrainingJobModelState:
    if state.lifecycle not in {JobLifecycle.READY, JobLifecycle.CHECKPOINT_READY}:
        raise TrainingStateError("RUNNING requires READY or CHECKPOINT_READY")
    if site not in state.eligible_sites:
        raise TrainingStateError("run site is not eligible")
    if state.current_site is not None and state.current_site != site:
        raise TrainingStateError("site mutation requires checkpoint migration")
    if len(gang_membership) != state.required_gpu_gang_size:
        raise TrainingStateError("full gang membership is required")
    return replace(
        state,
        lifecycle=JobLifecycle.RUNNING,
        current_site=site,
        current_logical_rack=logical_rack,
        gang_membership=gang_membership,
        migration_destination=None,
        current_compute_rate_per_hour=state.min_compute_rate_per_hour,
        power_state=PowerState.ACTIVE,
    )


def gang_allocation_feasible(
    required_gpu_gang_size: int,
    site: str,
    allocated_gpus_by_site: Mapping[str, int],
) -> bool:
    if required_gpu_gang_size <= 0:
        raise TrainingStateError("GPU gang size must be positive")
    if any(count < 0 for count in allocated_gpus_by_site.values()):
        raise TrainingStateError("GPU allocation cannot be negative")
    positive = {key: value for key, value in allocated_gpus_by_site.items() if value}
    return positive == {site: required_gpu_gang_size}


def run_compute_step(
    state: TrainingJobModelState,
    *,
    allocated_gpus_by_site: Mapping[str, int],
    effective_compute_rate_per_hour: float,
    dt_hours: float,
    elapsed_control_steps: int = 1,
) -> TrainingJobModelState:
    state.validate()
    if state.lifecycle is not JobLifecycle.RUNNING or state.current_site is None:
        raise TrainingStateError("compute progress requires a RUNNING job")
    if not gang_allocation_feasible(
        state.required_gpu_gang_size, state.current_site, allocated_gpus_by_site
    ):
        raise TrainingStateError("partial or split gang execution is forbidden")
    if dt_hours <= 0 or elapsed_control_steps <= 0:
        raise TrainingStateError("time increment must be positive")
    if not state.min_compute_rate_per_hour <= effective_compute_rate_per_hour <= state.max_compute_rate_per_hour:
        raise TrainingStateError("fast compute rate is outside the frozen envelope")

    completed_work = effective_compute_rate_per_hour * dt_hours
    remaining = max(0.0, state.remaining_work - completed_work)
    resource_gpuh = state.resource_gpuh + state.required_gpu_gang_size * dt_hours
    steps_since_checkpoint = state.steps_since_checkpoint + elapsed_control_steps
    lifecycle = JobLifecycle.RUNNING
    power_state = PowerState.ACTIVE
    if isclose(remaining, 0.0):
        remaining = 0.0
        lifecycle = JobLifecycle.COMPLETED
        power_state = PowerState.IDLE
    elif (
        state.checkpoint_eligible
        and state.checkpoint_interval_steps is not None
        and steps_since_checkpoint >= state.checkpoint_interval_steps
    ):
        lifecycle = JobLifecycle.CHECKPOINT_READY
        power_state = PowerState.IDLE

    result = replace(
        state,
        remaining_work=remaining,
        resource_gpuh=resource_gpuh,
        current_compute_rate_per_hour=(
            0.0 if lifecycle is not JobLifecycle.RUNNING else effective_compute_rate_per_hour
        ),
        steps_since_checkpoint=steps_since_checkpoint,
        lifecycle=lifecycle,
        power_state=power_state,
    )
    result.validate()
    return result


def run_compute_fraction_step(
    state: TrainingJobModelState,
    *,
    allocated_gpus_by_site: Mapping[str, int],
    compute_rate_fraction: float,
    dt_hours: float = 5.0 / 60.0,
    elapsed_control_steps: int = 1,
) -> TrainingJobModelState:
    """Apply W_next = max(0, W - gang * s * dt) for s in [0, 1]."""

    if not 0.0 <= compute_rate_fraction <= 1.0:
        raise TrainingStateError("compute-rate fraction must lie in [0, 1]")
    effective_rate = state.required_gpu_gang_size * compute_rate_fraction
    return run_compute_step(
        state,
        allocated_gpus_by_site=allocated_gpus_by_site,
        effective_compute_rate_per_hour=effective_rate,
        dt_hours=dt_hours,
        elapsed_control_steps=elapsed_control_steps,
    )


def begin_migration(
    state: TrainingJobModelState, *, destination: str, payload_bytes: int = 0
) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.CHECKPOINT_READY or not state.checkpoint_eligible:
        raise TrainingStateError("migration is allowed only at an authorized checkpoint boundary")
    if destination not in state.eligible_sites or destination == state.current_site:
        raise TrainingStateError("migration destination must be a different eligible site")
    if payload_bytes < 0:
        raise TrainingStateError("migration payload must be nonnegative")
    return replace(
        state,
        lifecycle=JobLifecycle.MIGRATING,
        migration_destination=destination,
        migration_source=state.current_site,
        migration_payload_remaining_bytes=payload_bytes,
        current_compute_rate_per_hour=0.0,
        power_state=PowerState.OFF,
    )


def complete_migration(
    state: TrainingJobModelState, *, restart_steps: int, destination_logical_rack: str
) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.MIGRATING or state.migration_destination is None:
        raise TrainingStateError("no migration is in progress")
    if restart_steps < 0:
        raise TrainingStateError("restart time must be nonnegative")
    if restart_steps == 0:
        return replace(
            state,
            lifecycle=JobLifecycle.RUNNING,
            current_site=state.migration_destination,
            current_logical_rack=destination_logical_rack,
            migration_destination=None,
            migration_payload_remaining_bytes=0,
            steps_since_checkpoint=0,
            current_compute_rate_per_hour=state.min_compute_rate_per_hour,
            power_state=PowerState.ACTIVE,
        )
    return replace(
        state,
        lifecycle=JobLifecycle.RESTARTING,
        current_site=state.migration_destination,
        current_logical_rack=destination_logical_rack,
        migration_destination=None,
        migration_payload_remaining_bytes=0,
        restart_remaining_steps=restart_steps,
        steps_since_checkpoint=0,
        power_state=PowerState.IDLE,
    )


def advance_restart(
    state: TrainingJobModelState, *, elapsed_steps: int = 1
) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.RESTARTING:
        raise TrainingStateError("job is not restarting")
    if elapsed_steps <= 0:
        raise TrainingStateError("elapsed restart steps must be positive")
    remaining = max(0, state.restart_remaining_steps - elapsed_steps)
    return replace(
        state,
        restart_remaining_steps=remaining,
        lifecycle=JobLifecycle.RUNNING if remaining == 0 else JobLifecycle.RESTARTING,
        current_compute_rate_per_hour=(
            state.min_compute_rate_per_hour if remaining == 0 else 0.0
        ),
        power_state=PowerState.ACTIVE if remaining == 0 else PowerState.IDLE,
    )


def validate_assignment_transition(
    before: TrainingJobModelState, after: TrainingJobModelState
) -> None:
    if before.required_gpu_gang_size != after.required_gpu_gang_size:
        raise TrainingStateError("GPU gang mutation is forbidden")
    if before.gang_membership != after.gang_membership:
        raise TrainingStateError("GPU gang membership mutation is forbidden")
    if before.current_site != after.current_site:
        allowed = (
            before.lifecycle is JobLifecycle.MIGRATING
            and before.migration_destination == after.current_site
        )
        if not allowed:
            raise TrainingStateError("destination mutation is forbidden between checkpoints")
    if before.current_logical_rack != after.current_logical_rack:
        allowed = before.lifecycle is JobLifecycle.MIGRATING
        if not allowed:
            raise TrainingStateError("logical rack mutation is forbidden between checkpoints")


@dataclass(frozen=True)
class DatasetPayload:
    dataset_id: str
    total_bytes: int

    def validate(self) -> None:
        if not self.dataset_id or self.total_bytes < 0:
            raise TrainingStateError("invalid dataset payload")


@dataclass(frozen=True)
class CheckpointStatePayload:
    aggregate_bytes: int | None = None
    component_bytes: Mapping[str, int] | None = None

    def total_bytes(self) -> int:
        if self.aggregate_bytes is not None and self.component_bytes is not None:
            raise TrainingStateError(
                "checkpoint aggregate and components cannot both be counted"
            )
        if self.aggregate_bytes is not None:
            if self.aggregate_bytes < 0:
                raise TrainingStateError("checkpoint bytes must be nonnegative")
            return self.aggregate_bytes
        if self.component_bytes is None:
            raise TrainingStateError("checkpoint size authority is unresolved")
        if any(value < 0 for value in self.component_bytes.values()):
            raise TrainingStateError("checkpoint component bytes must be nonnegative")
        return sum(self.component_bytes.values())


def migration_payload_bytes(
    datasets: tuple[DatasetPayload, ...],
    destination_inventory_bytes: Mapping[str, int],
    checkpoint_state: CheckpointStatePayload,
) -> int:
    missing_dataset_bytes = 0
    for dataset in datasets:
        dataset.validate()
        present = destination_inventory_bytes.get(dataset.dataset_id, 0)
        if present < 0:
            raise TrainingStateError("destination inventory cannot be negative")
        missing_dataset_bytes += max(0, dataset.total_bytes - present)
    return missing_dataset_bytes + checkpoint_state.total_bytes()
