"""Exact AC feasibility correction of the scale-1.25 B2 diagnostic."""
import sys
import stage_c_strong_local as c


def main():
    delta = float(sys.argv[1])
    mess_id = sys.argv[2] if len(sys.argv) > 2 else "MESS01"
    point = c.read(c.HERE / "STAGE_B_STRONG_TOP2.json")["selection"][0]
    source = (c.HERE / "stage_c_strong" / "results_local" / point["label"] /
              "MESS_1.25" / "RADIUS_10" / "B2")
    folder = (c.HERE / "stage_c_strong" / "results_q_repair_trials" / point["label"] /
              "MESS_1.25" / "RADIUS_10" / f"B2_{mess_id}_QPLUS_{delta:.0f}_SLOTS_80_81")
    folder.mkdir(parents=True, exist_ok=True)
    dispatch = c.read(source / "DISPATCH.json")
    changes = []
    for row in dispatch:
        if row["mess_id"] == mess_id and row["slot"] in (80, 81):
            old = row["q_kvar"]
            row["q_kvar"] += delta
            assert row["p_kw"] ** 2 + row["q_kvar"] ** 2 <= 500. ** 2 + 1e-6
            changes.append(dict(slot=row["slot"], old_Q=old, new_Q=row["q_kvar"]))
    c.save(folder / "Q_REPAIR_TRIAL.json", dict(kind="diagnostic_exact_AC_Q_feasibility_trial",
           source=str(source / "DISPATCH.json"), changes=changes, P_routes_energy_unchanged=True))
    c.save(folder / "DISPATCH.json", dispatch)
    result = c.exact(point, "B2", 1.25, dispatch, folder)
    print(result["rho"], result["Vmin"], result["Vmax"], result["AC_PASS"], flush=True)


if __name__ == "__main__":
    main()
