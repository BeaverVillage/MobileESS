import inspect
import json
from pathlib import Path

import pytest

from dayahead.aidc_boundary_v16_1 import (
    LEGACY_RACK_POWER_CAP_ACTIVE_CONSTRAINT_CALL_COUNT,
    REFERENCE_AUTHORITY_ID,
    aidc_power_spatial_weights,
    audit_boundary_separation,
    build_reference_schedule_v3,
)
from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.aidc_rack_mapping import FrozenRackAuthority, RackCapacity
from dayahead.authority import sha256_file
from dayahead.result_schema import COMPATIBILITY_ONLY_DATASETS_V16_1, PAPER_FACING_DATASETS_V16_1


ROOT = Path(__file__).resolve().parents[2]
V16 = ROOT / "dayahead" / "artifacts" / "v16"
V16_1 = ROOT / "dayahead" / "artifacts" / "v16_1"


def _authority_fixture() -> FrozenRackAuthority:
    racks = tuple(
        RackCapacity(
            f"AIDC{index // 4 + 1:02d}_LP{index % 4 + 1:02d}",
            f"AIDC{index // 4 + 1:02d}",
            f"IDC{index // 4 + 1:02d}",
            index % 4 + 1,
            100.0,
            999.0,
        )
        for index in range(48)
    )
    return FrozenRackAuthority("fixture", "0" * 64, racks, (1 / 48,) * 48, (1 / 48,) * 48)


def test_v16_1_authority_preserves_legacy_bytes_and_retires_absolute_semantics() -> None:
    authority = json.loads((V16_1 / "V16_1_AIDC_POWER_BOUNDARY_REFREEZE_AUTHORITY.json").read_text(encoding="utf-8"))
    retired = authority["legacy_power_capacity_retirement"]
    assert authority["authority_id"] == "V16_1_DA_AIDC_ICPS_BOUNDARYSEP"
    assert retired["required_active_hard_constraint_call_count"] == 0
    assert retired["absolute_kw_capacity_semantics"].startswith("RETIRED")
    assert sha256_file(Path(retired["source_path"])) == retired["source_sha256"]
    assert authority["retained_virtual_power_spatialization"]["authority_statement"].endswith(
        "Their absolute kW capacity semantics are retired."
    )
    assert sum(authority["retained_virtual_power_spatialization"]["aidc_weights"].values()) == pytest.approx(1.0)


def test_v3_scheduler_is_gpu_only_grid_mess_blind_and_kappa_exact() -> None:
    authority = _authority_fixture()
    racks = tuple(rack.rack_id for rack in authority.racks)
    gpu_caps = {rack.rack_id: rack.deliverable_gpu_capacity for rack in authority.racks}
    arrivals = {"N01_R00": (0.1,) + (0.0,) * 95}
    source = inspect.getsource(build_reference_schedule_v3)
    assert "it_power_cap" not in source and "rack_power_cap" not in source
    reference = build_reference_schedule_v3(racks, gpu_caps, arrivals)
    assert reference.authority_id == REFERENCE_AUTHORITY_ID
    assert reference.grid_signal_read_count == reference.mess_signal_read_count == 0
    assert reference.legacy_rack_power_cap_active_constraint_call_count == 0
    assert reference.flexible_power_kw[0][0] == pytest.approx(KAPPA_KW_PER_ACTIVE_H100_NODE[1] * 0.1 / 0.25)
    assert reference.flexible_gpu[0][0] == pytest.approx(4.0 * 0.1 / 0.25)


