"""Read original May01 outputs; write only this external audit directory."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
CODE = Path(r"D:\v42u4final")
CAMPAIGN = Path(r"D:\v42_common_mess_campaign_20261010_01")
B0 = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_transformer_normalamps_pr\docs\v42_may_b0_zero_margin_holdout\BUNDLE\DAY_20250501")
B1_RESULT = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01\dates\B1\2025-05-01\RESULT.json")
B2_RESULT = CAMPAIGN / "dates/B2/2025-05-01/attempts/common_u4_v1_01/RESULT.json"
LEDGER = {}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def register(path, expected=None):
    row = receipt(path)
    if expected:
        assert row["sha256"] == expected["sha256"] and row["bytes"] == expected["bytes"], (str(path), "ORIGINAL_RECEIPT_MISMATCH")
    LEDGER[row["path"]] = row
    return Path(row["path"])


def read(path, expected=None):
    return json.loads(register(path, expected).read_text(encoding="utf-8-sig"))


def arrays(path, expected=None):
    with np.load(register(path, expected), allow_pickle=False) as archive:
        return {k: archive[k].copy() for k in archive.files}


def write_json(name, value):
    path = OUT / name
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_csv(name, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows(rows)


def parameters(inventory):
    # Exactly v42_regcontrol.authority.regulator_parameters. TapNum is state.
    return dict(engine_version=inventory["engine_version"], regulators=[
        {k: r[k] for k in ("name", "transformer", "winding", "min_tap", "max_tap", "num_taps", "tap_step")}
        | dict(properties={k: v for k, v in r["resolved_properties"].items() if k != "TapNum"})
        for r in inventory["regulators"]], control_mode=inventory["control_mode"],
        solution_mode=inventory["solution_mode"], max_control_iterations=inventory["max_control_iterations"])


def run():
    manifest = read(CAMPAIGN / "COMMON_U4_QUALIFICATION_MANIFEST.json")
    result1 = read(B1_RESULT, manifest["B1_results"]["B1/2025-05-01"])
    result2 = read(B2_RESULT)
    baseline_authority = read(Path(r"D:\MobileESS_V42\docs\v42_transformer_normalamps_contract\MAY_B0_CURRENT_RECLASSIFICATION.json"))
    b0_expected = next(row for row in baseline_authority["source_files"] if "DAY_20250501" in row["path"])
    control_authority_path = CODE / "docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json"
    authority = read(control_authority_path)
    expected = authority["actual_static_compile"]
    assert expected == authority["planning_static_compile"]
    roots = {"B0": B0, "B1": Path(result1["evaluation"]["Fresh"]["folder"]), "B2": Path(result2["evaluation"]["Fresh"]["folder"])}
    logs, raw, physical = {}, {}, {}
    for arm, folder in roots.items():
        source_receipts = result1["evaluation"]["Fresh"] if arm == "B1" else result2["evaluation"]["Fresh"] if arm == "B2" else {}
        logs[arm] = read(folder / "RAW_CONTROL_LOG.json", source_receipts.get("control_log"))
        physical[arm] = read(folder / "RAW_PHYSICAL_INPUT_LOG.json", source_receipts.get("physical_input_log"))
        if arm == "B0":
            raw[arm] = arrays(folder / "V_ACTUAL_AC.npz", b0_expected)
            read(folder / "FRESH_ACTUAL_AC_RECEIPT.json")
        else:
            raw[arm] = arrays(folder / "fresh/OPENDSS_PHASE_ARRAYS.npz")
            read(folder / "FRESH_RESULT.json", source_receipts["receipt"])
        assert logs[arm]["source_initial_inventory"] == expected, (arm, "CONTROL_INVENTORY_DRIFT")
        assert len(logs[arm]["slots"]) == 96
        assert [row["slot"] for row in logs[arm]["slots"]] == list(range(96))
    exogenous_receipt = physical["B2"]["Actual_exogenous"]
    frame = pd.read_parquet(register(exogenous_receipt["path"], exogenous_receipt))
    stamps = [pd.Timestamp(t).isoformat() for t in frame.ts_fixed_aest_end]
    assert len(stamps) == 96 and stamps == list(map(str, raw["B0"]["timestamps_96"]))
    initial = [r["initial_tap"] for r in expected["regulators"]]
    regulator_sha, capacitor_sha = digest(parameters(expected)), digest(expected["capacitors"])
    individual_regulator_sha = {row["name"]: digest(row) for row in parameters(expected)["regulators"]}
    summaries, setting_rows, slot_rows, tap_rows = {}, [], [], []
    names = list(map(str, raw["B2"]["node_names"]))
    for arm in roots:
        data, log, inv = raw[arm], logs[arm], logs[arm]["source_initial_inventory"]
        assert list(map(str, data["node_names"])) == names
        voltage = data["V_ACTUAL_AC"] if arm == "B0" else data["voltage_pu"]
        convergence = data["converged"] if arm == "B0" else data["convergence"]
        assert voltage.shape == (96, 386) and np.isfinite(voltage).all() and convergence.all()
        taps, caps = data["regulator_taps"], data["capacitor_states"]
        assert taps.shape == (96, 7) and caps.shape == (96, 4) and (caps == 1).all()
        violation = (voltage < .95) | (voltage > 1.05)
        iteration_values = [row.get("control_iterations") for row in log["slots"]]
        solve_iteration_values = [row.get("convergence_iterations") for row in log["slots"]]
        summaries[arm] = dict(min_voltage_pu=float(voltage.min()), max_voltage_pu=float(voltage.max()),
            voltage_violation_cells=int(violation.sum()), under_voltage_cells=int((voltage < .95).sum()),
            over_voltage_cells=int((voltage > 1.05).sum()), convergence_slots=int(convergence.sum()),
            REGCONTROL_AUTHORITY_SHA=regulator_sha, CAPACITOR_FIXED_STATE_AUTHORITY_SHA=capacitor_sha,
            initial_inventory_SHA=digest(inv), source_inventory_exactly_equal=True,
            seven_RegControls_enabled_all_slots=True, fixed_caps_all_ON_all_slots=True, CapControl_count=0,
            solution_mode=inv["solution_mode"], control_mode=inv["control_mode"], control_mode_label="snapshot/static",
            max_control_iterations_configured=inv["max_control_iterations"], max_solution_iterations_configured=None,
            max_solution_iterations_configuration_evidence="NOT_RECORDED_IN_HISTORICAL_INVENTORY; original compiler does not override MaxIterations",
            observed_max_control_iterations=max(iteration_values) if all(v is not None for v in iteration_values) else None,
            observed_max_convergence_iterations=max(solve_iteration_values) if all(v is not None for v in solve_iteration_values) else None,
            per_slot_iteration_observation="HISTORICAL_RAW_LOG" if arm == "B0" else "NOT_RECORDED_IN_HISTORICAL_RAW_LOG",
            control_completion_evidence="96 explicit true RAW log rows" if arm == "B0" else "96 accepted measurements after unchanged source hook requires ControlActionsDone true; field not stored",
            previous_tap_evidence="HISTORICAL_RAW_LOG" if arm == "B0" else "DERIVED: source initial tap for slot0, prior recorded settled tap thereafter",
            tap_min_by_regulator=taps.min(axis=0).tolist(), tap_max_by_regulator=taps.max(axis=0).tolist(),
            tap_transition_count_by_regulator=np.sum(np.abs(taps-np.vstack([initial, taps[:-1]])) > 1e-12, axis=0).tolist())
        for r in inv["regulators"]:
            setting_rows.append(dict(arm=arm, regulator=r["name"], transformer=r["transformer"], winding=r["winding"],
                enabled=r["enabled"], initial_tap=r["initial_tap"], min_tap=r["min_tap"], max_tap=r["max_tap"],
                num_taps=r["num_taps"], tap_step=r["tap_step"], settings_SHA=regulator_sha,
                individual_regulator_settings_SHA=individual_regulator_sha[r["name"]],
                control_mode=inv["control_mode"], solution_mode=inv["solution_mode"], max_control_iterations=inv["max_control_iterations"],
                max_solution_iterations="NOT_RECORDED", **r["resolved_properties"]))
        for t, row in enumerate(log["slots"]):
            current_taps = row["actual_taps"] if arm == "B0" else row["taps"]
            current_caps = row["capacitor_states"] if arm == "B0" else row["caps"]
            assert np.array_equal(current_taps, taps[t]) and np.array_equal(current_caps, caps[t])
            assert row["all_7_RegControls_enabled"] is True and row["CapControl_count"] == 0
            if arm == "B0":
                assert row["REGCONTROL_AUTHORITY_SHA"] == regulator_sha and row["control_actions_done"] is True
                assert row["source_parameters_before_after_identical"] is True
            else:
                assert row["Planning_tap_replay"] is False
            previous = row["previous_taps"] if arm == "B0" else initial if t == 0 else taps[t-1].tolist()
            slot_rows.append(dict(arm=arm, slot0=t, slot1=t+1, timestamp_fixed_AEST_end=stamps[t],
                converged=bool(convergence[t]), all_7_RegControls_enabled=True, CapControl_count=0,
                capacitor_states=json.dumps(current_caps), settings_SHA=regulator_sha,
                control_actions_done=row.get("control_actions_done", "TRUE_REQUIRED_BY_ACCEPTED_SOURCE_HOOK;NOT_STORED"),
                control_iterations=row.get("control_iterations", "NOT_RECORDED"),
                convergence_iterations=row.get("convergence_iterations", "NOT_RECORDED"),
                maxcontroliter_configured=inv["max_control_iterations"], maxiterations_configured="NOT_RECORDED",
                min_voltage_pu=float(voltage[t].min()), max_voltage_pu=float(voltage[t].max()),
                voltage_violation_cells=int(violation[t].sum())))
            for j, reg in enumerate(inv["regulators"]):
                tap_rows.append(dict(arm=arm, slot0=t, slot1=t+1, timestamp_fixed_AEST_end=stamps[t],
                    regulator=reg["name"], transformer=reg["transformer"], winding=reg["winding"],
                    enabled=True, previous_tap=float(previous[j]), settled_tap=float(taps[t,j]),
                    settled_tap_position=int(round((float(taps[t,j])-1.)/reg["tap_step"])),
                    tap_change=float(taps[t,j]-previous[j]),
                    previous_tap_basis="RAW_CONTROL_LOG" if arm == "B0" else "INITIAL_OR_PREVIOUS_SETTLED_RECORD",
                    settings_SHA=regulator_sha, individual_regulator_settings_SHA=individual_regulator_sha[reg["name"]]))
    difference_rows = []
    for t in range(96):
        for j, reg in enumerate(expected["regulators"]):
            values = {arm: float(raw[arm]["regulator_taps"][t,j]) for arm in roots}
            difference_rows.append(dict(slot0=t, slot1=t+1, timestamp_fixed_AEST_end=stamps[t],
                regulator=reg["name"], B0_tap=values["B0"], B1_tap=values["B1"], B2_tap=values["B2"],
                B1_minus_B0=values["B1"]-values["B0"], B2_minus_B0=values["B2"]-values["B0"],
                B2_minus_B1=values["B2"]-values["B1"], B0_enabled=True, B1_enabled=True, B2_enabled=True,
                B0_caps="[1,1,1,1]", B1_caps="[1,1,1,1]", B2_caps="[1,1,1,1]",
                capacitor_differences=0, individual_regulator_settings_SHA=individual_regulator_sha[reg["name"]]))
    violations = []
    voltage = raw["B2"]["voltage_pu"]
    for t, j in np.argwhere((voltage < .95) | (voltage > 1.05)):
        value, node = float(voltage[t,j]), names[j]
        site = "STA"+node.split("mess_sta",1)[1].split("_",1)[0] if node.startswith("mess_sta") else None
        phy = physical["B2"]["slots"][t]
        connected = [u for u, location in enumerate(phy["MESS_locations"]) if location == site]
        violations.append(dict(slot0=int(t), slot1=int(t+1), timestamp_fixed_AEST_end=stamps[t],
            node_phase=node, phase="ABC"[int(node.rsplit(".",1)[1])-1],
            voltage_pu=value, violation_type="OVERVOLTAGE" if value > 1.05 else "UNDERVOLTAGE",
            unchanged_lower_limit_pu=.95, unchanged_upper_limit_pu=1.05,
            exceedance_pu=max(.95-value,value-1.05,0.), exceedance_percentage_points=100*max(.95-value,value-1.05,0.),
            B0_same_cell_voltage_pu=float(raw["B0"]["V_ACTUAL_AC"][t,j]),
            B1_same_cell_voltage_pu=float(raw["B1"]["voltage_pu"][t,j]), MESS_site=site,
            connected_MESS_units=json.dumps([f"MESS{u+1:02d}" for u in connected]),
            recorded_site_MESS_P_kw=sum(phy["MESS_P_kw"][u] for u in connected),
            recorded_site_MESS_Q_kvar=sum(phy["MESS_Q_kvar"][u] for u in connected)))
    assert len(violations) == 19 and all(r["violation_type"] == "OVERVOLTAGE" for r in violations)
    peak = max(violations, key=lambda r:r["exceedance_pu"])
    source_files = [CODE / p for p in ("v42_regcontrol/authority.py", "v42_regcontrol/session.py", "v42_regcontrol/runner.py",
        "v42_pr134_b1/replay.py", "v42_may_campaign_native90/operations.py", "docs/v42_autonomous_grid_controls_april_b0/audit_sources.py")]
    source_files += [Path(r"D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance") / p for p in
        ("dayahead/v28r2/opendss_backend.py", "dayahead/v28r2/opendss_mapping.py", "dayahead/v28r2/trajectory.py")]
    for path in source_files:
        register(path)
    static_integrity = []
    for row in authority["static_source_graph"]["files"]:
        registered = register(row["path"], row)
        static_integrity.append(dict(path=str(registered), sha256=row["sha256"], PASS=True))
    # Check the currently sealed B2 source against its persisted reviewer receipts.
    for row in result2["evaluation"]["reviewer_source_SHA"]:
        register(row["path"], row)
    write_csv("CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv", setting_rows)
    write_csv("CONTROL_SLOT_COMPARISON_B0_B1_B2.csv", slot_rows)
    write_csv("CONTROL_TAP_TRAJECTORIES_B0_B1_B2.csv", tap_rows)
    write_csv("CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv", difference_rows)
    write_json("CONTROL_ORIGINAL_SETTINGS.json", dict(regulator_parameters=parameters(expected),
        regulator_settings_SHA=regulator_sha, fixed_capacitors=expected["capacitors"], capacitor_settings_SHA=capacitor_sha,
        individual_regulator_settings_SHA=individual_regulator_sha,
        complete_source_initial_inventory=expected, tuning=0, additional_AC_solves=0))
    conclusion = dict(schema="V42_READ_ONLY_ORIGINAL_CONTROL_AUDIT_V1", UTC=datetime.now(timezone.utc).isoformat(),
        day="2025-05-01", source_SHA=manifest["execution_SHA"], source_commit=manifest["source_commit"],
        arms=summaries, voltage_peak=peak, violation_slots0=sorted({r["slot0"] for r in violations}),
        violation_node_phases=sorted({r["node_phase"] for r in violations}),
        all_19_cells_at_MESS_PCC=True, common_control_inventory_exact_equal=True,
        common_RegControl_settings_SHA=regulator_sha, common_fixed_capacitor_settings_SHA=capacitor_sha,
        individual_regulator_settings_SHA=individual_regulator_sha,
        control_implementation_defect_demonstrated=False,
        finding="Original common controls match exactly; B2 19 measured MESS-PCC overvoltage cells are preserved as Actual failure. P/Q cause requires independent assigned factorial replay.",
        historical_observability_gap="B1/B2 RAW logs omit solution/control iteration counts and explicit completion fields; unchanged acceptance hook requires ControlActionsDone true per slot. Unknown counts are not zero.",
        source_control_semantics=dict(fresh_day_source_initial_taps=initial, sequential_within_day=True,
            all_RegControls_enabled=True, snapshot_static=True, maxcontroliter=100,
            Planning_tap_cap_forcing=False, RegControl_parameter_setters_added=False, capacitor_state_repair=False,
            observed_CAPCONTROL_count=0, fixed_capacitor_states=[1,1,1,1]),
        source_bindings=dict(original_backend="dayahead.v28r2.opendss_backend.run_fresh_opendss",
            common_binding="v42_may_campaign_native90.operations.fresh -> _fresh_port(v42_pr134_b1.replay.fresh)",
            before_and_after_inventory_guard="v42_regcontrol.authority.assert_inventory",
            completion_guard="v42_pr134_b1.replay.fresh.measure_voltage requires Solution.ControlActionsDone() before logged voltage",
            original_Fresh_AST_routing="Only trajectory, injection application and zero-MESS receipt; controls/measure_voltage unchanged"),
        static_source_integrity=static_integrity,
        original_physical_files_preserved=True, original_voltage_limits_preserved=[.95,1.05],
        no_existing_files_written=True, optimization_calls=0, new_AC_solves=0)
    write_json("CONTROL_AUDIT_RESULT.json", conclusion)
    for original in LEDGER.values():
        assert receipt(original["path"]) == original, (original["path"], "ORIGINAL_BYTES_DRIFT_DURING_READ_ONLY_AUDIT")
    text = f"""# V42 May01 Original Controls and Voltage Audit

