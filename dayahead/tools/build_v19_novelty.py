from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
ACCESS_DATE = "2026-09-01"

QUERIES = [
    "temporal point process data center workload",
    "marked temporal point process GPU workload",
    "GPU job arrival prediction point process",
    "aggregate conditioned temporal point process",
    "mass conserving temporal point process",
    "mass-conserving event forecasting",
    "service-set forecasting temporal point process",
    "future event set workload forecasting",
    "long horizon marked event set prediction",
    "aggregate constrained event forecasting",
    "data center job arrival event forecasting",
    "AI data center workload forecasting point process",
    "energy-aware marked temporal point process",
]

MATRIX_FIELDS = [
    "paper_model",
    "year",
    "venue",
    "event_time_prediction",
    "marked_events",
    "long_horizon_all_at_once",
    "continuous_service_mass",
    "daily_aggregate_mass_head",
    "hard_aggregate_event_reconciliation",
    "gpu_resource_power_tier",
    "electrical_power_mapping",
    "d_minus_1_datacenter_scheduling",
    "nearest_component",
    "near_duplicate",
    "url",
]

WORKS = [
    {
        "paper_model": "DualTPP / Long Horizon Forecasting With Temporal Point Processes",
        "year": 2021,
        "venue": "ACM WSDM",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "NO; binwise constrained sequential inference",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO; aggregate count model",
        "hard_aggregate_event_reconciliation": "PARTIAL; count/timing constrained quadratic inference",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "micro event model plus macro aggregate constraint",
        "near_duplicate": "NO",
        "url": "https://doi.org/10.1145/3437963.3441740",
    },
    {
        "paper_model": "DEF / Detecting the Future",
        "year": 2026,
        "venue": "AAAI",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "YES",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "parallel query event detection plus horizon matching",
        "near_duplicate": "NO",
        "url": "https://doi.org/10.1609/aaai.v40i27.39413",
    },
    {
        "paper_model": "EventFlow",
        "year": 2026,
        "venue": "AISTATS",
        "event_time_prediction": "YES",
        "marked_events": "LIMITED/benchmark dependent",
        "long_horizon_all_at_once": "YES",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO; event-count distribution",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "non-autoregressive joint future event-time generation",
        "near_duplicate": "NO",
        "url": "https://openreview.net/forum?id=QXqKGOE2JW",
    },
    {
        "paper_model": "Add and Thin",
        "year": 2023,
        "venue": "NeurIPS",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "YES; diffusion conditional sampling",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "whole-window point-process generation",
        "near_duplicate": "NO",
        "url": "https://proceedings.neurips.cc/paper_files/paper/2023/file/b1d9c7e7bd265d81aae8d74a7a6bd7f1-Paper-Conference.pdf",
    },
    {
        "paper_model": "S2P2 / Deep Continuous-Time State-Space Models",
        "year": 2025,
        "venue": "NeurIPS/medical open manuscript record",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "continuous-time state-space event encoder",
        "near_duplicate": "NO",
        "url": "https://openreview.net/forum?id=91cd21773ccd043766294dd5cebc557ae7de3dce",
    },
    {
        "paper_model": "RMTPP",
        "year": 2016,
        "venue": "ACM KDD",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "recurrent marked continuous-time history encoder",
        "near_duplicate": "NO",
        "url": "https://doi.org/10.1145/2939672.2939875",
    },
    {
        "paper_model": "SAHP",
        "year": 2020,
        "venue": "ICML/PMLR",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "self-attentive history representation",
        "near_duplicate": "NO",
        "url": "https://proceedings.mlr.press/v119/zhang20q.html",
    },
    {
        "paper_model": "Transformer Hawkes Process",
        "year": 2020,
        "venue": "ICML",
        "event_time_prediction": "YES",
        "marked_events": "YES",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "NO",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "Transformer TPP baseline",
        "near_duplicate": "NO",
        "url": "https://arxiv.org/abs/2002.09291",
    },
    {
        "paper_model": "Deep Renewal Processes",
        "year": 2019,
        "venue": "NeurIPS TPP workshop / PLOS ONE extension",
        "event_time_prediction": "YES",
        "marked_events": "demand size",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "YES; intermittent demand size",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "intermittent occurrence and continuous size forecasting",
        "near_duplicate": "NO",
        "url": "https://arxiv.org/abs/1911.10416",
    },
    {
        "paper_model": "MC-LSTM",
        "year": 2021,
        "venue": "ICML/PMLR",
        "event_time_prediction": "NO",
        "marked_events": "NO",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "YES",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "YES; recurrent physical mass flow",
        "gpu_resource_power_tier": "NO",
        "electrical_power_mapping": "NO",
        "d_minus_1_datacenter_scheduling": "NO",
        "nearest_component": "hard architectural mass conservation",
        "near_duplicate": "NO",
        "url": "https://proceedings.mlr.press/v139/hoedt21a.html",
    },
    {
        "paper_model": "Characterization and Prediction of DL Workloads in Large-Scale GPU Datacenters",
        "year": 2021,
        "venue": "SC21",
        "event_time_prediction": "NO",
        "marked_events": "job/resource workload records",
        "long_horizon_all_at_once": "NO",
        "continuous_service_mass": "resource/runtime characterization",
        "daily_aggregate_mass_head": "NO",
        "hard_aggregate_event_reconciliation": "NO",
        "gpu_resource_power_tier": "GPU resource but not V19 tiers",
        "electrical_power_mapping": "energy-saving application, not tier bridge",
        "d_minus_1_datacenter_scheduling": "scheduling case studies, not this forecast contract",
        "nearest_component": "GPU datacenter workload prediction domain",
        "near_duplicate": "NO",
        "url": "https://www.sc21.supercomputing.org/proceedings/tech_paper/tech_paper_pages/pap594.html",
    },
]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    audit = {
        "artifact_id": "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT_V1",
        "access_date": ACCESS_DATE,
        "search_queries": QUERIES,
        "sources_queried": {
            "IEEE_Xplore": "SEARCH_RESULTS_ACCESSIBLE; no near-identical full paper found",
            "ACM_Digital_Library": "METADATA_AND_PRIMARY_PAPERS_ACCESSIBLE",
            "ScienceDirect": "ABSTRACTS_ACCESSIBLE; selected full text access variable",
            "SpringerLink": "SEARCH_AND_ABSTRACTS_ACCESSIBLE",
            "arXiv": "ACCESSIBLE",
            "OpenReview": "SEARCH/METADATA_ACCESSIBLE; some PDF challenges encountered",
            "NeurIPS": "PRIMARY_PROCEEDINGS_ACCESSIBLE",
            "ICML": "PMLR_PRIMARY_PROCEEDINGS_ACCESSIBLE",
            "ICLR": "OPENREVIEW_ACCESSIBLE",
            "KDD": "PRIMARY_KDD_PDF_ACCESSIBLE",
            "AAAI": "PRIMARY_PROCEEDINGS_ACCESSIBLE",
            "AISTATS": "OPENREVIEW/PMLR_METADATA_ACCESSIBLE",
            "Web_of_Science": "NOT_ACCESSED_NO_AUTHENTICATED_CONNECTOR",
            "Scopus": "NOT_ACCESSED_NO_AUTHENTICATED_CONNECTOR",
        },
        "nearest_prior_works": WORKS,
        "substantive_comparison": {
            "closest_single_work": "DualTPP",
            "closest_component_combination": ["DualTPP", "DEF", "EventFlow", "MC-LSTM"],
            "already_known_components": [
                "marked continuous-time event encoders",
                "macro count plus micro TPP coupling",
                "all-at-once horizon event decoding and matching",
                "hard conservation architectures",
                "hierarchical forecast reconciliation",
                "GPU workload characterization and scheduling",
            ],
            "distinct_system_level_combination": [
                "D-1 submission-only H100 history",
                "conditional next-day continuous service-mass mean and quantiles",
                "anonymous all-at-once time/tier/latency service-event set",
                "hard normalized allocation of the predicted aggregate service mass for mean/Q50/Q90",
                "direct frozen H100 tier-to-IT-to-PCC electrical bridge",
            ],
            "novelty_scope_warning": "The continuous-time encoder, set decoder, Sinkhorn matching, quantile heads, and normalization are not individually novel. Any claim must be limited to the aggregate-conditioned exact service-mass reconciliation system and its datacenter electrical application.",
        },
        "novelty_gate": "PASS_NO_NEAR_IDENTICAL_ARCHITECTURE",
        "near_duplicate_found": False,
        "world_first_claim_allowed": "NOT_YET",
        "gate_rationale": "No accessed single architecture jointly predicts continuous daily GPU service mass and an anonymous marked next-day service-event set with hard exact scenario-wise reconciliation and frozen electrical tier mapping. DualTPP is the strongest conceptual predecessor and prevents broad novelty claims.",
    }
    write_json(OUT / "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT.json", audit)

    with (OUT / "V19_NEAREST_PRIOR_WORK_MATRIX.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=MATRIX_FIELDS)
        writer.writeheader()
        writer.writerows(WORKS)

    nearest = WORKS[:5]
    lines = [
        "# V19 C-MASS-TPP systematic novelty audit",
        "",
        f"Access date: {ACCESS_DATE}",
        "",
        "## Gate",
        "",
        "`PASS_NO_NEAR_IDENTICAL_ARCHITECTURE`",
        "",
        "World-first claim allowed: `NOT_YET`",
        "",
        "No accessed paper was a near-identical architecture. This is not proof that no such work exists. The claim boundary is the system-level combination of an aggregate continuous service-mass head, an anonymous all-at-once marked service-set decoder, and hard scenario-wise reconciliation, followed by the frozen H100 electrical bridge.",
        "",
        "## Nearest five",
        "",
        "| Model | Most similar component | What it already has | What C-MASS-TPP adds | Near duplicate? |",
        "|---|---|---|---|---|",
    ]
    additions = {
        "DualTPP / Long Horizon Forecasting With Temporal Point Processes": "continuous GPU-h mass rather than counts; all-at-once anonymous marked packets; exact mean/Q50/Q90 mass identity; electrical bridge",
        "DEF / Detecting the Future": "daily mass head and exact aggregate-conditioned service-mass allocation plus electrical marks",
        "EventFlow": "continuous service mass, tier/latency marks, hard aggregate reconciliation, D-1 datacenter boundary",
        "Add and Thin": "deterministic aggregate-conditioned service packet allocation and electrical semantics",
        "S2P2 / Deep Continuous-Time State-Space Models": "long-horizon all-at-once service set and hard aggregate mass identity",
    }
    for row in nearest:
        lines.append(
            "| {paper_model} | {nearest_component} | event={event_time_prediction}, marked={marked_events}, all-at-once={long_horizon_all_at_once} | {added} | {near_duplicate} |".format(
                **row, added=additions[row["paper_model"]]
            )
        )
    lines.extend(
        [
            "",
            "## Conservative interpretation",
            "",
            "DualTPP already establishes the central idea that microscopic event forecasting can be coupled to a macroscopic aggregate constraint. DEF and EventFlow already establish all-at-once or joint long-horizon event forecasting. MC-LSTM and forecast-reconciliation research already establish hard conservation/coherence. Therefore C-MASS-TPP must not claim novelty for those components separately.",
            "",
            "The audit supports development and empirical testing, not a world-first statement. A formal publication claim still requires a human-led systematic review with citation chaining and access to Web of Science/Scopus.",
        ]
    )
    (OUT / "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
