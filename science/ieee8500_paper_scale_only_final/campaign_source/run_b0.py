"""Fresh B0 exact OpenDSS under the frozen final paper configuration."""
from bootstrap import *
import traceback


def main():
    protect()
    freeze = read(H / "FINAL_CANDIDATE_FREEZE.json")
    assert freeze["PAPER_PCC_CONFIG_USED"] and freeze["BG_SCALE"] == .552
    with np.load(H / "MAY01_B0_AIDC_POWER.npz") as data:
        pcc = data["pcc"].copy()
    from electrical_engine import Engine
    engine = Engine(H / "B0/DA_exact/runtime")
    rows, states, anchors = [], [], []
    try:
        for slot in range(96):
            engine.inputs(slot)
            engine.solve()
            a = engine.arrays()
            anchors.append(a)
            states.append(engine.state(slot))
            voltage = np.sqrt(a[0]); line = np.abs(a[1]); tx = np.abs(a[2])
            kva = np.abs(a[3]) / np.asarray(AX["winding_rating_kVA"])
            rows.append(dict(slot=slot, Vmin_pu=float(voltage.min()), Vmax_pu=float(voltage.max()),
                             max_phase_line_loading_pu=float(line.max()),
                             max_transformer_phase_current_pu=float(tx.max()),
                             max_transformer_winding_kva_pu=float(kva.max()),
                             converged=True, controls_settled=bool(engine.d.Solution.ControlActionsDone()),
                             line_witness=AX["line"][int(line.argmax())]))
    finally:
        engine.close()
    for row in rows:
        row["feasible"] = (row["controls_settled"] and row["Vmin_pu"] >= .95 - 1e-9 and
                           row["Vmax_pu"] <= 1.05 + 1e-9 and
                           max(row[key] for key in ("max_phase_line_loading_pu",
                                                     "max_transformer_phase_current_pu",
                                                     "max_transformer_winding_kva_pu")) <= 1 + 1e-9)
    names = ("Vmin_pu", "Vmax_pu", "max_phase_line_loading_pu",
             "max_transformer_phase_current_pu", "max_transformer_winding_kva_pu")
    metrics = {name: (min if name == "Vmin_pu" else max)(row[name] for row in rows) for name in names}
    report = dict(status="PASS" if all(row["feasible"] for row in rows) else "FAIL",
                  metrics=metrics, slots=rows, alpha8500=.552, paper_overlay_sha256=freeze["paper_overlay_sha256"])
    save(H / "B0/DA_exact/AC_VALIDATION.json", report)
    save(H / "B0_REPLAY/CONTROL_STATES.json", states)
    np.savez_compressed(H / "B0_REPLAY/ANCHORS.npz", control_names=np.asarray(NAMES),
                        x=np.c_[pcc, np.zeros((96, 48))],
                        v2=np.asarray([a[0] for a in anchors]),
                        line=np.asarray([a[1] for a in anchors]),
                        tx=np.asarray([a[2] for a in anchors]),
                        S=np.asarray([a[3] for a in anchors]))
    assert report["status"] == "PASS"
    rho = metrics["max_phase_line_loading_pu"]
    assert abs(rho - .9469122681695561) < 1e-8, rho
    save(H / "B0/COMPLETE.json", dict(status="PASS", stage="B0_DA_EXACT",
                                      rho=rho, validation=record(H / "B0/DA_exact/AC_VALIDATION.json")))
    print("B0_EXACT_PASS", rho, flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        save(H / "B0/FAILURE.json", dict(error=repr(exc), traceback=traceback.format_exc()))
        raise
