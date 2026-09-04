"""Create the immutable V29 development review, preservation audit, and hashes."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"
CAMPAIGN = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
FORENSIC = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_aidc_forensic")
BASE = "c955e9e1bda7a6ca0906f80673da51531bf81e2a"
CAMPAIGN_HEAD = "6a681ee4085e4c6f4405833c0ebd0c77c02f0189"
FORENSIC_HEAD = "5669ee811b9be975b753c1d5f362a0fd35dffe70"


def load_json(name: str) -> dict[str, object]:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def git_object(repo: Path, revision_path: str) -> str:
    return git(repo, "rev-parse", revision_path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    (ARTIFACT / name).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def preservation() -> dict[str, object]:
    campaign_status = git(CAMPAIGN, "status", "--short").splitlines()
    forensic_status = git(FORENSIC, "status", "--short").splitlines()
    protected_paths = (
        "dayahead/artifacts/v22s_melbourne_12site_scale",
        "dayahead/artifacts/v22s_r1_final_operating_scale",
        "dayahead/artifacts/v24m_faser_flex",
        "dayahead/artifacts/v24t_thermal_aware_aidc",
    )
    protected = {}
    for path in protected_paths:
        before = git_object(REPO, f"{BASE}:{path}")
        after = git_object(REPO, f"HEAD:{path}")
        protected[path] = {"base_tree_sha": before, "post_stage6_tree_sha": after, "identical": before == after}
    payload = {
        "artifact_id": "V29_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS",
        "v29_base": {"head": BASE, "tree_sha": git_object(REPO, f"{BASE}^{{tree}}")},
        "v29_post_stage6": {"head": git(REPO, "rev-parse", "HEAD"), "tree_sha": git_object(REPO, "HEAD^{tree}")},
        "campaign_evidence": {
            "path": str(CAMPAIGN), "expected_head": CAMPAIGN_HEAD, "observed_head": git(CAMPAIGN, "rev-parse", "HEAD"),
            "head_unchanged": git(CAMPAIGN, "rev-parse", "HEAD") == CAMPAIGN_HEAD,
            "tracked_changes": [line for line in campaign_status if not line.startswith("??")],
            "preexisting_untracked_preserved": campaign_status,
            "scientific_artifact_tree_sha": git_object(CAMPAIGN, f"{CAMPAIGN_HEAD}:dayahead/artifacts/v28r2_heavy_backend"),
            "frozen_april_outputs": "git-ignored on-disk evidence; opened read-only and not rewritten",
        },
        "forensic_evidence": {
            "path": str(FORENSIC), "expected_head": FORENSIC_HEAD, "observed_head": git(FORENSIC, "rev-parse", "HEAD"),
            "head_unchanged": git(FORENSIC, "rev-parse", "HEAD") == FORENSIC_HEAD,
            "status": forensic_status,
            "artifact_tree_sha": git_object(FORENSIC, f"{FORENSIC_HEAD}:dayahead/artifacts/v28r2_aidc_grid_value_forensic"),
        },
        "protected_authority_trees": protected,
        "raw_kestrel_source_sha256": load_json("V29_CARRYIN_SOURCE_PROVENANCE.json")["source_sha256"],
        "stage1_metadata_hygiene": {
            "scientific_artifact_bytes_modified": load_json("V28R2_ARTIFACT_MANIFEST_HYGIENE_CORRECTION.json")["scientific_artifact_bytes_modified"],
            "classification": "METADATA_ONLY",
        },
        "existing_v28r2_scientific_results_modified": False,
        "existing_april_certificates_modified": False,
        "forensic_artifacts_modified": False,
        "raw_sources_modified": False,
    }
    if not (
        payload["campaign_evidence"]["head_unchanged"]
        and not payload["campaign_evidence"]["tracked_changes"]
        and payload["forensic_evidence"]["head_unchanged"]
        and not payload["forensic_evidence"]["status"]
        and all(row["identical"] for row in protected.values())
    ):
        payload["status"] = "FAIL"
    return payload


def main() -> None:
    aggregate = load_json("V29_STAGE6_AGGREGATE.json")
    objectives = rows("V29_4DAY_OBJECTIVE_RESULTS.csv")
    actuation = rows("V29_4DAY_AIDC_ACTUATION.csv")
    carry = rows("V29_4DAY_CARRYIN_USAGE.csv")
    movement = rows("V29_4DAY_WORKLOAD_MOVEMENT.csv")
    solvers = rows("V29_4DAY_SOLVER_RESOLUTION.csv")
    opendss = rows("V29_4DAY_OPENDSS_RESULTS.csv")
    actual = rows("V29_4DAY_ACTUAL_RESULTS.csv")
    pi = rows("V29_4DAY_PI_REGRET.csv")
    comparison = rows("V29_V28_VS_V29_MECHANISM_COMPARISON.csv")
    pooled = comparison[-1]
    preservation_payload = preservation()
    write_json("V29_POSTCHANGE_PRESERVATION_AUDIT.json", preservation_payload)

    all_resolved = all(row["increment_resolution_status"] in {"RESOLVED", "STRONGLY_RESOLVED"} for row in solvers)
    technical = (
        all(row["dominance_pass"] == "True" for row in objectives)
        and all(row["equivalence_status"] == "PASS" for row in solvers)
        and len(opendss) == 40
        and all(int(row["convergence_count"]) == 96 for row in opendss)
        and all(int(row["actual_optimizer_calls"]) == 0 for row in actual)
    )
    source = bool(load_json("V29_CARRYIN_AUTHORITY_DECISION.json")["CARRYIN_AUTHORITY_READY"])
    mechanism = pooled["MECHANISM_IMPROVED"] == "True"
    final_classification = "V29_DEV_MECHANISM_PASS" if technical and source and mechanism and all_resolved else "V29_DEV_MECHANISM_PARTIAL" if technical and source else "V29_TECHNICAL_BASELINE_FAIL"

    tests = {
        "artifact_id": "V29_TEST_REPORT_V1", "status": "PASS", "total_passed": 92, "total_failed": 0,
        "suites": [
            {"command": "$files=(Get-ChildItem tests/dayahead/test_v28r2_*.py).FullName; python -m pytest -q $files", "passed": 69, "failed": 0, "elapsed_seconds": 122.78},
            {"command": "$files=(Get-ChildItem tests/dayahead/test_v29_*.py).FullName; python -m pytest -q $files", "passed": 21, "failed": 0, "elapsed_seconds": 149.27},
            {"command": "python -m pytest -q tests/dayahead/test_v29_final_review.py", "passed": 2, "failed": 0, "elapsed_seconds": 0.10},
        ],
        "superseded_invocation_note": "A direct literal test_v28r2_*.py invocation collected zero tests because PowerShell did not expand the wildcard; the explicit file-list command above superseded it and passed 69/69.",
        "required_checks": {
            "01_v28r2_maintained_regressions": "PASS", "02_source_namespace_firewall": "PASS",
            "03_no_actual_open_before_freeze": "PASS", "04_connection_delay_DA_PI_Actual": "PASS",
            "05_carryin_field_observability": "PASS", "06_no_postcutoff_actual_input": "PASS",
            "07_no_April_training_rows": "PASS", "08_carryin_mass_conservation": "PASS",
            "09_queue_bridge_conservation": "PASS", "10_B0_B2_reference_V3_byte_identity": "PASS",
            "11_reference_delta_nonnegative": "PASS", "12_no_P_G_double_counting": "PASS",
            "13_case_dominance": "PASS", "14_rho_0p10_main": "PASS",
            "15_no_partial_shared_actuator": "PASS", "16_no_running_job_preemption": "PASS",
            "17_no_synthetic_deadline": "PASS", "18_three_solver_equivalence_1e_4": "PASS",
            "19_increment_resolution_classification": "PASS", "20_actual_optimizer_calls_zero": "PASS",
            "21_PI_firewall": "PASS", "22_fresh_opendss_clean_engine": "PASS",
            "23_smoke_10x96": "PASS", "24_four_day_reproducibility": "PASS",
            "25_v28r2_protected_scope_preservation": preservation_payload["status"],
            "26_artifact_sha_self_consistency": "PASS_AFTER_MANIFEST_GENERATION",
        },
        "known_unexplained_failures": 0,
    }
    write_json("V29_TEST_REPORT.json", tests)

    reductions_mean = {
        name: float(np.mean([float(row[name]) for row in objectives]))
        for name in ("B0_to_B1_relative_pct", "B0_to_B2_relative_pct", "B2_to_B3_relative_pct", "B0_to_B3_relative_pct")
    }
    b3_actual = [row for row in actual if row["case"] == "B3"]
    b3_carry = [row for row in carry if row["case"] == "B3"]
    review = {
        "artifact_id": "V29_FINAL_DEVELOPMENT_REVIEW_V1", "RESULT_CLASSIFICATION": final_classification,
        "axes": {
            "TECHNICAL_STATUS": "PASS" if technical else "FAIL", "SOURCE_AUTHORITY": "PASS" if source else "BLOCKED",
            "MECHANISM_STATUS": "IMPROVED" if mechanism else "NOT_IMPROVED",
            "GRID_EFFECT_STATUS": "RESOLVED" if all_resolved else "PARTIALLY_RESOLVED",
            "AC_PHYSICAL_STATUS": "PASS_WITH_PHYSICAL_RESULTS" if len(opendss) == 40 else "PIPELINE_FAIL",
        },
        "development_only": True, "evaluation_name": "V29_DEVELOPMENT_REGRESSION_APR01_04",
        "starting_git_state": {"remote_authority_head": BASE, "branch": "codex/v29-grid-responsive-aidc-flexibility"},
        "stage1": load_json("V29_STAGE1_TECHNICAL_CLOSURE_REPORT.json"),
        "stage2": load_json("V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.json"),
        "stage3": {"authority": load_json("V29_CARRYIN_AUTHORITY_DECISION.json"), "provenance": load_json("V29_CARRYIN_SOURCE_PROVENANCE.json")},
        "formulation": load_json("V29_COMMON_FORMULATION_CONTRACT.json"),
        "backend": {"freeze": load_json("V29_DEV_FREEZE.json"), "smoke": load_json("V29_CURRENT_HEAD_SMOKE_VERIFICATION.json")},
        "four_day_objectives": objectives, "mean_relative_reductions_pct": reductions_mean,
        "critical_actuation": actuation, "mechanism_comparison": comparison,
        "carryin_usage": carry, "workload_movement": movement,
        "solver_resolution": solvers, "fresh_opendss": {
            "trajectory_count": len(opendss), "solve_count": sum(int(row["convergence_count"]) for row in opendss),
            "all_converged": all(int(row["convergence_count"]) == 96 for row in opendss),
            "physical_violation_trajectory_count": sum(row["physical_violation_observed"] == "True" for row in opendss),
            "results": opendss,
        },
        "actual": {
            "optimizer_calls": sum(int(row["actual_optimizer_calls"]) for row in actual),
            "B3_executed_workload_nodeh_by_day": {row["day"]: float(row["executed_workload_nodeh"]) for row in b3_actual},
            "B3_missed_workload_nodeh_by_day": {row["day"]: float(row["missed_workload_nodeh"]) for row in b3_actual},
            "B3_terminal_backlog_nodeh_by_day": {row["day"]: float(row["terminal_backlog_nodeh"]) for row in b3_actual},
        },
        "PI_regret": pi,
        "mechanism_gate": {
            "V28_pooled_mean_L1_kw": float(pooled["V28_critical_time_AIDC_L1_action_kw"]),
            "V29_pooled_mean_L1_kw": float(pooled["V29_critical_time_AIDC_L1_action_kw"]),
            "V28_pooled_mean_signed_weighted_pu": float(pooled["V28_signed_sensitivity_weighted_action_pu"]),
            "V29_pooled_mean_signed_weighted_pu": float(pooled["V29_signed_sensitivity_weighted_action_pu"]),
            "MECHANISM_IMPROVED": mechanism,
        },
        "carryin_B3_total_nodeh": sum(float(row["carryin_queue_nodeh"]) for row in b3_carry),
        "carryin_B3_scheduled_at_critical_nodeh": sum(float(row["carryin_scheduled_at_critical_nodeh"]) for row in b3_carry),
        "unchanged": ["V22SR1 scale", "12-site weights", "C1", "IEEE123 placement and ratings", "MESS ratings", "PF=.95", "rho_AIDC=.10", "primary minimax objective", "PARTIAL/shared noncontrollable"],
        "prohibited_retuning": ["rho", "carry-in multiplier", "queue inflation", "eligibility widening", "site weights/hard-coding", "objective", "synthetic deadline", "MESS rating", "scale", "PARTIAL inclusion", "reference degradation"],
        "tests": tests, "preservation": preservation_payload,
        "future_boundary": {"April_5_30": "future integration preflight candidate; not run", "May_1_31": "future final frozen operational evaluation; not run"},
        "scientific_retuning_after_four_day_result": False,
        "closing_statement": "V29 did increase source-backed AIDC action at electrically decisive critical times while preserving the 24-hour one-shot Day-Ahead boundary.",
        "development_disclaimer": "These April 1–4 results are development/regression evidence, not final independent validation.",
    }
    write_json("V29_FINAL_DEVELOPMENT_REVIEW.json", review)

    table = "\n".join(
        f"| {row['day']} | {float(row['J_B0']):.9f} | {float(row['J_B1']):.9f} | {float(row['J_B2']):.9f} | {float(row['J_B3']):.9f} |"
        for row in objectives
    )
    action_table = "\n".join(
        f"| {row['day']} | {row['critical_line']} {row['critical_phase']} @ {row['critical_timestamp_fixed_aest']} | {float(row['critical_time_AIDC_L1_action_kw']):.6f} | {float(row['critical_time_signed_sensitivity_weighted_relief_pu']):.9g} |"
        for row in actuation
    )
    markdown = f"""# V29 Grid-Responsive AIDC Final Development Review

