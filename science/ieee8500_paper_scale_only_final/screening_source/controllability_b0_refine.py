"""Exact B0 refinement within the user's 0.93–0.95 hard-limit band."""
from stage_a_strong import HERE, authority_guard, case, save


def main():
    authority_guard()
    out=HERE/"controllability_search_20260920"
    root=out/"b0_cases"
    rows=[]
    for aidc,bgs in ((2.4,(.550,.552,.554,.556)),(2.5,(.550,.551,.552))):
        for bg in bgs:
            row=case(bg,aidc,root)
            rows.append(row)
            save(out/"B0_REFINEMENT_RUNNING.json",dict(status="RUNNING",rows=rows))
            if row["Vmin"]<.95 and row["rho"]>=.93:
                break
    eligible=[r for r in rows if r["AC_PASS"] and .93<=r["rho"]<=.95]
    save(out/"B0_REFINEMENT_COMPLETE.json",dict(status="COMPLETE",rows=rows,eligible=eligible))
    print("REFINED_ELIGIBLE",[(r["background_scale"],r["aidc_scale"],r["rho"],r["Vmin"]) for r in eligible])


if __name__=="__main__":main()
