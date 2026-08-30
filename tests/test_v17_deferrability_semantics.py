from __future__ import annotations

import math

import pytest

from dayahead.aidc_ml_data import NODE_CLASSES
from dayahead.v17_deferrability_semantics import (
    DEFERRAL_SLOTS,
    LATENCY_CLASSES,
    build_reference_schedule_v4,
    latency_class,
)


def test_latency_classes_use_frozen_left_open_right_closed_boundaries() -> None:
    assert latency_class(0.0) == "FIXED"
    assert latency_class(600.0) == "FIXED"
    assert latency_class(math.nextafter(600.0, math.inf)) == "C1"
    assert latency_class(1800.0) == "C1"
    assert latency_class(math.nextafter(1800.0, math.inf)) == "C2"
    assert latency_class(3600.0) == "C2"
    assert latency_class(7200.0) == "C3"
    assert latency_class(10800.0) == "C4"
    assert latency_class(math.nextafter(10800.0, math.inf)) == "C5"
    assert latency_class(-1.0) is None


def test_deferral_budgets_are_conservative_complete_grid_slots() -> None:
    assert DEFERRAL_SLOTS == {"C1": 0, "C2": 2, "C3": 4, "C4": 8, "C5": 12}


def _empty_arrivals() -> dict[tuple[str, int], list[float]]:
    return {
        (latency_class_name, node_class): [0.0] * 96
        for latency_class_name in LATENCY_CLASSES
        for node_class in NODE_CLASSES
    }


def test_reference_v4_is_grid_blind_earliest_feasible_and_deadline_safe() -> None:
    arrivals = _empty_arrivals()
    arrivals[("C1", 1)][3] = 0.5
    arrivals[("C2", 2)][3] = 1.0
    result = build_reference_schedule_v4(arrivals, {"R01": 2.0})
    assert result.authority_id == "REFERENCE_COMPUTE_SCHEDULE_V4"
    assert result.service_by_class_node_rack_slot[("C1", 1, "R01", 3)] == pytest.approx(0.5)
    assert result.service_by_class_node_rack_slot[("C2", 2, "R01", 3)] == pytest.approx(1.0)
    assert result.evidence["max_no_anticipation_violation_nodeh"] == pytest.approx(0.0)
    assert result.evidence["max_deadline_shortfall_nodeh"] == pytest.approx(0.0)
    assert result.evidence["terminal_backlog_nodeh"] == pytest.approx(0.0)
    assert result.evidence["grid_information_reads"] == 0
    assert result.evidence["MESS_information_reads"] == 0


def test_reference_v4_fails_closed_when_same_slot_c1_cannot_be_served() -> None:
    arrivals = _empty_arrivals()
    arrivals[("C1", 1)][0] = 2.0
    with pytest.raises(RuntimeError, match="REFERENCE_V4_DEADLINE_INFEASIBLE"):
        build_reference_schedule_v4(arrivals, {"R01": 1.0})

