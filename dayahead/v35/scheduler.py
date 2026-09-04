"""Memory-aware launch policy for cheap AIDC and heavy MESS case processes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .contracts import MEMORY_RESERVE_BYTES


def available_physical_memory_bytes() -> int:
    try:
        import psutil

        return int(psutil.virtual_memory().available)
    except (ImportError, OSError):
        return 0


@dataclass(frozen=True)
class CaseLaunch:
    day: str
    case: str
    heavy: bool


def ordered_launches(values: Sequence[CaseLaunch]) -> tuple[CaseLaunch, ...]:
    """Prefer B0/B1 while retaining deterministic day/case ordering."""

    order = {"B0": 0, "B1": 1, "B2": 2, "B3": 3}
    return tuple(sorted(values, key=lambda item: (item.heavy, item.day, order[item.case])))


def heavy_launch_capacity(
    *,
    available_bytes: int | None = None,
    estimated_heavy_process_bytes: int = 6 * 1024**3,
    reserve_bytes: int = MEMORY_RESERVE_BYTES,
    hard_cap: int = 2,
) -> int:
    available = available_physical_memory_bytes() if available_bytes is None else int(available_bytes)
    if available <= reserve_bytes or estimated_heavy_process_bytes <= 0:
        return 0
    return max(0, min(int(hard_cap), (available - reserve_bytes) // int(estimated_heavy_process_bytes)))


def may_launch_heavy(
    active_heavy: int,
    *,
    available_bytes: int | None = None,
    estimated_heavy_process_bytes: int = 6 * 1024**3,
) -> bool:
    return int(active_heavy) < heavy_launch_capacity(
        available_bytes=available_bytes,
        estimated_heavy_process_bytes=estimated_heavy_process_bytes,
    )


def wait_until_heavy_safe(
    *,
    active_heavy: int,
    memory_reader: Callable[[], int] = available_physical_memory_bytes,
    estimated_heavy_process_bytes: int = 6 * 1024**3,
) -> bool:
    """Single non-blocking safety check; supervisors perform timed polling."""

    return may_launch_heavy(
        active_heavy,
        available_bytes=memory_reader(),
        estimated_heavy_process_bytes=estimated_heavy_process_bytes,
    )
