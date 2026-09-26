"""Exact paper PCC AC sensitivities around feasible B0 states only."""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from stage_a_strong import Engine, HERE, PAPER, authority_guard, read, sha
from stage_c_coefficients_old import configure, save

OUT = HERE / "controllability_search_20260920"
ROOT = OUT / "sensitivity"


def selected_slots(point):
    # Include enough slots to resolve up to an 0.11 pu full-day gap. The
    # maximum untouched-slot loading is retained as the relaxation floor.
    cutoff = point["rho"] - .11
    slots = tuple(r["slot"] for r in point["rows"] if r["rho"] >= cutoff)
    floor = max(r["rho"] for r in point["rows"] if r["slot"] not in slots)
    return slots, floor


def generate(point):
    label = point["label"]
    folder = ROOT / label
    manifest_path = folder / "MANIFEST.json"
    if manifest_path.exists():
        m = read(manifest_path)
        for r in m["files"]:
            assert sha(r["path"]) == r["sha256"]
        return m
    folder.mkdir(parents=True, exist_ok=True)
    slots, floor = selected_slots(point)
    prior = read(folder/"RUNNING.json")["files"] if (folder/"RUNNING.json").exists() else []
    files = list(prior)
    for item in files:
        assert sha(item["path"]) == item["sha256"]
    completed = {item["slot"] for item in files}
    for t in slots:
        if t in completed:
            continue
        e = Engine(folder / f"slot_{t:02d}" / "runtime")
        try:
            for u in range(t+1):
                configure(e, u, point["background_scale"])
                x_u = np.r_[(point["aidc_scale"]/2.)*e.ap[u], np.zeros(48)]
                e.controls(x_u)
                e.d.Solution.SolveSnap()
                assert e.d.Solution.Converged() and e.d.Solution.ControlActionsDone() and e.d.Error.Number()==0
            x=x_u
            start = time.perf_counter()
            auto = e.arrays()
            row = point["rows"][t]
            assert abs(float(np.abs(auto[1]).max())-row["rho"]) < 1e-8, (label,t,row["rho"],float(np.abs(auto[1]).max()))
            state = e.state(t)
            e.hold(state)
            e.controls(x)
            e.d.Solution.SolveSnap()
            assert e.d.Solution.Converged() and e.d.Error.Number()==0
            anchor = e.arrays()
            jac = [np.zeros((60,len(a)),dtype=a.dtype) for a in anchor]
            for k in range(60):
                sides=[]
                for sign in (1.,-1.):
                    trial=x.copy()
                    trial[k]+=sign
                    e.controls(trial)
                    e.d.Solution.SolveSnap()
                    assert e.d.Solution.Converged() and e.d.Error.Number()==0
                    sides.append(e.arrays())
                for j in range(4):
                    jac[j][k]=(sides[0][j]-sides[1][j])/2.
            path=folder/f"slot_{t:02d}.npz"
            np.savez_compressed(path, x=x, v2=anchor[0], line=anchor[1], tx=anchor[2], S=anchor[3],
                                v2_J=jac[0], line_J=jac[1], tx_J=jac[2], S_J=jac[3])
            files.append(dict(slot=t,path=str(path),sha256=sha(path),
                              auto_rho=float(np.abs(auto[1]).max()),
                              held_rho=float(np.abs(anchor[1]).max()),
                              auto_Vmin=float(np.sqrt(auto[0]).min()),
                              held_Vmin=float(np.sqrt(anchor[0]).min()),
                              wall_seconds=time.perf_counter()-start))
            save(folder/"RUNNING.json",dict(files=files, selected_slots=list(slots),outside_floor=floor))
            print("SENSITIVITY",label,t,round(files[-1]["wall_seconds"],2),flush=True)
        finally:
            e.close()
    m=dict(status="PASS",label=label,BG=point["background_scale"],AIDC=point["aidc_scale"],
           selected_slots=list(slots),outside_slot_exact_rho_floor=floor,
           B0_exact_rho=point["rho"],base_AIDC_array_multiplier=point["aidc_scale"]/2.,
           paper_overlay_sha256=sha(PAPER/"IEEE8500_PCC_Overlay.dss"),
           authority_source="sequential exact B0 AC with native regulator/capacitor states held only for centered derivatives",
           perturbation="+/-1 kW or kvar on each of 60 original paper PCC ports",
           files=files)
    save(manifest_path,m)
    return m


def main():
    authority_guard()
    points=read(OUT/"B0_SEARCH_COMPLETE.json")["eligible"]
    unique={p["label"]:p for p in points}
    manifests=[]
    for point in sorted(unique.values(),key=lambda r:-r["aidc_scale"]):
        manifests.append(generate(point))
    save(OUT/"SENSITIVITY_COMPLETE.json",dict(status="COMPLETE",manifests=manifests))


if __name__=="__main__":
    main()
