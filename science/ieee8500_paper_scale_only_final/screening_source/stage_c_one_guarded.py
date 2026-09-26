"""Repeat a local Stage C solve with numerical voltage margin for AC parity."""
import math
import os
import sys

import stage_c_strong_local as c


_original_add_row = c.add_row


def guarded_add_row(model, rho, z, controls, slot, kind, index):
    if kind not in ("low", "high"):
        return _original_add_row(model, rho, z, controls, slot, kind, index)
    real, _ = c.affine(z, controls, "v2", "v2_J", index)
    if kind == "low":
        model.addConstr(real >= 0.951 ** 2, name=f"low_guard_{slot}_{index}")
    else:
        model.addConstr(real <= 1.049 ** 2, name=f"high_guard_{slot}_{index}")


def main():
    c.authority_guard()
    index, policy, scale, radius = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    assert policy in ("B2", "B3") and scale in c.SCALES
    os.environ["STAGE_C_LOCAL_RADIUS_KW_KVAR"] = str(radius)
    c.add_row = guarded_add_row
    point = c.read(c.HERE / "STAGE_B_STRONG_TOP2.json")["selection"][index]
    folder = (c.HERE / "stage_c_strong" / "results_guarded" / point["label"] /
              f"MESS_{scale:.2f}" / f"RADIUS_{radius:.0f}" / policy)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "EXACT_AC.json").exists():
        result = c.read(folder / "EXACT_AC.json")
    else:
        dispatch = c.optimize(point, policy, scale, folder)
        if dispatch is None:
            raise RuntimeError("SCREENING_OPTIMIZER_NO_OPTIMAL_SOLUTION")
        result = c.exact(point, policy, scale, dispatch, folder)
    print(policy, scale, result["rho"], result["AC_PASS"], flush=True)


if __name__ == "__main__":
    main()
