"""Paper-PCC, 96-slot exact OpenDSS B0 scale screen; no optimization."""
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PAPER = ROOT / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
sys.path.insert(0, str(PAPER))
from electrical_engine import Engine, PF_TAN  # noqa: E402
import electrical_engine as paper_engine  # noqa: E402
from forensic import read, sha  # noqa: E402

BG = (.44, .45, .46, .47, .48)
AIDC = (1.75, 1.90, 2.00, 2.10, 2.20)


def authority_guard():
    audit = read(HERE / "FORENSIC_AUTHORITY.json")
    assert audit["PAPER_CONFIG_RESTORED"] and not audit["RESITED_PCC_USED"]
    records = {Path(r["path"]): r["sha256"] for r in audit["core_records"]}
    for path in (PAPER / "PCC_Master.dss", PAPER / "PCC_OVERLAY_INVENTORY.json",
                 PAPER / "IEEE8500_PCC_Overlay.dss", PAPER / "MAY01_B0_AIDC_POWER.npz",
                 PAPER / "D1_AEMO_VIC1_FORECAST.json", PAPER / "SCREENING_RULE.json",
                 PAPER / "electrical_engine.py"):
        assert sha(path) == records[path], path
    assert sha(PAPER / "PCC_OVERLAY_INVENTORY.json") == "5aeafee6eae2add1bb32e00617c3528f571d4407fbcc8d1f010b0dd2bf46e88d"
    assert sha(PAPER / "IEEE8500_PCC_Overlay.dss") == "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def case(bg, aidc):
    bg_text = f"{bg:.2f}" if abs(bg - round(bg, 2)) < 1e-10 else f"{bg:.3f}"
    label = f"BG_{bg_text}_AIDC_{aidc:.2f}"
    out = HERE / "stage_a_relative" / label
    if (out / "RESULT.json").exists():
        result = read(out / "RESULT.json")
        assert result["background_scale"] == bg and result["aidc_scale"] == aidc
        return result
    start = time.perf_counter()
    e = Engine(out / "runtime")
    rows = []
    try:
        for t in range(96):
            # The paper engine supplies the unchanged native load spatial pattern,
            # May-1 forecast shape, PV allocation, PCCs, and automatic controls.
            paper_engine.s.old.inputs(e.d, e.loads, e.P, e.Q, e.ap, e.aq,
                                      bg, e.md, e.mpv, e.ratio, t)
            for i in range(len(e.loads)):
                e.d.Generators.Name(f"op8500_pv_{i:04d}")
                pv_kw = float(.5 * e.ratio * e.P[i] * e.mpv[t])
                e.d.CktElement.Enabled(pv_kw > 0)
                if pv_kw > 0:
                    e.d.Generators.kW(pv_kw)
                    e.d.Generators.kvar(0.)
            # This paper NPZ already contains the physical 2x AIDC image.
            # Requested AIDC scale multiplies the paper physical 2x image.
            e.controls(np.r_[aidc * e.ap[t], np.zeros(48)])
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
            row = {
                "slot": t, "rho": float(line_abs.max()),
                "Vmin": float(volts.min()), "Vmax": float(volts.max()),
                "transformer_current": float(tx_abs.max()),
                "transformer_kva": float(kva.max()),
                "critical_line": str(e.ax["line_label"][li]),
                "converged": True, "controls_settled": settled, "dss_error": 0,
            }
            row["AC_PASS"] = (settled and row["Vmin"] >= .95 - 1e-9
                              and row["Vmax"] <= 1.05 + 1e-9
                              and max(row["rho"], row["transformer_current"], row["transformer_kva"]) <= 1 + 1e-9)
            rows.append(row)
    finally:
        e.close()
    critical = max(rows, key=lambda r: r.get("rho", -1))
    result = {
        "label": label, "background_scale": bg, "aidc_scale": aidc,
        "MESS_scale": 1., "PV_scale": .5, "slots_completed": len(rows),
        "rho": critical.get("rho"),
        "Vmin": min((r.get("Vmin", float("inf")) for r in rows), default=None),
        "Vmax": max((r.get("Vmax", -float("inf")) for r in rows), default=None),
        "transformer_current": max((r.get("transformer_current", 0) for r in rows), default=None),
        "transformer_kva": max((r.get("transformer_kva", 0) for r in rows), default=None),
        "critical_line": critical.get("critical_line"), "critical_slot": critical["slot"],
        "AC_PASS": len(rows) == 96 and all(r["AC_PASS"] for r in rows),
        "wall_seconds": time.perf_counter() - start,
        "paper_overlay_sha256": sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
        "rows": rows,
    }
    save(out / "RESULT.json", result)
    print(label, "rho", result["rho"], "AC", result["AC_PASS"], "seconds", round(result["wall_seconds"], 2), flush=True)
    return result


def main():
    authority_guard()
    pairs = [(bg, aidc) for bg in BG for aidc in AIDC]
    if "--baseline-only" in sys.argv:
        pairs = [(.5, 1.)]
    elif "--refine" in sys.argv:
        pairs = [(bg, aidc) for bg in (.50, .51, .52, .53) for aidc in (2.10, 2.20)]
    elif "--fine" in sys.argv:
        pairs = [(bg, 2.20) for bg in (.515, .525)]
    results = []
    for bg, aidc in pairs:
        results.append(case(bg, aidc))
        cols = ("background_scale", "aidc_scale", "MESS_scale", "rho", "Vmin", "Vmax",
                "critical_line", "critical_slot", "transformer_current", "transformer_kva",
                "slots_completed", "AC_PASS", "wall_seconds")
        csv_name = ("STAGE_A_RELATIVE_BASELINE.csv" if "--baseline-only" in sys.argv else
                    "STAGE_A_RELATIVE_FINE.csv" if "--fine" in sys.argv else
                    "STAGE_A_RELATIVE_REFINED.csv" if "--refine" in sys.argv else "STAGE_A_RELATIVE_FULL.csv")
        with (HERE / csv_name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=cols)
            writer.writeheader()
            writer.writerows({key: r.get(key) for key in cols} for r in results)
    if "--baseline-only" not in sys.argv:
        eligible = [r for r in results if r["AC_PASS"] and .87 <= r["rho"] <= .90]
        top = sorted(eligible, key=lambda r: (-r["aidc_scale"], -r["rho"], r["background_scale"]))[:3]
        top_name = ("STAGE_A_RELATIVE_FINE_TOP3.json" if "--fine" in sys.argv else
                    "STAGE_A_RELATIVE_REFINED_TOP3.json" if "--refine" in sys.argv else "STAGE_A_RELATIVE_TOP3.json")
        save(HERE / top_name, {"status": "COMPLETE", "selection": top,
                                          "eligible_count": len(eligible)})
        print("STAGE_A_COMPLETE", len(results), "eligible", len(eligible), flush=True)


if __name__ == "__main__":
    main()
