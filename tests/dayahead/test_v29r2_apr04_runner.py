from __future__ import annotations

import inspect
import csv

from dayahead.v28r2.variable_registry import build_resource_model
from dayahead.v29r2 import apr04_runner


def test_resource_model_has_separate_backward_compatible_trust_arguments() -> None:
    parameters = inspect.signature(build_resource_model).parameters
    assert "rho" in parameters and "rho_aidc" in parameters and "rho_mess" in parameters
    assert parameters["rho"].default == .1
    assert parameters["rho_aidc"].default is None
    assert parameters["rho_mess"].default is None


def test_apr04_runner_has_hard_freeze_and_actual_firewalls() -> None:
    source = inspect.getsource(apr04_runner.run_apr04)
    assert "require_dev_freeze(repo)" in source
    assert source.index("_freeze_schedules") < source.index("materialize_actual_workload")
    assert "actual_optimizer_calls\": 0" in source
    assert "DAYAHEAD_NOREGRET" not in source
    assert apr04_runner.DAY == "2025-04-04"


def test_v29_baseline_comparison_normalizes_heterogeneous_csv_schemas(tmp_path) -> None:
    root = tmp_path / "dayahead/artifacts/v29_grid_responsive_aidc"
    root.mkdir(parents=True)
    fixtures = {
        "V29_4DAY_OBJECTIVE_RESULTS.csv": (
            ("day", "case", "planning_objective"),
            (apr04_runner.DAY, "B2", "0.52"),
        ),
        "V29_4DAY_OPENDSS_RESULTS.csv": (
            ("day", "case", "rho_max_AC", "critical_line"),
            (apr04_runner.DAY, "B2", "0.56", "L1"),
        ),
    }
    for name, records in fixtures.items():
        with (root / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerows(records)
    rows = apr04_runner._read_v29_baseline(tmp_path)
    assert len(rows) == 2
    assert rows[0].keys() == rows[1].keys()
    assert rows[0]["planning_objective"] == "0.52"
    assert rows[0]["rho_max_AC"] == ""
    assert rows[1]["planning_objective"] == ""
    assert rows[1]["rho_max_AC"] == "0.56"