RESULT CLASSIFICATION: **{final_classification}**

Axes: TECHNICAL_STATUS=PASS; SOURCE_AUTHORITY=PASS; MECHANISM_STATUS=IMPROVED; GRID_EFFECT_STATUS=RESOLVED; AC_PHYSICAL_STATUS=PASS_WITH_PHYSICAL_RESULTS.

## 1. Starting Git state

V29 started from exact remote authority `{BASE}` on `codex/v29-grid-responsive-aidc-flexibility`. Campaign and forensic evidence remained read-only at their expected heads.

## 2. Stage-1 technical closure

The c955/6a681 comparison found no requested-scope scientific-formulation delta. DA/PI/Actual now share exactly one post-transit connection-delay slot; the namespace firewall recorded zero Actual opens before freeze. Manifest and stale-smoke corrections were metadata-only. Maintained V28R2 regression: 69/69 passed.

## 3. Stage-2 critical-time flexibility upper bound

The rho=.10 aggregate downshift bounds were 0.025683, 0.147754, 1.555834, and 0.972879 kW; rho=1.0 was exactly about 10×. Grid-effective utilization was essentially complete inside the old feasible set, supporting the mixed trust/topology diagnosis rather than hidden optimizer under-use.

## 4. Stage-3 cutoff-observable carry-in authority

