"""Native physical series connection, reverse flow, and integrity guards."""
import copy
import json
import math
from pathlib import Path

import pytest

from v42_regcontrol import authority
from v42_voltage_control import svr, siting


@pytest.fixture(scope="module")
def inventory():
    e, _, _ = authority.compile_verified()
    return siting.original_inventory(e, source_receipts=[siting.receipt(
        Path(__file__).resolve().parents[1]/"docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json")])


def test_actual_24_logical_36_separate_physical_endpoints(inventory):
    assert inventory["logical_site_count"] == 24
    assert inventory["physical_endpoint_count"] == 36
    ends = inventory["original_endpoints"]
    assert len({r["pcc_bus"] for r in ends}) == 36
    a, b = [next(r for r in ends if r["physical_endpoint_id"] == "IDC01_"+ep) for ep in ("AIDC", "MESS")]
    assert a["service_transformer"] != b["service_transformer"]
    assert a["service_kva"] == 1500 and b["service_kva"] == 750


def test_primary_serial_path_and_exact_direct_coverage(inventory):
    u = siting.candidate_unit(inventory, "STA08")
    assert u["cut_element"] == "Transformer.mess_sta08_tx" and u["cut_terminal"] == 1
    assert u["original_bus_spec"] == "67.1.2.3"
    assert u["direct_downstream_bus_coverage"] == ["mess_sta08_pcc"]
    assert "67" not in u["direct_downstream_bus_coverage"]
    assert not u["upstream_voltage_coverage_claim"]
    v = siting.candidate_unit(inventory, "BUS83")
    assert v["cut_element"] == "Line.l84" and v["original_bus_spec"] == "82.1.2.3"
    assert "83" in v["direct_downstream_bus_coverage"] and "mess_sta12_pcc" in v["direct_downstream_bus_coverage"]
    assert "82" not in v["direct_downstream_bus_coverage"]
    assert v["phase_kva"]/v["nominal_kv_ln"] == pytest.approx(400)


@pytest.mark.parametrize("key,value", [
    ("phase_kva", float("inf")), ("phase_kva", -1), ("phases", [1,2]),
    ("original_bus_spec", "67.1.2.3 New Generator.bad"),
    ("max_tap", 10), ("num_taps", 0), ("max_tap_change", 16),
    ("remote_ptratio", 20), ("reverse_policy", "REVERSE_LOOK_UPSTREAM"),
    ("vreg_volts", 130), ("no_load_loss_pct", -1),
])
def test_invalid_nonphysical_or_unbounded_contract_rejected(inventory, key, value):
    c = siting.development_contract(inventory); c["units"][0][key] = value
    with pytest.raises((ValueError, OverflowError)):
        svr.validate_contract(c)


def test_contract_exact_roundtrip_and_duplicate_cut_rejection(inventory):
    c = siting.development_contract(inventory)
    assert svr.validate_contract(c) == json.loads(json.dumps(c))
    c["units"].append(copy.deepcopy(c["units"][0]))
    with pytest.raises(ValueError, match="DUPLICATE"):
        svr.validate_contract(c)


def test_source_mismatch_rejected_before_any_equipment_is_added(inventory):
    e, _, _ = authority.compile_verified(); count = len(e.Circuit.AllElementNames())
    c = siting.development_contract(inventory); c["units"][0]["original_bus_spec"] = "83.1.2.3"
    with pytest.raises(ValueError, match="SOURCE_CUT_CONNECTION_MISMATCH"):
        svr.install(e, c)
    assert len(e.Circuit.AllElementNames()) == count


def test_finite_original_capacity_and_control_enabled_guards(inventory):
    e, _, _ = authority.compile_verified(); c = siting.development_contract(inventory)
    c["units"][0]["phase_kva"] = 500
    with pytest.raises(ValueError, match="CAPACITY"):
        svr.install(e, c)
    e.Text.Command("Edit RegControl.creg1a Enabled=No")
    with pytest.raises(ValueError, match="DISABLED"):
        svr.install(e, siting.development_contract(inventory))


