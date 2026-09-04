from __future__ import annotations

import random

import pytest

from dayahead.aidc_ml_data import NODE_CLASSES
from dayahead.v17_deferrability_semantics import LATENCY_CLASSES, build_reference_schedule_v4
from dayahead.v17_reference_scheduler_v5 import (
    AUTHORITY_ID,
    build_reference_schedule_v5,
    weighted_waterfill,
)


def _empty() -> dict[tuple[str, int], list[float]]:
    return {(name, node): [0.0] * 96 for name in LATENCY_CLASSES for node in NODE_CLASSES}


def _physical(schedule, reverse: dict[str, str] | None = None):
    reverse = reverse or {}
    return {
        (name, node, reverse.get(rack, rack), slot): value
        for (name, node, rack, slot), value in schedule.service_by_class_node_rack_slot.items()
    }


def test_v4_root_cause_and_v5_proportional_unsaturated_identity() -> None:
    arrivals = _empty(); arrivals[("C1", 1)][3] = 0.5
    capacities = {"AIDC01_LP01": 1.0, "AIDC02_LP01": 3.0}
    v4 = build_reference_schedule_v4(arrivals, capacities)
    v5 = build_reference_schedule_v5(arrivals, capacities)
    assert v4.service_by_class_node_rack_slot[("C1", 1, "AIDC01_LP01", 3)] == pytest.approx(0.5)
    assert v4.service_by_class_node_rack_slot[("C1", 1, "AIDC02_LP01", 3)] == 0.0
    assert v5.authority_id == AUTHORITY_ID
    assert v5.service_by_class_node_rack_slot[("C1", 1, "AIDC01_LP01", 3)] == pytest.approx(0.125)
    assert v5.service_by_class_node_rack_slot[("C1", 1, "AIDC02_LP01", 3)] == pytest.approx(0.375)


def test_weighted_waterfill_saturation_and_conservation() -> None:
    remaining = {"R1": 0.1, "R2": 2.0, "R3": 3.0}
    allocation = weighted_waterfill(3.0, {"R1": 1.0, "R2": 2.0, "R3": 3.0}, remaining)
    assert allocation["R1"] == pytest.approx(0.1)
    assert sum(allocation.values()) == pytest.approx(3.0, abs=1e-12)
    assert all(value >= -1e-12 for value in remaining.values())
    assert allocation["R2"] / allocation["R3"] == pytest.approx(2.0 / 3.0)


def test_v5_capacity_workload_deadline_and_terminal_identities() -> None:
    arrivals = _empty()
    arrivals[("C1", 1)][0] = 0.4
    arrivals[("C5", 16)][10] = 1.2
    result = build_reference_schedule_v5(arrivals, {"R1": 0.5, "R2": 1.0})
    assert result.evidence["max_rack_capacity_violation_nodeh"] == 0.0
    assert result.evidence["service_parity_abs_error_nodeh"] <= 1e-12
    assert result.evidence["terminal_backlog_nodeh"] == 0.0
    assert result.evidence["max_no_anticipation_violation_nodeh"] <= 1e-12
    assert result.evidence["max_deadline_shortfall_nodeh"] <= 1e-12


def test_v5_physical_label_and_dictionary_order_invariance() -> None:
    arrivals = _empty(); arrivals[("C2", 2)][7] = 1.7
    capacities = {"A": 0.5, "B": 1.0, "C": 2.0, "D": 0.75}
    baseline = _physical(build_reference_schedule_v5(arrivals, capacities))
    relabel = {"A": "z", "B": "y", "C": "x", "D": "w"}
    renamed = {relabel[key]: value for key, value in reversed(tuple(capacities.items()))}
    reverse = {value: key for key, value in relabel.items()}
    renamed_physical = _physical(build_reference_schedule_v5(arrivals, renamed), reverse)
    assert max(abs(baseline[key] - renamed_physical[key]) for key in baseline) <= 1e-12
    items = list(capacities.items()); random.Random(20260830).shuffle(items)
    shuffled = dict(items)
    shuffled_physical = _physical(build_reference_schedule_v5(arrivals, shuffled))
    assert max(abs(baseline[key] - shuffled_physical[key]) for key in baseline) <= 1e-12


def test_v5_reference_scheduler_firewall_counters_are_zero() -> None:
    result = build_reference_schedule_v5(_empty(), {"R1": 1.0})
    for key in ("grid_information_reads", "MESS_information_reads", "J_I_reads", "H_reads", "OpenDSS_calls", "optimized_result_reads", "AIDC_label_ordering_influence", "Rack_label_ordering_influence"):
        assert result.evidence[key] == 0