B2 Actual contains **19 overvoltage cells**, all at MESS PCC nodes. B0 and B1 contain zero voltage violations. All three arms converged at all 96 slots.

Peak: **{peak['node_phase']} / phase {peak['phase']}**, slot {peak['slot0']} (0-based; {peak['timestamp_fixed_AEST_end']}), **{peak['voltage_pu']:.16f} pu**, exceeding the unchanged 1.05 pu limit by **{peak['exceedance_pu']:.16f} pu** ({peak['exceedance_percentage_points']:.12f} percentage points).

The three full source initial inventories are identical. The same seven RegControls remain enabled in every recorded slot. They share settings SHA **{regulator_sha}**, snapshot/static mode, maxcontroliter=100, initial taps all 1.0, and four fixed capacitors ON. CapControl count is zero. RegControl settings, settled taps, capacitor states, original models and voltage limits were not changed.

B0 records control iteration counts (maximum {summaries['B0']['observed_max_control_iterations']}) and convergence iterations (maximum {summaries['B0']['observed_max_convergence_iterations']}). Original B1/B2 logs do not record these counts or configured MaxIterations. These fields remain UNKNOWN. Their unchanged post-solve hook requires ControlActionsDone=true and the original control inventory before accepting each voltage measurement; this establishes completion through the accepted source path, while distinguishing it from an explicit historical log field.

