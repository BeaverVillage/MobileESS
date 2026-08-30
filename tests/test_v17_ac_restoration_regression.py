from dayahead.v17_ac_restoration_regression_fixture import run_fixture


def test_non_scientific_local_ac_cut_restoration_regression() -> None:
    result = run_fixture()
    assert result["initial"]["fresh_ac_status"] == "FAIL"
    assert result["cut"]["type"] == "LOCAL_VIOLATION_SPECIFIC_LINEAR_CUT"
    assert result["optimization_call_count"] == 2
    assert result["fresh_ac_call_count"] == 2
    assert result["restored"]["fresh_ac_status"] == "PASS"
    assert result["science_parameter_changes"] == 0
    assert result["status"] == "PASS_FAIL_CUT_REOPTIMIZE_PASS"
