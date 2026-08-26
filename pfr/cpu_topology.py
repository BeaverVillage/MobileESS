"""CPU-topology allocation for independent solver processes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence


def allocate_disjoint_cpu_groups(
    core_siblings: Sequence[Sequence[int]],
    *,
    workers: int,
    threads_per_worker: int,
    use_all_cpus: bool = False,
) -> tuple[tuple[int, ...], ...]:
    """Allocate disjoint logical CPUs while avoiding siblings within a worker."""

    if workers < 1 or threads_per_worker < 1:
        raise ValueError("workers and threads_per_worker must be positive")
    normalized = tuple(tuple(sorted(set(group))) for group in core_siblings)
    if not normalized or any(not group for group in normalized):
        raise ValueError("core_siblings must contain non-empty CPU groups")
    logical = [cpu for group in normalized for cpu in group]
    if len(logical) != len(set(logical)):
        raise ValueError("a logical CPU appears in more than one physical core")
    required = workers * threads_per_worker
    if required > len(logical):
        raise ValueError(
            f"topology needs {required} logical CPUs but only {len(logical)} are allowed"
        )
    if threads_per_worker > len(normalized):
        raise ValueError(
            "threads_per_worker exceeds the number of physical cores; "
            "sibling-free worker allocation is impossible"
        )

    group_sizes = [threads_per_worker] * workers
    if use_all_cpus:
        for index in range(len(logical) - required):
            group_sizes[index % workers] += 1
    if max(group_sizes) > len(normalized):
        raise ValueError(
            "a worker CPU budget exceeds the physical-core count; "
            "sibling-free allocation is impossible"
        )
    # Assign one logical CPU from a physical core at a time.  Once SMT use is
    # unavoidable, minimize the largest pairwise physical-core overlap and
    # spread contention over previously uncontended workers.  A simple lane
    # slice (for example [0,2] followed later by [1,3]) makes two workers share
    # both cores and lets that slow pair determine whole-campaign wall time.
    remaining = [len(group) for group in normalized]
    next_lane = [0 for _group in normalized]
    core_sets: list[set[int]] = []
    groups_list: list[tuple[int, ...]] = []
    for size in group_sizes:
        chosen_cores: set[int] = set()
        chosen_cpus: list[int] = []
        for _slot in range(size):
            candidates = []
            for core_index, available in enumerate(remaining):
                if available < 1 or core_index in chosen_cores:
                    continue
                predicted_overlaps = [
                    len(chosen_cores & prior) + int(core_index in prior)
                    for prior in core_sets
                ]
                owner_contention = [
                    sum(len(prior & other) for other in core_sets if other is not prior)
                    for prior in core_sets
                    if core_index in prior
                ]
                candidates.append(
                    (
                        max(predicted_overlaps, default=0),
                        len(normalized[core_index]) - available,
                        max(owner_contention, default=0),
                        sum(owner_contention),
                        core_index,
                    )
                )
            if not candidates:
                raise RuntimeError("unable to construct a sibling-free CPU group")
            core_index = min(candidates)[-1]
            chosen_cores.add(core_index)
            chosen_cpus.append(normalized[core_index][next_lane[core_index]])
            next_lane[core_index] += 1
            remaining[core_index] -= 1
        core_sets.append(chosen_cores)
        groups_list.append(tuple(chosen_cpus))
    groups = tuple(groups_list)
    cpu_to_core = {
        cpu: core_index
        for core_index, group in enumerate(normalized)
        for cpu in group
    }
    if any(
        len({cpu_to_core[cpu] for cpu in group}) != len(group)
        for group in groups
    ):
        raise RuntimeError("a worker CPU group contains sibling logical CPUs")
    return groups


def discover_disjoint_cpu_groups(
    *,
    workers: int,
    threads_per_worker: int,
) -> tuple[tuple[int, ...], ...]:
    """Read Linux CPU topology and return fail-closed worker affinity groups."""

    if os.name != "posix" or not Path("/sys/devices/system/cpu").is_dir():
        raise RuntimeError("topology-aware affinity requires Linux/WSL sysfs")
    allowed = sorted(os.sched_getaffinity(0))
    by_core: dict[tuple[int, int], list[int]] = {}
    for cpu in allowed:
        topology = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        key = (
            int((topology / "physical_package_id").read_text(encoding="utf-8")),
            int((topology / "core_id").read_text(encoding="utf-8")),
        )
        by_core.setdefault(key, []).append(cpu)
    siblings = tuple(tuple(sorted(by_core[key])) for key in sorted(by_core))
    return allocate_disjoint_cpu_groups(
        siblings,
        workers=workers,
        threads_per_worker=threads_per_worker,
        # Measurements on the target 16-logical-CPU host show that reserving
        # exactly the solver thread budget is faster than forcing Python and
        # OpenDSS to contend for every remaining sibling.
        use_all_cpus=False,
    )
