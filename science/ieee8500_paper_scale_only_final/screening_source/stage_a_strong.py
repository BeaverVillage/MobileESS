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

BG = (.40, .60)
AIDC = (2.20, 2.30, 2.40, 2.50, 2.60)


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


def case(bg, aidc, out_root=None):
    bg_text = f"{bg:.5f}"
    label = f"BG_{bg_text}_AIDC_{aidc:.2f}"
    out = (Path(out_root) if out_root is not None else HERE / "stage_a_strong") / label
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
            # The paper NPZ already contains the physical 2x AIDC image.
            # The user-specified absolute scale is target / 2.00.
            e.controls(np.r_[(aidc / 2.) * e.ap[t], np.zeros(48)])
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
    baseline = case(.5, 2.)
    expected = 0.8543958835735742
    assert baseline["AC_PASS"] and abs(baseline["rho"] - expected) < 1e-10
    save(HERE / "STAGE_A_STRONG_BASELINE_REGRESSION.json", {
        "status": "PASS", "aidc_scale": 2., "array_multiplier": 1.,
        "expected_rho": expected, "observed_rho": baseline["rho"],
        "paper_overlay_sha256": baseline["paper_overlay_sha256"]})
    results = [baseline]
    for aidc in AIDC:
        low, high = BG
        lower, upper = case(low, aidc), case(high, aidc)
        results.extend([lower, upper])
        assert lower["rho"] < .935 < upper["rho"], (aidc, lower["rho"], upper["rho"])
        for _ in range(9):
            mid = round((low + high) / 2., 5)
            row = case(mid, aidc)
            results.append(row)
            if row["rho"] < .935:
                low = mid
            else:
                high = mid
            if row["AC_PASS"] and .933 <= row["rho"] <= .937:
                break
        eligible_for_scale = [r for r in results if r["aidc_scale"] == aidc and
                              r["AC_PASS"] and .92 <= r["rho"] <= .95]
        print("ADAPTIVE_SCALE", aidc, "eligible", len(eligible_for_scale), flush=True)
        save(HERE / "STAGE_A_STRONG_RUNNING.json", {"status": "RUNNING", "results": results})
    cols = ("background_scale", "aidc_scale", "MESS_scale", "rho", "Vmin", "Vmax",
            "critical_line", "critical_slot", "transformer_current", "transformer_kva",
            "slots_completed", "AC_PASS", "wall_seconds")
    with (HERE / "STAGE_A_STRONG_FULL.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        writer.writerows({key: r.get(key) for key in cols} for r in results)
    eligible = [r for r in results if r["AC_PASS"] and .92 <= r["rho"] <= .95]
    by_scale = {}
    for row in eligible:
        scale = row["aidc_scale"]
        if scale not in by_scale or (abs(row["rho"] - .935), -row["Vmin"]) < (abs(by_scale[scale]["rho"] - .935), -by_scale[scale]["Vmin"]):
            by_scale[scale] = row
    top = sorted(by_scale.values(), key=lambda r: (-r["aidc_scale"], -r["Vmin"]))[:3]
    save(HERE / "STAGE_A_STRONG_TOP3.json", {"status": "COMPLETE", "selection": top,
        "eligible_count": len(eligible), "distinct_AIDC_scales": len(by_scale),
        "target": [0.92, 0.95], "array_multiplier": "target_AIDC_scale / 2.00"})
    print("STAGE_A_STRONG_COMPLETE", len(results), "eligible", len(eligible), flush=True)


if __name__ == "__main__":
    main()
