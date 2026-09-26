"""Exact paper-feeder MESS sensitivities at shortlisted scale-only B0 points.

Only the original 48 MESS PCC P/Q ports are perturbed. Native controls are
settled first, then held for the centered electrical derivatives, as in the
paper coefficient generator. These coefficients are diagnostic, not policy.
"""
import json
import os
import sys
import time
from pathlib import Path

for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
sys.dont_write_bytecode = True
import numpy as np
from stage_a_strong import Engine, PAPER, HERE, authority_guard, paper_engine, read, sha

SLOTS = tuple(list(range(34, 54)) + list(range(68, 86)))


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def configure(e, t, bg):
    paper_engine.s.old.inputs(e.d, e.loads, e.P, e.Q, e.ap, e.aq,
                              bg, e.md, e.mpv, e.ratio, t)
    for i in range(len(e.loads)):
        e.d.Generators.Name(f"op8500_pv_{i:04d}")
        pv_kw = float(.5 * e.ratio * e.P[i] * e.mpv[t])
        e.d.CktElement.Enabled(pv_kw > 0)
        if pv_kw > 0:
            e.d.Generators.kW(pv_kw)
            e.d.Generators.kvar(0.)


def pcc_for(policy):
    if policy == "B2":
        with np.load(PAPER / "MAY01_B0_AIDC_POWER.npz") as z:
            return z["pcc"].copy()
    with np.load(PAPER / "B1_REUSE/POWER.npz") as z:
        return z["pcc"].copy()


def generate(point, policy, t):
    label = point["label"]
    folder = HERE / "stage_c_strong" / "coefficients" / label / policy / f"slot_{t:02d}"
    result = folder / "COEFFICIENTS.npz"
    if result.exists():
        meta = read(folder / "GENERATED.json")
        assert sha(result) == meta["sha256"]
        return meta
    folder.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    e = Engine(folder / "runtime")
    try:
        bg, aidc = point["background_scale"], point["aidc_scale"]
        configure(e, t, bg)
        x = np.r_[(aidc / 2.) * pcc_for(policy)[t], np.zeros(48)]
        e.controls(x)
        e.d.Solution.SolveSnap()
        assert e.d.Solution.Converged() and e.d.Solution.ControlActionsDone() and e.d.Error.Number() == 0
        state = e.state(t)
        e.hold(state)
        e.controls(x)
        e.d.Solution.SolveSnap()
        assert e.d.Solution.Converged() and e.d.Error.Number() == 0
        anchor = e.arrays()
        derivative = [np.empty((48, len(a)), dtype=a.dtype) for a in anchor]
        for k in range(48):
            sides = []
            for sign in (1., -1.):
                trial = x.copy()
                trial[12 + k] += sign
                e.controls(trial)
                e.d.Solution.SolveSnap()
                assert e.d.Solution.Converged() and e.d.Error.Number() == 0
                sides.append(e.arrays())
            for j in range(4):
                derivative[j][k] = (sides[0][j] - sides[1][j]) / 2.
        np.savez_compressed(result, x=x, v2=anchor[0], line=anchor[1],
                            tx=anchor[2], S=anchor[3], v2_J=derivative[0],
                            line_J=derivative[1], tx_J=derivative[2], S_J=derivative[3])
        meta = dict(status="PASS", label=label, policy=policy, slot=t, background_scale=bg,
                    aidc_scale=aidc, aidc_array_multiplier=aidc / 2.,
                    perturbation="centered +/-1 kW or kvar on each original MESS PCC port",
                    paper_overlay_sha256=sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
                    sha256=sha(result), wall_seconds=time.perf_counter() - start)
        save(folder / "GENERATED.json", meta)
        print("COEFFICIENT", label, policy, t, round(meta["wall_seconds"], 2), flush=True)
        return meta
    finally:
        e.close()


def main():
    authority_guard()
    points = read(HERE / "STAGE_B_STRONG_TOP2.json")["selection"]
    rows = []
    for point in points:
        for policy in ("B2", "B3"):
            for t in SLOTS:
                rows.append(generate(point, policy, t))
        save(HERE / "STAGE_C_COEFFICIENTS_RUNNING.json", dict(status="RUNNING", rows=rows))
    save(HERE / "STAGE_C_COEFFICIENTS_COMPLETE.json", dict(status="COMPLETE", rows=rows))


if __name__ == "__main__":
    main()
