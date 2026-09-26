"""Audit all exact B0 points and preserve the empty qualifying Top 3."""
import json
import numpy as np

from controllability_relaxed import OUT, solve_slot
from stage_a_strong import HERE, PAPER, authority_guard, read, sha, save


def main():
    authority_guard()
    anchors=read(OUT/"B0_SEARCH_COMPLETE.json")["eligible"]
    refined=read(OUT/"B0_REFINEMENT_COMPLETE.json")["eligible"]
    points={r["label"]:r for r in anchors+refined}
    rows=[]
    refined_bounds={r["label"]:r for r in read(OUT/"REFINED_CRITICAL_BOUNDS_COMPLETE.json")["results"]}
    for label,point in points.items():
        if label in refined_bounds:
            bound=refined_bounds[label]
            scales=bound["scales"]
            source_path=OUT/"REFINED_CRITICAL_BOUNDS_COMPLETE.json"
            coefficient_root="critical_sensitivity"
        else:
            source_path=OUT/f"CRITICAL_BOUND_{label}.json"
            bound=read(source_path)
            scales=bound["rows"]
            coefficient_root="critical_sensitivity" if point["aidc_scale"]==2.4 else "sensitivity"
        assert len(scales)==5 and point["AC_PASS"]
        for s in scales:
            row=dict(BG=point["background_scale"],AIDC=point["aidc_scale"],MESS=s["MESS"],
                     exact_B0_rho=point["rho"],Vmin=point["Vmin"],Vmax=point["Vmax"],
                     B0_critical_line=point["critical_line"],B0_critical_slot=point["critical_slot"],
                     critical_slot_relaxed_rho=s["critical_slot_relaxed_rho"],
                     controllability_gap_upper_bound=s["whole_day_gap_cannot_exceed"],
                     AC_PASS=True,qualifies=s["whole_day_gap_cannot_exceed"]>=.05,
                     source=dict(path=str(source_path),sha256=sha(source_path)),
                     coefficient_root=coefficient_root)
            rows.append(row)
    assert len(rows)==45
    qualifying=[r for r in rows if r["qualifies"]]
    near=sorted(rows,key=lambda r:(-r["controllability_gap_upper_bound"],-r["AIDC"],r["MESS"]))[:3]
    with np.load(PAPER/"B3_A1_electrical_rows/PCC_IMPLIED_BOUNDS.npz") as b:
        lower_all=b["lower"].copy();upper_all=b["upper"].copy()
    rating=np.asarray(read(PAPER/"AXES.json")["winding_rating_kVA"])
    for row in near:
        label=f"BG_{row['BG']:.5f}_AIDC_{row['AIDC']:.2f}"
        t=row["B0_critical_slot"]
        source=OUT/row["coefficient_root"]/label/f"slot_{t:02d}.npz"
        with np.load(source) as data:z={k:data[k] for k in data.files}
        lower=lower_all[t]*(row["AIDC"]/2.)
        upper=upper_all[t]*(row["AIDC"]/2.)
        aidc=solve_slot(z,lower,upper,rating,"aidc",row["MESS"],t)
        mess=solve_slot(z,lower,upper,rating,"mess",row["MESS"],t)
        assert aidc["status"]==mess["status"]=="PASS"
        row["AIDC_contribution_potential_upper_bound"]=row["exact_B0_rho"]-aidc["relaxed_rho"]
        row["MESS_contribution_potential_upper_bound"]=row["exact_B0_rho"]-mess["relaxed_rho"]
        row["AIDC_only_relaxed_rho_at_critical_slot"]=aidc["relaxed_rho"]
        row["MESS_only_relaxed_rho_at_critical_slot"]=mess["relaxed_rho"]
        row["coefficient_sha256"]=sha(source)
        save(OUT/"near_miss_contributions"/f"{label}_MESS_{row['MESS']:.2f}.json",
             dict(row=row,AIDC_slot_solve=aidc,MESS_slot_solve=mess))
    halt=read(OUT/"B0_SEARCH_COMPLETE.json")["decisions"][-1]
    assert halt["status"].startswith("STOP_") and halt["AIDC"]==2.7
    production=HERE/"full_production_paper_BG054688_AIDC240_MESS150"
    assert not read(production/"PRODUCTION_AUTHORIZATION.json")["authorized"]
    assert read(production/"PREMATURE_PRODUCTION_DIAGNOSTIC.json")["long_AIDC_14400_second_search_started"] is False
    report=dict(status="COMPLETE_NO_QUALIFYING_CANDIDATE",date="2025-05-01",
                exact_B0_operating_points=len(points),MESS_capability_combinations=len(rows),
                threshold_controllability_gap=.05,top3=[],qualifying_count=len(qualifying),
                near_misses=near,all_rows=rows,
                AIDC_2P70_halt=halt,
                relaxed_diagnostic="Independent critical-slot continuous LP around exact paper B0 AC. AIDC may shift site/time demand within paper per-site power bounds. Up to six fractional MESS occupy only paper PCC ports. Original job/WAN/route/energy chronology is held as authority but relaxed for this upper-bound screen.",
                bound_logic="Full-day maximum line loading is at least the optimized loading at the original B0 critical slot, so one-slot improvement is an upper bound on the full-day relaxed gap under this diagnostic model.",
                paper_overlay_sha256=sha(PAPER/"IEEE8500_PCC_Overlay.dss"),
                AIDC_double_scaling=False,AIDC_array_multiplier="target_absolute_scale/2.00",
                PAPER_PCC_CONFIG_USED=True,RESITING_USED=False,FEEDER_MODIFIED=False,
                SCALE_ONLY_CHANGE=True,production_started=False,
                actual_pipeline_parity_status=read(HERE/"ACTUAL_PIPELINE_PARITY_FREEZE.json")["status"],
                Actual_replayed_during_candidate_screening=False,
                premature_production_preserved=sha(production/"PREMATURE_PRODUCTION_DIAGNOSTIC.json"),
                production_authorization_disabled=True)
    save(OUT/"CONTROLLABILITY_SCREEN_COMPLETE.json",report)
    lines=["# IEEE8500 paper-PCC controllability screen", "",
           "Status: **no candidate meets the 0.05 pu relaxed-gap threshold**. Full production was not started.", "",
           "| BG | AIDC | MESS | B0 exact rho | Vmin | Vmax | critical slot | critical-slot relaxed rho | gap ceiling | AIDC ceiling | MESS ceiling | AC |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|"]
    for r in near:
        lines.append(f"| {r['BG']:.5f} | {r['AIDC']:.2f} | {r['MESS']:.2f} | {r['exact_B0_rho']:.6f} | {r['Vmin']:.6f} | {r['Vmax']:.6f} | {r['B0_critical_slot']} | {r['critical_slot_relaxed_rho']:.6f} | {r['controllability_gap_upper_bound']:.6f} | {r['AIDC_contribution_potential_upper_bound']:.6f} | {r['MESS_contribution_potential_upper_bound']:.6f} | PASS |")
    lines += ["", "These are the three closest **rejected** combinations, not selected Top 3 candidates.",
              f"AIDC 2.70 stopped at B0 rho {halt['threshold_B0_rho']:.6f}, Vmin {halt['threshold_Vmin']:.6f} (<0.95).",
              "The relaxation permits fractional vehicle placement and AIDC time shifts; its values are screening ceilings and are not B1/B2/B3 results.",
              "Paper PCC overlay SHA256: `843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243`.",
              "The earlier scale 0.54688/2.40/1.50 production staging is preserved as PREMATURE_PRODUCTION_DIAGNOSTIC; authorization is disabled."]
    (OUT/"CONTROLLABILITY_SCREEN_REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(report["status"],"best ceiling",near[0]["controllability_gap_upper_bound"])


if __name__=="__main__":main()
