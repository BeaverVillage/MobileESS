import json
from pathlib import Path

from pfr.tools.prepare_full_month_source_view import period
from pfr.tools.run_frozen_rep_week_daily_campaign import payload, period_specs


REPO = Path(__file__).parents[1]
CONTRACT = REPO / "pfr/contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json"


def test_april_contract_has_exact_calendar_and_issue_boundaries() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["status"] == "FROZEN_BEFORE_APRIL_EXECUTION"
    assert len(contract["periods"]) == 1
    april = contract["periods"][0]
    assert april["period_id"] == "APR2025_FULL"
    assert april["calendar_start"] == "2025-04-01"
    assert april["days"] == 30
    assert april["global_issue_first"] == 90 * 288
    assert april["global_issue_last"] == 120 * 288 - 1
    assert april["expected_commit_markers"] == 30 * 8 * 288 == 69120


def test_april_power_and_mobility_ranges_cover_scored_month() -> None:
    april = json.loads(CONTRACT.read_text(encoding="utf-8"))["periods"][0]
    scored = set(range(april["global_issue_first"], april["global_issue_last"] + 1))
    power = {
        issue
        for start in april["power_generation_starts"]
        for issue in range(start, start + 2304)
    }
    generated = {
        issue
        for row in april["mobility_generation_chunks"]
        for issue in range(row["start"], row["start"] + row["count"])
    }
    reused = {
        issue
        for row in april["reused_mobility_expected_ranges"]
        for issue in range(row["first"], row["last"] + 1)
    }
    assert power == set(
        range(april["global_issue_first"], april["source_padding_issue_last"] + 1)
    )
    assert scored <= generated | reused


def test_april_contract_is_selectable_without_changing_february_march() -> None:
    selected, contract, path = period(REPO, "APR2025_FULL", CONTRACT)
    assert path == CONTRACT
    assert contract["schema_version"] == "FROZEN_2025_APRIL_VALIDATION_PERIOD_V1"
    assert selected["global_issue_first"] == 25920


def test_april_daily_specs_and_registries_are_complete() -> None:
    april = json.loads(CONTRACT.read_text(encoding="utf-8"))["periods"][0]
    specs = period_specs(april)
    assert len(specs) == 30
    assert specs[0].calendar_date == "2025-04-01"
    assert specs[-1].calendar_date == "2025-04-30"
    rows = [{"calendar_date": spec.calendar_date, "status": "PASS"} for spec in specs]
    main = payload(
        april, rows, workers=4, final=True, continue_after_failure=True
    )
    b8 = payload(
        april,
        rows,
        workers=4,
        final=True,
        continue_after_failure=True,
        supplementary_b8_periodic_5min=True,
    )
    assert main["method_ids"] == [f"B{index}" for index in range(8)]
    assert b8["method_ids"] == ["B8"]


def test_all_month_runners_bind_same_frozen_calibration() -> None:
    scripts = [
        REPO / "pfr/tools/run_january_to_march_2025_local.sh",
        REPO / "pfr/tools/run_full_february_march_2025_local.sh",
        REPO / "pfr/tools/run_january_2025_b8_periodic5_local.sh",
        REPO / "pfr/tools/run_april_2025_local.sh",
    ]
    assert all("--risk-calibration" in path.read_text(encoding="utf-8") for path in scripts)
    orchestrator = (
        REPO / "pfr/tools/run_january_to_april_2025_local.sh"
    ).read_text(encoding="utf-8")
    assert orchestrator.index("run_january_to_march_2025_local.sh") < orchestrator.index(
        "prepare_april_2025_local.sh"
    ) < orchestrator.index("run_april_2025_local.sh")
