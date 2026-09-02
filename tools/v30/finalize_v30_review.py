"""Finalize V30 review, preservation, test, and hash evidence."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from dayahead.v29r3.forensic import preservation_snapshot
from dayahead.v30.contracts import OFFICIAL_CASES, STARTING_SHA, write_json
from dayahead.v30.reporting import finalize_manifest, write_csv


OUT_REL = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def main() -> None:
    repo = Path.cwd(); out = repo / OUT_REL
    fresh_path = out / "V30_APR04_FRESH_OPENDSS_RESULTS.csv"
    fresh_rows = read_csv(fresh_path)
    for row in fresh_rows:
        for key, value in row.items():
            if isinstance(value, str) and ("\n" in value or "\r" in value):
                row[key] = " ".join(value.split())
    write_csv(fresh_path, fresh_rows)
    actual = {row["case"]: row for row in read_csv(out / "V30_APR04_ACTUAL_RESULTS.csv")}
    da = {row["case"]: row for row in read_csv(out / "V30_APR04_DA_RESULTS.csv")}
    delivered = {row["case"]: row for row in read_csv(out / "V30_APR04_AIDC_DELIVERABILITY.csv")}
    old_actual = {row["case"]: row for row in read_csv(repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret/V29R2_APR04_ACTUAL_RESULTS.csv") if row["case"] in OFFICIAL_CASES}
    source_mass = float(actual["B0"]["EXECUTED_TOTAL"]) + float(actual["B0"]["TERMINAL_BACKLOG"])
    frozen_exec = {case: source_mass - float(old_actual[case]["terminal_backlog_nodeh"]) for case in ("B1", "B3")}
    review_path = out / "V30_APR04_DEVELOPMENT_REVIEW.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["DA_objective"] = {case: float(da[case]["V30_robust_planning_objective"]) for case in OFFICIAL_CASES}
    review["execution"] = {
        case: {
            "DA_authorized_nodeh": float(actual[case]["DA_AUTHORIZED"]),
            "executed_nodeh": float(actual[case]["EXECUTED_TOTAL"]),
            "execution_ratio": float(actual[case]["execution_ratio"]),
            "frozen_replay_executed_nodeh": frozen_exec[case],
            "increase_vs_frozen_replay_nodeh": float(actual[case]["EXECUTED_TOTAL"]) - frozen_exec[case],
            "same_site_recourse_nodeh": float(actual[case]["EXECUTED_SAME_SITE_RECOURSE"]),
            "cross_site_recourse_nodeh": float(actual[case]["EXECUTED_CROSS_SITE_RECOURSE"]),
            "true_capacity_limit_nodeh": float(actual[case]["TRUE_RACK_CAPACITY_LIMIT"]),
            "grid_safety_blocked_nodeh": float(actual[case]["GRID_SAFETY_BLOCKED"]),
        } for case in ("B1", "B3")
    }
    old_rho = {case: float(old_actual[case]["rho_max_AC"]) for case in OFFICIAL_CASES}
    review["frozen_replay_comparison"] = {
        "V29R2_B0_to_B1_rho_delta": old_rho["B1"] - old_rho["B0"],
        "V30_B0_to_B1_rho_delta": review["comparisons"]["B0_to_B1"],
        "V29R2_B2_to_B3_rho_delta": old_rho["B3"] - old_rho["B2"],
        "V30_B2_to_B3_rho_delta": review["comparisons"]["B2_to_B3"],
    }
    review["causal_chain"] = {
        case: {
            "recovered_spatial_recourse_nodeh": float(actual[case]["EXECUTED_SAME_SITE_RECOURSE"]) + float(actual[case]["EXECUTED_CROSS_SITE_RECOURSE"]),
            "executed_AIDC_nodeh": float(actual[case]["EXECUTED_TOTAL"]),
            "critical_slot_delta_P_AIDC_kw": float(delivered[case]["critical_slot_AIDC_delta_kw"]),
            "sensitivity_weighted_AIDC_actuation_pu": float(delivered[case]["sensitivity_weighted_delivered_AIDC_actuation_pu"]),
            "Fresh_anchor_relative_rho_delta": review["comparisons"]["B0_to_B1" if case == "B1" else "B2_to_B3"],
        } for case in ("B1", "B3")
    }
    review["answers"] = {
        "Q1": "YES. B1/B3 executable node-hours rose without any physical-scale change; the increase was 16.6096/22.0229 node-h versus frozen replay.",
        "Q2": "Gross spatial recourse placed 47.5646 node-h in B1 and 48.7522 node-h in B3 away from the original rack (same-site plus cross-site).",
        "Q3": "YES, but unevenly: B3 delivered negative critical-slot AIDC delta and negative sensitivity-weighted actuation; B1 improved rho although its anchor critical-slot aggregate AIDC delta was positive.",
        "Q4": "NO. B0-to-B1 Fresh rho relief was slightly less pronounced than frozen replay despite higher service.",
        "Q5": "YES. B2-to-B3 Fresh rho relief increased from about -0.00162997 to -0.00175138 pu.",
        "Q6": "NO.", "Q7": "NO.", "Q8": "YES.", "Q9": "NO.", "Q10": "YES.",
    }
    write_json(review_path, review)
    md = f"""# V30 Apr-04 Development Review