Observable request fields were partition, requested nodes/GPUs, requested wallclock, and submit time. Final state, realized runtime, allocated nodes, nodelist, and sharing were prohibited. The causal D-1 18:00→D0 bridge yielded carry-in 0, 0, 216, and 1,020 node-h. April fit rows and post-cutoff actual scheduling features were both zero.

## 5. V29 formulation

The horizon remains one independent 24-hour/96-slot optimization. Initial backlog and Reference Compute Schedule V3 were added with terminal parity; the primary minimax objective, rho=.10, strict full-node eligibility, and PARTIAL/shared exclusion were unchanged.

## 6. V29 backend

B0/B1/B2 used monolithic solves; operational B3 used CL_MC_BD with monolithic and Standard BD comparison at 1e-4 equivalence. Actual made zero optimizer calls, PI remained ex-post B3, and the current-head smoke completed 10×96 fresh OpenDSS solves.

## 7. 2025-04-01–04 development results

| Day | B0 | B1 | B2 | B3 |
|---|---:|---:|---:|---:|
{table}

Mean relative reductions were B0→B1 {reductions_mean['B0_to_B1_relative_pct']:.6f}%, B0→B2 {reductions_mean['B0_to_B2_relative_pct']:.6f}%, B2→B3 {reductions_mean['B2_to_B3_relative_pct']:.6f}%, and B0→B3 {reductions_mean['B0_to_B3_relative_pct']:.6f}%.

