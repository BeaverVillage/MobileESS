from pfr.tools.analyze_january_daily import bootstrap_mean_ci, lag1_autocorrelation


def test_constant_paired_difference_is_deterministic_iid() -> None:
    result = bootstrap_mean_ci([2.0] * 31)

    assert result["bootstrap_mode"] == "PAIRED_DAY_IID"
    assert result["mean_difference"] == 2.0
    assert result["ci95_lower"] == 2.0
    assert result["ci95_upper"] == 2.0


def test_material_serial_dependence_selects_moving_block() -> None:
    values = [float(index) for index in range(31)]

    assert abs(lag1_autocorrelation(values)) >= 0.30
    first = bootstrap_mean_ci(values)
    second = bootstrap_mean_ci(values)

    assert first == second
    assert first["bootstrap_mode"] == "CIRCULAR_MOVING_BLOCK"
