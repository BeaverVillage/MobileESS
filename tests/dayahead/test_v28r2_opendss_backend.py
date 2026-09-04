import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.opendss_mapping import aidc_injection_mapping, mess_injection_mapping
from dayahead.v28r2.opendss_results import OpenDSSResult
from dayahead.v28r2.trajectory import FrozenTrajectory


def _payload():
    route = {
        f"MESS{i:02d}": {"service_site": f"IDC{i:02d}"}
        for i in range(1, 5)
    }
    payload = {
        "case": "B3", "planning_pcc_power_kw": np.zeros((96, 12)).tolist(),
        "planning_pcc_reactive_kvar": np.zeros((96, 12)).tolist(),
        "mess_p_kw": np.zeros((96, 4)).tolist(),
        "mess_q_kvar": np.zeros((96, 4)).tolist(), "mess_route_location": route,
    }
    payload["schedule_sha256"] = canonical_sha256(payload)
    return payload


def _result(converged=True):
    return OpenDSSResult(
        day="2025-04-01", namespace="DAYAHEAD", case="B3",
        schedule_sha256="a" * 64,
        node_names=("1.1", "2.2"), node_phases=("A", "B"),
        branch_names=("line.l1", "transformer.tx1"),
        branch_phases=("A", "B"), branch_kinds=("line", "transformer"),
        convergence=np.full(96, converged), voltage_pu=np.ones((96, 2)),
        phase_current_a=np.ones((96, 2)),
        phase_current_loading_pu=np.full((96, 2), .5),
        transformer_total_kva_loading_pu=np.column_stack((
            np.full(96, np.nan), np.full(96, .7),
        )),
        losses_kw_kvar=np.ones((96, 2)), regulator_taps=np.ones((96, 7)),
        capacitor_states=np.zeros((96, 4)), opendss_version="TEST", elapsed_seconds=1.0,
    )


def test_injection_sign_contract():
    assert aidc_injection_mapping(10, 3) == {"load_p_kw": 10.0, "load_q_kvar": 3.0}
    assert mess_injection_mapping(10, 2)["generator_p_kw"] == 10
    assert mess_injection_mapping(-10, -2)["charging_load_p_kw"] == 10
    assert mess_injection_mapping(-10, -2)["generator_p_kw"] == 0


def test_frozen_trajectory_verifies_payload_sha_and_axes():
    payload = _payload()
    trajectory = FrozenTrajectory.from_schedule_payload(
        payload, day="2025-04-01", namespace="DAYAHEAD",
    )
    trajectory.validate()
    assert tuple(trajectory.mess_locations_96x4[0]) == ("IDC01", "IDC02", "IDC03", "IDC04")
    assert len(trajectory.immutable_sha256) == 64
    payload["mess_p_kw"][0][0] = 1.0
    with pytest.raises(RuntimeError, match="SCHEDULE_PAYLOAD_SHA"):
        FrozenTrajectory.from_schedule_payload(payload, day="2025-04-01", namespace="DAYAHEAD")


def test_phase_aware_result_summary_persistence_and_nonconvergence_fail_closed(tmp_path):
    result = _result()
    result.validate()
    assert result.summary["OpenDSS_solve_count"] == 96
    assert result.summary["rho_max_AC"] == .5
    assert result.summary["physical_violation"] is False
    manifest = result.write(tmp_path)
    assert set(manifest["files"]) == {
        "OPENDSS_PHASE_ARRAYS.npz", "OPENDSS_SUMMARY.json", "OPENDSS_VIOLATIONS.json",
    }
    assert (tmp_path / "OPENDSS_OUTPUT_MANIFEST.json").is_file()
    with pytest.raises(RuntimeError, match="NONCONVERGENCE"):
        _result(False).validate()


def test_static_mapping_artifact_has_exact_frozen_axes():
    repo = Path(__file__).resolve().parents[2]
    artifact = json.loads((
        repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_OPENDSS_MAPPING_VALIDATION.json"
    ).read_text(encoding="utf-8"))
    assert artifact["status"] == "PASS"
    assert artifact["pcc_aidc_load_count"] == 12
    assert artifact["pcc_mess_discharge_element_count"] == 24
    assert artifact["new_feeder_created"] is False
