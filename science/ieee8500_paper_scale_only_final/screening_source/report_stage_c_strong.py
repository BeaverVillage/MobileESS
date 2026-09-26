"""Freeze screened operating point and distinguish diagnostics from production."""
import json
from pathlib import Path
from stage_a_strong import HERE, PAPER, authority_guard, read, sha


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def metrics(path):
    x = read(path)
    return {k: x[k] for k in ("rho", "Vmin", "Vmax", "critical_line", "critical_slot",
             "transformer_current", "transformer_kva", "max_abs_P", "max_abs_Q",
             "SOC_min", "SOC_max", "AC_PASS", "paper_overlay_sha256")}


def main():
    authority_guard()
    point = read(HERE / "STAGE_B_STRONG_TOP2.json")["selection"][0]
    assert point["aidc_scale"] == 2.4 and point["background_scale"] == .54688
    b = next(r for r in read(HERE / "STAGE_B_STRONG_COMPLETE.json")["rows"]
             if r["AIDC"] == 2.4)
    root = HERE / "stage_c_strong"
    sources = {
        1.0: (root / "results_local" / point["label"] / "MESS_1.00" / "RADIUS_10" / "B2" / "EXACT_AC.json",
              root / "results_local" / point["label"] / "MESS_1.00" / "RADIUS_30" / "B3" / "EXACT_AC.json"),
    }
    for scale in (1.25, 1.5, 1.75, 2.0):
        sources[scale] = (
            root / "results_local" / point["label"] / f"MESS_{scale:.2f}" / "RADIUS_1" / "B2" / "EXACT_AC.json",
            root / "results_q_repair_trials" / point["label"] / f"MESS_{scale:.2f}" / "RADIUS_100" /
            "QDELTA_350_THROUGH_87" / "B3" / "EXACT_AC.json")
    rows = []
    for scale, (p2, p3) in sources.items():
        x2, x3 = metrics(p2), metrics(p3)
        assert x2["paper_overlay_sha256"] == x3["paper_overlay_sha256"] == sha(PAPER / "IEEE8500_PCC_Overlay.dss")
        row = dict(BG=b["BG"], AIDC=b["AIDC"], MESS=scale,
                   B0=b["B0_exact_rho"], B1_diagnostic=b["B1_diagnostic_exact_rho"],
                   B2_diagnostic=x2["rho"], B3_diagnostic=x3["rho"],
                   B0_minus_B1=b["B0_minus_B1"],
                   B0_minus_B2=b["B0_exact_rho"]-x2["rho"],
                   B0_minus_B3=b["B0_exact_rho"]-x3["rho"],
                   B2_minus_B3=x2["rho"]-x3["rho"],
                   Vmin=min(b["Vmin"], x2["Vmin"], x3["Vmin"]),
                   Vmax=max(b["Vmax"], x2["Vmax"], x3["Vmax"]),
                   B2=x2, B3=x3, all_exact_AC_PASS=b["AC_PASS"] and x2["AC_PASS"] and x3["AC_PASS"],
                   natural_order=b["B0_exact_rho"] > b["B1_diagnostic_exact_rho"] > x2["rho"] > x3["rho"],
                   B2_evidence=dict(path=str(p2), sha256=sha(p2)),
                   B3_evidence=dict(path=str(p3), sha256=sha(p3)))
        rows.append(row)
    eligible = [r for r in rows if r["all_exact_AC_PASS"] and r["natural_order"]]
    assert eligible
    selected = sorted(eligible, key=lambda r: (-r["B0_minus_B3"], r["MESS"]))[0]
    assert selected["MESS"] == 1.5
    freeze = dict(status="SCREENING_CANDIDATE_FROZEN_PRODUCTION_NOT_RUN", date="2025-05-01",
                  BG_scale=selected["BG"], AIDC_absolute_scale=selected["AIDC"], MESS_rating_scale=selected["MESS"],
                  AIDC_array_multiplier=selected["AIDC"]/2.,
                  base_MESS=dict(Pmax_kW=300., Smax_kVA=400., capacity_kWh=1200., Emin_kWh=440., Emax_kWh=1080., initial_terminal_kWh=760.),
                  scaled_MESS=dict(Pmax_kW=300.*selected["MESS"], Smax_kVA=400.*selected["MESS"], capacity_kWh=1200.*selected["MESS"], Emin_kWh=440.*selected["MESS"], Emax_kWh=1080.*selected["MESS"], initial_terminal_kWh=760.*selected["MESS"]),
                  diagnostic_metrics={k: selected[k] for k in ("B0", "B1_diagnostic", "B2_diagnostic", "B3_diagnostic", "B0_minus_B1", "B0_minus_B2", "B0_minus_B3", "B2_minus_B3", "Vmin", "Vmax")},
                  paper_overlay_sha256=sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
                  actual_baseline_parity_sha256=sha(HERE / "ACTUAL_PIPELINE_PARITY_FREEZE.json"),
                  B2_evidence=selected["B2_evidence"], B3_evidence=selected["B3_evidence"],
                  diagnostic_limitations=["Frozen paper MESS routes; new critical-window P/Q only",
                                          "Uniform local trust radius for numerical linearization",
                                          "B3 exact-AC Q feasibility restoration at slots 81-87",
                                          "B1 reused paper schedule; B1/B2/B3 require fresh full production"],
                  PAPER_PCC_CONFIG_USED=True, RESITING_USED=False, SCALE_ONLY_CHANGE=True,
                  AIDC_DOUBLE_SCALING=False, Actual_screening_repetitions=0)
    b26 = next(r for r in read(HERE / "STAGE_B_STRONG_COMPLETE.json")["rows"] if r["AIDC"] == 2.6)
    save(HERE / "STAGE_C_STRONG_SCREEN_COMPLETE.json", dict(status="COMPLETE_WITH_EARLY_PRUNING_OF_AIDC_2P60",
         selected=selected, rows=rows, AIDC_2P60=dict(B0=b26["B0_exact_rho"],
         note="Stage B B0-B1 is negative at AIDC 2.60; new P/Q diagnostic at MESS 1.0 and 2.0 also failed exact AC. Pruned before full scale grid.",
         B0_minus_B1=b26["B0_minus_B1"]),
         kind="screening diagnostics, no production result"))
    save(HERE / "FINAL_SCALE_CANDIDATE_FREEZE.json", freeze)
    print(selected["BG"], selected["AIDC"], selected["MESS"], selected["B0_minus_B3"], selected["B2_minus_B3"])


if __name__ == "__main__":
    main()