Read-only source analysis found no demonstrated common-control implementation defect. The original Fresh backend SolveSnap body remains unchanged. Its Planning-state setter hook is replaced with an inventory-only check, so Actual regulators operate autonomously. Any causal attribution to MESS P or Q is pending the separately assigned factorial replay.

Files: `CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv` preserves all resolved properties and each of seven individual regulator settings SHAs. `CONTROL_SLOT_COMPARISON_B0_B1_B2.csv` and `CONTROL_TAP_TRAJECTORIES_B0_B1_B2.csv` preserve per-slot observations. `CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv` compares settled tap values, enabled status and fixed capacitors directly across arms. `CONTROL_SOURCE_SHA_LEDGER.json` checks all original bytes before/after this audit. Detailed voltage cells and Planning/Actual comparison are published separately in `B2_MAY01_VOLTAGE_VIOLATIONS.csv` and `B2_MAY01_VOLTAGE_AUDIT.json` by the numerical audit.

This audit made zero optimizer calls and zero new AC solves. It wrote only external audit artifacts and preserved the old failed canary result.
"""
    with (OUT / "CONTROL_AUDIT_REPORT.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    write_json("CONTROL_SOURCE_SHA_LEDGER.json", dict(schema="V42_READ_ONLY_AUDIT_SOURCE_SHA_LEDGER_V1",
        sources=list(LEDGER.values()), before_after_SHA_equal=True, source_count=len(LEDGER),
        audit_script=receipt(__file__),
        audit_outputs=[receipt(OUT/name) for name in ("CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv", "CONTROL_SLOT_COMPARISON_B0_B1_B2.csv",
            "CONTROL_TAP_TRAJECTORIES_B0_B1_B2.csv", "CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv", "CONTROL_ORIGINAL_SETTINGS.json",
            "CONTROL_AUDIT_RESULT.json", "CONTROL_AUDIT_REPORT.md")]))
    print(json.dumps(dict(PASS=True, source_count=len(LEDGER), cells=len(violations), peak=peak,
        common_control_SHA=regulator_sha, summaries=summaries, output=str(OUT)), ensure_ascii=False))


if __name__ == "__main__":
    run()
