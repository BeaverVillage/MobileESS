"""OpenDSS phase-coupled diagnostics on immutable observed development input.

These are conditional static responses at a selected original operating slot,
not converter certification, a feasible optimization point, or a future input.
Each perturbation replays all earlier original slots in a fresh source context.
Fixed-control probes disable controls ONLY after the original operating point
has settled; automatic probes retain the original seven RegControls unchanged.
"""
from __future__ import annotations

import math
from pathlib import Path
import types

import numpy as np

from .siting import receipt, write_csv, write_json

OLD_OPERATIONS = Path(r"D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01\output\OPERATIONS")
OLD_INJECTIONS = Path(r"D:\v42_actual_voltage_audit_20261010\factorial\FULL_PQ_REPLAY\BASE_PHYSICAL_INJECTIONS.json")


def original_development_inputs(operations=OLD_OPERATIONS, injection_path=OLD_INJECTIONS):
    import json
    operations = Path(operations)
    with np.load(operations / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz", allow_pickle=False) as archive:
        mess = {key: archive[key].copy() for key in archive.files}
    with np.load(operations / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as archive:
        ac = {key: archive[key].copy() for key in archive.files}
    injections = json.loads(Path(injection_path).read_text(encoding="utf-8-sig"))
    if len(injections) != 96 or mess["P_kw"].shape != (96, 4) or mess["Q_kvar"].shape != (96, 4):
        raise ValueError("ORIGINAL_96_SLOT_DEVELOPMENT_AXIS_REQUIRED")
    if any(row["slot"] != slot for slot, row in enumerate(injections)):
        raise ValueError("ORIGINAL_INJECTION_SLOT_ORDER")
    return dict(mess=mess, ac=ac, injections=injections,
        receipts=[receipt(operations / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz"),
                  receipt(operations / "ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz"),
                  receipt(operations / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz"), receipt(injection_path)])


def apply_original_injections(engine, inputs, slot):
    """Set exactly the previously observed original engine load/PV/MESS input."""
    row = inputs["injections"][slot]
    for name, (p, q) in row["loads"].items():
        engine.Loads.Name(name)
        if engine.Loads.Name().lower() != name.lower(): raise ValueError("ORIGINAL_LOAD_ABSENT:" + name)
        engine.Loads.kW(p); engine.Loads.kvar(q)
    for name, (p, q) in row["generators"].items():
        engine.Generators.Name(name)
        if engine.Generators.Name().lower() != name.lower(): raise ValueError("ORIGINAL_GENERATOR_ABSENT:" + name)
        engine.Generators.kW(p); engine.Generators.kvar(q)
    for name in engine.Generators.AllNames():
        if name.lower().startswith("mess_dis_"):
            engine.Generators.Name(name); engine.Generators.kW(0); engine.Generators.kvar(0)
    for name in engine.Loads.AllNames():
        if name.lower().startswith("mess_chg_"):
            engine.Loads.Name(name); engine.Loads.kW(0); engine.Loads.kvar(0)
    mess = inputs["mess"]
    services = {}
    for index, location in enumerate(mess["locations"][slot].astype(str)):
        p, q = float(mess["P_kw"][slot, index]), float(mess["Q_kvar"][slot, index])
        if location.startswith("TRANSIT_"):
            if abs(p) > 1e-9 or abs(q) > 1e-9: raise ValueError("FROZEN_TRANSIT_PQ_NONZERO")
            continue
        totals = services.setdefault(location.lower(), [0., 0.])
        totals[0] += p; totals[1] += q
    for location, (p, q) in sorted(services.items()):
        engine.Generators.Name("mess_dis_" + location); engine.Generators.kW(max(p, 0)); engine.Generators.kvar(q)
        engine.Loads.Name("mess_chg_" + location); engine.Loads.kW(max(-p, 0)); engine.Loads.kvar(0)


def vector(engine, node_names):
    values = dict(zip(map(str.lower, engine.Circuit.AllNodeNames()), engine.Circuit.AllBusMagPu()))
    return np.asarray([values[name.lower()] for name in node_names], dtype=float)


def controls(engine):
    from v42_regcontrol import authority
    source = authority.source()
    taps, caps = source["native_state"](engine)
    return dict(taps=taps, capacitors=caps, control_iterations=int(engine.Solution.ControlIterations()),
        total_electrical_iterations=int(engine.Solution.Iterations()),
        most_electrical_iterations_done=int(engine.Solution.MostIterationsDone()),
        control_actions_done=bool(engine.Solution.ControlActionsDone()),
        converged=bool(engine.Solution.Converged()),
        configured_max_control_iterations=int(engine.Solution.MaxControlIterations()),
        configured_max_electrical_iterations=int(engine.Solution.MaxIterations()))


def service_netflow(engine, names):
    """Original service winding currents/kVA, with unchanged nameplate ratings."""
    rows=[]
    for name in names:
        engine.Transformers.Name(name)
        if engine.Transformers.Name().lower()!=name.lower():raise ValueError("ORIGINAL_SERVICE_TX_ABSENT")
        conductors=int(engine.CktElement.NumConductors())
        nodes=list(map(int,engine.CktElement.NodeOrder()))
        current=list(map(float,engine.CktElement.CurrentsMagAng()))[::2]
        powers=list(map(float,engine.CktElement.Powers()))
        terminals=[]
        for winding in range(1,int(engine.Transformers.NumWindings())+1):
            engine.Transformers.Wdg(winding)
            kva,kv=float(engine.Transformers.kVA()),float(engine.Transformers.kV())
            phases=int(engine.CktElement.NumPhases())
            rating=kva/(math.sqrt(3)*kv) if phases==3 else kva/kv
            positions=[(winding-1)*conductors+j for j in range(conductors) if nodes[(winding-1)*conductors+j] in (1,2,3)]
            phase_currents=[current[j] for j in positions]
            p=sum(powers[2*j] for j in positions);q=sum(powers[2*j+1] for j in positions)
            terminals.append(dict(winding=winding,nameplate_kva=kva,nameplate_kv=kv,current_rating_a=rating,
                phase_current_a=phase_currents,maximum_phase_current_utilization=max(phase_currents)/rating,
                net_P_consumption_kw=p,net_Q_consumption_kvar=q,net_apparent_kva=math.hypot(p,q),
                apparent_utilization=math.hypot(p,q)/kva,
                current_and_kva_PASS=max(phase_currents)<=rating and math.hypot(p,q)<=kva))
        rows.append(dict(name=name,original_service_capacity_bypassed=False,windings=terminals,
            PASS=all(row["current_and_kva_PASS"] for row in terminals)))
    return rows


def prepare_original_slot(inputs, slot):
    from v42_regcontrol import authority
    engine, _adapter, _inventory = authority.compile_verified()
    try:
        for t in range(slot + 1):
            apply_original_injections(engine, inputs, t)
            engine.Solution.SolveSnap()
            if not engine.Solution.Converged() or not engine.Solution.ControlActionsDone():
                raise ValueError("ORIGINAL_DEVELOPMENT_BASELINE_DID_NOT_SETTLE")
        measured = vector(engine, inputs["ac"]["node_names"].astype(str))
        expected = inputs["ac"]["voltage_pu"][slot]
        state = controls(engine)
        if measured.tobytes() != expected.tobytes():
            raise ValueError("ORIGINAL_SLOT_VOLTAGE_NOT_BIT_EXACT:" + str(float(np.max(np.abs(measured-expected)))))
        if np.asarray(state["taps"]).tobytes() != inputs["ac"]["regulator_taps"][slot].tobytes():
            raise ValueError("ORIGINAL_SLOT_TAPS_NOT_BIT_EXACT")
        if not np.array_equal(state["capacitors"], inputs["ac"]["capacitor_states"][slot]):
            raise ValueError("ORIGINAL_SLOT_CAPACITORS_CHANGED")
        return engine, measured, state
    except Exception:
        engine.Basic.ClearAll()
        raise


def install_ideal_phase_probe(engine, site, phase, *, name="development_q_probe"):
    """Ideal constrained-Q measurement element; NOT the final physical device."""
    if phase not in site["phases"] or site["status"] == "INVALID_SITE":
        raise ValueError("INVALID_ACTUAL_PHASE_FOR_Q_PROBE")
    command = (f"New Generator.{name} bus1={site['pcc_bus']}.{phase}.0 phases=1 conn=wye "
               f"kV={site['nominal_kv_ln']:.17g} kW=0 kvar=0 kVA=1000 model=1 Vminpu=.85 Vmaxpu=1.15")
    engine.Text.Command(command)
    if engine.Error.Number(): raise ValueError("Q_PROBE_INSTALL:" + engine.Error.Description())
    return name


def response(inputs, site, phase, q_kvar, slot, mode, *, physical_bank=False):
    from v42_regcontrol import authority
    if mode not in ("FIXED_SETTLED_TAPS", "ORIGINAL_AUTOMATIC_REGCONTROL"):
        raise ValueError("UNKNOWN_CONTROL_RESPONSE_MODE")
    engine, original_v, original_control = prepare_original_slot(inputs, slot)
    try:
        device = None
        baseline_v = original_v
        if physical_bank:
            from .device import install
            device = install(engine, site)
            engine.Solution.SolveSnap()
            if not engine.Solution.Converged() or not engine.Solution.ControlActionsDone():
                raise ValueError("PHYSICAL_ZERO_Q_BANK_DID_NOT_SETTLE")
            baseline_v = vector(engine, inputs["ac"]["node_names"].astype(str))
            original_control = controls(engine)
            probe_name = device.names[phase-1]["generator"]
        else:
            probe_name = install_ideal_phase_probe(engine, site, phase)
        if mode == "FIXED_SETTLED_TAPS":
            for name in authority.source()["REGULATORS"]:
                engine.Text.Command("Disable RegControl." + name)
            engine.Text.Command("Set controlmode=off")
        if device is None:
            engine.Generators.Name(probe_name); engine.Generators.kvar(float(q_kvar))
        else:
            q = [0.,0.,0.]; q[phase-1] = float(q_kvar)
            applied = device.apply_q(q,dt_seconds=10.)
            if not np.allclose(applied["applied_Q_supply_kvar"],q,rtol=0,atol=1e-8):
                raise ValueError("PHYSICAL_Q_RESPONSE_PROBE_HIT_CURRENT_KVA_OR_RATE_CAP")
        engine.Solution.SolveSnap()
        new_v = vector(engine, inputs["ac"]["node_names"].astype(str))
        state = controls(engine)
        if not state["converged"] or (mode == "ORIGINAL_AUTOMATIC_REGCONTROL" and not state["control_actions_done"]):
            raise ValueError("Q_PERTURBATION_DID_NOT_SETTLE")
        engine.Generators.Name(probe_name)
        engine.Circuit.SetActiveElement("generator." + probe_name)
        powers = list(map(float, engine.CktElement.Powers()))
        currents = list(map(float, engine.CktElement.CurrentsMagAng()))
        actual_p, actual_q, actual_current = powers[0], powers[1], currents[0]
        # The original DSS electrical convergence criterion remains unchanged;
        # terminal power is measured, including its small solve residual.
        if not math.isclose(-actual_q, q_kvar, rel_tol=1e-3, abs_tol=1e-3):
            raise ValueError("GENERATOR_Q_SIGN_OR_POWER_READBACK_MISMATCH")
        return new_v, dict(slot0=slot, site_id=site["site_id"], endpoint_id=site.get("endpoint_id"),
            device_id=site.get("device_id"), injection_bus=site["pcc_bus"],
            injection_phase="ABC"[phase-1], Q_injection_kvar=q_kvar, control_mode=mode,
            device_kind="ACTUAL_LV_COUPLING_BANK_DIAGNOSTIC_NOT_PHYSICAL_APPROVAL" if physical_bank else "IDEAL_SINGLE_PHASE_Q_PROBE_NOT_PHYSICAL_APPROVAL",
            original_voltage_bit_exact=True, baseline_voltage_pu=baseline_v.tolist(),
            installed_physical_device=device.measure() if device is not None else None,
            original_service_transformer_netflow=service_netflow(engine,site.get("service_transformers",())),
            original_control=original_control, measured_control=state,
            meaningful_tap_changes=sum(abs(a-b) > 1e-12 for a,b in zip(original_control["taps"],state["taps"])),
            generator_terminal_consumption_P_kw=actual_p, generator_terminal_consumption_Q_kvar=actual_q,
            current_a=actual_current, apparent_kva=math.hypot(actual_p, actual_q),
            Q_terminal_readback_error_kvar=-actual_q-q_kvar,
            voltage_min_pu=float(new_v.min()), voltage_max_pu=float(new_v.max()),
            voltage_violations=int(((new_v < .95-1e-8)|(new_v > 1.05+1e-8)).sum()))
    finally:
        engine.Basic.ClearAll()


def measure_sensitivity(output, *, sites, slots=(10,), magnitudes=(1., 5., 25., 100.), inputs=None, physical_bank=False):
    """Measure all output phases for every requested source phase and ±Q."""
    inputs = inputs or original_development_inputs()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    columns, summary, matrix_rows = [], [], []
    nodes = inputs["ac"]["node_names"].astype(str)
    for slot in slots:
        for site in sites:
            for phase in site["phases"]:
                for mode in ("FIXED_SETTLED_TAPS", "ORIGINAL_AUTOMATIC_REGCONTROL"):
                    for magnitude in magnitudes:
                        if magnitude <= 0 or not np.isfinite(magnitude): raise ValueError("POSITIVE_PERTURBATION_REQUIRED")
                        plus, pmeta = response(inputs, site, phase, magnitude, slot, mode,physical_bank=physical_bank)
                        minus, mmeta = response(inputs, site, phase, -magnitude, slot, mode,physical_bank=physical_bank)
                        positive_baseline = np.asarray(pmeta["baseline_voltage_pu"])
                        negative_baseline = np.asarray(mmeta["baseline_voltage_pu"])
                        baseline_difference = float(np.abs(positive_baseline-negative_baseline).max())
                        if baseline_difference > 1e-12:
                            raise ValueError("INDEPENDENT_PLUS_MINUS_BASELINE_DIFFERED")
                        baseline = (positive_baseline+negative_baseline)/2
                        central = (plus-minus)/(2*magnitude)
                        positive = (plus-baseline)/magnitude
                        negative = (baseline-minus)/magnitude
                        col = dict(slot0=slot, site_id=site["site_id"], endpoint_id=site.get("endpoint_id"),
                            device_id=site.get("device_id"), injection_bus=site["pcc_bus"],
                            injection_phase="ABC"[phase-1], mode=mode, magnitude_kvar=magnitude,
                            positive=pmeta, negative=mmeta,
                            plus_minus_baseline_max_difference_pu=baseline_difference)
                        columns.append(central);summary.append(col)
                        matrix_rows.extend(dict(slot0=slot, site_id=site["site_id"], endpoint_id=site.get("endpoint_id"),
                            device_id=site.get("device_id"), injection_bus=site["pcc_bus"],
                            injection_phase="ABC"[phase-1], control_mode=mode, perturbation_kvar=magnitude,
                            measured_node=node, measured_phase="ABC"[int(node.rsplit('.',1)[1])-1],
                            baseline_voltage_pu=float(baseline[index]), voltage_plus_pu=float(plus[index]),
                            voltage_minus_pu=float(minus[index]), dV_dQ_central_pu_per_kvar=float(central[index]),
                            dV_dQ_positive_pu_per_kvar=float(positive[index]), dV_dQ_negative_pu_per_kvar=float(negative[index]),
                            one_sided_slope_difference_pu_per_kvar=float(positive[index]-negative[index]),
                            tap_changed_plus=pmeta["meaningful_tap_changes"], tap_changed_minus=mmeta["meaningful_tap_changes"])
                            for index,node in enumerate(nodes))
    np.savez_compressed(output / "DSTATCOM_SENSITIVITY_ARRAYS.npz", node_names=nodes, central=np.asarray(columns))
    write_csv(output / "DSTATCOM_SENSITIVITY_MATRIX.csv", matrix_rows)
    proof = dict(schema="V42_DSTATCOM_OPENDSS_PHASE_COUPLED_SENSITIVITY_V1", diagnostic_only=True,
        official_canary=False, development_date="2025-05-01", May01_observed_development_not_holdout=True,
        Native_optimizer_calls=0, original_source_settings_changed=False,
        fixed_taps_mode_only_in_diagnostic_context=True, all_prior_slots_replayed=True,
        phase_coupling="ALL_386_EXISTING_NODE_PHASES_FOR_EACH_INJECTION_PHASE",
        physical_coupling_bank_included=physical_bank,
        probe_is_not_final_converter_or_service_capacity_approval=True,
        input_receipts=inputs["receipts"], experiment_count=2*len(summary), columns=summary,
        artifacts=[receipt(output / "DSTATCOM_SENSITIVITY_ARRAYS.npz"),receipt(output / "DSTATCOM_SENSITIVITY_MATRIX.csv")])
    if any(receipt(row["path"])!=row for row in inputs["receipts"]):
        raise ValueError("ORIGINAL_DEVELOPMENT_INPUT_CHANGED_DURING_PROBES")
    proof["original_inputs_before_after_SHA_equal"]=True
    write_json(output / "DSTATCOM_SENSITIVITY_AUDIT.json", proof)
    return proof


def engineering_location_stress(output, *, sites, input_cases=None, q_magnitudes=(392.31411216132904,), inputs=None, location_ids=None):
    """Observed-development physical stress; never a new feasible frozen plan.

    One 3-phase MESS is exposed at each possible service location with other
    MESS P/Q zero. This screens endpoint exposure and does not prove coverage
    of every four-unit feasible dispatch/route combination. The controller sees
    only the present voltage. External stress changes are named and recorded.
    """
    from .device import install
    from .settings import ControllerSettings
    from .controller import LocalVoltVarController
    from v42_regcontrol import authority
    settings=ControllerSettings()
    inputs=inputs or original_development_inputs()
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=authority.source()
    input_cases=input_cases or [dict(name="OBSERVED_MAY01_ACTUAL_SLOT10",slot0=10)]
    locations=[site for site in sites if site["endpoint_id"]=="MESS"]
    if len(locations)!=24 or len(sites)!=36:raise ValueError("24_LOGICAL_MESS_LOCATIONS_36_PHYSICAL_DEVICES_REQUIRED")
    if location_ids is not None:
        locations=[site for site in locations if site["site_id"] in location_ids]
        if len(locations)!=len(set(location_ids)):raise ValueError("UNKNOWN_DEVELOPMENT_LOCATION")
    result_rows=[];receipts=[]
    for case in input_cases:
        for site in locations:
            for magnitude in q_magnitudes:
                if not 0<magnitude<=392.31411216132904+1e-9:raise ValueError("OBSERVED_ORIGINAL_MESS_Q_ENVELOPE_REQUIRED")
                for sign in (-1,1):
                    name=case["name"]+"_"+site["device_id"]+("_SUPPLY" if sign>0 else "_ABSORB")
                    folder=output/name
                    if folder.exists():raise ValueError("DEVELOPMENT_STRESS_OUTPUT_ALREADY_EXISTS:"+name)
                    folder.mkdir()
                    engine,baseline_v,baseline_control=prepare_original_slot(inputs,case["slot0"])
                    try:
                        # Existing operator injections remain source-backed;
                        # all MESS injection changes are explicit diagnostics.
                        for item in engine.Generators.AllNames():
                            if item.lower().startswith("mess_dis_"):
                                engine.Generators.Name(item);engine.Generators.kW(0);engine.Generators.kvar(0)
                        for item in engine.Loads.AllNames():
                            if item.lower().startswith("mess_chg_"):
                                engine.Loads.Name(item);engine.Loads.kW(0);engine.Loads.kvar(0)
                        engine.Generators.Name("mess_dis_"+site["site_id"].lower())
                        engine.Generators.kW(0);engine.Generators.kvar(sign*magnitude)
                        if "background" in case:
                            adapter=__import__("json").loads(source["assets"].runtime_adapter.read_text(encoding="utf8"))
                            native=source["NativeAllocation"].from_adapter(adapter)
                            native.apply(engine,case["background"],case["slot0"])
                            for row in adapter["pv_generators"]:
                                engine.Generators.Name(row["generator_name"])
                                key=(str(row["bus"]).lower(),"ABC"[int(row["phase"])-1])
                                engine.Generators.kW(case["background"].pv_generation_kw_96[case["slot0"]].get(key,0));engine.Generators.kvar(0)
                        engine.Solution.SolveSnap()
                        off=vector(engine,inputs["ac"]["node_names"].astype(str))
                        off_control=controls(engine)
                        devices=[install(engine,candidate,settings) for candidate in sites]
                        engine.Solution.SolveSnap()
                        controller=LocalVoltVarController(devices,settings)
                        control=controller.settle_slot(engine,0)
                        on=vector(engine,inputs["ac"]["node_names"].astype(str))
                        all_nodes=[str(node) for node in engine.Circuit.AllNodeNames() if node.rsplit('.',1)[1] in ('1','2','3')]
                        all_v=vector(engine,all_nodes)
                        tx=service_netflow(engine,engine.Transformers.AllNames())
                        max_line_ratio=0.;line_violations=0
                        for line in engine.Lines.AllNames():
                            engine.Lines.Name(line);rating=float(engine.Lines.NormAmps())
                            nod=list(engine.CktElement.NodeOrder());cur=list(engine.CktElement.CurrentsMagAng())[::2]
                            ratios=[float(current)/rating for node,current in zip(nod,cur) if node in (1,2,3)]
                            max_line_ratio=max(max_line_ratio,max(ratios))
                            line_violations+=sum(ratio>1 for ratio in ratios)
                        original_bad=int(((on<.95)|(on>1.05)).sum())
                        all_bad=int(((all_v<.95)|(all_v>1.05)).sum())
                        tx_bad=sum(not row["PASS"] for row in tx)
                        row=dict(case=name,development_only=True,original_operating_slot0=case["slot0"],
                            controller_diagnostic_slot_index=0,logical_site=site["site_id"],endpoint=site["device_id"],
                            observed_original_MESS_envelope_Q_supply_kvar=sign*magnitude,MESS_P_kw=0,
                            all_other_MESS_PQ_zero=True,installation_devices=36,total_nameplate_MVAr=sum(d.spec.rating_kvar for d in devices)/1000,
                            OFF_original_Vmin_pu=float(off.min()),OFF_original_Vmax_pu=float(off.max()),
                            OFF_original_voltage_violations=int(((off<.95)|(off>1.05)).sum()),
                            ON_original_Vmin_pu=float(on.min()),ON_original_Vmax_pu=float(on.max()),
                            ON_original_voltage_violations=original_bad,ON_all_original_and_added_voltage_violations=all_bad,
                            ON_all_Vmin_pu=float(all_v.min()),ON_all_Vmax_pu=float(all_v.max()),
                            controller_converged=control["controller_converged"],controller_feedback_iterations=control["iterations"],
                            current_and_kva_violating_transformers=tx_bad,line_terminal_phase_violations=line_violations,
                            maximum_original_and_added_line_current_loading_percent=100*max_line_ratio,
                            peak_STATCOM_phase_Q_abs_kvar=max(abs(p["Q_supply_kvar"]) for d in control["final_devices"] for p in d["phases"]),
                            peak_STATCOM_phase_rating_utilization=max(p["converter_kva_utilization"] for d in control["final_devices"] for p in d["phases"]),
                            physical_PASS=control["PASS"] and original_bad==all_bad==tx_bad==line_violations==0,
                            strict_feasible_optimized_plan=False,SOC_or_route_proof=False,
                            global_four_MESS_dispatch_robustness_proved=False,future_information_in_controller=False,
                            Native_optimizer_calls=0,source_initial_exact_baseline_voltage=True,
                            frozen_settings=settings.to_dict())
                        np.savez_compressed(folder/"DEVELOPMENT_STRESS_ARRAYS.npz",original_node_names=inputs["ac"]["node_names"],
                            OFF_voltage_pu=off,ON_voltage_pu=on,all_node_names=np.asarray(all_nodes),all_ON_voltage_pu=all_v)
                        write_json(folder/"DEVELOPMENT_STRESS_RECEIPT.json",dict(**row,controller=control,transformer_netflow=tx,
                            original_OFF_controls=off_control,original_observed_baseline_controls=baseline_control,
                            exogenous_case={key:value for key,value in case.items() if key!='background'},input_receipts=inputs["receipts"],
                            arrays_receipt=receipt(folder/"DEVELOPMENT_STRESS_ARRAYS.npz")))
                        result_rows.append(row);receipts.append(receipt(folder/"DEVELOPMENT_STRESS_RECEIPT.json"))
                        write_csv(output/"DSTATCOM_DEVELOPMENT_LOCATION_STRESS.csv",result_rows)
                    finally:
                        engine.Basic.ClearAll()
    if any(receipt(row["path"])!=row for row in inputs["receipts"]):raise ValueError("ORIGINAL_INPUT_MUTATION_DURING_DEVELOPMENT_STRESS")
    result=dict(schema="V42_DSTATCOM_DEVELOPMENT_LOCATION_STRESS_V1",development_cases=len(result_rows),
        PASS=all(row["physical_PASS"] for row in result_rows),all24_potential_MESS_locations_screened=len(locations)==24,
        original_inputs_before_after_SHA_equal=True,independent_May_actual_read=[],Native_calls=0,
        optimized_plan_feasibility_claim=False,source_settings_control_unchanged=True,
        full_four_MESS_dispatch_and_day_robustness_proved=False,receipts=receipts,
        summary_receipt=receipt(output/"DSTATCOM_DEVELOPMENT_LOCATION_STRESS.csv"))
    write_json(output/"DSTATCOM_DEVELOPMENT_LOCATION_STRESS_AUDIT.json",result)
    return result
