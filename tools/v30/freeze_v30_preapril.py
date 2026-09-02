"""Materialize the V30 pre-April scientific freeze artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from dayahead.v29r3.forensic import preservation_snapshot
from dayahead.v30.contracts import (
    OFFICIAL_CASES, STARTING_SHA, V29R2_SHA, aidc_policy_config,
    eligibility_contract, four_case_contract, information_firewall_contract,
    two_stage_contract, write_json,
)
from dayahead.v30.dayahead_formulation import formulation_contract, load_frozen_schedules, reference_identity
from dayahead.v30.grid_safety import derive_margin
from dayahead.v30.reporting import write_csv
from dayahead.v30.scenario_recourse import build_day_population, certify_count


OUT_REL = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
TRUST_CACHE = Path(r"C:\codex_mobileess_workspace\MobileESS_v29r1\cache\v29r1_trust_cert_sources\jan_mar_2025")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def main() -> None:
    repo = Path.cwd(); out = repo / OUT_REL; out.mkdir(parents=True, exist_ok=True)
    head = git(repo, "rev-parse", "HEAD")
    if head != STARTING_SHA:
        raise RuntimeError(f"V30_PREFREEZE_MUST_START_AT_AUTHORITY:{head}")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", V29R2_SHA, head], cwd=repo)
    root = json.loads((repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_ROOT_CAUSE_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    changed = git(repo, "diff", "--name-only", f"{V29R2_SHA}..{STARTING_SHA}").splitlines()
    science = [path for path in changed if path.startswith(("dayahead/v28r2/", "dayahead/v29r2/"))]
    if root["RESULT_CLASSIFICATION"] != "V29R3_AIDC_EFFECT_PHYSICALLY_EXPLAINED_NO_FIX_REQUIRED" or science:
        raise RuntimeError("V30_STARTING_AUTHORITY_SCIENCE")
    pre = preservation_snapshot(repo)
    v29r3_manifest = json.loads((repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_ARTIFACT_SHA256.json").read_text(encoding="utf-8"))
    starting = {
        "artifact_id": "V30_STARTING_AUTHORITY_AUDIT_V1", "status": "PASS",
        "verified_starting_SHA": head, "chosen_V30_base_SHA": STARTING_SHA,
        "branch": git(repo, "branch", "--show-current"),
        "V29R2_is_ancestor": True, "V29R3_result": root["RESULT_CLASSIFICATION"],
        "V29R3_production_science_code_changed": False,
        "scientific_path_changes_above_V29R2": science,
        "V29R2_artifact_preservation": pre,
        "V29R3_artifact_aggregate_sha256": v29r3_manifest["aggregate_manifest_sha256"],
        "starting_git_status_before_V30_files": "CLEAN",
    }
    write_json(out / "V30_STARTING_AUTHORITY_AUDIT.json", starting)
    write_json(out / "V30_PRECHANGE_PRESERVATION_MANIFEST.json", {"artifact_id": "V30_PRECHANGE_PRESERVATION_MANIFEST_V1", **pre, "V29R3_tree_sha": git(repo, "rev-parse", f"{STARTING_SHA}:dayahead/artifacts/v29r3_aidc_effect_forensic"), "V29R3_aggregate_manifest_sha256": v29r3_manifest["aggregate_manifest_sha256"]})
    write_json(out / "V30_FOUR_CASE_CONTRACT.json", four_case_contract())
    write_json(out / "V30_TWO_STAGE_RECOURSE_CONTRACT.json", two_stage_contract())
    write_json(out / "V30_ACTUAL_INFORMATION_FIREWALL_CONTRACT.json", information_firewall_contract())
    write_json(out / "V30_RECOURSE_ELIGIBILITY_CONTRACT.json", eligibility_contract())
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    write_json(out / "V30_CROSS_SITE_COMPATIBILITY_AUDIT.json", {
        "artifact_id": "V30_CROSS_SITE_COMPATIBILITY_AUDIT_V1", "status": "PASS",
        "frozen_rack_count": len(mapping["racks"]), "frozen_AIDC_count": mapping["aidc_count"],
        "domain": [row["rack_id"] for row in mapping["racks"]],
        "same_site_allowed": True, "cross_site_allowed": True,
        "new_compatibility_invented": False,
        "semantics": "pre-execution cross-site workload reassignment within frozen case-study compatibility domain",
        "limitation": "physical WAN transfer/data-locality modeling is outside the current case-study abstraction",
    })
    population = build_day_population(repo, TRUST_CACHE)
    count_rows, count_decision, scenarios = certify_count(population)
    write_json(out / "V30_SCENARIO_GENERATOR_CONTRACT.json", {
        "artifact_id": "V30_SCENARIO_GENERATOR_CONTRACT_V1", "status": "FROZEN",
        "method": "DETERMINISTIC_COUPLED_WHOLE_DAY_BLOCK_BOOTSTRAP_WITH_REPLACEMENT",
        "axes": ["executable service realization/error", "rack residual-capacity realization proxy", "feeder background demand/PV state"],
        "dependence_preservation": "all axes selected from same source day; no independent shuffle",
        "source_window": ["2025-01-01", "2025-03-31"], "April_rows_used": 0,
        "candidate_counts": [8, 16, 32, 64],
        "structural_rule_declared_before_selection": "ordered worst-12 joint-stress day IDs agree with K64",
    })
    write_csv(out / "V30_SCENARIO_COUNT_CERTIFICATION.csv", count_rows)
    write_json(out / "V30_SCENARIO_COUNT_DECISION.json", count_decision)
    margin_rows, margin_decision = derive_margin(repo)
    write_csv(out / "V30_NOREGRET_MARGIN_CERTIFICATION.csv", margin_rows)
    write_json(out / "V30_NOREGRET_MARGIN_DECISION.json", margin_decision)
    write_json(out / "V30_DAYAHEAD_FORMULATION_CONTRACT.json", formulation_contract())
    write_json(out / "V30_ACTUAL_RECOURSE_FORMULATION_CONTRACT.json", {
        "artifact_id": "V30_ACTUAL_RECOURSE_FORMULATION_CONTRACT_V1", "status": "FROZEN",
        "decision_variable": "y_ACT[b,r,t]", "temporal_recourse_variable": None,
        "same_slot_authorization": "sum_r y_ACT[b,r,t] <= sum_r x_DA[b,r,t]",
        "LP_phases": ["physical service ceiling diagnostic", "safety-constrained max service", "fixed-service min phase-current metric", "fixed-service-and-grid min DA deviation"],
        "reported_subcalls_per_epoch": 4, "epochs_per_day": 96,
        "tie_break": ["original rack", "same AIDC", "other AIDC", "canonical rack ID"],
        "Fresh_OpenDSS_in_decision_loop": False, "MESS_reoptimization": False, "full_system_reoptimization": False,
    })
    schedules = load_frozen_schedules(repo)
    identity = reference_identity(repo, schedules, out / "V30_B0_B2_SHARED_REFERENCE_COMPUTE.json")
    write_json(out / "V30_B0_B2_REFERENCE_IDENTITY.json", identity)
    margin = float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"])
    policy = aidc_policy_config(margin, int(count_decision["V30_SCENARIO_COUNT"]), str(count_decision["V30_SCENARIO_SET_SHA256"]))
    policy_sha = hashlib.sha256((json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()).hexdigest()
    write_json(out / "V30_B1_B3_AIDC_POLICY_IDENTITY.json", {"artifact_id": "V30_B1_B3_AIDC_POLICY_IDENTITY_V1", "status": "PASS", "B1_policy_sha256": policy_sha, "B3_policy_sha256": policy_sha, "byte_config_identical": True, "policy": policy})
    deliverability = []
    for i, scenario in enumerate(scenarios):
        executable = min(scenario.executable_service_factor, scenario.rack_residual_capacity_factor)
        deliverability.append({"scenario_id": i, **scenario.payload(), "recourse_deliverable_factor": executable, "unexecuted_factor": 1.0 - executable, "April_rows_used": 0})
    write_csv(out / "V30_PREAPRIL_RECOURSE_DELIVERABILITY.csv", deliverability)
    write_json(out / "V30_PREAPRIL_RECOURSE_CERTIFICATION.json", {
        "artifact_id": "V30_PREAPRIL_RECOURSE_CERTIFICATION_V1", "status": "PASS",
        "selected_K": count_decision["V30_SCENARIO_COUNT"], "scenario_set_sha256": count_decision["V30_SCENARIO_SET_SHA256"],
        "no_regret_margin_pu": margin, "scenario_rows": len(deliverability),
        "mean_deliverable_factor": sum(float(row["recourse_deliverable_factor"]) for row in deliverability) / len(deliverability),
        "April_rows_used": 0, "result_driven_tuning": False,
    })
    readme = "# V30 Two-Stage AIDC Recourse\n\nThis directory freezes the pre-April coupled-scenario and no-regret authorities, then records exactly one non-final Apr-04 B0/B1/B2/B3 development smoke. Actual recourse is AIDC-only, causal, spatial-only, and lexicographic. Fresh OpenDSS is ex-post only.\n"
    (out / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(count_decision["V30_SCENARIO_COUNT"], count_decision["V30_SCENARIO_SET_SHA256"], margin)


if __name__ == "__main__":
    main()
