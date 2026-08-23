import json
from pathlib import Path


CONTRACT = (
    Path(__file__).parents[1]
    / "pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
)


def test_full_month_contract_covers_all_90_calendar_days() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    feb, mar = contract["periods"]

    assert feb["calendar_start"] == "2025-02-01"
    assert feb["days"] == 28
    assert feb["global_issue_first"] == 31 * 288
    assert feb["global_issue_last"] == (31 + 28) * 288 - 1
    assert feb["expected_commit_markers"] == 28 * 8 * 288

    assert mar["calendar_start"] == "2025-03-01"
    assert mar["days"] == 31
    assert mar["global_issue_first"] == (31 + 28) * 288
    assert mar["global_issue_last"] == 90 * 288 - 1
    assert mar["expected_commit_markers"] == 31 * 8 * 288

    assert 31 * 8 * 288 + sum(
        period["expected_commit_markers"] for period in contract["periods"]
    ) == 90 * 8 * 288 == 207360


def test_generated_and_reused_mobility_ranges_cover_each_full_month() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for period in contract["periods"]:
        expected = set(
            range(period["global_issue_first"], period["global_issue_last"] + 1)
        )
        reusable = {
            issue
            for row in period["reused_mobility_expected_ranges"]
            for issue in range(row["first"], row["last"] + 1)
        }
        generated = {
            issue
            for row in period["mobility_generation_chunks"]
            for issue in range(row["start"], row["start"] + row["count"])
        }
        assert expected <= reusable | generated


def test_power_generation_ranges_cover_scored_range_and_padding() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for period in contract["periods"]:
        generated = {
            issue
            for start in period["power_generation_starts"]
            for issue in range(start, start + 2304)
        }
        assert generated == set(
            range(
                period["global_issue_first"],
                period["source_padding_issue_last"] + 1,
            )
        )