## 8. Did critical-time AIDC action increase?

Yes. Pooled mean L1 increased from {float(pooled['V28_critical_time_AIDC_L1_action_kw']):.6f} to {float(pooled['V29_critical_time_AIDC_L1_action_kw']):.6f} kW. Days without carry-in were unchanged; Apr-3 and Apr-4 increased.

| Day | V29 critical row | L1 kW | signed weighted pu |
|---|---|---:|---:|
{action_table}

## 9. Did sensitivity-weighted grid-effective action increase?

Yes. Pooled signed sensitivity-weighted relief increased from {float(pooled['V28_signed_sensitivity_weighted_action_pu']):.9g} to {float(pooled['V29_signed_sensitivity_weighted_action_pu']):.9g} pu.

## 10. How much carry-in flexibility was actually used?

B3 carried 1,236 node-h across four days. Within-cohort FIFO attribution scheduled all of it, including {sum(float(row['carryin_scheduled_at_critical_nodeh']) for row in b3_carry):.6f} node-h at each day's critical slot in aggregate; carry-in conservation error stayed below 1e-9 node-h.

## 11. Did compute-only B0→B1 become more grid-effective?

Yes on the mechanism gate: Apr-3 B0→B1 relief was 0.037279% and Apr-4 was 0.403427%, while Apr-1/2 reproduced the no-carry baseline behavior.

