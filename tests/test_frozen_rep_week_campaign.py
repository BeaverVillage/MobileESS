from pfr.tools.run_frozen_rep_week_daily_campaign import period_specs
from pfr.tools.run_pfr_matrix import _block, _indexed_power_blocks


def test_frozen_rep_week_specs_keep_global_issue_axis() -> None:
    specs = period_specs(
        {
            "period_id": "W07_2025-02-17",
            "calendar_start": "2025-02-17",
            "days": 7,
            "global_issue_first": 13536,
        }
    )

    assert specs[0].calendar_date == "2025-02-17"
    assert specs[0].start_issue == 13536
    assert specs[-1].calendar_date == "2025-02-23"
    assert specs[-1].start_issue == 15264
    assert specs[-1].candidate_id == "W07_2025-02-17_DAY07"


def test_rep_week_power_block_uses_frozen_global_issue_range(tmp_path) -> None:
    block = tmp_path / "power_price" / "block_00_13536_14111"
    block.mkdir(parents=True)
    _indexed_power_blocks.cache_clear()

    assert _block(tmp_path, 13536) == block
    assert _block(tmp_path, 14111) == block
