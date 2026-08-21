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
    NORMALIZED_EFFECTIVE_COMPUTE = "NORMALIZED_EFFECTIVE_COMPUTE"


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
        return TrainingJobModelState(
            job_uid=self.job_uid,
            arrival_step=self.arrival_step,
            deadline_step=self.deadline_step,
            required_gpu_gang_size=self.requested_gpu_count,
            current_site=None,
            eligible_sites=parameterization.eligible_sites,
            total_work=parameterization.total_work,
            remaining_work=parameterization.total_work,
            work_unit=WorkUnit.NORMALIZED_EFFECTIVE_COMPUTE,
            resource_gpuh=0.0,
            checkpoint_eligible=parameterization.checkpoint_eligible,
            checkpoint_interval_steps=parameterization.checkpoint_interval_steps,
            steps_since_checkpoint=0,
            checkpoint_state_bytes=parameterization.checkpoint_state_bytes,
            migration_destination=None,
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
    current_site: str | None
    eligible_sites: tuple[str, ...]
    total_work: float
    remaining_work: float
    work_unit: WorkUnit
    resource_gpuh: float
    checkpoint_eligible: bool
    checkpoint_interval_steps: int | None
    steps_since_checkpoint: int
    checkpoint_state_bytes: int | None
    migration_destination: str | None
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
        if self.current_site is not None and self.current_site not in self.eligible_sites:
            raise TrainingStateError("current site is not eligible")
        if self.migration_destination is not None and self.migration_destination not in self.eligible_sites:
            raise TrainingStateError("migration destination is not eligible")
        if self.total_work <= 0 or not 0 <= self.remaining_work <= self.total_work:
            raise TrainingStateError("remaining work must lie in [0, total work]")
        if self.resource_gpuh < 0:
            raise TrainingStateError("resource GPUh must be nonnegative")
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


def start_running(state: TrainingJobModelState, *, site: str) -> TrainingJobModelState:
    if state.lifecycle not in {JobLifecycle.READY, JobLifecycle.CHECKPOINT_READY}:
        raise TrainingStateError("RUNNING requires READY or CHECKPOINT_READY")
    if site not in state.eligible_sites:
        raise TrainingStateError("run site is not eligible")
    if state.current_site is not None and state.current_site != site:
        raise TrainingStateError("site mutation requires checkpoint migration")
    return replace(
        state,
        lifecycle=JobLifecycle.RUNNING,
        current_site=site,
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


def begin_migration(
    state: TrainingJobModelState, *, destination: str
) -> TrainingJobModelState:
    if state.lifecycle is not JobLifecycle.CHECKPOINT_READY or not state.checkpoint_eligible:
        raise TrainingStateError("migration is allowed only at an authorized checkpoint boundary")
    if destination not in state.eligible_sites or destination == state.current_site:
        raise TrainingStateError("migration destination must be a different eligible site")
    return replace(
        state,
        lifecycle=JobLifecycle.MIGRATING,
        migration_destination=destination,
        current_compute_rate_per_hour=0.0,
        power_state=PowerState.OFF,
    )


def complete_migration(
    state: TrainingJobModelState, *, restart_steps: int
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
            migration_destination=None,
            steps_since_checkpoint=0,
            current_compute_rate_per_hour=state.min_compute_rate_per_hour,
            power_state=PowerState.ACTIVE,
        )
    return replace(
        state,
        lifecycle=JobLifecycle.RESTARTING,
        current_site=state.migration_destination,
        migration_destination=None,
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
    if before.current_site != after.current_site:
        allowed = (
            before.lifecycle is JobLifecycle.MIGRATING
            and before.migration_destination == after.current_site
        )
        if not allowed:
            raise TrainingStateError("destination mutation is forbidden between checkpoints")


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
