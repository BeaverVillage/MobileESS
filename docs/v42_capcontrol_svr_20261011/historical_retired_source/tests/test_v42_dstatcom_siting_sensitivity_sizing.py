from pathlib import Path

import numpy as np
import pytest

from v42_dstatcom.sizing import coupled_droop_stability, local_coupled_requirement, modular_rating


def test_phase_capacity_and_total_are_both_reserved():
    row = modular_rating([300., 0., 0.], site_id="STA01")
    assert row["selected_candidate_rating_kvar"] == 1500
    assert row["independent_phase_rating_kvar"] == 500
    assert row["phase_safety_factor"] >= 1.5
    assert row["physical_approval"] is False


def test_sta08_initial_1500_and_q_sign_do_not_change_apparent_requirement():
    positive = modular_rating([40., 20., 10.], site_id="STA08")
    negative = modular_rating([-40., -20., -10.], site_id="STA08")
    assert positive["selected_candidate_rating_kvar"] == negative["selected_candidate_rating_kvar"] == 1500
    assert positive["required_phase_apparent_kva"] == negative["required_phase_apparent_kva"]


@pytest.mark.parametrize("required", [[np.nan,0,0], [1,2], [1,2,3,4]])
def test_missing_or_nonfinite_phase_requirement_never_zero_rating(required):
    with pytest.raises(ValueError): modular_rating(required,site_id="STA01")


def test_compensation_uses_off_diagonal_phase_coupling():
    matrix = np.array([[.0003,-.00004,-.00002],[-.00003,.00025,-.00002],[-.00001,-.00003,.00028]])
    voltage = np.array([1.058,1.050,1.049])
    result = local_coupled_requirement(voltage,matrix)
    q = np.array(result["signed_required_phase_Q_kvar"])
    assert np.all(q < 0)
    assert np.max(np.abs(voltage+matrix@q-1.045)) < 1e-14
    assert not np.allclose(q,(1.045-voltage)/np.diag(matrix))
    assert result["global_network_physical_PASS"] is False


def test_ill_conditioned_coupling_not_approved():
    with pytest.raises(ValueError): local_coupled_requirement([1.058,1.02,1.02],np.ones((3,3)))


def test_coupled_stability_detects_unstable_cross_endpoint_response():
    # Diagonal-only analysis would report stable; simultaneous coupling fails.
    matrix = np.array([[.0001,.002],[.002,.0001]])
    result = coupled_droop_stability(matrix,[250,250],damping=.025)
    assert result["conditional_fixed_tap_small_signal_PASS"] is False
    assert result["maximum_linear_stable_damping_bound"] == 0
    assert result["nonlinear_96_slot_physical_PASS"] is None


def test_stability_uses_target_fraction_not_hardware_operating_limit():
    result = coupled_droop_stability(np.eye(3)*.0003,[250,250,500])
    assert result["droop_gain_kvar_per_pu"] == [4500,4500,9000]
    assert result["conditional_fixed_tap_small_signal_PASS"] is True
    assert result["nonlinear_96_slot_physical_PASS"] is None


def test_actual_36_endpoints_are_not_merged_and_service_ratings_retained():
    from v42_regcontrol.authority import compile_verified
    from v42_dstatcom.siting import inspect_sites
    engine,_adapter,_inventory = compile_verified()
    try:
        rows = inspect_sites(engine)
        assert len(rows) == 36 and len({row["site_id"] for row in rows}) == 24
        assert len({row["pcc_bus"] for row in rows}) == len({row["device_id"] for row in rows}) == 36
        sta = next(row for row in rows if row["site_id"] == "STA08")
        assert sta["pcc_bus"] == "mess_sta08_pcc" and sta["mv_parent_bus"] == "67"
        assert sta["service_transformer_kva"] == 750
        assert sta["nominal_kv_ln"] == pytest.approx(.48/np.sqrt(3))
        idc = [row for row in rows if row["site_id"] == "IDC08"]
        assert {row["pcc_bus"] for row in idc} == {"idc_idc08_pcc","mess_idc08_pcc"}
        assert {row["service_transformer_kva"] for row in idc} == {750,1500}
        assert all(not row["installed"] and row["service_spare_capacity_not_assumed"] for row in rows)
        assert all(0 in w["node_order"] for row in rows for w in row["service_transformer"]["windings"])
        from v42_dstatcom.siting import canonical_24_sites
        selected = canonical_24_sites(rows)
        assert len(selected) == 24
        assert sum(row["initial_design_rating_kvar"] for row in selected) == 18750
        assert {row["endpoint_id"] for row in selected if row["site_id"].startswith("IDC")} == {"AIDC"}
        assert all(not row["pcc_bus"].startswith("mess_idc") for row in selected)
        with pytest.raises(ValueError): canonical_24_sites(selected[:-1])
    finally:
        engine.Basic.ClearAll()


def test_recorded_signed_dss_evidence_without_repeating_fixed_control_probes():
    # The latest user contract requires all future physical runs to keep the
    # original7 RegControls automatic. Validate the immutable prior evidence
    # instead of replaying a fixed/controlmode-off diagnostic in the test gate.
    import csv
    import hashlib
    import json
    root = Path("D:/v42_dstatcom_development_20261010/STA08_FIRST")
    proof_path = root / "DSTATCOM_SENSITIVITY_AUDIT.json"
    if not proof_path.exists():
        pytest.skip("Historical signed-probe evidence unavailable; no new fixed-control run permitted")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    sample = next(row for row in proof["columns"] if row["mode"] == "FIXED_SETTLED_TAPS"
                  and row["injection_phase"] == "A" and row["magnitude_kvar"] == 25)
    pmeta, mmeta = sample["positive"], sample["negative"]
    with (root / "DSTATCOM_SENSITIVITY_MATRIX.csv").open(encoding="utf-8-sig", newline="") as stream:
        cells = {row["measured_node"]:row for row in csv.DictReader(stream)
                 if row["control_mode"] == "FIXED_SETTLED_TAPS"
                 and row["injection_phase"] == "A" and float(row["perturbation_kvar"]) == 25}
    assert float(cells["mess_sta08_pcc.1"]["voltage_plus_pu"]) > float(cells["mess_sta08_pcc.1"]["voltage_minus_pu"])
    assert float(cells["mess_sta08_pcc.1"]["voltage_minus_pu"]) < 1.05
    assert float(cells["mess_sta08_pcc.3"]["voltage_minus_pu"]) > float(cells["mess_sta08_pcc.3"]["voltage_plus_pu"])
    assert pmeta["generator_terminal_consumption_Q_kvar"] < 0 < mmeta["generator_terminal_consumption_Q_kvar"]
    assert pmeta["original_voltage_bit_exact"] is True
    assert pmeta["meaningful_tap_changes"] == mmeta["meaningful_tap_changes"] == 0
    assert pmeta["device_kind"].endswith("NOT_PHYSICAL_APPROVAL")
    for saved in proof["artifacts"]:
        with Path(saved["path"]).open("rb") as stream:
            assert hashlib.file_digest(stream,"sha256").hexdigest() == saved["sha256"]
