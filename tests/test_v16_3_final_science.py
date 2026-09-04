import json
from pathlib import Path

from dayahead.authority import sha256_file


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dayahead/artifacts/v16_3_final"


def test_frozen_shadow_authority_bytes_are_unchanged():
    assert sha256_file(ROOT/"dayahead/v16_3_shadow.py")=="dbbe9ee0b318f02247469501db32d68fb2f51e4335a9380c08e89fa38763da78"


def test_final_eligibility_is_data_only_and_frozen():
    value=json.loads((OUT/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json").read_text(encoding="utf-8"))
    assert value["included_day_count"]==54
    assert value["excluded_day_count"]==2
    assert value["optimization_result_reads_for_eligibility"]==0
    assert value["AC_result_reads_for_eligibility"]==0
    assert value["benchmark_days"]=={"MAY_PRIMARY":"2025-05-02","JUNE_REPLICATION":"2025-06-02"}


def test_final_d1_cache_manifest_preserves_reference_failures():
    value=json.loads((OUT/"V16_3_FINAL_D1_AC_CACHE_MANIFEST.json").read_text(encoding="utf-8"))
    assert value["prepared_day_count"]==41
    assert value["frozen_reference_failure_day_count"]==13
    assert value["file_count"]==82
    assert all(row["clipping_calls"]==0 and row["redistribution_calls"]==0 for row in value["frozen_reference_failures"])


def test_execution_contract_precedes_science_and_freezes_four_cases():
    value=json.loads((OUT/"V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json").read_text(encoding="utf-8"))
    assert value["authority_commit"]=="2246063175977f152f3ac8df8f65a861cc7bbd22"
    assert tuple(value["cases"]) == ("B0","B1","B2","B3")
    assert value["solver"]["parameters"]["Seed"]==20260828
    assert value["benders"]["gamma_crit"]==.98
    assert value["no_tuning_counters_at_contract_freeze"]["OpenDSS_calls_inside_Benders"]==0