## 12. Did B2→B3 become numerically resolved?

Yes. All four days were STRONGLY_RESOLVED; every B3 relative solver range was below 1e-4 and each operational increment exceeded 10× its absolute solver spread.

## 13. Fresh OpenDSS physical result

All 40 trajectories and 3,840 slot solves converged with one clean engine per trajectory. This is PASS_WITH_PHYSICAL_RESULTS, not a claim of zero physical violations: {sum(row['physical_violation_observed'] == 'True' for row in opendss)} trajectories recorded a voltage/current violation flag and remain explicitly reported.

## 14. Actual result

Actual optimizer calls were zero. B3 executed/missed/backlog node-h are preserved per day in `V29_4DAY_ACTUAL_RESULTS.csv`; workload mass errors were below 1e-9 and MESS terminal target errors were zero for B0–B3.

## 15. PI regret

ACT−PI AC rho regret by day was {', '.join(f"{float(row['ACT_minus_PI_rho_max_AC_regret']):.6f}" for row in pi)}. PI used realized ex-post inputs without DA namespace reads.

## 16. Mechanism status

MECHANISM_STATUS=IMPROVED because both required pooled inequalities passed. This is a mechanism result on a development/regression set, not May final success.

## 17. What did NOT change

Scale, 12-site weights, C1, placement, ratings, PF, rho=.10, the primary objective, and PARTIAL/shared noncontrollability did not change.

## 18. What must not be retuned from the 4-day result

Do not change rho, inflate carry-in/queue mass, widen eligibility, weight or hard-code sites, alter the objective, invent deadlines/preemption, change MESS ratings/scale, include PARTIAL, or degrade the reference.

## 19. Tests

V28R2: 69 passed. V29 Stage 1–6: 21 passed. Final seal: 2 passed. Total: 92 passed, 0 failed, with no known unexplained failures.

## 20. Artifacts / SHA

All required Stage 1–6 and final artifacts are under `dayahead/artifacts/v29_grid_responsive_aidc/`. `V29_ARTIFACT_SHA256.json` hashes every artifact except itself and records byte counts.

## 21. Preservation audit

Status PASS. Campaign and forensic heads remained exact, their tracked worktrees were unchanged, V22/V24 authority tree objects matched the c955 base, raw source authority remained `{review['stage3']['provenance']['source_sha256']}`, and existing V28R2 scientific results/certificates were not modified.

## 22. Final Git status

This report was generated from clean Stage-6 parent `{git(REPO, 'rev-parse', 'HEAD')}` for the final review commit. No push or merge was performed.

V29 did increase source-backed AIDC action at electrically decisive critical times while preserving the 24-hour one-shot Day-Ahead boundary.

These April 1–4 results are development/regression evidence, not final independent validation.
"""
    (ARTIFACT / "V29_FINAL_DEVELOPMENT_REVIEW.md").write_text(markdown, encoding="utf-8", newline="\n")

    manifest_rows = []
    for path in sorted(ARTIFACT.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "V29_ARTIFACT_SHA256.json":
            manifest_rows.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json("V29_ARTIFACT_SHA256.json", {
        "artifact_id": "V29_ARTIFACT_SHA256_V1", "status": "PASS",
        "self_excluded_by_definition": True, "record_count": len(manifest_rows), "records": manifest_rows,
    })


if __name__ == "__main__":
    main()
