import json
from pathlib import Path

import pandas as pd

from pfr.tools.run_frozen_rep_week_daily_campaign import payload
from pfr.tools.preflight_january_2025 import (
    validate_method_contracts,
    validate_workload_scheduler_contract,
)


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


def test_full_month_campaign_has_separate_b0_b7_and_b8_registries() -> None:
    period = json.loads(CONTRACT.read_text(encoding="utf-8"))["periods"][0]
    rows = [
        {"calendar_date": f"2025-02-{day:02d}", "status": "PASS"}
        for day in range(1, 29)
    ]
    main = payload(
        period,
        rows,
        workers=4,
        final=True,
        continue_after_failure=True,
    )
    b8 = payload(
        period,
        rows,
        workers=4,
        final=True,
        continue_after_failure=True,
        supplementary_b8_periodic_5min=True,
    )
    assert main["status"] == "PASS"
    assert main["methods_per_day"] == 8
    assert main["method_ids"] == [f"B{index}" for index in range(8)]
    assert b8["status"] == "PASS"
    assert b8["methods_per_day"] == 1
    assert b8["method_ids"] == ["B8"]


def test_common_b0_b8_contract_is_valid_for_all_month_preflights() -> None:
    result = validate_method_contracts()
    assert result["pass"] is True
    assert result["periodic_methods"] == ["B1", "B2", "B3", "B4", "B5"]
    assert result["supplementary_b8"]["periodic_replan_steps"] == 1
    assert (
        result["supplementary_b8"][
            "same_capabilities_as_b7_except_replan_invocation_timing"
        ]
        is True
    )


def test_preflight_accepts_burst_that_requires_capacity_queue(
    tmp_path: Path,
) -> None:
    jobs_path = tmp_path / "jobs.parquet"
    pd.DataFrame(
        {
            "origin_IDC_id": ["IDC04"] * 300,
            "arrival_step": [1852] * 300,
            "requested_gpu": [1] * 300,
        }
    ).to_parquet(jobs_path, index=False)

    result = validate_workload_scheduler_contract(
        Path(__file__).parents[1], jobs_path
    )

    assert result["pass"] is True
    assert result["maximum_single_job_gpu"] == 1
    assert result["maximum_same_issue_idc_arrival_gpu"] == 300
    assert result["arrival_groups_requiring_capacity_queue"] == 1
    assert result["capacity_queue_required_by_cohort"] is True
