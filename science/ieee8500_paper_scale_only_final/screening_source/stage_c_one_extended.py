"""Extend critical slots only where exact diagnostics identified violations."""
import os
import sys

import stage_c_coefficients_old as coeff
import stage_c_strong_local as c


def main():
    c.authority_guard()
    index, policy, scale, radius = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    point = c.read(c.HERE / "STAGE_B_STRONG_TOP2.json")["selection"][index]
    assert index == 1 and policy in ("B2", "B3") and scale in c.SCALES
    extras = (29,) if policy == "B2" else (86, 87, 94)
    for slot in extras:
        coeff.generate(point, policy, slot)
    c.SLOTS = tuple(sorted(set(c.SLOTS) | set(extras)))
    c.SLOT_SET = set(c.SLOTS)
    os.environ["STAGE_C_LOCAL_RADIUS_KW_KVAR"] = str(radius)
    folder = (c.HERE / "stage_c_strong" / "results_extended" / point["label"] /
              f"MESS_{scale:.2f}" / f"RADIUS_{radius:.0f}" / policy)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "EXACT_AC.json").exists():
        result = c.read(folder / "EXACT_AC.json")
    else:
        dispatch = c.optimize(point, policy, scale, folder)
        if dispatch is None:
            raise RuntimeError("SCREENING_OPTIMIZER_NO_OPTIMAL_SOLUTION")
        result = c.exact(point, policy, scale, dispatch, folder)
    print(policy, scale, radius, result["rho"], result["AC_PASS"], flush=True)


if __name__ == "__main__":
    main()
