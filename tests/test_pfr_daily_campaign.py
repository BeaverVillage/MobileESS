import pytest

from pfr.tools.run_pfr_daily_campaign import day_specs


def test_january_day_specs_use_global_fixed_aest_issue_axis() -> None:
    specs = day_specs(1, 7)

    assert len(specs) == 7
    assert specs[0].calendar_date == "2025-01-01"
    assert specs[0].start_issue == 0
    assert specs[-1].calendar_date == "2025-01-07"
    assert specs[-1].start_issue == 6 * 288
    assert specs[-1].candidate_id == "JAN2025_DAY07"


def test_january_day_specs_reject_non_january_range() -> None:
    with pytest.raises(ValueError):
        day_specs(0, 7)
    with pytest.raises(ValueError):
        day_specs(8, 32)
