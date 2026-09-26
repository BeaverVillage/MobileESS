"""Scale-only, fixed-paper-schedule B1 diagnostic with exact OpenDSS.

This is a diagnostic replay, not production optimization or a new Actual run.
It keeps paper jobs, routes, PCCs and P/Q shape frozen while scaling permitted
ratings and physical injections. New production must optimize once selected.
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
sys.dont_write_bytecode = True
import numpy as np

from forensic import HERE, ROOT, read, sha

PAPER = ROOT / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
BASE = ROOT / "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913"
sys.path.insert(0, str(PAPER))
from electrical_engine import Engine  # noqa: E402
import electrical_engine as paper_engine  # noqa: E402

CONTROL_FILES = {
    "B0": BASE / "B0/DA_FINAL_96/CONTROLS.npz",
    "B1": BASE / "B1/DA_FINAL_96/CONTROLS.npz",
    "B2": PAPER / "B2/physical_closure/accepted_clean_exact/CONTROLS.npz",
    "B3": PAPER / "B3/final_exact/CONTROLS.npz",
}
DA_AUTHORITY = {
    "B0": BASE / "B0/DA_FINAL_96/AC_VALIDATION.json",
    "B1": BASE / "B1/DA_FINAL_96/AC_VALIDATION.json",
    "B2": PAPER / "B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json",
    "B3": PAPER / "B3/final_exact/AC_VALIDATION.json",
}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_controls(policy):
    with np.load(CONTROL_FILES[policy], allow_pickle=False) as z:
        x = z["x"].copy()
    assert x.shape == (96, 60)
    return x


def run(policy, bg, aidc, mess, label):
    folder = HERE / "stage_b_strong" / label / policy
    if (folder / "RESULT.json").is_file():
        return read(folder / "RESULT.json")
    start = time.perf_counter()
    base = source_controls(policy)
    # Uniformly scale the paper physical demand and MESS P/Q. The frozen paper
    # control trajectory is diagnostic; no route or job is reoptimized here.
    x = base.copy()
    x[:, :12] *= aidc / 2.
    x[:, 12:] *= mess
    # A PCC column aggregates any simultaneously connected vehicles, so PCS
    # ratings apply to each vehicle in FINAL_AUTHORITY, not to the column sum.
    if policy in ("B2", "B3"):
        trajectory = read(PAPER / policy / "FINAL_AUTHORITY.json")["trajectory_slots"]
        assert len(trajectory) == 96 * 6
        assert all(abs(r["p_kw"] * mess) <= 300 * mess + 1e-6 and
                   (r["p_kw"] * mess) ** 2 + (r["q_kvar"] * mess) ** 2 <= (400 * mess) ** 2 + 1e-5
                   for r in trajectory)
    e = Engine(folder / "runtime")
    rows = []
    try:
        for t in range(96):
            paper_engine.s.old.inputs(e.d, e.loads, e.P, e.Q, e.ap, e.aq,
                                      bg, e.md, e.mpv, e.ratio, t)
            for i in range(len(e.loads)):
                e.d.Generators.Name(f"op8500_pv_{i:04d}")
                pv_kw = float(.5 * e.ratio * e.P[i] * e.mpv[t])
                e.d.CktElement.Enabled(pv_kw > 0)
                if pv_kw > 0:
                    e.d.Generators.kW(pv_kw)
                    e.d.Generators.kvar(0.)
            e.controls(x[t])
            e.d.Solution.SolveSnap()
            converged = bool(e.d.Solution.Converged())
            settled = bool(e.d.Solution.ControlActionsDone())
            error = int(e.d.Error.Number())
            if not converged or error:
                rows.append({"slot": t, "converged": converged,
                             "controls_settled": settled, "dss_error": error, "AC_PASS": False})
                break
            v2, line, tx, apparent = e.arrays()
            volts = np.sqrt(v2)
            line_abs = np.abs(line)
            tx_abs = np.abs(tx)
            kva = np.abs(apparent) / e.ax["kva_rating"]
            li = int(line_abs.argmax())
            row = {"slot": t, "rho": float(line_abs[li]), "Vmin": float(volts.min()),
                   "Vmax": float(volts.max()), "transformer_current": float(tx_abs.max()),
                   "transformer_kva": float(kva.max()),
                   "critical_line": str(e.ax["line_label"][li]),
                   "converged": True, "controls_settled": settled, "dss_error": 0}
            row["AC_PASS"] = (settled and row["Vmin"] >= .95 - 1e-9
                              and row["Vmax"] <= 1.05 + 1e-9
                              and max(row["rho"], row["transformer_current"], row["transformer_kva"]) <= 1 + 1e-9)
            rows.append(row)
    finally:
        e.close()
    critical = max(rows, key=lambda r: r.get("rho", -1))
    high_slots = [r for r in rows if r["slot"] in set(range(34, 54)) | set(range(68, 86))]
    result = {
        "policy": policy, "BG": bg, "AIDC": aidc, "MESS": mess,
        "kind": "FROZEN_PAPER_DA_SCHEDULE_DIAGNOSTIC_NOT_PRODUCTION",
        "source_controls": str(CONTROL_FILES[policy]),
        "source_controls_sha256": sha(CONTROL_FILES[policy]),
        "Pmax_kW": 300 * mess, "Smax_kVA": 400 * mess,
        "capacity_kWh": 1200 * mess, "Emin_kWh": 440 * mess,
        "Emax_kWh": 1080 * mess, "E0_kWh": 760 * mess,
        "ET_kWh": 760 * mess, "efficiency": .95,
        "travel_energy_semantics": "unchanged; not reoptimized in this diagnostic",
        "slots_completed": len(rows), "rho": critical.get("rho"),
        "Vmin": min((r.get("Vmin", float("inf")) for r in rows), default=None),
        "Vmax": max((r.get("Vmax", -float("inf")) for r in rows), default=None),
        "transformer_current": max((r.get("transformer_current", 0) for r in rows), default=None),
        "transformer_kva": max((r.get("transformer_kva", 0) for r in rows), default=None),
        "critical_line": critical.get("critical_line"), "critical_slot": critical["slot"],
        "AC_PASS": len(rows) == 96 and all(r["AC_PASS"] for r in rows),
        "high_loading_windows_slots": len(high_slots),
        "high_loading_windows_rho": max((r["rho"] for r in high_slots), default=None),
        "wall_seconds": time.perf_counter() - start, "rows": rows,
    }
    save(folder / "RESULT.json", result)
    print(label, mess, policy, "rho", result["rho"], "AC", result["AC_PASS"], flush=True)
    return result


def main():
    assert read(HERE / "FORENSIC_AUTHORITY.json")["PAPER_CONFIG_RESTORED"]
    assert sha(PAPER / "IEEE8500_PCC_Overlay.dss") == "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"
    choices = read(HERE / "STAGE_A_STRONG_REFINED_TOP3.json")["selection"]
    summary = []
    for choice in choices:
        label, bg, aidc = choice["label"], choice["background_scale"], choice["aidc_scale"]
        policies = {policy: run(policy, bg, aidc, 1., label) for policy in ("B0", "B1")}
        row = {"BG": bg, "AIDC": aidc,
               "B0_exact_rho": policies["B0"]["rho"],
               "B1_diagnostic_exact_rho": policies["B1"]["rho"],
               "B0_minus_B1": policies["B0"]["rho"] - policies["B1"]["rho"],
               "Vmin": min(policies[p]["Vmin"] for p in policies),
               "Vmax": max(policies[p]["Vmax"] for p in policies),
               "critical_line": max(policies.values(), key=lambda r: r["rho"])["critical_line"],
               "critical_slot": max(policies.values(), key=lambda r: r["rho"])["critical_slot"],
               "AC_PASS": all(r["AC_PASS"] for r in policies.values()),
               "kind": "FROZEN_PAPER_B1_SCHEDULE_DIAGNOSTIC_NOT_PRODUCTION"}
        summary.append(row)
        save(HERE / "STAGE_B_STRONG_RUNNING.json", {"status": "RUNNING", "rows": summary})
    cols = ("BG", "AIDC", "B0_exact_rho", "B1_diagnostic_exact_rho", "B0_minus_B1",
            "Vmin", "Vmax", "critical_line", "critical_slot", "AC_PASS")
    with (HERE / "STAGE_B_STRONG.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        writer.writerows({key: r[key] for key in cols} for r in summary)
    save(HERE / "STAGE_B_STRONG_COMPLETE.json", {"status": "COMPLETE", "rows": summary})


if __name__ == "__main__":
    main()
