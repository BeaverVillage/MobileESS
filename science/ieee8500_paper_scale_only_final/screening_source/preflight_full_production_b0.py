"""Independent fresh production-input B0 exact replay before long searches."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from stage_a_strong import HERE, PAPER, authority_guard, read, sha

DEST = HERE / "full_production_paper_BG054688_AIDC240_MESS150"


def main():
    authority_guard()
    sys.path.insert(0, str(DEST))
    spec = importlib.util.spec_from_file_location("paper_scale_production_engine", DEST / "electrical_engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Engine = module.Engine
    preflight = DEST / "B0_PRODUCTION_INPUT_PREFLIGHT_RETRY1"
    e = Engine(preflight / "runtime")
    rows = []
    try:
        for t in range(96):
            e.inputs(t)
            e.solve()
            v2, line, tx, apparent = e.arrays()
            v, rho = np.sqrt(v2), np.abs(line)
            row = dict(slot=t, rho=float(rho.max()), Vmin=float(v.min()), Vmax=float(v.max()),
                       tx_current=float(np.abs(tx).max()),
                       tx_kva=float((np.abs(apparent)/e.ax["kva_rating"]).max()),
                       critical_line=str(e.ax["line_label"][int(rho.argmax())]),
                       converged=bool(e.d.Solution.Converged()),
                       controls_settled=bool(e.d.Solution.ControlActionsDone()))
            row["AC_PASS"] = (row["converged"] and row["controls_settled"] and
                              row["Vmin"] >= .95 and row["Vmax"] <= 1.05 and
                              max(row["rho"], row["tx_current"], row["tx_kva"]) <= 1.)
            rows.append(row)
    finally:
        e.close()
    critical = max(rows, key=lambda r:r["rho"])
    result = dict(status="PASS" if len(rows)==96 and all(r["AC_PASS"] for r in rows) else "FAIL",
                  rho=critical["rho"], Vmin=min(r["Vmin"] for r in rows),
                  Vmax=max(r["Vmax"] for r in rows), critical_slot=critical["slot"],
                  critical_line=critical["critical_line"],
                  paper_overlay_sha256=sha(DEST / "IEEE8500_PCC_Overlay.dss"),
                  production_source_master_sha256=sha(DEST / "PCC_Master.dss"),
                  production_power_sha256=sha(DEST / "MAY01_B0_AIDC_POWER.npz"),
                  rows=rows)
    target = read(HERE / "FINAL_SCALE_CANDIDATE_FREEZE.json")["diagnostic_metrics"]["B0"]
    result["screening_B0_rho"] = target
    result["absolute_difference"] = abs(result["rho"]-target)
    result["parity_PASS"] = result["status"]=="PASS" and result["absolute_difference"]<1e-10
    out=preflight / "RESULT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(result["rho"], result["Vmin"], result["parity_PASS"])
    assert result["parity_PASS"]


if __name__ == "__main__":
    main()
