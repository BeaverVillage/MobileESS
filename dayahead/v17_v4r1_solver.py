"""GPU-hour adapter for the frozen V16.3/V17 planning solver.

The historical solver uses node-hour payloads and a four-GPU node
coefficient.  V4R1 changes only that unit boundary: one workload unit is one
GPU-hour and its board-power coefficient is the frozen Dataset312 Q50 value.
The underlying solver and all historical authority files remain untouched.
"""

from __future__ import annotations

from unittest.mock import patch

from . import final_science_solver_v16_3 as _frozen
from .v17_v4r1_april import KAPPA_GPU_Q50_KW


def solve_shadow(**kwargs):
    """Call the frozen solver with the prospective V4R1 unit conversion."""

    sentinel = "V4R1_GPU_HOUR"
    with (
        patch.object(_frozen, "GPU_PER_NODE", 1.0),
        patch.object(_frozen, "_cohort_node_class", lambda _cohort: sentinel),
        patch.dict(_frozen.KAPPA_KW_PER_ACTIVE_H100_NODE, {sentinel: KAPPA_GPU_Q50_KW}),
    ):
        return _frozen.solve_shadow(**kwargs)

