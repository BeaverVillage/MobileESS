"""Run one resumable Stage C diagnostic case after its coefficients exist."""
import os
import sys
from stage_c_strong_local import HERE, read, optimize, exact, authority_guard


def main():
    authority_guard()
    index, policy, scale, radius = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    os.environ["STAGE_C_LOCAL_RADIUS_KW_KVAR"] = str(radius)
    point = read(HERE / "STAGE_B_STRONG_TOP2.json")["selection"][index]
    assert policy in ("B2", "B3") and scale in (1., 1.25, 1.5, 1.75, 2.)
    folder = HERE / "stage_c_strong" / "results_local" / point["label"] / f"MESS_{scale:.2f}" / f"RADIUS_{radius:.0f}" / policy
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "EXACT_AC.json").exists():
        print(read(folder / "EXACT_AC.json")["rho"])
        return
    dispatch = optimize(point, policy, scale, folder)
    if dispatch is None:
        raise RuntimeError("SCREENING_OPTIMIZER_NO_OPTIMAL_SOLUTION")
    result = exact(point, policy, scale, dispatch, folder)
    print(policy, scale, result["rho"], result["AC_PASS"], flush=True)


if __name__ == "__main__":
    main()
