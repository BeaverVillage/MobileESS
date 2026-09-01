from __future__ import annotations

import inspect
import json
from pathlib import Path

from dayahead import final_science_protocol_v16_3 as protocol
from dayahead import run_v16_3_execution_contract as runner


ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json"


def test_contract_is_frozen_before_scientific_access() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["status"] == "FROZEN_COMMITTED_BEFORE_MAY_JUNE_SCIENTIFIC_ACCESS"
    assert payload["authority_commit"] == protocol.AUTHORITY_COMMIT
    assert payload["data_access_at_contract_creation"] == {
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
        "may_result_inspection_count": 0,
        "june_result_inspection_count": 0,
    }
    assert payload["protocol_mutation_after_commit_allowed"] is False


def test_case_objective_solver_and_decomposition_are_predeclared() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert set(payload["cases"]) == {"B0", "B1", "B2", "B3"}
    assert payload["frozen_parameters"]["objective"] == "MINIMUM_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING"
    assert payload["solver"]["version"] == "13.0.3"
    assert payload["solver"]["parameters"]["Threads"] == 1
    assert payload["solver"]["parameters"]["Seed"] == 20260828
    assert payload["solver"]["parameters"]["MIPGap"] == 1e-3
    assert payload["benders"]["gamma_crit"] == 0.98
    assert payload["benders"]["benchmark_day_rule"] == "LEXICOGRAPHICALLY_FIRST_ELIGIBLE_DAY_IN_EACH_PERIOD"


def test_eligibility_cannot_read_or_exclude_by_result() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["eligibility"]["result_dependent_exclusion_allowed"] is False
    assert payload["evaluation_periods"]["JUNE_REPLICATION"]["end"] == "2025-06-25"
    source = inspect.getsource(runner.execute)
    assert "read_parquet" not in source and "zipfile" not in source
    assert "optimize" not in source.lower() and "opendss" not in source.lower()


def test_no_tuning_counters_are_all_zero() -> None:
    assert protocol.NO_TUNING_COUNTERS
    assert set(protocol.NO_TUNING_COUNTERS.values()) == {0}
