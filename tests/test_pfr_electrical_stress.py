import pytest

from pfr.electrical_stress import (
    ElectricalStress,
    stress_from_extrema,
    trajectory_summary,
    voltage_stress_from_extrema,
)


def test_voltage_stress_is_normalized_to_hard_limits() -> None:
    assert voltage_stress_from_extrema(1.0, 1.0) == pytest.approx(0.0)
    assert voltage_stress_from_extrema(0.975, 1.025) == pytest.approx(0.5)
    assert voltage_stress_from_extrema(0.95, 1.05) == pytest.approx(1.0)
    assert voltage_stress_from_extrema(0.94, 1.02) > 1.0


def test_worst_stress_keeps_physical_components_separate() -> None:
    stress = stress_from_extrema(
        minimum_voltage_pu=0.97,
        maximum_voltage_pu=1.01,
        maximum_line_loading_fraction=0.84,
        maximum_transformer_loading_fraction=0.71,
    )
    assert stress.voltage == pytest.approx(0.6)
    assert stress.worst == pytest.approx(0.84)
    assert stress.as_dict()["worst_electrical_stress_pu"] == pytest.approx(0.84)


def test_trajectory_summary_matches_frozen_lexicographic_exposure() -> None:
    summary = trajectory_summary(
        (
            ElectricalStress(0.2, 0.4, 0.3),
            ElectricalStress(0.8, 0.5, 0.6),
        ),
        step_hours=1.0 / 12.0,
    )
    assert summary["worst_electrical_stress_pu"] == pytest.approx(0.8)
    assert summary["electrical_stress_exposure_pu_hours"] == pytest.approx(0.1)


def test_invalid_extrema_fail_closed() -> None:
    with pytest.raises(ValueError):
        voltage_stress_from_extrema(1.02, 0.98)
