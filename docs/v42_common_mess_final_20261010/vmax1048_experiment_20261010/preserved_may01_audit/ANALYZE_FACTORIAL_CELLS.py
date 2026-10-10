"""Read-only decomposition of the original 19 AC cells and observed tap paths."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\v42_actual_voltage_audit_20261010")
OPS = Path(r"D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01\output\OPERATIONS")
VARIANTS = ("FULL_PQ_REPLAY", "P_ONLY_Q_ZERO", "Q_ONLY_P_ZERO", "ZERO_PQ")
LINE_AUTHORITY = Path(r"D:\MobileESS_V42\docs\v42_transformer_normalamps_contract\LINE_CURRENT_AUTHORITY_UNCHANGED.csv")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=digest, bytes=path.stat().st_size)


def csv_write(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({key: json.dumps(value) if isinstance(value, (list, dict)) else value
            for key, value in row.items()} for row in rows)


def main():
    factorial = read(ROOT / "FACTORIAL_REPLAY_STATUS.json")
    assert factorial["PASS"] is True and factorial["baseline_reproduced_bit_exact"]
    source = read(OPS / "FRESH/RAW_CONTROL_LOG.json")["source_initial_inventory"]
    # Original backend REGULATORS order, also pinned by the coefficient anchor.
    names = ("reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c")
    initial = {row["transformer"].lower(): row["initial_tap"] for row in source["regulators"]}
    arrays = {name: np.load(ROOT / "factorial" / name / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False)
        for name in VARIANTS}
    planning = np.load(ROOT / "B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz", allow_pickle=False)
    mess = np.load(OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz", allow_pickle=False)
    for name in VARIANTS:
        assert np.array_equal(arrays[name]["node_names"], planning["node_names"])
    assert np.array_equal(arrays["FULL_PQ_REPLAY"]["voltage_pu"], planning["Actual_V_pu"])
    with (ROOT / "B2_MAY01_VOLTAGE_VIOLATIONS.csv").open(encoding="utf-8-sig") as stream:
        original_cells = list(csv.DictReader(stream))
    rows = []
    for cell in original_cells:
        slot, node = int(cell["slot_0based"]), int(cell["node_axis_0based"])
        vfull, vp, vq, vz = [float(arrays[name]["voltage_pu"][slot, node]) for name in VARIANTS]
        station = cell["node"].removeprefix("mess_").removesuffix("_pcc").upper()
        indices = [i for i, location in enumerate(mess["locations"][slot].astype(str)) if location.upper() == station]
        taps = {name: arrays[name]["regulator_taps"][slot].tolist() for name in VARIANTS}
        row = dict(cell, VFull_PQ=vfull, VPonly_Qzero=vp, VQonly_Pzero=vq, Vzero_PQ=vz,
            P_effect_when_Qzero_pu=vp-vz, Q_effect_when_Pzero_pu=vq-vz,
            P_effect_when_Qoriginal_pu=vfull-vq, Q_effect_when_Poriginal_pu=vfull-vp,
            P_Q_interaction_pu=vfull-vp-vq+vz,
            full_MESS_effect_vs_zero_pu=vfull-vz,
            Planning_Actual_difference_pu=vfull-float(planning["Planning_V_pu"][slot,node]),
            station=station, local_MESS_units=[str(mess["unit_ids"][i]) for i in indices],
            local_original_MESS_P_kw=sum(float(mess["P_kw"][slot,i]) for i in indices),
            local_original_MESS_Q_kvar=sum(float(mess["Q_kvar"][slot,i]) for i in indices),
            all_original_MESS_P_kw=mess["P_kw"][slot].tolist(),
            all_original_MESS_Q_kvar=mess["Q_kvar"][slot].tolist(),
            all_original_MESS_locations=mess["locations"][slot].astype(str).tolist(),
            Full_taps=taps["FULL_PQ_REPLAY"], Ponly_taps=taps["P_ONLY_Q_ZERO"],
            Qonly_taps=taps["Q_ONLY_P_ZERO"], Zero_taps=taps["ZERO_PQ"],
            Full_vs_Zero_literal_tap_differences=int(np.count_nonzero(np.asarray(taps["FULL_PQ_REPLAY"]) != np.asarray(taps["ZERO_PQ"]))),
            Full_vs_Zero_different_regulators=int(np.count_nonzero(np.abs(np.asarray(taps["FULL_PQ_REPLAY"])-np.asarray(taps["ZERO_PQ"])) > 1e-12)))
        assert vfull == float(cell["Actual_V_pu"])
        rows.append(row)
    csv_write(ROOT / "B2_MAY01_19CELL_PQ_FACTORIAL.csv", rows)
    tap_rows, controls, tap_summary = [], {}, {}
    zero_taps = arrays["ZERO_PQ"]["regulator_taps"]
    for name in VARIANTS:
        taps = arrays[name]["regulator_taps"]
        observed = read(ROOT / "factorial" / name / "OBSERVED_CONTROL_ITERATIONS.json")
        assert taps.shape == (96,7)
        assert np.array_equal(arrays[name]["capacitor_states"], arrays["ZERO_PQ"]["capacitor_states"])
        controls[name] = dict(max_control_iterations=max(r["control_iterations"] for r in observed),
            max_electrical_iterations=max(r["electrical_iterations"] for r in observed),
            configured_max_control_iterations=sorted(set(r["configured_max_control_iterations"] for r in observed)),
            configured_max_electrical_iterations=sorted(set(r["configured_max_electrical_iterations"] for r in observed)),
            control_actions_done_slots=sum(r["control_actions_done"] for r in observed),
            raw_observation_receipt=receipt(ROOT / "factorial" / name / "OBSERVED_CONTROL_ITERATIONS.json"))
        tap_summary[name] = dict(literal_slot_regulator_differences_vs_zero=int(np.count_nonzero(taps != zero_taps)),
            physical_slot_regulator_differences_vs_zero=int(np.count_nonzero(np.abs(taps-zero_taps) > 1e-12)),
            physical_slots_different_vs_zero=int(np.count_nonzero(np.any(np.abs(taps-zero_taps) > 1e-12,axis=1))),
            maximum_absolute_tap_delta_vs_zero=float(np.abs(taps-zero_taps).max()),
            within_day_physical_tap_changes=int(np.count_nonzero(np.abs(np.diff(taps,axis=0)) > 1e-12)),
            fixed_capacitor_states_identical=True)
        for slot in range(96):
            for index, regulator in enumerate(names):
                tap_rows.append(dict(variant=name,slot_0based=slot,slot_1based=slot+1,regulator_transformer=regulator,
                    source_initial_tap=initial[regulator.lower()], actual_autonomous_tap=float(taps[slot,index]),
                    zero_PQ_autonomous_tap=float(zero_taps[slot,index]),delta_vs_zero=float(taps[slot,index]-zero_taps[slot,index]),
                    physical_tap_step_delta_vs_zero=int(round((taps[slot,index]-zero_taps[slot,index])/.00625)),
                    physical_changed_since_previous_slot=bool(slot and abs(taps[slot,index]-taps[slot-1,index]) > 1e-12),
                    forced_tap_changes=0,control_settings_changed=False))
    csv_write(ROOT / "B2_MAY01_FACTORIAL_TAP_TRAJECTORIES.csv", tap_rows)
    # Use original raw amperes and the unchanged B1 line-phase authority.
    # Stored normalized loading is checked as a receipt, not used as the metric.
    with LINE_AUTHORITY.open(encoding="utf-8-sig", newline="") as stream:
        line_limits = {r["branch_phase"]: float(r["NormalAmps"]) for r in csv.DictReader(stream)}
    assert len(line_limits) == 263 and all(x > 0 for x in line_limits.values())
    line_rows, raw_line_metrics = [], {}
    for name in VARIANTS:
        archive = arrays[name]
        selected = np.flatnonzero(archive["branch_kinds"].astype(str) == "line")
        keys = [f"{archive['branch_names'][i]}::{archive['branch_phases'][i]}" for i in selected]
        assert len(set(keys)) == 263 and set(keys) == set(line_limits)
        limits = np.asarray([line_limits[k] for k in keys], dtype=float)
        raw = np.abs(archive["phase_current_a"][:, selected]) / limits[None, :]
        stored = archive["phase_current_loading_pu"][:, selected]
        error = float(np.abs(raw-stored).max())
        assert error <= 5e-12
        slot, branch = np.unravel_index(int(np.argmax(raw)), raw.shape)
        metric = dict(variant=name, actual_maximum_line_loading_percent=float(100*raw[slot,branch]),
            peak_slot_0based=int(slot), peak_slot_1based=int(slot)+1,
            peak_branch_phase=keys[branch], peak_current_a=float(abs(archive["phase_current_a"][slot,selected[branch]])),
            peak_NormalAmps=float(limits[branch]), exact_line_phase_set_count=len(keys),
            line_current_violation_cells=int(np.count_nonzero(raw > 1.0)),
            maximum_stored_normalized_loading_error_pu=error,
            formula="100*max(abs(raw_phase_current_a)/unchanged_NormalAmps) over original 263 line phases and 96 slots",
            raw_AC_receipt=receipt(ROOT / "factorial" / name / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz"))
        expected = next(v for v in factorial["variants"] if v["variant"] == name)
        assert abs(metric["actual_maximum_line_loading_percent"]-expected["actual_maximum_line_loading_percent"]) <= 5e-10
        raw_line_metrics[name] = metric
        line_rows.append(metric)
    csv_write(ROOT / "B2_MAY01_FACTORIAL_RAW_LINE_LOADING.csv", line_rows)
    worst = max(rows,key=lambda row:row["VFull_PQ"])
    metadata = dict(schema="V42_DIAGNOSTIC_FACTORIAL_CELL_DECOMPOSITION_V1", diagnostic_only=True,
        original_violation_cells=len(rows), worst_original_cell=worst,
        original_19_cells_still_upper_violating={key:sum(row[key] > 1.05 for row in rows)
            for key in ("VFull_PQ", "VPonly_Qzero", "VQonly_Pzero", "Vzero_PQ")},
        original_19_conditional_effect_ranges_pu={key:[min(row[key] for row in rows),max(row[key] for row in rows)]
            for key in ("P_effect_when_Qzero_pu", "Q_effect_when_Pzero_pu", "P_effect_when_Qoriginal_pu", "Q_effect_when_Poriginal_pu", "P_Q_interaction_pu")},
        factorial_interpretation="Whole-day P/Q interventions including endogenous sequential control response; conditional effects are not linear sensitivity derivatives or isolated tap effects.",
        Planning_Actual_interpretation="Planning voltage is reconstructed from the original fixed affine FULL model. Actual is measured nonlinear OpenDSS with the unchanged enabled autonomous controls. These trajectories quantify the discrepancy, but do not identify an isolated contribution of tap changes without changing controls.",
        tap_summary=tap_summary, tap_comparison_semantics="Physical change threshold1e-12 pu, far below the unchanged original0.00625 tap step; exact array differences retained separately.",
        measured_diagnostic_control_counts=controls,
        raw_line_loading_metrics=raw_line_metrics,
        unchanged_B1_line_authority=receipt(LINE_AUTHORITY),
        historical_B1_B2_control_counts="UNKNOWN in original historical logs; new diagnostic observations are separate receipts.",
        files=[receipt(ROOT / "B2_MAY01_19CELL_PQ_FACTORIAL.csv"), receipt(ROOT / "B2_MAY01_FACTORIAL_TAP_TRAJECTORIES.csv"),
            receipt(ROOT / "B2_MAY01_FACTORIAL_RAW_LINE_LOADING.csv"), receipt(LINE_AUTHORITY),
            receipt(ROOT / "B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz"), receipt(OPS / "ACTUAL/ACTUAL_MESS_TRAJECTORY.npz"),
            receipt(ROOT / "FACTORIAL_REPLAY_STATUS.json"), receipt(__file__)])
    (ROOT / "B2_MAY01_FACTORIAL_CELL_AUDIT.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    for archive in arrays.values():archive.close()
    planning.close();mess.close()
    print(json.dumps({"original_cells":len(rows),"worst":worst,"tap_summary":tap_summary,"control_counts":controls},ensure_ascii=False))


if __name__ == "__main__":main()
