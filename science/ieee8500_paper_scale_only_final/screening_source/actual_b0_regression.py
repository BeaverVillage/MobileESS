"""One independent paper-scale B0 Actual replay, separate from DA screening."""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT / "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913"
PAPER = ROOT / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
OUTPUT = HERE / "actual_b0_regression_paper_2x_retry1_20260920"
SOURCE = BASE / "validate_actual.py"
spec = importlib.util.spec_from_file_location("paper_validate_actual_b0_once", SOURCE)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
from forensic import sha, read  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    authority = read(HERE / "FORENSIC_AUTHORITY.json")
    assert authority["PAPER_CONFIG_RESTORED"] and not authority["RESITED_PCC_USED"]
    expected_overlay = "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"
    assert sha(PAPER / "IEEE8500_PCC_Overlay.dss") == expected_overlay
    historical = BASE / "actual/B0/FINAL_ACTUAL/AC_SUMMARY.json"
    expected = read(historical)
    assert expected["validation_scope"] == "REALIZED_OPERATION_AC"
    assert abs(expected["max_phase_line_loading_pu"] - .8537462147791017) < 1e-12
    assert not OUTPUT.exists(), "B0 Actual regression may run only once in this namespace"
    OUTPUT.mkdir()
    v.H = OUTPUT
    v.selected = lambda: {"B0": (v.read(BASE / "REFERENCE_JOBS.json"), [])}
    method = v.METHOD
    (OUTPUT / "BATTERY_EFFICIENCY_AUTHORITY.json").write_bytes(
        (method / "BATTERY_EFFICIENCY_AUTHORITY.json").read_bytes())
    sources = [Path(__file__), SOURCE, BASE / "electrical_engine.py",
               BASE / "PCC_Master.dss", BASE / "PCC_OVERLAY_INVENTORY.json",
               BASE / "IEEE8500_PCC_Overlay.dss", BASE / "REFERENCE_JOBS.json",
               BASE / "AIDC_2X_AUTHORITY.json", BASE / "HEADROOM_AUTHORITY.json",
               BASE / "D1_AEMO_VIC1_FORECAST.json", BASE / "SCREENING_RULE.json",
               historical, method / "METHOD_FREEZE.json", method / "robust_search.py",
               method / "frozen_code/qsafe.py"]
    v.save(OUTPUT / "RULE_FREEZE.json", dict(
        status="FROZEN_BEFORE_B0_ACTUAL_REGRESSION", date="2025-05-01",
        policy="B0", original_BG=.5, original_PV=.5,
        absolute_AIDC_scale=2., array_multiplier=1.,
        paper_PCC_overlay_sha256=expected_overlay,
        Actual_controller="original violation-triggered Q-only robust V2; B0 baseline replay",
        source_files=[v.rec(p) for p in sources],
        new_scheduling_optimizer_calls=0, scope="REALIZED_OPERATION_AC"))
    v.verify()
    v.protect()
    ns = v.kernel()
    # The archived run refers to two source files whose original repository
    # checkout has since been pruned. Resolve read-only, byte-identical copies
    # while retaining the historical logical paths in the replay evidence.
    import dayahead.v40d_actual.mobility_inputs as mobility
    historical_repo = Path("C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt")
    aliases = {
        str(historical_repo / "dayahead/v35/execution.py"):
            (Path("C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v35/execution.py"),
             "dd50172ebc176a638421174c620694bd0f6180d6f714739dc485706ebf90c1da"),
        str(historical_repo / "dayahead/mess_physics.py"):
            (Path("C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/mess_physics.py"),
             "d7bac71fb7522a8c94cf181b3a3ca8dcf1034b8faa6cf561ad3663ef2726a50b"),
    }
    original_reference = mobility.reference
    def verified_reference(path):
        path = Path(path)
        if path.exists():
            return original_reference(path)
        local, expected_sha = aliases[str(path)]
        assert sha(local) == expected_sha
        return dict(path=str(path), sha256=expected_sha, bytes=local.stat().st_size)
    mobility.reference = verified_reference
    v.save(OUTPUT / "HISTORICAL_READ_ALIASES.json", dict(
        status="BYTE_IDENTICAL_READ_ONLY", aliases={key: dict(local_copy=str(local),
        sha256=digest, bytes=local.stat().st_size) for key, (local, digest) in aliases.items()}))
    import gurobipy as gp
    gp.Model.optimize = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DA_OPTIMIZER_FORBIDDEN_IN_ACTUAL"))
    start = time.perf_counter()
    da = v.inputs(ns)
    assert (OUTPUT / "B0/INPUT_READY.json").exists()
    v.run_policy("B0", ns, da)
    v.verify()
    result = read(OUTPUT / "B0/FINAL_ACTUAL/AC_SUMMARY.json")
    observed = result["max_phase_line_loading_pu"]
    tolerance = 1e-9
    actual_pass = (result["AC_feasible"] and result["converged_slots"] == 96
                   and result["controls_settled_slots"] == 96
                   and abs(observed - expected["max_phase_line_loading_pu"]) <= tolerance)
    da_report = read(HERE / "stage_a_strong/BG_0.50000_AIDC_2.00/RESULT.json")
    da_expected = read(BASE / "B0/DA_FINAL_96/AC_VALIDATION.json")["metrics"]["max_phase_line_loading_pu"]
    da_pass = abs(da_report["rho"] - da_expected) <= tolerance
    audit = dict(status="PASS" if actual_pass and da_pass else "FAIL",
                 actual_pipeline_parity="PASS" if actual_pass else "FAIL",
                 paper_overlay_sha256=expected_overlay,
                 source_validate_actual_sha256=sha(SOURCE),
                 historical_actual_summary_sha256=sha(historical),
                 DA=dict(scope="DAY_AHEAD_EXACT_AC", observed_rho=da_report["rho"],
                         expected_rho=da_expected, tolerance=tolerance,
                         status="PASS" if da_pass else "FAIL"),
                 Actual=dict(scope="REALIZED_OPERATION_EXACT_AC", observed_rho=observed,
                             expected_rho=expected["max_phase_line_loading_pu"],
                             tolerance=tolerance, AC_feasible=result["AC_feasible"],
                             status="PASS" if actual_pass else "FAIL"),
                 difference_between_scopes=da_report["rho"] - observed,
                 actual_campaign_runs=1, screening_candidate_Actual_runs=0,
                 wall_seconds=time.perf_counter() - start)
    write(OUTPUT / "PARITY.json", audit)
    print("B0_ACTUAL_PARITY", audit["status"], observed, "DA", da_report["rho"], flush=True)
    assert audit["status"] == "PASS"


if __name__ == "__main__":
    main()
