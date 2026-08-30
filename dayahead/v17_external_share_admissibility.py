"""External-literature admissibility audit for the V17 flexible share.

This module is deliberately fail-closed.  It records the prospectively
declared selection rule, the full-paper denominator forensic, and the
decision not to resume V17 when no scope-matched numerical authority exists.
It imports no science loader, optimizer, model, or OpenDSS integration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


STARTING_CHECKPOINT = "6baa991ee52c2ac8bf3d6d16348c204434d8ab7a"
PRIOR_EVIDENCE_CHECKPOINT = "1d9dd4be2c519ce25c0bc4cf67d6389defede2ac"
PRECHECK_SHA256 = "2e3797d20b38ed9a97280b6a51446bf28a4b879b49290f25a003e85063af3232"
GAP_SHA256 = "7301e2c6cffee85d82444a0be0fc3e91be0ff32eabff6bf33063ccc0ce4d43a9"

CAPRARA_PDF_SHA256 = "9afe7c3efe6fb986de0c95cf524c3309255447306258c7e2a378a53d35da78a6"
CAPRARA_UPCOMMONS_SHA256 = "36e6c6684c2798218e0170133d2cdf69f5fe0764388e1dab5da6133d0bbc5b58"
CAPRARA_CROSSREF_SHA256 = "5875d3d5f583be2c4f1364a5d32eba8ed23f4365413d4c3bd4bbc64ce7ed68d3"
CAO_CROSSREF_SHA256 = "094ba9016b4252ae8c1a11caaf63eba2d3afefaae661778989dc8eaac5fe0331"

BLOCK_STATUS = "V17_BLOCKED_FLEXIBLE_SHARE_AUTHORITY_MISSING"
FINAL_CLASSIFICATION = "V17_SHARE_AUTH_C_CAPRARA_SCOPE_MISMATCH_OTHER_SOURCE_NOT_FOUND"
NEXT_DECISION = "V17_FURTHER_REDESIGN_REQUIRED"

MAIN_AUTHORITY_RULE = (
    "Select the numeric deferrable IT-power/energy share from the "
    "highest-scope-matching SCI/SCIE source that: (a) uses real production "
    "traces or measurements, (b) directly maps schedulable workload to "
    "power/energy, (c) preserves service through deferral, and (d) requires "
    "no denominator conversion."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zero_counters() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "May_June_result_dependent_tuning": 0,
        "V16_3_scientific_authority_changes": 0,
        "V16_3_historical_result_changes": 0,
        "beta_changes": 0,
        "kappa_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "AIDC_site_changes": 0,
        "arbitrary_flexible_share_values": 0,
        "effect_selected_share_values": 0,
        "arbitrary_clipping_calls": 0,
        "OpenDSS_calls_inside_Benders": 0,
        "eta_FLEX_calibration_calls": 0,
        "RC_MQT_retraining_calls": 0,
        "April_B0_B1_B2_B3_calls": 0,
        "Fresh_OpenDSS_calls": 0,
    }


def build_admissibility() -> dict[str, Any]:
    """Return the deterministic external-literature scope audit."""

    return {
        "artifact_id": "V17_EXTERNAL_SCI_FLEXIBLE_SHARE_ADMISSIBILITY_V1",
        "status": "FAIL_CLOSED_NO_ADMISSIBLE_EXTERNAL_AUTHORITY",
        "checkpoint": {
            "branch": "codex/dayahead-aidc-joint-v1",
            "starting_checkpoint": STARTING_CHECKPOINT,
            "prior_evidence_checkpoint": PRIOR_EVIDENCE_CHECKPOINT,
        },
        "required_quantity": {
            "symbol": "f_FLEX_AUTH",
            "definition": "facility-level schedulable/deferrable IT workload energy share",
            "denominator": "V17 IT-only whole-facility P_IT_REF envelope",
            "temporal_semantics": "D-1 schedulable workload envelope with service preserved",
        },
        "main_authority_rule": MAIN_AUTHORITY_RULE,
        "rule_frozen_before_April_execution": True,
        "caprara_full_paper_forensic": {
            "citation": (
                "A. Caprara, Y. Yu, F. Teng, A. Junyent-Ferre, "
                "E. Bullich-Massague, and M. Aragues-Penalba, Data center "
                "workload flexibility for power system demand response: "
                "Evidence from Alibaba traces, International Journal of "
                "Electrical Power & Energy Systems 178 (2026) 111940."
            ),
            "doi": "10.1016/j.ijepes.2026.111940",
            "journal": "International Journal of Electrical Power & Energy Systems",
            "peer_review_verification": {
                "status": "PASS",
                "evidence": "UPCommons item metadata marks the publisher version Peer Reviewed.",
                "url": "https://upcommons.upc.edu/entities/publication/c15cab92-e0eb-4124-852d-e02e1dde9bdc",
            },
            "SCIE_verification": {
                "status": "PASS",
                "evidence": (
                    "RWTH Publications journal authority records Web of Science "
                    "Science Citation Index Expanded coverage and Clarivate "
                    "Master Journal List coverage, updated 2025-11-07."
                ),
                "url": "https://publications.rwth-aachen.de/record/25002/export/print?ln=en",
            },
            "archive": {
                "publisher_version_path": (
                    "output/pdf/v17_external_literature/"
                    "Caprara_2026_IJEPES_111940_CC_BY_4_0.pdf"
                ),
                "publisher_version_sha256": CAPRARA_PDF_SHA256,
                "bytes": 9261880,
                "license": "CC BY 4.0",
                "repository": "Universitat Politecnica de Catalunya UPCommons",
                "repository_item_uuid": "c15cab92-e0eb-4124-852d-e02e1dde9bdc",
                "repository_bitstream_uuid": "e87ee20a-d65c-451d-8023-ef0bc3ec3325",
                "upcommons_metadata_path": (
                    "output/pdf/v17_external_literature/"
                    "Caprara_2026_UPCommons_metadata.json"
                ),
                "upcommons_metadata_sha256": CAPRARA_UPCOMMONS_SHA256,
                "crossref_metadata_path": (
                    "output/pdf/v17_external_literature/"
                    "Caprara_2026_Crossref_metadata.json"
                ),
                "crossref_metadata_sha256": CAPRARA_CROSSREF_SHA256,
            },
            "full_paper_inspected": True,
            "reported_approximately_20_percent": {
                "exact_table_sum_fraction": 0.205,
                "reported_main_rounded_fraction": 0.20,
                "numerator": (
                    "Average estimated GPU-side power attributable to tasks with "
                    "observed queue latency greater than 10 minutes; Table 5 bins "
                    "sum to 20.5 percent."
                ),
                "denominator": (
                    "Average total estimated GPU-side power of all modeled Alibaba "
                    "MLaaS tasks over the common trace interval. Because all bins "
                    "share the same interval, the power share is also an energy-share "
                    "ratio for that modeled GPU trace."
                ),
                "time_aggregation": (
                    "A-posteriori latency-class distribution over the cleaned "
                    "two-month Alibaba MLaaS trace. It is distinct from the "
                    "one-week LAD-Flex activation study."
                ),
                "flexibility_semantics": (
                    "Temporal task deferral/postponement, not spatial migration, "
                    "cancellation, or permanent load removal."
                ),
                "service_semantics": (
                    "Tasks are not cancelled, are assumed to run to completion, and "
                    "eligibility uses observed latency plus duration/window rules. "
                    "Later rescheduling rebound and full inter-task dependency costs "
                    "are not modeled."
                ),
                "not_equivalent_to": [
                    "server IT power",
                    "total IT equipment power",
                    "whole-facility utility power",
                    "V17 ESIF whole-facility IT envelope",
                    "the separate up-to-22-percent favorable-window peak deferral outcome",
                ],
            },
            "evidence_locations": [
                {
                    "page": 5,
                    "location": "Section 3.1 power-model preamble",
                    "finding": "No measured per-device telemetry; first-order GPU model supports workload-level estimates only.",
                },
                {
                    "page": 6,
                    "location": "Section 3.1, Equations (1)-(7)",
                    "finding": "IT-side GPU model and latency-class power/energy aggregation; cooling, UPS, and auxiliaries excluded.",
                },
                {
                    "page": 11,
                    "location": "Table 5 and Section 5.1",
                    "finding": "Latency greater than 10 minutes accounts for 20.5 percent of estimated GPU-side average power.",
                },
                {
                    "page": 14,
                    "location": "Figure 10 and Section 5.2.1",
                    "finding": "Whole-facility response and PUE are unobserved; favorable-window deferral percentages are separate outcomes.",
                },
                {
                    "page": 20,
                    "location": "Section 5.2.4 and Table 12",
                    "finding": "Deferred tasks later consume the same energy; rescheduling rebound is not quantified.",
                },
                {
                    "pages": [24, 25],
                    "location": "Section 6 limitations and Section 7 conclusions",
                    "finding": "First-order GPU-side, not whole-facility; no facility telemetry or dynamic PUE; multi-task dependencies remain a limitation.",
                },
            ],
            "admissibility_gates": {
                "1_peer_reviewed_SCIE": "PASS",
                "2_real_trace_or_measurement_basis": "PASS_REAL_TRACE",
                "3_explicit_power_or_energy_attribution": "PASS_ESTIMATED_GPU_POWER",
                "4_explicit_schedulable_definition": "PASS_LATENCY_BASED_DEFERRAL",
                "5_service_deferred_not_removed": "PASS_WITH_REBOUND_LIMITATION",
                "6_denominator_close_to_V17_IT_envelope": "FAIL_GPU_ONLY_SCOPE",
                "7_no_denominator_conversion_required": "FAIL_GPU_TO_WHOLE_IT_CONVERSION_REQUIRED",
            },
            "main_authority_decision": "REJECTED_SCOPE_MISMATCH",
            "CAPRARA_MAIN_AUTHORITY": "REJECTED_SCOPE_MISMATCH",
            "adopted_value": None,
        },
        "cao_supporting_source": {
            "citation": (
                "Y. Cao, M. Cheng, S. Zhang, H. Mao, P. Wang, C. Li, "
                "Y. Feng, and Z. Ding, Data-driven flexibility assessment "
                "for internet data center towards periodic batch workloads, "
                "Applied Energy 324 (2022) 119665."
            ),
            "doi": "10.1016/j.apenergy.2022.119665",
            "journal": "Applied Energy",
            "peer_reviewed_journal_article": True,
            "SCIE_verification": {
                "status": "PASS",
                "evidence": "Applied Energy appears in the Science Citation Index Expanded journal list.",
                "url": "https://lkouniv.ac.in/site/writereaddata/siteContent/ESCI_011024.pdf",
            },
            "archive": {
                "crossref_metadata_path": (
                    "output/pdf/v17_external_literature/"
                    "Cao_2022_Crossref_metadata.json"
                ),
                "crossref_metadata_sha256": CAO_CROSSREF_SHA256,
                "public_author_full_text_inspected": True,
                "public_author_full_text_url": (
                    "https://www.researchgate.net/publication/362489057_"
                    "Data-driven_flexibility_assessment_for_internet_data_"
                    "center_towards_periodic_batch_workloads"
                ),
                "publisher_url": "https://www.sciencedirect.com/science/article/pii/S0306261922009631",
                "local_full_pdf_redistributed": False,
                "redistribution_note": "Publisher PDF is not open access; metadata and exact inspection provenance are archived without redistributing it.",
            },
            "full_text_findings": {
                "basis": "Three Alibaba production batch clusters and a data-driven job-level power mapping.",
                "reported_context": [
                    "Table I background: batch workloads are about 40 percent by count and about 70 percent of total power.",
                    "Background: periodic workloads are about 24 percent by count of all workloads and about 60 percent of batch workloads.",
                    "Figure 11 case study: about 68 percent of periodic-job power has slack shorter than 15 minutes; other bins describe longer slack.",
                ],
                "denominator_problem": (
                    "The case-study slack distribution is conditioned on periodic-job "
                    "power, not total whole-IT power; non-periodic and auxiliary other "
                    "load is modeled separately. Task-count and batch-power percentages "
                    "do not directly produce a whole-IT schedulable energy share."
                ),
                "prohibited_derivation_used": False,
                "main_authority_decision": "REJECTED_NO_DIRECT_SCOPE_MATCHED_SINGLE_SHARE",
                "supporting_evidence_only": True,
            },
        },
        "replacement_search": {
            "search_scope": (
                "Peer-reviewed journal studies of numeric schedulable, deferrable, "
                "or shiftable data-center compute power/energy shares using real "
                "production traces or measurements."
            ),
            "screened_nonqualifying_examples": [
                {
                    "source": "Flexible data centers reduce power system costs but can increase emissions",
                    "doi": "10.1016/j.isci.2026.116497",
                    "rejection": "Uses 20/60/100-percent flexible-share scenarios as model inputs, not an empirically derived authority value.",
                },
                {
                    "source": "The Potential of Data Center Energy Demand To Provide Grid Flexibility",
                    "doi": "10.1007/s40518-025-00258-9",
                    "rejection": "Review reports that the potential scale remains poorly understood and supplies no direct whole-IT trace-derived share satisfying the rule.",
                },
                {
                    "source": "Workload-flexible data centers reduce renewable curtailment in Europe's net-zero energy system",
                    "doi": "10.1016/j.crsus.2026.100755",
                    "rejection": "Energy-system scenario study; flexible share is an input scenario rather than a production-trace-derived whole-IT fraction.",
                },
                {
                    "source": "Mixture-of-experts based multi-critic deep reinforcement learning for sustainable management of data center microgrids",
                    "doi": "10.1016/j.apenergy.2026.127561",
                    "rejection": "Assumes a 70-percent flexible workload share in simulation instead of estimating it from the Alibaba trace.",
                },
            ],
            "qualifying_replacement_found": False,
            "search_conclusion": "OTHER_SOURCE_NOT_FOUND",
        },
        "exact_adopted_main_value": None,
        "external_authority_artifact_created": False,
        "eta_FLEX": None,
        "scientific_refreeze_resumed": False,
        "downstream_actions_not_run": [
            "eta_FLEX calibration",
            "Reference Scheduler V4",
            "fixed-plus-flex label construction",
            "RC-MQT retraining",
            "April D-1 anchors and surrogate validation",
            "April B0/B1/B2/B3",
            "Primary or Secondary Fresh OpenDSS",
            "April-15 decomposition equivalence",
        ],
        "final_classification": FINAL_CLASSIFICATION,
        "next_decision": NEXT_DECISION,
        "counters": _zero_counters(),
    }


def build_resolution(admissibility: dict[str, Any]) -> dict[str, Any]:
    """Return the descendant gap-resolution record without rewriting history."""

    return {
        "artifact_id": "V17_FLEXIBLE_SHARE_AUTHORITY_GAP_RESOLUTION_V1",
        "status": BLOCK_STATUS,
        "resolution_status": "NOT_RESOLVED_EXTERNAL_SCI_SCOPE_MISMATCH",
        "historical_artifacts_immutable": True,
        "parents": [
            {
                "path": "dayahead/artifacts/v17_candidate/V17_AIDC_FLEXIBLE_SHARE_AUTHORITY_PRECHECK.json",
                "sha256": PRECHECK_SHA256,
            },
            {
                "path": "dayahead/artifacts/v17_candidate/V17_FLEXIBLE_SHARE_AUTHORITY_GAP.json",
                "sha256": GAP_SHA256,
            },
        ],
        "external_admissibility_artifact": {
            "path": "dayahead/artifacts/v17_candidate/V17_EXTERNAL_SCI_FLEXIBLE_SHARE_ADMISSIBILITY.json",
            "artifact_id": admissibility["artifact_id"],
        },
        "CAPRARA_MAIN_AUTHORITY": "REJECTED_SCOPE_MISMATCH",
        "qualifying_replacement_found": False,
        "gap_mark": "RETAINED_NOT_RESOLVED",
        "exact_adopted_main_value": None,
        "eta_FLEX": None,
        "scientific_refreeze_resumed": False,
        "final_classification": FINAL_CLASSIFICATION,
        "next_decision": NEXT_DECISION,
        "counters": admissibility["counters"],
    }


def verify_archives(repo_root: Path) -> dict[str, str]:
    """Fail closed if archived evidence differs from its frozen digest."""

    expected = {
        "output/pdf/v17_external_literature/Caprara_2026_IJEPES_111940_CC_BY_4_0.pdf": CAPRARA_PDF_SHA256,
        "output/pdf/v17_external_literature/Caprara_2026_UPCommons_metadata.json": CAPRARA_UPCOMMONS_SHA256,
        "output/pdf/v17_external_literature/Caprara_2026_Crossref_metadata.json": CAPRARA_CROSSREF_SHA256,
        "output/pdf/v17_external_literature/Cao_2022_Crossref_metadata.json": CAO_CROSSREF_SHA256,
        "dayahead/artifacts/v17_candidate/V17_AIDC_FLEXIBLE_SHARE_AUTHORITY_PRECHECK.json": PRECHECK_SHA256,
        "dayahead/artifacts/v17_candidate/V17_FLEXIBLE_SHARE_AUTHORITY_GAP.json": GAP_SHA256,
    }
    observed: dict[str, str] = {}
    for relative_path, expected_sha in expected.items():
        path = repo_root / relative_path
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"archive hash mismatch for {relative_path}: {actual_sha} != {expected_sha}"
            )
        observed[relative_path] = actual_sha
    return observed


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
    repo_root = Path(__file__).resolve().parents[1]
    verify_archives(repo_root)
    admissibility = build_admissibility()
    _write_json(
        args.output_dir / "V17_EXTERNAL_SCI_FLEXIBLE_SHARE_ADMISSIBILITY.json",
        admissibility,
    )
    _write_json(
        args.output_dir / "V17_FLEXIBLE_SHARE_AUTHORITY_GAP_RESOLUTION.json",
        build_resolution(admissibility),
    )
    print(FINAL_CLASSIFICATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
