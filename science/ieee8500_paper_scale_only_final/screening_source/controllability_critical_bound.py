"""Cheap necessary bound: one critical slot can disqualify an entire B0 point."""
import sys
import numpy as np

from controllability_relaxed import OUT, SCALES, solve_slot
from stage_a_strong import HERE, PAPER, authority_guard, read, sha, save


def main():
    authority_guard()
    label=sys.argv[1]
    points={r["label"]:r for r in read(OUT/"B0_SEARCH_COMPLETE.json")["eligible"]}
    point=points[label]
    t=point["critical_slot"]
    source_root=sys.argv[2] if len(sys.argv)>2 else "sensitivity"
    source=OUT/source_root/label/f"slot_{t:02d}.npz"
    assert source.is_file()
    with np.load(source) as data:z={k:data[k] for k in data.files}
    with np.load(PAPER/"B3_A1_electrical_rows/PCC_IMPLIED_BOUNDS.npz") as bounds:
        lower=bounds["lower"][t].copy()*(point["aidc_scale"]/2.)
        upper=bounds["upper"][t].copy()*(point["aidc_scale"]/2.)
    rating=np.asarray(read(PAPER/"AXES.json")["winding_rating_kVA"])
    rows=[]
    for scale in SCALES:
        result=solve_slot(z,lower,upper,rating,"joint",scale,t)
        assert result["status"]=="PASS"
        rows.append(dict(MESS=scale,critical_slot_relaxed_rho=result["relaxed_rho"],
                         whole_day_gap_cannot_exceed=point["rho"]-result["relaxed_rho"],
                         slot_result=result))
    dropped=max(r["whole_day_gap_cannot_exceed"] for r in rows)<.05
    report=dict(status="REJECT_BY_NECESSARY_ONE_SLOT_BOUND" if dropped else "MAY_SURVIVE_NEEDS_MULTI_SLOT_DIAGNOSTIC",
                label=label,BG=point["background_scale"],AIDC=point["aidc_scale"],
                B0_exact_rho=point["rho"],B0_AC_PASS=point["AC_PASS"],
                critical_slot=t,critical_line=point["critical_line"],
                paper_overlay_sha256=sha(PAPER/"IEEE8500_PCC_Overlay.dss"),
                coefficient_sha256=sha(source),
                reason="The full-day relaxed max rho is at least the optimized rho of this one critical slot; therefore its B0 improvement cannot exceed the listed slot gap.",
                rows=rows)
    save(OUT/f"CRITICAL_BOUND_{label}.json",report)
    print(label,report["status"],[(r["MESS"],round(r["whole_day_gap_cannot_exceed"],6)) for r in rows])


if __name__=="__main__":main()
