"""Targeted contract tests for the V35R3G forensic artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from dayahead.v35r3g.audit import (
    h100_partition,
    list_has_values,
    parse_formatted_energy,
    sharing_classification,
    spatial_classification,
)
from dayahead.v35r3g.contracts import (
    ARCHIVE_SHA256,
    BRANCH,
    CONDITIONAL_ARTIFACTS,
    HIGHEST_AUTHORITY,
    MODELABILITY,
    PARENT_HEAD,
    PHYSICAL_BOUNDARY,
    PRIMARY_CLASSIFICATION,
    REQUIRED_ARTIFACTS,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v35r3g_kestrel_h100_operational_energy_forensic"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("gpu-h100", True),
        ("debug,gpu-h100", True),
        ("GPU-H100-TEST", True),
        ("gpu-a100", False),
        (None, False),
    ],
)
def test_frozen_h100_identity(value, expected):
    assert h100_partition(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ([], False), (["node-a"], True), ("[]", False), ("job-a", True)],
)
def test_sharing_list_semantics(value, expected):
    assert list_has_values(value) is expected


def test_sharing_three_way_contract():
    frame = pd.DataFrame(
        {
            "shared_job_count": [None, 2, 0],
            "nodes_shared": [[], [], []],
            "jobs_shared": [[], ["x"], []],
        }
    )
    assert sharing_classification(frame).tolist() == [
        "EXCLUSIVE_CONFIRMED",
        "SHARED_CONFIRMED",
        "SHARING_UNKNOWN",
    ]


def test_spatial_contract_keeps_node_and_gpu_counts_distinct():
    frame = pd.DataFrame(
        {
            "shared_job_count": [None, None, 1, 0],
            "nodes_shared": [[], [], ["n"], []],
            "jobs_shared": [[], [], ["j"], []],
            "nodes_req": [1, 1, 1, 1],
            "nodes_used": [1, 1, 1, 1],
            "gpu_nodes_occupied": [1, 1, 1, 1],
            "gpus_requested": [4, 2, 4, 4],
        }
    )
    h100 = pd.Series([True] * 4)
    assert spatial_classification(frame, h100).tolist() == [
        "FULL_NODE_EXCLUSIVE",
        "PARTIAL_EXCLUSIVE",
        "SHARED",
        "UNKNOWN_SHARING",
    ]


def test_formatted_energy_parser_and_units():
    parsed = parse_formatted_energy(pd.Series(["1", "1K", "2.5M", "bad", None]))
    assert parsed.iloc[:3].tolist() == [1.0, 1_000.0, 2_500_000.0]
    assert parsed.iloc[3:].isna().all()


def test_exact_lineage_and_isolation():
    start = load("V35R3G_START_STATE.json")
    assert start["parent_HEAD_expected"] == PARENT_HEAD
    assert start["parent_HEAD_actual"] == PARENT_HEAD
    assert start["branch_actual"] == BRANCH == git("branch", "--show-current")
    assert git("merge-base", "HEAD", PARENT_HEAD) == PARENT_HEAD
    assert start["isolated_worktree"] is True


def test_diff_scope_contains_only_forensic_outputs():
    changed = git("diff", "--name-only", PARENT_HEAD).splitlines()
    changed += git("ls-files", "--others", "--exclude-standard").splitlines()
    allowed = ("dayahead/v35r3g/", "dayahead/artifacts/v35r3g_", "tests/v35r3g/")
    assert changed
    assert all(path.replace("\\", "/").startswith(allowed) for path in changed)
    assert not any("mess" in path.casefold() for path in changed)


def test_source_authority_exact_and_immutable():
    source = load("V35R3G_SOURCE_AUTHORITY.json")
    assert source["archive_SHA256_expected"] == ARCHIVE_SHA256
    assert source["archive_SHA256_actual"] == ARCHIVE_SHA256
    assert source["ZIP_structure"] == "PASS"
    assert source["ZIP_CRC"] == "NOT_RESCANNED_SHA256_PRIMARY"
    assert source["redownloads"] == source["source_mutations"] == 0
    assert source["primary_source_is_transformed_copy"] is False


def test_row_granularity_and_array_semantics():
    audit = load("V35R3G_ROW_GRANULARITY_AUDIT.json")
    assert audit["rows"] == 10_559_977
    assert audit["unique_id_count"] == 10_559_977
    assert audit["duplicate_id_extra_rows"] == 0
    assert audit["job_id_array_pos_duplicate_extra_rows"] == 0
    assert audit["array_element_rows"] > 0
    assert audit["step_suffix_rows"] == 0
    assert "distinct array elements" in audit["energy_interpretation"]


def test_energy_field_discovery_and_counts():
    census = load("V35R3G_ENERGY_FIELD_CENSUS.json")
    discovered = census["energy_power_columns_discovered"]
    assert "consumed_energy_raw_joules" in discovered
    assert "consumed_energy_raw_watt_hours" in discovered
    raw = census["fields"]["consumed_energy_raw_joules"]
    assert raw["positive_count"] == 7_064_950
    assert raw["zero_count"] == 2_005_097
    assert raw["non_null_count"] == 9_070_047
    assert raw["negative_count"] == raw["nonfinite_count"] == 0


def test_joule_watt_hour_reconciliation():
    unit = load("V35R3G_ENERGY_UNIT_RECONCILIATION.json")
    assert unit["classification"] == "PASS_DERIVED_UNIT_CONVERSION"
    assert unit["comparable_rows"] == 9_070_047
    assert unit["mismatch_count"] == 0
    assert unit["maximum_relative_error"] < 1e-12
    assert unit["independent_sensor_count"] == 1
    assert unit["watt_hours_is_derived"] is True


def test_zero_missing_and_invalid_fail_closed():
    validity = load("V35R3G_ENERGY_VALIDITY_CONTRACT.json")
    assert validity["H100_counts"]["positive"] == 0
    assert validity["H100_counts"]["zero"] + validity["H100_counts"]["missing"] > 0
    assert validity["authorized_H100_positive_valid_rows"] == 0
    assert "not interpreted as physical zero" in validity["ENERGY_ZERO_OR_MISSING"]


def test_physical_boundary_never_assumes_components():
    boundary = load("V35R3G_CONSUMED_ENERGY_PHYSICAL_BOUNDARY.json")
    assert boundary["ConsumedEnergyRaw_physical_boundary"] == PHYSICAL_BOUNDARY
    for field in (
        "includes_GPU_energy",
        "includes_CPU_energy",
        "includes_memory",
        "includes_fans_baseboard_network",
        "whole_node_AC_or_DC_input",
        "idle_or_base_contribution",
    ):
        assert boundary[field] == "UNKNOWN"
    assert boundary["H100_GPU_energy_name_authorized"] is False
    assert boundary["whole_node_IT_energy_name_authorized"] is False


def test_documentation_lineage_recorded():
    source = load("V35R3G_SOURCE_AUTHORITY.json")
    assert len(source["documentation_files"]) >= 4
    assert len(source["external_documentation"]) == 4
    assert all(item["url"].startswith("https://") for item in source["external_documentation"])
    assert all(item["access_date"] == "2026-09-03" for item in source["external_documentation"])


def test_attribution_and_shared_conservation_fail_closed():
    attribution = load("V35R3G_SLURM_ENERGY_ATTRIBUTION_CONTRACT.json")
    conservation = load("V35R3G_SHARED_ENERGY_CONSERVATION.json")
    assert attribution["shared_or_co_resident_jobs"] == "UNSUPPORTED"
    assert attribution["SHARED_JOB_ENERGY_ATTRIBUTION"] == "UNSUPPORTED"
    assert conservation["classification"] == "SHARED_ENERGY_DOUBLE_COUNT_RISK"
    assert conservation["conservation_provable"] is False
    assert not any(conservation[key] for key in ("equal_split", "GPU_fraction_split", "runtime_split", "node_fraction_split"))


def test_four_gpu_full_node_authority_and_requested_used_rule():
    contract = load("V35R3G_FULL_NODE_H100_CONTRACT.json")
    assert contract["GPUs_per_normal_H100_node"] == 4
    assert "nodes_req=nodes_used=gpu_nodes_occupied" in contract["FULL_NODE_EXCLUSIVE_H100"]
    assert contract["denominator"].startswith("nodes_used")


def test_global_and_preissue_h100_positive_energy_are_empty():
    global_census = load("V35R3G_GLOBAL_ENERGY_CENSUS.json")["cohorts"]
    preissue = load("V35R3G_PREISSUE_CAUSAL_ENERGY_CENSUS.json")["cohorts"]
    assert global_census["H100_CONFIRMED"]["jobs"] == 1_332_564
    assert global_census["H100_POSITIVE_ENERGY"]["jobs"] == 0
    assert preissue["PREISSUE_H100_POSITIVE_ENERGY"]["jobs"] == 0
    assert preissue["PREISSUE_FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY"]["jobs"] == 0


def test_all_fixed_recency_windows_are_reported_and_empty_of_positive_energy():
    frame = pd.read_csv(ARTIFACTS / "V35R3G_RECENCY_COVERAGE.csv")
    assert frame["window"].tolist() == ["30D", "60D", "120D", "180D", "365D", "ALL"]
    assert frame["positive_energy_jobs"].eq(0).all()
    assert frame["full_node_exclusive_positive_energy_jobs"].eq(0).all()


def test_spatial_temporal_matrix_is_complete():
    matrix = pd.read_csv(ARTIFACTS / "V35R3G_SPATIAL_TEMPORAL_COVERAGE_MATRIX.csv")
    assert len(matrix) == 7 * 4
    assert set(matrix["window"]) == {
        "GLOBAL", "PREISSUE_ALL", "PREISSUE_365D", "PREISSUE_180D",
        "PREISSUE_120D", "PREISSUE_60D", "PREISSUE_30D",
    }
    assert matrix["positive_energy_jobs"].eq(0).all()
    assert matrix["usable_label_jobs"].eq(0).all()


def test_historical_label_and_future_query_firewall():
    firewall = load("V35R3G_FUTURE_POWER_MODEL_CAUSAL_FIREWALL.json")
    features = load("V35R3G_FUTURE_POWER_QUERY_FEATURES.json")
    assert firewall["preissue_rule"].endswith("2025-03-31T08:00:00+00:00")
    assert firewall["Apr01_consumed_energy_reads"] == 0
    assert firewall["Apr01_realized_runtime_reads"] == 0
    assert firewall["Apr01_future_end_reads"] == 0
    assert features["target_available"] is False
    forbidden = " ".join(features["forbidden"])
    assert all(token in forbidden for token in ("end_time", "wallclock_used", "consumed_energy"))


def test_apr01_feature_only_coverage_counts():
    coverage = load("V35R3G_APR01_FEATURE_DOMAIN_COVERAGE.json")
    expected = {
        "Apr01_running": 243,
        "Apr01_temporal_pending": 339,
        "strict_current_F0_full_node": 3,
        "PARTIAL_shared_temporal": 336,
    }
    assert {name: item["rows"] for name, item in coverage["cohorts"].items()} == expected
    assert all(item["covered_rows"] == 0 for item in coverage["cohorts"].values())
    columns = coverage["column_projection_audit"]
    assert columns["Apr01_consumed_energy_columns_read"] == []
    assert columns["Apr01_realized_runtime_columns_read"] == []
    assert columns["Apr01_future_end_columns_read"] == []


def test_modelability_and_authority_decisions():
    model = load("V35R3G_POWER_MODELABILITY_AUDIT.json")
    authority = load("V35R3G_AUTHORITY_DECISION.json")
    decision = load("V35R3G_NEXT_STEP_DECISION.json")
    assert model["classification"] == MODELABILITY
    assert model["model_trained"] is False
    assert authority["highest_energy_authority"] == HIGHEST_AUTHORITY
    assert authority["primary_classification"] == PRIMARY_CLASSIFICATION
    assert decision["CAUSAL_H100_POWER_MODEL_NEXT"] == "NO"
    assert decision["SHARED_H100_POWER_NEXT"] == "DEFER"
    assert decision["DATASET312_AUTHORITY_CHANGED"] == "NO"
    assert decision["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"


def test_no_conditional_power_or_label_artifacts():
    assert all(not (ARTIFACTS / name).exists() for name in CONDITIONAL_ARTIFACTS)


def test_compute_and_scope_firewalls():
    compute = load("V35R3G_COMPUTE_ACCOUNTING.json")
    isolation = load("V35R3G_ISOLATION_AUDIT.json")
    assert compute["source_scans"] == 2
    assert compute["normalized_rows"] == 10_559_977
    assert compute["XGBoost"] is compute["Gurobi"] is compute["GPU_training"] is False
    for field in (
        "XGBoost_fit_calls", "Gurobi_calls", "MESS_runs", "node_packing_runs",
        "grid_reads", "Fresh_reads", "Planning_reads", "Apr02_plus_result_reads",
        "May_result_reads", "Dataset312_scaling_or_label_reads",
    ):
        assert isolation[field] == 0
    assert isolation["push"] is isolation["merge"] is False


def test_required_unconditional_artifacts_and_lineage():
    assert len(REQUIRED_ARTIFACTS) == 36
    assert all((ARTIFACTS / name).is_file() for name in REQUIRED_ARTIFACTS)
    for path in ARTIFACTS.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["source_archive_sha256"] == ARCHIVE_SHA256
        assert payload["source_code_commit"]


def test_final_review_has_exact_numbered_and_question_sets():
    review = load("V35R3G_FINAL_REVIEW.json")
    assert set(review["numbered_report"]) == {str(index) for index in range(1, 81)}
    assert set(review["questions"]) == {f"Q{index}" for index in range(1, 23)}
    assert review["numbered_report"]["67"] == HIGHEST_AUTHORITY
    assert review["numbered_report"]["68"] == PRIMARY_CLASSIFICATION
    assert review["numbered_report"]["71"] == "NO"
    assert review["numbered_report"]["72"] == "NO"
