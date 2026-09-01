import json
from pathlib import Path

import pytest

from dayahead.aidc_rack_mapping import (
    FrozenRackAuthority,
    RackCapacity,
    build_capacity_feasible_reference,
    reference_delta_audit,
)
from dayahead.aidc_realized_decomposition import realized_replay
from dayahead.aidc_reference_delta import planning_residual


ARTIFACTS = Path(__file__).resolve().parents[2] / "dayahead" / "artifacts" / "v16"


def test_fixed_priority_reference_fails_closed_instead_of_refitting_spatial_weights():
    racks = tuple(
        RackCapacity(f"AIDC{index // 4 + 1:02d}_LP{index % 4 + 1:02d}", f"AIDC{index // 4 + 1:02d}", f"IDC{index // 4 + 1:02d}", index % 4 + 1, 100.0, 100.0)
        for index in range(48)
    )
    authority = FrozenRackAuthority("fixture", "0" * 64, racks, (1 / 48,) * 48, (1 / 48,) * 48)
    arrivals = {"N01_R00": (0.1,) * 96}
    reference = build_capacity_feasible_reference(authority, arrivals)
    audit = reference_delta_audit(authority, reference, (100.0,) * 96, (1.0,) * 96)
    assert audit["status"] == "FAIL_REFERENCE_DELTA_DECOMPOSITION"
    assert audit["negative_gpu_residual_count"] == 96
    assert audit["mapping_fitting_call_count"] == 0
    assert audit["residual_clipping_call_count"] == 0


def test_negative_reference_and_realized_residuals_are_never_clipped():
    with pytest.raises(ValueError, match="FAIL_REFERENCE_DELTA"):
        planning_residual(((1.0,),) * 96, ((1.0 + 1e-12,),) * 96)
    with pytest.raises(ValueError, match="FAIL_REALIZED"):
        realized_replay((1.0,) * 96, (1.0 + 1e-12,) * 96, ((0.0,),) * 96, (1.0,))


def test_full_ieee123_release_is_exact_but_c12_token_is_not_minted_after_c7_failure():
    release = json.loads((ARTIFACTS / "C7_FULL_IEEE123_AUTHORITY_RELEASE.json").read_text(encoding="utf-8"))
    c7 = json.loads((ARTIFACTS / "C7_FULL_IEEE123_REPORT.json").read_text(encoding="utf-8"))
    c12 = json.loads((ARTIFACTS / "C12_PREPRODUCTION_FREEZE_STATUS.json").read_text(encoding="utf-8"))
    gates = json.loads((ARTIFACTS / "FINAL_G0_G15_GATE_TABLE.json").read_text(encoding="utf-8"))
    rack = json.loads((ARTIFACTS / "AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    assert release["status"] == "PASS"
    assert release["source_archive"]["status"] == "PASS"
    assert all(value["authority_location_type"] == "VERIFIED_ZIP_MEMBER" for value in release["source_files"].values())
    assert release["compiled_full_authority"]["runtime_augmented_bus_count"] == 168
    assert all(value["status"] == "PASS" for value in release["source_files"].values())
    assert rack["rack_count"] == 48 and rack["uniform_replacement_used"] is False
    assert rack["power_weight_sum"] == pytest.approx(1.0)
    assert rack["gpu_weight_sum"] == pytest.approx(1.0)
    assert c7["status"] == "FAIL_REFERENCE_DELTA_DECOMPOSITION"
    assert c7["reference_delta"]["gpu_residual_min"] < 0
    assert c7["full_ieee123_monolithic_solve_call_count"] == 0
    assert gates["gates"]["G12"] == "NOT_RUN_BLOCKED_BY_G10"
    assert c12["status"] == "BLOCKED_NOT_MINTED"
    assert c12["production_freeze_token"] is None
    assert c12["token_mint_call_count"] == 0
    assert c12["MAY_PRIMARY_UNLOCK_READY"] is False
    assert c12["may_loader_access_count"] == 0
    assert c12["june_loader_access_count"] == 0
