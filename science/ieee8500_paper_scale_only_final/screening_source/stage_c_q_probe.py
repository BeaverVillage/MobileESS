"""Read-only exact AC response to one proposed diagnostic reactive change."""
import sys
import numpy as np
from stage_c_strong_local import Engine, HERE, SERVICE_INDEX, read, pcc_for, configure


def probe(point, dispatch, policy, slot, mess_id, delta):
    by = {(r["mess_id"], r["slot"]): r for r in dispatch}
    pcc = pcc_for(policy) * (point["aidc_scale"] / 2.)
    e = Engine(HERE / "stage_c_strong" / "probe_runtime")
    try:
        for t in range(slot + 1):
            configure(e, t, point["background_scale"])
            x = np.r_[pcc[t], np.zeros(48)]
            for mid in sorted({r["mess_id"] for r in dispatch}):
                r = by[mid, t]
                if r["mode"] == "CONNECTED":
                    i = SERVICE_INDEX[r["service_id"]]
                    x[12 + i] += r["p_kw"]
                    x[36 + i] += r["q_kvar"] + (delta if t == slot and mid == mess_id else 0.)
            e.controls(x)
            e.d.Solution.SolveSnap()
            assert e.d.Solution.Converged() and e.d.Error.Number() == 0
        v2, line, tx, apparent = e.arrays()
        v = np.sqrt(v2)
        i = int(v.argmin())
        return dict(slot=slot, mess_id=mess_id, delta_Q_kvar=delta, Vmin=float(v[i]),
                    low_node=str(e.nodes[i]), rho=float(np.abs(line).max()),
                    Vmax=float(v.max()), controls_settled=bool(e.d.Solution.ControlActionsDone()))
    finally:
        e.close()


def main():
    index, policy, scale, radius, slot, mid, delta = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6], float(sys.argv[7])
    point = read(HERE / "STAGE_B_STRONG_TOP2.json")["selection"][index]
    namespace = "results_local" if index == 0 else "results_extended"
    folder = (HERE / "stage_c_strong" / namespace / point["label"] /
              f"MESS_{float(scale):.2f}" / f"RADIUS_{float(radius):.0f}" / policy)
    dispatch = read(folder / "DISPATCH.json")
    print(probe(point, dispatch, policy, slot, mid, delta))


if __name__ == "__main__":
    main()
