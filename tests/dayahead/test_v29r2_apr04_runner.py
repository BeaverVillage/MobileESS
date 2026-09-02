from __future__ import annotations

import inspect

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
