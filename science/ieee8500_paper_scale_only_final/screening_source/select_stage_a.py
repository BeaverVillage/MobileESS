"""Freeze the three highest-AIDC-share B0 points inside the exact target band."""
import json
from pathlib import Path

from forensic import HERE, sha


def main():
    labels = ("BG_0.515_AIDC_2.20", "BG_0.52_AIDC_2.20", "BG_0.525_AIDC_2.20")
    rows = []
    for label in labels:
        path = HERE / "stage_a_corrected" / label / "RESULT.json"
        row = json.loads(path.read_text(encoding="utf-8"))
        assert row["AC_PASS"] and row["slots_completed"] == 96 and .87 <= row["rho"] <= .90
        rows.append({key: row[key] for key in ("label", "background_scale", "aidc_scale",
                   "rho", "Vmin", "Vmax", "critical_line", "critical_slot",
                   "transformer_current", "transformer_kva", "AC_PASS")})
        rows[-1]["source_sha256"] = sha(path)
    output = {"status": "FROZEN", "selection": rows, "rule": "all 96-slot exact AC PASS; AIDC 2.20 maximum screened share; B0 0.87-0.90", "paper_PCC_only": True}
    (HERE / "STAGE_A_SELECTED_TOP3.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SELECTED", *(row["label"] for row in rows))


if __name__ == "__main__":
    main()
