"""Fail-closed V17 facility flexible-share authority precheck.

This module records the source audit that must precede any V17 scientific
re-freeze.  It intentionally has no imports from the V16.3 final-science
loaders and performs no model, solver, OpenDSS, or May/June data access.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AUTHORITY_COMMIT = "2246063175977f152f3ac8df8f65a861cc7bbd22"
DECOMPOSITION_COMMIT = "1c46d6510be6be6e00f3305821cbe3bbbd79bdd9"
FORENSIC_COMMIT = "945845c0195b9f2d04ebd4a14924904dd2f5620f"
FORENSIC_SHA256 = "94c5874bff9cec8d87959f3b19bd4d5b41fd8d6a974614a87a74607aaaceb338"

BLOCK_STATUS = "V17_BLOCKED_FLEXIBLE_SHARE_AUTHORITY_MISSING"
FINAL_CLASSIFICATION = "V17_APRIL_D_FLEXIBLE_SHARE_AUTHORITY_MISSING"
NEXT_DECISION = "V17_FURTHER_REDESIGN_REQUIRED"


def _zero_counters() -> dict[str, int]:
    return {
        "V16_3_scientific_authority_changes": 0,
        "V16_3_historical_result_changes": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "May_June_result_dependent_tuning": 0,
        "beta_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "kappa_changes": 0,
        "alpha_grid_changes": 0,
        "native_ieee123_changes": 0,
        "native_rating_changes": 0,
        "voltage_limit_changes": 0,
        "current_limit_changes": 0,
        "AIDC_site_changes": 0,
        "tap_semantics_changes": 0,
        "gamma_crit_changes": 0,
        "arbitrary_clipping_calls": 0,
        "post_hoc_effect_tuning_calls": 0,
        "OpenDSS_calls_inside_Benders": 0,
        "eta_FLEX_calibration_calls": 0,
        "RC_MQT_retraining_calls": 0,
        "April_B0_B1_B2_B3_calls": 0,
        "Fresh_OpenDSS_calls": 0,
        "decomposition_regression_calls": 0,
    }


def build_precheck() -> dict[str, Any]:
    """Return deterministic evidence for the failed authority gate."""

    return {
        "artifact_id": "V17_AIDC_FLEXIBLE_SHARE_AUTHORITY_PRECHECK_V1",
        "status": BLOCK_STATUS,
        "checkpoint": {
            "branch": "codex/dayahead-aidc-joint-v1",
            "V16_3_scientific_authority_commit": AUTHORITY_COMMIT,
            "decomposition_completion_commit": DECOMPOSITION_COMMIT,
            "AIDC_forensic_checkpoint": FORENSIC_COMMIT,
            "AIDC_forensic_root_sha256": FORENSIC_SHA256,
            "accepted_prior_classification": "AIDC_CAUSE_B_FLEXIBLE_POWER_SCALE_LIMITED",
            "accepted_prior_decision": "CURRENT_V16_3_AIDC_RESULT_IS_PHYSICALLY_EXPLAINED",
        },
        "required_authority_definition": {
            "quantity": "facility-level schedulable/deferrable IT workload energy share",
            "symbol": "f_FLEX_AUTH",
            "required_scope": "IT-only whole-facility envelope",
            "required_temporal_semantics": "share represented by D-1 schedulable workload",
            "must_be_independent_of": [
                "beta_AIDC",
                "feeder penetration",
                "PUE",
                "PF",
                "kappa_n",
                "May/June outcomes",
                "B1-B0 or B3-B2 improvement",
            ],
        },
        "audited_sources": [
            {
                "source_id": "V16_FINAL_SCIENTIFIC_REFREEZE_HANDOFF",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/정리 자료/MobileESS_AIDC_DayAhead_ML_Optimization_FINAL_SCIENTIFIC_REFREEZE_Codex_Handoff_20260829_CODEX_IMPLEMENTATION_AUTHORITY_FINAL_REVISED.docx",
                "sha256": "c1f46f2066ccbba9936b9bfe0667da9ae37e7c418fbf0ff186a93ebd6d80baf5",
                "definition_found": "ESIF total IT magnitude; Kestrel source-qualified flexible-workload shape; Dataset312 kappa",
                "measured_vs_assumed": "mixed source roles, but no facility flexible-share value",
                "facility_scope": "NLR ESIF facility with Kestrel subsystem",
                "temporal_scope": "training/April/May/June protocol definitions",
                "IT_only": True,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "Defines component roles and explicitly forbids arbitrary GPU-to-total scaling, but supplies no facility-level schedulable fraction.",
            },
            {
                "source_id": "NLR_ESIF_FACILITY_POWER",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR ESIF PUE  IT Power/README.md",
                "sha256": "f69d32f1af598c48a899d54d48b26def2ca78a0c11d848516169570ecae4c029",
                "definition_found": "observed whole-facility IT power and PUE time series",
                "measured_vs_assumed": "measured",
                "facility_scope": "ESIF whole facility",
                "temporal_scope": "facility time series",
                "IT_only": True,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "No field labels which portion of IT power is schedulable or deferrable.",
            },
            {
                "source_id": "NLR_KESTREL_JOBS",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/datacard.md",
                "sha256": "0139b75b80cd3029e0af54e22fc0dbad3080e92a8a7a602f1bd62cd7a36f62e9",
                "definition_found": "measured job submissions, starts, ends, resources, queue wait, and sharing evidence",
                "measured_vs_assumed": "measured/derived scheduler records",
                "facility_scope": "Kestrel subsystem, not ESIF whole-facility IT",
                "temporal_scope": "job records",
                "IT_only": False,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "Supports workload shape and cohort eligibility but has neither a whole-facility denominator nor an authoritative flexible-share label.",
            },
            {
                "source_id": "NLR_DATASET312",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/dataset.zip",
                "sha256": "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137",
                "citation": "Vercellino et al., Measurement of Generative AI Workload Power Profiles for Whole-Facility Data Center Infrastructure Planning, arXiv:2604.07345 (2026)",
                "citation_url": "https://arxiv.org/abs/2604.07345",
                "definition_found": "measured workload power plus synthetic 10-MW whole-facility profiles at 20/40/60/80 percent target utilization",
                "measured_vs_assumed": "workload power measured; whole-facility profiles simulated",
                "facility_scope": "synthetic colocation facility running training/fine-tuning jobs",
                "temporal_scope": "year-long simulation scenarios",
                "IT_only": True,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "Target utilization is not a schedulable energy share; no single utilization scenario is an authorized main value; the frozen V16 source role is parameter-only for kappa.",
            },
            {
                "source_id": "YORK_FIGSHARE_H100_B200",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/H100B200 AI Training Power Dataset/High-resolution-AI-Data-Center-Training-Workloads-Dataset_FigShare.zip",
                "definition_found": "measured node/machine workload power profiles",
                "measured_vs_assumed": "measured workload profiles",
                "facility_scope": "node and machine measurements",
                "temporal_scope": "benchmark runs",
                "IT_only": True,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "No whole-facility flexible-share label and explicitly excluded from the frozen NLR main authority.",
            },
            {
                "source_id": "V14_2_LITERATURE_REGISTRY",
                "exact_path": "C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/정리 자료/Mobile_ESS_AI_ICPS_정식화_구현명세_v14_2_Current_Authority_20260827.docx",
                "sha256": "1d4dadae504c9ecf95c3623b2d91036e8c5ee564ee1395be6b4f5d47d85d0394",
                "definition_found": "bibliographic motivation for data-center flexibility and a dimensionless rho_C reporting metric",
                "measured_vs_assumed": "literature registry only",
                "facility_scope": "varied",
                "temporal_scope": "not applicable",
                "IT_only": None,
                "schedulable_or_deferrable_share": False,
                "admissible_main_authority": False,
                "rejection_reason": "No archived numeric facility-level schedulable share or deterministic main-case selection rule.",
            },
        ],
        "authority_preference_results": {
            "1_measured_facility_level_label": "NOT_FOUND",
            "2_archived_engineering_report_evidence": "NOT_FOUND_FOR_SCHEDULABLE_SHARE",
            "3_archived_peer_reviewed_literature": "NO_NUMERIC_MAIN_SHARE_FOUND",
            "4_predeclared_case_study_assumption": "NO_VALUE_OR_SELECTION_RULE_PREDECLARED",
        },
        "exact_adopted_main_value": None,
        "uncertainty_or_sensitivity_values": [],
        "eta_FLEX": None,
        "scientific_refreeze_started": False,
        "stop_point": "SECTION_4_SOURCE_BACKED_FLEXIBLE_SHARE_AUTHORITY_PRECHECK",
        "final_classification": FINAL_CLASSIFICATION,
        "next_decision": NEXT_DECISION,
        "counters": _zero_counters(),
    }


def build_gap(precheck: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": "V17_FLEXIBLE_SHARE_AUTHORITY_GAP_V1",
        "status": BLOCK_STATUS,
        "missing_authority": precheck["required_authority_definition"],
        "why_existing_sources_are_insufficient": [
            "ESIF measures whole-facility IT magnitude but not schedulability.",
            "Kestrel describes a subsystem workload but supplies no facility-level share denominator.",
            "Dataset312 utilization scenarios do not define a schedulable fraction and provide no authorized main-case choice.",
            "Archived literature entries contain no numeric, scope-matched main flexible-share authority.",
        ],
        "minimum_evidence_to_unblock": [
            "A measured facility-level IT label separating schedulable/deferrable and fixed energy, with source hash and time scope; or",
            "an archived source giving a numeric schedulable IT share for a scope defensibly matching this case study, together with a prospectively frozen main-value selection rule.",
        ],
        "prohibited_gap_fills": [
            "selecting a Dataset312 utilization scenario after observing grid benefit",
            "equating utilization with flexible share",
            "scaling from the existing Kestrel-to-ESIF ratio to obtain a desired effect",
            "clipping or broadening Kestrel eligibility",
            "using May/June inputs or outcomes",
        ],
        "downstream_actions_not_run": [
            "eta_FLEX calibration",
            "reference scheduler V4",
            "fixed-plus-flex label construction",
            "RC-MQT retraining",
            "April affine-region validation",
            "AC restoration",
            "April B0/B1/B2/B3",
            "April-15 decomposition regression",
        ],
        "final_classification": FINAL_CLASSIFICATION,
        "next_decision": NEXT_DECISION,
        "counters": precheck["counters"],
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "v17_candidate",
    )
    args = parser.parse_args()
    precheck = build_precheck()
    _write_json(args.output_dir / "V17_AIDC_FLEXIBLE_SHARE_AUTHORITY_PRECHECK.json", precheck)
    _write_json(args.output_dir / "V17_FLEXIBLE_SHARE_AUTHORITY_GAP.json", build_gap(precheck))
    print(BLOCK_STATUS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
