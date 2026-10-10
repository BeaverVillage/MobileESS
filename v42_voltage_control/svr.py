"""Finite, physical series voltage regulators using native OpenDSS control.

No bus voltage is assigned and no converter/Q device is created.  A contract
declares one existing branch terminal to split; the original branch is retained
with only that bus connection changed.  Native RegControl alone changes taps.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re

SCHEMA = "V42_SERIES_SVR_CONTRACT_V1"
ORIGINAL_REGCONTROLS = ("creg1a", "creg2a", "creg3a", "creg3c", "creg4a", "creg4b", "creg4c")
_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_BUS = re.compile(r"^[a-zA-Z0-9_]+(?:\.[0-3])*$")
_DYNAMIC_REG_PROPERTIES = {"TapNum", "Reset"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _finite(x, name, lower=0.0, upper=None, *, strict=True):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("SVR_NONFINITE_OR_NONNUMERIC:" + name)
    if (x <= lower if strict else x < lower) or (upper is not None and x > upper):
        raise ValueError("SVR_PARAMETER_RANGE:" + name)
    return float(x)


def validate_contract(contract):
    """Validate and return an exact JSON roundtrip; never fill hidden defaults."""
    c = json.loads(json.dumps(contract, allow_nan=False))
    if c.get("schema") != SCHEMA or not isinstance(c.get("units"), list) or not c["units"]:
        raise ValueError("SVR_CONTRACT_SCHEMA_OR_EMPTY")
    if c.get("autonomous_native_control") is not True or c.get("tap_optimization_variables") != 0:
        raise ValueError("SVR_NATIVE_AUTONOMOUS_CONTROL_REQUIRED")
    if c.get("bus_voltage_assignment") is not False or c.get("Q_injection_devices") != 0:
        raise ValueError("SVR_NONPHYSICAL_REPAIR_FORBIDDEN")
    ids, cuts, newbuses = set(), set(), set()
    for u in c["units"]:
        for key in ("id", "upstream_new_bus"):
            if not _NAME.fullmatch(str(u.get(key, ""))):
                raise ValueError("SVR_UNSAFE_NAME:" + key)
        if u["id"].lower() in ids or u["upstream_new_bus"].lower() in newbuses:
            raise ValueError("SVR_DUPLICATE_ID_OR_BUS")
        ids.add(u["id"].lower()); newbuses.add(u["upstream_new_bus"].lower())
        for key in ("original_bus_spec", "downstream_bus", "sensed_bus"):
            if not _BUS.fullmatch(str(u.get(key, ""))):
                raise ValueError("SVR_UNSAFE_BUS:" + key)
        if u["phases"] != [1, 2, 3]:
            raise ValueError("SVR_THREE_PHASE_SERIES_BANK_REQUIRED")
        cls, sep, name = str(u.get("cut_element", "")).partition(".")
        if cls.lower() not in ("transformer", "line") or not sep or not _NAME.fullmatch(name):
            raise ValueError("SVR_INVALID_CUT_ELEMENT")
        terminal = u.get("cut_terminal")
        if isinstance(terminal, bool) or terminal not in (1, 2):
            raise ValueError("SVR_INVALID_CUT_TERMINAL")
        cut = (u["cut_element"].lower(), terminal)
        if cut in cuts:
            raise ValueError("SVR_DUPLICATE_SERIES_CUT")
        cuts.add(cut)
        if u.get("series_orientation") not in ("UPSTREAM_OF_EXISTING_BRANCH", "DOWNSTREAM_OF_EXISTING_BRANCH"):
            raise ValueError("SVR_SERIES_ORIENTATION_REQUIRED")
        if (terminal == 1) != (u["series_orientation"] == "UPSTREAM_OF_EXISTING_BRANCH"):
            raise ValueError("SVR_CUT_ORIENTATION_MISMATCH")
        for key in ("nominal_kv_ln", "sensed_kv_ln", "phase_kva", "xhl_pct", "winding_r_pct", "vreg_volts", "band_volts", "ptratio", "remote_ptratio", "ctprim", "delay_seconds", "tap_delay_seconds"):
            _finite(u[key], key)
        _finite(u["no_load_loss_pct"], "no_load_loss_pct", strict=False)
        if any(not float(u[key]).is_integer() for key in ("delay_seconds", "tap_delay_seconds")):
            raise ValueError("SVR_INTEGER_SECONDS_REQUIRED_FOR_PINNED_QUEUE_PRECISION")
        _finite(u["min_tap"], "min_tap", upper=1.0)
        _finite(u["max_tap"], "max_tap", lower=1.0, strict=False)
        if u["min_tap"] >= u["max_tap"] or u["min_tap"] < .8 or u["max_tap"] > 1.2:
            raise ValueError("SVR_FINITE_TAP_RANGE_REQUIRED")
        if not isinstance(u["num_taps"], int) or isinstance(u["num_taps"], bool) or not 2 <= u["num_taps"] <= 64:
            raise ValueError("SVR_FINITE_TAP_STEPS_REQUIRED")
        if u["max_tap_change"] != 1:
            raise ValueError("SVR_ONE_NATIVE_TAP_STEP_REQUIRED")
        if u["vreg_volts"]-u["band_volts"]/2 < 114 or u["vreg_volts"]+u["band_volts"]/2 > 126:
            raise ValueError("SVR_CONTROL_BAND_OUTSIDE_UNCHANGED_VOLTAGE_LIMITS")
        if abs(u["ptratio"] * 120 - u["nominal_kv_ln"] * 1000) > 1e-8 or abs(u["remote_ptratio"] * 120 - u["sensed_kv_ln"] * 1000) > 1e-8:
            raise ValueError("SVR_PT_NOMINAL_VOLTAGE_MISMATCH")
        if u.get("reverse_policy") != "FORWARD_LOCAL_VOLTAGE_BIDIRECTIONAL_POWER":
            raise ValueError("SVR_REVERSE_POLICY_REQUIRED")
        if not isinstance(u.get("engineering_assumptions"), list) or not u["engineering_assumptions"]:
            raise ValueError("SVR_ENGINEERING_ASSUMPTIONS_REQUIRED")
        if not u.get("source_receipts"):
            raise ValueError("SVR_SOURCE_RECEIPTS_REQUIRED")
    return c


def _command(engine, text):
    engine.Text.Command(text)
    number = int(engine.Error.Number())
    if number:
        raise ValueError("SVR_DSS_COMMAND_ERROR:" + str(number) + ":" + str(engine.Error.Description()))


def _properties(engine, name):
    if not engine.Circuit.SetActiveElement(name):
        raise ValueError("SVR_ELEMENT_MISSING:" + name)
    return {p: str(engine.Properties.Value(p)) for p in engine.CktElement.AllPropertyNames()}


def _original_regulators(engine):
    existing = {str(n).lower() for n in engine.RegControls.AllNames()}
    if not set(ORIGINAL_REGCONTROLS).issubset(existing):
        raise ValueError("SVR_ORIGINAL_SEVEN_CONTROLS_MISSING")
    rows = []
    for name in ORIGINAL_REGCONTROLS:
        props = _properties(engine, "RegControl." + name)
        if not bool(engine.CktElement.Enabled()):
            raise ValueError("SVR_ORIGINAL_CONTROL_DISABLED")
        rows.append(dict(name=name, enabled=True, properties={k: v for k, v in props.items() if k not in _DYNAMIC_REG_PROPERTIES}))
    if int(engine.Solution.ControlMode()) == -1:
        raise ValueError("SVR_ORIGINAL_AUTO_CONTROL_REQUIRED")
    return rows


def _existing_branch(engine, element):
    # Transformer properties refer to the selected winding.  Normalize the
    # selector before comparing a preserved branch, without changing physics.
    if element.lower().startswith("transformer."):
        engine.Transformers.Name(element.split(".", 1)[1]); engine.Transformers.Wdg(1)
    props = _properties(engine, element)
    row = dict(element=element, buses=list(engine.CktElement.BusNames()), phases=int(engine.CktElement.NumPhases()),
               norm_amps=float(engine.CktElement.NormalAmps()), properties=props)
    if element.lower().startswith("transformer."):
        engine.Transformers.Name(element.split(".", 1)[1]); windings = []
        for w in range(1, int(engine.Transformers.NumWindings()) + 1):
            engine.Transformers.Wdg(w)
            windings.append(dict(winding=w, kv=float(engine.Transformers.kV()), kva=float(engine.Transformers.kVA()),
                                 tap=float(engine.Transformers.Tap()), min_tap=float(engine.Transformers.MinTap()),
                                 max_tap=float(engine.Transformers.MaxTap()), num_taps=int(engine.Transformers.NumTaps()),
                                 delta=bool(engine.Transformers.IsDelta())))
        row["windings"] = windings
    return row


def _branch_static(row):
    excluded = {"Bus", "Buses", "Bus1", "Bus2", "Wdg", "WdgCurrents"}
    return {k: v for k, v in row.items() if k not in ("buses", "properties")} | dict(properties={k: v for k, v in row["properties"].items() if k not in excluded})


def _added_transformer_static(row):
    value = _branch_static(row)
    value["windings"] = [{k: v for k, v in w.items() if k != "tap"} for w in row["windings"]]
    value["properties"] = {k: v for k, v in value["properties"].items() if k not in ("Tap", "Taps")}
    return value


def _terminal(engine, element, phase_kva, kv_ln):
    engine.Circuit.SetActiveElement(element)
    powers = list(engine.CktElement.Powers()); currents = list(engine.CktElement.CurrentsMagAng())
    n = int(engine.CktElement.NumConductors()); terminals = []
    for t in range(int(engine.CktElement.NumTerminals())):
        p, q = float(powers[2*t*n]), float(powers[2*t*n+1]); s = math.hypot(p, q)
        amps = float(currents[2*t*n]); rated_amps = phase_kva / kv_ln
        terminals.append(dict(terminal=t+1, P_into_kw=p, Q_into_kvar=q, apparent_kva=s,
                              current_a=amps, nameplate_kva=phase_kva, normal_current_a=rated_amps,
                              apparent_loading_pu=s/phase_kva, current_loading_pu=amps/rated_amps,
                              thermal_PASS=s <= phase_kva*(1+1e-8) and amps <= rated_amps*(1+1e-8)))
    loss = list(engine.CktElement.Losses())
    return dict(element=element, buses=list(engine.CktElement.BusNames()), terminals=terminals,
                losses_kw=float(loss[0])/1000, losses_kvar=float(loss[1])/1000)


def _bus(engine, name, kv_ln):
    if not engine.Circuit.SetActiveBus(name):
        raise ValueError("SVR_BUS_MISSING:" + name)
    volts = list(engine.Bus.VMagAngle()); nodes = list(engine.Bus.Nodes())
    base = float(engine.Bus.kVBase())
    if abs(base-kv_ln) > 1e-7:
        raise ValueError("SVR_BUS_NOMINAL_BASE_DRIFT:"+name)
    values = [{"node": int(n), "voltage_v": float(volts[2*k]), "voltage_pu": float(volts[2*k])/(kv_ln*1000)}
              for k, n in enumerate(nodes) if int(n) in (1, 2, 3)]
    return dict(bus=name, nominal_kv_ln=kv_ln, compiled_kv_base_ln=base, nodes=values,
                voltage_PASS=all(.95-1e-8 <= r["voltage_pu"] <= 1.05+1e-8 for r in values))


class SeriesSVRCollection:
    def __init__(self, engine, contract, receipt, initial_state):
        self.engine = engine; self.contract = copy.deepcopy(contract)
        self.installation_receipt = receipt; self.initial_state = initial_state
        self.observer_names = receipt["added_RegControl_names"]

    def measure(self):
        e = self.engine
        if _original_regulators(e) != self.installation_receipt["original_seven_control_parameters"]:
            raise ValueError("SVR_ORIGINAL_REGULATOR_DRIFT")
        devices = []
        for u in self.contract["units"]:
            current = _existing_branch(e, u["cut_element"])
            old = next(r for r in self.installation_receipt["original_branches"] if r["element"] == u["cut_element"])
            if _branch_static(current) != _branch_static(old):
                raise ValueError("SVR_ORIGINAL_BRANCH_RATING_OR_PHYSICS_DRIFT")
            expected = old["buses"].copy(); expected[u["cut_terminal"]-1] = u["upstream_new_bus"] + ".1.2.3"
            if [b.lower() for b in current["buses"]] != [b.lower() for b in expected]:
                raise ValueError("SVR_ORIGINAL_BRANCH_SERIES_CONNECTION_DRIFT")
            phases = []
            for ph in u["phases"]:
                name = "svr_" + u["id"].lower() + "_p" + str(ph)
                tx_static = _added_transformer_static(_existing_branch(e, "Transformer."+name))
                if tx_static != self.installation_receipt["added_transformer_static"][name]:
                    raise ValueError("SVR_ADDED_TRANSFORMER_PARAMETER_OR_RATING_DRIFT")
                tx = _terminal(e, "Transformer." + name, u["phase_kva"], u["nominal_kv_ln"])
                e.Transformers.Name(name); e.Transformers.Wdg(2); tap = float(e.Transformers.Tap())
                rc = _properties(e, "RegControl." + name)
                if {k: v for k, v in rc.items() if k not in _DYNAMIC_REG_PROPERTIES} != self.installation_receipt["added_regulator_static"][name]:
                    raise ValueError("SVR_ADDED_CONTROLLER_PARAMETER_DRIFT")
                nominal_tap_number = (tap-1) / ((u["max_tap"]-u["min_tap"])/u["num_taps"])
                phases.append(tx | dict(phase=ph, tap=tap, tap_number=nominal_tap_number,
                    tap_range_PASS=u["min_tap"]-1e-9 <= tap <= u["max_tap"]+1e-9,
                    autonomous_control_enabled=bool(e.CktElement.Enabled()), controller_parameters=rc))
            nodes = [_bus(e, u["upstream_new_bus"], u["nominal_kv_ln"]), _bus(e, u["sensed_bus"].split(".")[0], u["sensed_kv_ln"])]
            devices.append(dict(id=u["id"], downstream_bus=u["downstream_bus"], sensed_bus=u["sensed_bus"],
                                new_bus=u["upstream_new_bus"], phases=phases, node_readbacks=nodes,
                                hardware_PASS=all(p["tap_range_PASS"] and p["autonomous_control_enabled"] and
                                                  all(t["thermal_PASS"] for t in p["terminals"]) for p in phases),
                                added_nodes_voltage_PASS=nodes[0]["voltage_PASS"]))
        return dict(schema="V42_SERIES_SVR_MEASUREMENT_V1", contract_SHA=digest(self.contract),
                    original_seven_AUTO=True, Converged=bool(e.Solution.Converged()),
                    ControlActionsDone=bool(e.Solution.ControlActionsDone()),
                    ControlIterations=int(e.Solution.ControlIterations()), solution_iterations=int(e.Solution.Iterations()),
                    time_semantics="native OpenDSS; static iterations are not elapsed seconds",
                    devices=devices, hardware_PASS=all(x["hardware_PASS"] for x in devices),
                    added_nodes_voltage_PASS=all(x["added_nodes_voltage_PASS"] for x in devices),
                    whole_original_network_PASS=None)


def install(engine, contract):
    """Install the declared series bank; caller must own a fresh DSS context."""
    c = validate_contract(contract); original_regs = _original_regulators(engine)
    original_branches = []; unit_preflight = []
    all_elements = {str(n).lower() for n in engine.Circuit.AllElementNames()}
    all_buses = {str(n).lower() for n in engine.Circuit.AllBusNames()}
    for u in c["units"]:
        if u["upstream_new_bus"].lower() in all_buses:
            raise ValueError("SVR_NEW_BUS_COLLISION")
        for ph in u["phases"]:
            name = "svr_" + u["id"].lower() + "_p" + str(ph)
            if "transformer."+name in all_elements or "regcontrol."+name in all_elements:
                raise ValueError("SVR_DEVICE_NAME_COLLISION")
        row = _existing_branch(engine, u["cut_element"])
        if row["phases"] != 3 or row["buses"][u["cut_terminal"]-1].lower() != u["original_bus_spec"].lower():
            raise ValueError("SVR_SOURCE_CUT_CONNECTION_MISMATCH")
        nodes = [int(x) for x in u["original_bus_spec"].split(".")[1:]]
        if nodes != [1, 2, 3]:
            raise ValueError("SVR_CUT_PHASE_WIRING_UNPROVEN")
        bus = u["original_bus_spec"].split(".")[0]
        engine.Circuit.SetActiveBus(bus)
        if set(engine.Bus.Nodes()) != {1, 2, 3} or abs(float(engine.Bus.kVBase())-u["nominal_kv_ln"]) > 1e-7:
            raise ValueError("SVR_SOURCE_BUS_PHASE_OR_KV_MISMATCH")
        if u["sensed_bus"].split(".")[0].lower() not in all_buses:
            raise ValueError("SVR_SENSE_BUS_NOT_EXISTING_SOURCE")
        engine.Circuit.SetActiveBus(u["sensed_bus"].split(".")[0])
        if abs(float(engine.Bus.kVBase())-u["sensed_kv_ln"]) > 1e-7:
            raise ValueError("SVR_SENSE_KV_MISMATCH")
        original_limit = (row["windings"][u["cut_terminal"]-1]["kva"]/3 if "windings" in row
                          else row["norm_amps"]*u["nominal_kv_ln"])
        if u["phase_kva"] > original_limit*(1+1e-8):
            raise ValueError("SVR_NAMEPLATE_EXCEEDS_DECLARED_SOURCE_BRANCH_CAPACITY")
        original_branches.append(row); unit_preflight.append((u, bus))
    added_tx = []; added_regs = []
    for u, bus in unit_preflight:
        new_spec = u["upstream_new_bus"] + ".1.2.3"
        if u["cut_element"].lower().startswith("transformer."):
            _command(engine, "Edit " + u["cut_element"] + " Wdg=" + str(u["cut_terminal"]) + " Bus=" + new_spec)
        else:
            _command(engine, "Edit " + u["cut_element"] + " Bus" + str(u["cut_terminal"]) + "=" + new_spec)
        first, second = ((bus, u["upstream_new_bus"]) if u["cut_terminal"] == 1 else (u["upstream_new_bus"], bus))
        for ph in u["phases"]:
            name = "svr_"+u["id"].lower()+"_p"+str(ph)
            _command(engine, f"New Transformer.{name} Phases=1 Windings=2 Buses=[{first}.{ph}.0 {second}.{ph}.0] Conns=[wye wye] kVs=[{u['nominal_kv_ln']:.15g} {u['nominal_kv_ln']:.15g}] kVAs=[{u['phase_kva']:.15g} {u['phase_kva']:.15g}] %Rs=[{u['winding_r_pct']:.15g} {u['winding_r_pct']:.15g}] XHL={u['xhl_pct']:.15g} %NoLoadLoss={u['no_load_loss_pct']:.15g} NormHkVA={u['phase_kva']:.15g} EmergHkVA={u['phase_kva']:.15g} Wdg=1 Tap=1 MinTap=1 MaxTap=1 NumTaps=0 Wdg=2 Tap=1 MinTap={u['min_tap']:.15g} MaxTap={u['max_tap']:.15g} NumTaps={u['num_taps']}")
            sensed = u["sensed_bus"].split(".")[0] + "." + str(ph)
            _command(engine, f"New RegControl.{name} Transformer={name} Winding=2 TapWinding=2 VReg={u['vreg_volts']:.15g} Band={u['band_volts']:.15g} PTRatio={u['ptratio']:.15g} CTPrim={u['ctprim']:.15g} R=0 X=0 Bus={sensed} RemotePTRatio={u['remote_ptratio']:.15g} Delay={u['delay_seconds']:.15g} TapDelay={u['tap_delay_seconds']:.15g} MaxTapChange=1 Reversible=No Cogen=No RevNeutral=No InverseTime=No EventLog=Yes Enabled=Yes")
            added_tx.append(name); added_regs.append(name)
    if _original_regulators(engine) != original_regs:
        raise ValueError("SVR_INSTALL_ORIGINAL_REGULATOR_DRIFT")
    # Define the nominal base of each *new* bus, not its solved voltage.  A new
    # bus otherwise has kVBase=0 and AllBusVmagPu returns volts rather than pu.
    # This command performs no power-flow solve and changes no original base.
    _command(engine, "MakeBusList")
    for u in c["units"]:
        _command(engine, f"SetkVBase {u['upstream_new_bus']} kVln={u['nominal_kv_ln']:.15g}")
        engine.Circuit.SetActiveBus(u["upstream_new_bus"])
        if abs(float(engine.Bus.kVBase())-u["nominal_kv_ln"]) > 1e-7:
            raise ValueError("SVR_ADDED_BUS_BASE_NOT_COMPILED")
    tx_static = {name: _added_transformer_static(_existing_branch(engine, "Transformer."+name)) for name in added_tx}
    rc_static = {name: {k: v for k, v in _properties(engine, "RegControl."+name).items() if k not in _DYNAMIC_REG_PROPERTIES} for name in added_regs}
    for u in c["units"]:
        for ph in u["phases"]:
            name = "svr_"+u["id"].lower()+"_p"+str(ph); actual = tx_static[name]
            if any(abs(w["kva"]-u["phase_kva"]) > 1e-8 or abs(w["kv"]-u["nominal_kv_ln"]) > 1e-8 for w in actual["windings"]):
                raise ValueError("SVR_COMPILED_NAMEPLATE_MISMATCH")
            if abs(float(actual["properties"]["NormHkVA"])-u["phase_kva"]) > 1e-8:
                raise ValueError("SVR_COMPILED_NORMAL_KVA_MISMATCH")
    receipt = dict(schema="V42_SERIES_SVR_INSTALLATION_RECEIPT_V1", contract_SHA=digest(c),
                   original_seven_control_parameters=original_regs, original_branches=original_branches,
                   added_transformer_static=tx_static, added_regulator_static=rc_static,
                   original_branch_edits="ONLY_DECLARED_TERMINAL_BUS", added_transformer_names=added_tx,
                   added_RegControl_names=added_regs, added_bus_names=[u["upstream_new_bus"] for u in c["units"]],
                   three_phase_bank_count=len(c["units"]), single_phase_transformer_count=len(added_tx),
                   autonomous_native_control=True, Bus_voltage_assignment=False, Q_injection_devices=0,
                   Planning_physics_regeneration_required=True, physical_topology_changed=True,
                   whole_network_gate_required=True)
    initial = dict(taps=[1.0]*len(added_tx), original_seven_parameters_SHA=digest(original_regs),
                   Actual_must_compile_independently=True, Planning_tap_copy=False)
    return SeriesSVRCollection(engine, c, receipt, initial)