@pytest.mark.parametrize("P_kw,Q_kvar", [(600,300), (-600,-300)])
def test_real_native_remote_lv_pt_and_bidirectional_series_power(inventory, P_kw, Q_kvar):
    # Synthetic finite development stress, never a frozen Actual or canary.
    e, _, _ = authority.compile_verified(); c = siting.development_contract(inventory)
    coll = svr.install(e, c)
    e.Text.Command(f"New Load.svr_unit_test_probe Bus1=mess_sta08_pcc.1.2.3 Phases=3 Conn=wye kV=.48 kW={P_kw} kvar={Q_kvar} Model=1")
    e.Solution.SolveSnap(); m = coll.measure()
    assert m["Converged"] and m["ControlActionsDone"] and m["original_seven_AUTO"]
    d = m["devices"][0]
    assert d["hardware_PASS"] and d["added_nodes_voltage_PASS"]
    assert all(x["voltage_PASS"] for x in d["node_readbacks"])
    assert d["node_readbacks"][0]["compiled_kv_base_ln"] == pytest.approx(4.16/math.sqrt(3))
    for phase in d["phases"]:
        # The physically measured primary terminal power reverses.  No assumed
        # supply-sign convention or forced voltage is used to make it pass.
        assert phase["terminals"][0]["P_into_kw"]*P_kw > 0
        assert phase["losses_kw"] > 0
        assert phase["tap_range_PASS"]
        assert float(phase["controller_parameters"]["VReg"]) == 120
        assert float(phase["controller_parameters"]["RemotePTRatio"]) == pytest.approx(.48/math.sqrt(3)*1000/120)
    assert set(coll.observer_names) == {"svr_sta08_p1", "svr_sta08_p2", "svr_sta08_p3"}
    assert e.RegControls.Count() == 10
    assert m["whole_original_network_PASS"] is None
    assert coll.installation_receipt["Planning_physics_regeneration_required"]


def test_late_added_controller_and_original_branch_rating_edits_never_pass(inventory):
    e, _, _ = authority.compile_verified(); coll = svr.install(e, siting.development_contract(inventory))
    e.Solution.SolveSnap(); coll.measure()
    e.Text.Command("Edit RegControl.svr_sta08_p1 VReg=121")
    with pytest.raises(ValueError, match="ADDED_CONTROLLER_PARAMETER_DRIFT"):
        coll.measure()
    e.Text.Command("Edit RegControl.svr_sta08_p1 VReg=120")
    e.Text.Command("Edit Transformer.mess_sta08_tx Wdg=1 kVA=1000")
    with pytest.raises(ValueError, match="ORIGINAL_BRANCH_RATING_OR_PHYSICS_DRIFT"):
        coll.measure()


def test_native_voltage_regulation_cannot_hide_new_bank_overload(inventory):
    e, _, _ = authority.compile_verified(); coll = svr.install(e, siting.development_contract(inventory))
    e.Text.Command("New Load.svr_overload_probe Bus1=mess_sta08_pcc.1.2.3 Phases=3 Conn=wye kV=.48 kW=900 kvar=0 Model=1")
    e.Solution.SolveSnap(); m = coll.measure()
    assert m["Converged"]
    assert not m["hardware_PASS"]
    assert any(t["apparent_loading_pu"] > 1 for p in m["devices"][0]["phases"] for t in p["terminals"])


def test_late_new_transformer_and_original_regulator_edits_never_pass(inventory):
    e, _, _ = authority.compile_verified(); coll = svr.install(e, siting.development_contract(inventory))
    e.Solution.SolveSnap()
    e.Text.Command("Edit Transformer.svr_sta08_p1 XHL=0.001")
    with pytest.raises(ValueError, match="ADDED_TRANSFORMER_PARAMETER_OR_RATING_DRIFT"):
        coll.measure()
    e.Text.Command("Edit RegControl.creg1a R=0")
    with pytest.raises(ValueError, match="ORIGINAL_REGULATOR_DRIFT"):
        coll.measure()
