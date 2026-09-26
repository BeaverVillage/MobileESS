"""AC feasibility trial on a newly optimized diagnostic MESS dispatch."""
import sys
from pathlib import Path

import stage_c_strong_local as c


def main():
    index, policy, scale, radius, delta = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    last_slot = int(sys.argv[6]) if len(sys.argv) > 6 else 86
    point = c.read(c.HERE / "STAGE_B_STRONG_TOP2.json")["selection"][index]
    source = (c.HERE / "stage_c_strong" / "results_local" / point["label"] /
              f"MESS_{scale:.2f}" / f"RADIUS_{radius:.0f}" / policy)
    folder = (c.HERE / "stage_c_strong" / "results_q_repair_trials" / point["label"] /
              f"MESS_{scale:.2f}" / f"RADIUS_{radius:.0f}" / f"QDELTA_{delta:.0f}_THROUGH_{last_slot}" / policy)
    folder.mkdir(parents=True, exist_ok=True)
    dispatch = c.read(source / "DISPATCH.json")
    changes = []
    for row in dispatch:
        if row["mess_id"] == "MESS04" and 81 <= row["slot"] <= last_slot and row["mode"] == "CONNECTED":
            old = row["q_kvar"]
            row["q_kvar"] += delta
            assert abs(row["p_kw"]) <= 300. * scale + 1e-8
            assert row["p_kw"] ** 2 + row["q_kvar"] ** 2 <= (400. * scale) ** 2 + 1e-6
            changes.append(dict(slot=row["slot"], mess_id=row["mess_id"], prior_Q=old, revised_Q=row["q_kvar"]))
    c.save(folder / "Q_REPAIR_TRIAL.json", dict(kind="diagnostic_exact_AC_Q_feasibility_trial",
           source=str(source / "DISPATCH.json"), MESS=scale, changes=changes,
           P_unchanged=True, routes_unchanged=True, energy_unchanged=True))
    c.save(folder / "DISPATCH.json", dispatch)
    result = c.exact(point, policy, scale, dispatch, folder)
    print(result["rho"], result["Vmin"], result["Vmax"], result["AC_PASS"], flush=True)


if __name__ == "__main__":
    main()
