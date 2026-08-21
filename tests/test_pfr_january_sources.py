from pathlib import Path

import pandas as pd

from pfr.tools.build_january_job_cohort import materialize
from pfr.tools.run_pfr_matrix import _runtime_initial_state


def test_january_cohort_uses_source_microsecond_timestamps_without_shift() -> None:
    frame = pd.DataFrame(
        {
            "job_uid": ["before", "jan", "feb"],
            "origin_IDC_id": ["IDC01"] * 3,
            "arrival_timestamp_ns": [
                1735689599000000,
                1735689601000000,
                1738368000000000,
            ],
            "latest_start_timestamp_ns": [
                1735689600000000,
                1735689901000000,
                1738368300000000,
            ],
            "latest_completion_timestamp_ns": [
                1735690200000000,
                1735690501000000,
                1738368900000000,
            ],
            "requested_gpu": [8.0, 8.0, 8.0],
            "job_power_prefreeze_authorized": [True] * 3,
            "scheduler_wan_valid": [True] * 3,
            "rack_power_valid": [True] * 3,
        }
    )

    cohort, audit = materialize(frame)

    assert cohort["job_uid"].tolist() == ["jan"]
    assert cohort["arrival_step"].tolist() == [0]
    assert audit["synthetic_date_shift"] is False


def test_runtime_accepts_v13_2_daily_canonical_pre() -> None:
    pre = {
        "canonical_pre_sha256": "abc",
        "canonical_pre": {
            "mess_energy_kwh": [760.0] * 4,
            "mess_locations": ["STA09", "IDC12", "STA07", "STA11"],
            "ai_queue_empty": True,
            "ai_running_empty": True,
            "wan_inventory_empty": True,
            "wan_pipeline_empty": True,
            "active_slow_plan": None,
        },
    }

    state = _runtime_initial_state(pre, 288)

    assert state.issue == 288
    assert state.state_sha256 == "abc"
    assert state.mess_energy_kwh == {f"MESS{i:02d}": 760.0 for i in range(1, 5)}
    assert state.mess_location["MESS01"] == "STA09"
