"""Adaptive paper-PCC exact B0 search toward lower BG and higher AIDC share."""
import json
from pathlib import Path

from stage_a_strong import HERE, PAPER, authority_guard, case, read, save, sha

OUT = HERE / "controllability_search_20260920"
ROOT = OUT / "b0_cases"


def run(aidc, bg, seen):
    bg = round(bg, 5)
    key = (bg, aidc)
    if key not in seen:
        seen[key] = case(bg, aidc, ROOT)
        save(OUT / "B0_SEARCH_RUNNING.json", dict(status="RUNNING", rows=list(seen.values())))
    return seen[key]


def threshold(aidc, target, seen):
    low, high = .30, .60
    a, b = run(aidc, low, seen), run(aidc, high, seen)
    while a["rho"] >= target:
        low -= .05
        a = run(aidc, low, seen)
    while b["rho"] < target:
        high += .05
        b = run(aidc, high, seen)
    for _ in range(11):
        mid = (low + high) / 2.
        row = run(aidc, mid, seen)
        if row["rho"] < target:
            low = round(mid, 5)
        else:
            high = round(mid, 5)
        if high-low <= .0002:
            break
    return run(aidc, high, seen)


def main():
    authority_guard()
    assert sha(PAPER / "IEEE8500_PCC_Overlay.dss") == "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"
    seen = {}
    anchors = []
    for aidc, bg in ((2.4, .54688), (2.5, .54844), (2.6, .54625)):
        old = read(HERE / "stage_a_strong" / f"BG_{bg:.5f}_AIDC_{aidc:.2f}" / "RESULT.json")
        assert old["AC_PASS"] and .93 <= old["rho"] <= .95
        anchors.append(old)
    decisions = []
    for index in range(7, 13):
        aidc = round(2.0 + .1*index, 2)
        first = threshold(aidc, .9302, seen)
        eligible = [r for (bg, scale), r in seen.items() if scale == aidc and r["AC_PASS"] and .93 <= r["rho"] <= .95]
        if not eligible:
            decisions.append(dict(AIDC=aidc, status="STOP_HIGHER_AIDC_PHYSICAL_FEASIBILITY_DIRECTION",
                                  threshold_B0_rho=first["rho"], threshold_Vmin=first["Vmin"],
                                  threshold_AC_PASS=first["AC_PASS"]))
            break
        best = min(eligible, key=lambda r:r["background_scale"])
        decisions.append(dict(AIDC=aidc, status="ELIGIBLE", selected_BG=best["background_scale"],
                              B0_rho=best["rho"], Vmin=best["Vmin"]))
        # At the same absolute AIDC scale, collect a stronger stress point if
        # the original 0.95 voltage floor remains feasible.
        high = threshold(aidc, .94, seen)
        decisions[-1]["rho_0p94_attempt"] = dict(BG=high["background_scale"], rho=high["rho"],
                                                Vmin=high["Vmin"], AC_PASS=high["AC_PASS"])
    all_rows = anchors + list(seen.values())
    eligible = [r for r in all_rows if r["AC_PASS"] and .93 <= r["rho"] <= .95]
    result = dict(status="COMPLETE", policy="B0_ONLY_EXACT_AC", rows=all_rows,
                  eligible=eligible, decisions=decisions,
                  AIDC_multiplier="absolute target / 2.00", PV_scale=.5,
                  paper_overlay_sha256=sha(PAPER / "IEEE8500_PCC_Overlay.dss"),
                  production_started=False)
    save(OUT / "B0_SEARCH_COMPLETE.json", result)
    print("B0_SEARCH_COMPLETE", len(all_rows), "eligible", len(eligible), "last", decisions[-1])


if __name__ == "__main__":
    main()
