from __future__ import annotations

import inspect

from dayahead import final_science_solver_v16_3 as frozen
from dayahead import v17_v4r1_science, v17_v4r1_solver


def test_gpu_hour_adapter_does_not_modify_frozen_solver_source() -> None:
    before = inspect.getsource(frozen.solve_shadow)
    assert "GPU_PER_NODE / DT_HOURS" in before
    assert inspect.getsource(frozen.solve_shadow) == before


def test_gpu_hour_adapter_freezes_board_power_q50() -> None:
    assert v17_v4r1_solver.KAPPA_GPU_Q50_KW == 0.48563611660901085


def test_same_seven_day_firewall() -> None:
    assert tuple(v17_v4r1_science.DEBUG_DAYS) == (
        "2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13",
        "2025-04-15", "2025-04-22", "2025-04-23",
    )
    assert v17_v4r1_science._firewall()["May_scientific_input_reads"] == 0
    assert v17_v4r1_science._firewall()["June_scientific_input_reads"] == 0


def test_multi_slot_restoration_is_partitioned_without_changing_common_loop(monkeypatch) -> None:
    calls = []
    class Violation:
        def __init__(self, slot): self.slot = slot
    def frozen(*args, **kwargs):
        rows = args[5]; calls.append(tuple(row.slot for row in rows)); return [rows[0].slot], 2
    monkeypatch.setattr(v17_v4r1_science, "local_fresh_ac_cuts", frozen)
    cuts, solve_calls = v17_v4r1_science._cuts_by_slot(
        None, None, None, None, None, [Violation(9), Violation(3), Violation(9)],
        case="B3", iteration_index=1, margins={},
    )
    assert calls == [(3,), (9, 9)]
    assert cuts == [3, 9]
    assert solve_calls == 4