def test_system_first_power_reconstruction_gpu_caps_and_pue_once() -> None:
    authority = _authority_fixture()
    racks = tuple(rack.rack_id for rack in authority.racks)
    reference = build_reference_schedule_v3(
        racks,
        {rack.rack_id: rack.deliverable_gpu_capacity for rack in authority.racks},
        {"N01_R00": (0.1,) + (0.0,) * 95},
    )
    audit = audit_boundary_separation(authority, reference, (100.0,) * 96, (10.0,) * 96)
    assert audit["status"] == "PASS"
    assert audit["P_RES_SYS_kw"]["negative_slot_count"] == 0
    assert audit["G_RES_SYS"]["negative_slot_count"] == 0
    assert audit["power_reconstruction_max_abs_error_kw"] <= 1e-12
    assert audit["rack_gpu_cap_violation_count"] == 0
    assert audit["pue_application_count"] == 1
    assert audit["pue_reconstruction_max_abs_error_kw"] <= 1e-12
    assert audit["legacy_rack_power_cap_active_constraint_call_count"] == 0
    assert LEGACY_RACK_POWER_CAP_ACTIVE_CONSTRAINT_CALL_COUNT == 0
    aidcs, weights = aidc_power_spatial_weights(authority)
    assert len(aidcs) == 12 and sum(weights) == pytest.approx(1.0)


def test_v16_1_paper_schema_isolated_from_legacy_rack_total_power() -> None:
    assert PAPER_FACING_DATASETS_V16_1 == {
        "AIDC_BASE_IT_POWER_KW",
        "AIDC_TOTAL_IT_POWER_KW",
        "AIDC_RACK_FLEX_POWER_KW",
        "AIDC_RACK_GPU",
        "AIDC_RACK_FLEX_GPU",
    }
    assert COMPATIBILITY_ONLY_DATASETS_V16_1 == {"AIDC_RACK_POWER_KW"}


def test_april_v16_1_artifacts_are_v3_byte_identical_and_campaign_locked() -> None:
    report_path = V16_1 / "C7_FULL_IEEE123_REPORT_V16_1.json"
    if not report_path.exists():
        pytest.skip("April full-IEEE123 V16.1 revalidation artifact not materialized yet")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    g10 = json.loads((V16_1 / "G10_V16_1_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS_FULL_IEEE123_V16_1"
    assert report["reference_b0_b2_bytes_identical"]
    assert report["reference_b0_b2_sha_identical"]
    assert report["legacy_rack_power_cap_active_constraint_call_count"] == 0
    assert report["service_parity_residual"] == 0.0
    assert report["reference_delta"]["pue_application_count"] == 1
    assert report["reference_delta"]["power_reconstruction_max_abs_error_kw"] <= 1e-9
    assert report["rack_gpu_cap_violation_count"] == 0
    assert report["full_ieee123_aidc_pcc_mapping"]["aidc_count"] == 12
    assert report["full_ieee123_aidc_pcc_mapping"]["all_hosts_present_in_compiled_full_ieee123"]
    assert report["full_ieee123_aidc_pcc_mapping"]["mapping_rated_kw_active_constraint_call_count"] == 0
    assert report["may_loader_access_count"] == report["june_loader_access_count"] == 0
    assert g10["status"] == "PASS"
    assert g10["g12_call_count"] == g10["g13_call_count"] == g10["g14_call_count"] == g10["c12_call_count"] == 0
    assert g10["may_loader_access_count"] == g10["june_loader_access_count"] == 0


def test_g11_fails_closed_without_a_complete_april_aemo_vintage() -> None:
    report = json.loads((V16_1 / "G11_V16_1_FULL_IEEE123_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "FAIL_AEMO_COMPLETE_VINTAGE_NOT_FOUND"
    assert report["stop_rule_applied"] is True
    assert report["input_authority_gate"]["demand_complete_vintage_count_for_operating_day"] == 0
    assert report["input_authority_gate"]["pv_complete_vintage_count_for_operating_day"] == 0
    assert report["prohibited_substitutions_rejected"]["per_slot_vintage_mixing_used"] is False
    assert report["prohibited_substitutions_rejected"]["actual_used_as_forecast"] is False
    assert report["g11_execution"]["reduced_star_used_as_final_evidence"] is False
    assert report["g11_execution"]["final_full_ieee123_grid_lp_count"] == 0
    assert all(value == 0 for value in report["downstream_call_counts"].values())
    assert report["firewall"]["may_loader_access_count"] == 0
    assert report["firewall"]["june_loader_access_count"] == 0
