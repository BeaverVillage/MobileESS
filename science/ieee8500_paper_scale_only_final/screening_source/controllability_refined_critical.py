"""One-slot necessary gap bound for refined feasible B0 operating points."""
import numpy as np

import controllability_coefficients as coeff
from controllability_relaxed import OUT, SCALES, solve_slot
from stage_a_strong import PAPER, authority_guard, read, sha, save


def main():
    authority_guard()
    points=read(OUT/"B0_REFINEMENT_COMPLETE.json")["eligible"]
    coeff.ROOT=OUT/"critical_sensitivity"
    coeff.selected_slots=lambda point: ((point["critical_slot"],),
        max(r["rho"] for r in point["rows"] if r["slot"]!=point["critical_slot"]))
    with np.load(PAPER/"B3_A1_electrical_rows/PCC_IMPLIED_BOUNDS.npz") as b:
        lower_all=b["lower"].copy();upper_all=b["upper"].copy()
    rating=np.asarray(read(PAPER/"AXES.json")["winding_rating_kVA"])
    results=[]
    for point in points:
        manifest=coeff.generate(point)
        t=point["critical_slot"]
        source=OUT/"critical_sensitivity"/point["label"]/f"slot_{t:02d}.npz"
        with np.load(source) as a:z={k:a[k] for k in a.files}
        lower=lower_all[t]*(point["aidc_scale"]/2.)
        upper=upper_all[t]*(point["aidc_scale"]/2.)
        scales=[]
        for scale in SCALES:
            result=solve_slot(z,lower,upper,rating,"joint",scale,t)
            assert result["status"]=="PASS"
            scales.append(dict(MESS=scale,critical_slot_relaxed_rho=result["relaxed_rho"],
                               whole_day_gap_cannot_exceed=point["rho"]-result["relaxed_rho"],
                               slot_result=result))
        row=dict(label=point["label"],BG=point["background_scale"],AIDC=point["aidc_scale"],
                 exact_B0_rho=point["rho"],Vmin=point["Vmin"],Vmax=point["Vmax"],
                 B0_critical_line=point["critical_line"],B0_critical_slot=t,
                 paper_overlay_sha256=sha(PAPER/"IEEE8500_PCC_Overlay.dss"),
                 coefficient_sha256=sha(source),
                 status="REJECT_BY_ONE_SLOT" if max(x["whole_day_gap_cannot_exceed"] for x in scales)<.05 else "MAY_SURVIVE",
                 scales=scales)
        results.append(row)
        save(OUT/"REFINED_CRITICAL_BOUNDS_RUNNING.json",dict(status="RUNNING",results=results))
        print("REFINED_BOUND",row["label"],row["status"],[(x["MESS"],round(x["whole_day_gap_cannot_exceed"],5)) for x in scales],flush=True)
    save(OUT/"REFINED_CRITICAL_BOUNDS_COMPLETE.json",dict(status="COMPLETE",results=results))


if __name__=="__main__":main()
