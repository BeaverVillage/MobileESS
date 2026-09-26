"""Freeze the scale-only screen result and forensic comparison."""
import csv
import json
from pathlib import Path

from forensic import HERE, ROOT, PAPER, RESITED, read, sha

ARCHIVE = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_MAY01_MESS6_RAW_RESULTS_20260914_151641.tar.gz")


def main():
    forensic = read(HERE / "FORENSIC_AUTHORITY.json")
    archive_audit = read(HERE / "RAW_ARCHIVE_AUDIT.json")
    assert archive_audit["all_identical"]
    rows = list(csv.DictReader((HERE / "STAGE_B_DIAGNOSTIC.csv").open(encoding="utf-8")))
    pass_rows = [r for r in rows if r["AC_PASS"] == "True" and r["natural_order"] == "True"]
    assert len(pass_rows) == 1
    selected = pass_rows[0]
    assert (float(selected["BG"]), float(selected["AIDC"]), float(selected["MESS"])) == (.525, 2.2, 1.)
    selection = {
        "status": "SCREEN_SELECTED_PRODUCTION_NOT_STARTED",
        "date": "2025-05-01", "BG_scale": .525, "AIDC_scale": 2.2,
        "MESS_scale": 1., "source": "PAPER_PRE_RESITING",
        "PAPER_CONFIG_RESTORED": True, "RESITED_PCC_USED": False,
        "FEEDER_MODIFIED": False, "SCALE_ONLY_MODIFICATION": True,
        "paper_PCC_inventory_sha256": sha(PAPER / "PCC_OVERLAY_INVENTORY.json"),
        "paper_overlay_sha256": sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
        "re_sited_PCC_inventory_sha256": sha(RESITED / "PCC_OVERLAY_INVENTORY.json"),
        "re_sited_overlay_sha256": sha(RESITED / "PCC_OVERLAY.dss"),
        "archive_sha256": sha(ARCHIVE), "archive_audit_sha256": sha(HERE / "RAW_ARCHIVE_AUDIT.json"),
        "diagnostic": {key: (float(value) if key in ("BG", "AIDC", "MESS", "B0_exact_rho",
                            "B1_exact_rho", "B2_exact_rho", "B3_exact_rho", "Vmin", "Vmax",
                            "B0_minus_B3", "B2_minus_B3") else value)
                       for key, value in selected.items()},
        "diagnostic_limit": "Frozen paper DA schedules; neither new optimization nor Actual outcome.",
        "strict_actual_SOC_gate": True,
        "prior_paper_B3_Emin_exception_kWh": forensic["paper_B3_Emin_exception_kWh"],
    }
    (HERE / "SELECTION.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    f = forensic["paper_mapping"]
    r = forensic["resited_mapping"]
    lines = [
        "# IEEE8500 paper authority and scale-only screening",
        "", "## Authority", "",
        "- Source: 2025-05-01 paper Table X production; original six-MESS PCC mapping.",
        "- Raw archive SHA-256: `" + selection["archive_sha256"] + "` (" + str(ARCHIVE.stat().st_size) + " bytes).",
        "- Seven selected archive members, including B0–B3 Actual AC summaries, mapping freeze, PCC inventory and final result, are byte-identical to the paper files on disk.",
        "- Historical inherited-source manifest: " + str(forensic["historical_manifest_checked"]) + " records SHA verified; no missing or mismatched file.",
        "- Table X source Actual rho: " + ", ".join(f"{p}={v:.8f}" for p, v in forensic["paper_result"].items()) + ".",
        "- Paper PCC overlay SHA-256: `" + selection["paper_overlay_sha256"] + "`; re-sited overlay SHA-256: `" + selection["re_sited_overlay_sha256"] + "`.",
        "- Paper canonical 36-PCC mapping SHA-256: `" + forensic["paper_mapping_canonical_sha256"] + "`; re-sited: `" + forensic["resited_mapping_canonical_sha256"] + "`.",
        "- Native feeder source and regulator/capacitor/PV files are individually hashed in `FORENSIC_AUTHORITY.json`.",
        "", "## Station → electrical PCC comparison", "",
        "| Station | Paper host | Re-sited host | Changed |", "|---|---|---|---|",
    ]
    for station in [f"STA{i:02}" for i in range(1, 13)] + [f"AIDC{i:02}" for i in range(1, 13)]:
        key = "MESS:" + station
        a, b = f[key], r[key]
        changed = a["host_bus"] != b["host_bus"] or a["phases"] != b["phases"]
        lines.append(f"| {station} | `{a['host_bus']}` ({a['phases']}φ) | `{b['host_bus']}` ({b['phases']}φ) | {'YES' if changed else 'no'} |")
    lines += ["", "AIDC load PCC difference: AIDC02 `d6023352-1_int` (paper) → `e184626` (re-sited). The other 11 AIDC load hosts are equal.",
              "", "## Stage A", "",
              "The requested 25 BG/AIDC points were all exact 96-slot AC PASS; none reached the 0.87–0.90 band (maximum 0.8188618622). Adjacent BG refinement found:",
              "", "| BG | AIDC | B0 exact rho | Vmin | Vmax | Critical slot | AC |", "|---:|---:|---:|---:|---:|---:|---|" ]
    for row in read(HERE / "STAGE_A_SELECTED_TOP3.json")["selection"]:
        lines.append(f"| {row['background_scale']:.3f} | {row['aidc_scale']:.2f} | {row['rho']:.9f} | {row['Vmin']:.6f} | {row['Vmax']:.6f} | {row['critical_slot']} | PASS |")
    lines += ["", "## Stage B: fixed paper DA schedule diagnostic", "",
              "MESS P/S/E limits scale uniformly; efficiency, route, mobility energy and station/PCC identities do not change. This diagnostic proportionally scales the frozen paper P/Q. It does not certify a newly optimized policy or Actual.",
              "", "| BG | AIDC | MESS | B0 | B1 | B2 | B3 | Vmin | Vmax | AC | Natural order |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for row in rows:
        lines.append("| " + " | ".join([
            f"{float(row['BG']):.3f}", f"{float(row['AIDC']):.2f}", f"{float(row['MESS']):.1f}",
            *[f"{float(row[p+'_exact_rho']):.6f}" for p in ("B0", "B1", "B2", "B3")],
            f"{float(row['Vmin']):.6f}", f"{float(row['Vmax']):.6f}",
            "PASS" if row["AC_PASS"] == "True" else "FAIL", "YES" if row["natural_order"] == "True" else "no",
        ]) + " |")
    lines += ["", "**Selected for one full production:** BG=0.525, AIDC=2.20, MESS=1.0. The frozen-schedule diagnostic has B0−B3=0.0140804653 and B2−B3=0.0034372629. The MESS 1.5/2.0 proportional-dispatch failures are voltage failures of that diagnostic dispatch, not a proof of optimization infeasibility.",
              "", "The paper B3 Actual had a 0.0013131923 kWh MESS06 Emin shortfall. Any new production result with any SOC/energy violation must fail the physically clean gate; the historical exception is not imported as an allowance.",
              "", "## Status", "", "```ini", "PAPER_CONFIG_RESTORED = TRUE", "RESITED_PCC_USED = FALSE", "FEEDER_MODIFIED = FALSE", "SCALE_ONLY_MODIFICATION = TRUE", "FULL_PRODUCTION_COMPLETE = FALSE", "```", ""]
    (HERE / "FORENSIC_AND_SCREEN_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("REPORT_WRITTEN", len(rows), "stage B rows")


if __name__ == "__main__":
    main()