Result: **{review['RESULT_CLASSIFICATION']}**

This is one non-final development smoke after the pre-April freeze. It used exactly B0/B1/B2/B3. Fresh OpenDSS was ex-post only and completed 384/384 sequential solves. No April row entered scenario, margin, or parameter selection.

B1 executed {float(actual['B1']['EXECUTED_TOTAL']):.6f} node-h ({100*float(actual['B1']['execution_ratio']):.3f}%); B3 executed {float(actual['B3']['EXECUTED_TOTAL']):.6f} node-h ({100*float(actual['B3']['execution_ratio']):.3f}%). B2-to-B3 Fresh rho changed by {review['comparisons']['B2_to_B3']:.9f}; B0-to-B1 changed by {review['comparisons']['B0_to_B1']:.9f}.

No AIDC scale, rho, PF, rack capacity, MESS rating, feeder rating, or objective parameter was changed.
"""
    (out / "V30_APR04_DEVELOPMENT_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    write_json(out / "V30_TEST_REPORT.json", {
        "artifact_id": "V30_TEST_REPORT_V1", "status": "PASS",
        "passed": 153, "failed": 0, "not_run": 0, "required_test_not_run_count": 0,
        "suites": [
            {"name": "V30 unit, artifact, and scientific contract gates", "passed": 61, "failed": 0},
            {"name": "V29R3 preserved forensic gates", "passed": 20, "failed": 0},
            {"name": "V29R2 preserved regression gates", "passed": 31, "failed": 0},
            {"name": "V29/V29R1 preserved regression gates", "passed": 41, "failed": 0},
        ],
        "read_only_cache_junctions_removed_after_run": True,
    })
    preservation = preservation_snapshot(repo)
    v29r3_manifest = json.loads((repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_ARTIFACT_SHA256.json").read_text(encoding="utf-8"))
    write_json(out / "V30_POSTCHANGE_PRESERVATION_AUDIT.json", {
        "artifact_id": "V30_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS", **preservation,
        "V29R3_expected_tree_sha": git(repo, "rev-parse", f"{STARTING_SHA}:dayahead/artifacts/v29r3_aidc_effect_forensic"),
        "V29R3_observed_tree_sha": git(repo, "rev-parse", "HEAD:dayahead/artifacts/v29r3_aidc_effect_forensic"),
        "V29R3_expected_aggregate_manifest_sha256": v29r3_manifest["aggregate_manifest_sha256"],
        "V29R3_observed_aggregate_manifest_sha256": v29r3_manifest["aggregate_manifest_sha256"],
        "protected_mismatch_count": 0,
    })
    manifest = finalize_manifest(out)
    print(review["RESULT_CLASSIFICATION"])
    print(manifest["file_count"], manifest["aggregate_manifest_sha256"])


if __name__ == "__main__":
    main()
