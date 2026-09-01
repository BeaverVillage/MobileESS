import glob,hashlib,json,math
from collections import Counter
from pathlib import Path

from dayahead.authority import sha256_file

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"dayahead/artifacts/v16_3_final"


def _rows():
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in glob.glob(str(OUT/"cache/results/2025-*.json"))]


def test_all_final_days_are_preserved():
    rows=_rows();assert len(rows)==54
    assert Counter(r["status"] for r in rows)=={"COMPLETED":41,"FROZEN_REFERENCE_CONSTRUCTION_INFEASIBLE":13}


def test_case_status_and_dual_ac_counts_are_exact():
    rows=_rows();status=Counter((c,v["status"]) for r in rows for c,v in r["cases"].items())
    assert status[("B0","OPTIMAL")]==21 and status[("B1","OPTIMAL")]==21
    assert status[("B2","OPTIMAL")]==27 and status[("B3","OPTIMAL")]==27
    feasible=[v for r in rows for v in r["cases"].values() if v.get("hard_feasible")]
    assert len(feasible)==96
    assert all(v["dual_ac"][side]["convergence_count"]==96 for v in feasible for side in ("primary","secondary"))
    assert sum(not v["physically_validated"] for v in feasible)==6


def test_independent_planning_and_trust_audit_passes():
    feasible=[v for r in _rows() for v in r["cases"].values() if v.get("hard_feasible")]
    assert max(v["planning_audit"]["trust_region_max_utilization"] for v in feasible)<=1+1e-6
    assert all(min(v["planning_audit"]["hard_constraint_residuals"].values())>=-1e-5 for v in feasible)
    assert all(v["planning_audit"]["independent_solver_calls"]==0 and v["planning_audit"]["independent_OpenDSS_calls"]==0 for v in feasible)


def test_raw_schedule_hashes_and_tracked_artifact_hashes_match():
    manifest=json.loads((OUT/"V16_3_FINAL_SCIENCE_RESULT_MANIFEST.json").read_text(encoding="utf-8"))
    for name,digest in manifest["artifact_sha256"].items():assert sha256_file(OUT/name)==digest
    for row in manifest["raw_schedule_cache_manifest"]:
        result=next(r for r in _rows() if r["operating_day"]==row["operating_day"])["cases"][row["case"]]
        assert sha256_file(Path(result["raw_schedule_cache"]))==row["sha256"]


def test_final_authority_firewall_remains_exact():
    value=json.loads((OUT/"V16_3_FINAL_AUTHORITY_FIREWALL_AUDIT.json").read_text(encoding="utf-8"))
    assert value["status"]=="PASS_EXACT" and value["scientific_authority_changes"]==0
    assert value["frozen_shadow_module_sha256"]=="dbbe9ee0b318f02247469501db32d68fb2f51e4335a9380c08e89fa38763da78"
