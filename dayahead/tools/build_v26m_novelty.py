"""Serialize the post-oracle SAFE-Flex systematic novelty audit."""

from __future__ import annotations

import csv
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"
COLUMNS = [
    "Paper", "URL", "Data_center", "GPU", "Job_level_state",
    "Survival_residual_service", "Unseen_arrivals", "Known_innovation_decomposition",
    "Scheduler_constraints", "Random_feasible_set", "Inner_safe_set",
    "Trajectory_calibration", "Intertemporal_conservation", "Grid_use_output",
    "Near_duplicate", "Closest_overlap", "Key_difference",
]


ROWS = [
    {
        "Paper": "Harnessing Flexible Spatial and Temporal Data Center Workloads for Grid Regulation Services (Fan & Zhao, 2026)",
        "URL": "https://arxiv.org/abs/2602.01508", "Data_center": "YES", "GPU": "NO",
        "Job_level_state": "PARTIAL_QUEUE_STATE", "Survival_residual_service": "NO",
        "Unseen_arrivals": "PARTIAL_LOAD_FORECAST", "Known_innovation_decomposition": "NO",
        "Scheduler_constraints": "YES_SPACE_TIME", "Random_feasible_set": "PARTIAL_CHANCE_CONSTRAINTS",
        "Inner_safe_set": "NO", "Trajectory_calibration": "NO", "Intertemporal_conservation": "YES",
        "Grid_use_output": "YES", "Near_duplicate": "NO",
        "Closest_overlap": "day-ahead queue-aware deliverable data-center regulation",
        "Key_difference": "co-optimization/VaR constraints rather than job residual survival propagated to a conformal inner random set",
    },
    {
        "Paper": "Online Electricity Purchase for Data Center with Dynamic Virtual Battery (Gao et al., 2024)",
        "URL": "https://arxiv.org/abs/2404.19387", "Data_center": "YES", "GPU": "NO",
        "Job_level_state": "NO", "Survival_residual_service": "NO", "Unseen_arrivals": "AGGREGATE_UNCERTAINTY",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "PARTIAL_FLEXIBLE_TASKS",
        "Random_feasible_set": "DYNAMIC_VIRTUAL_BATTERY", "Inner_safe_set": "NO",
        "Trajectory_calibration": "NO", "Intertemporal_conservation": "YES", "Grid_use_output": "YES",
        "Near_duplicate": "NO", "Closest_overlap": "uncertain dynamic flexibility aggregation",
        "Key_difference": "no observable GPU-job state, survival model, or trajectory-calibrated inner set",
    },
    {
        "Paper": "Truthful Online Scheduling of Cloud Workloads under Uncertainty (Babaioff et al., 2022)",
        "URL": "https://arxiv.org/abs/2203.01213", "Data_center": "CLOUD", "GPU": "NO",
        "Job_level_state": "YES_STATEMENTS_OF_WORK", "Survival_residual_service": "NO",
        "Unseen_arrivals": "YES_PROBABILISTIC", "Known_innovation_decomposition": "NO",
        "Scheduler_constraints": "YES", "Random_feasible_set": "NO", "Inner_safe_set": "NO",
        "Trajectory_calibration": "NO", "Intertemporal_conservation": "YES", "Grid_use_output": "NO",
        "Near_duplicate": "NO", "Closest_overlap": "probabilistic future arrivals and durations in cloud scheduling",
        "Key_difference": "mechanism-design scheduler, not day-ahead flexibility-set forecasting",
    },
    {
        "Paper": "Tiresias: A GPU Cluster Manager for Distributed Deep Learning (Gu et al., 2019)",
        "URL": "https://rtcl.eecs.umich.edu/rtclweb/assets/publications/2019/gu-nsdi19.pdf",
        "Data_center": "CLUSTER", "GPU": "YES", "Job_level_state": "YES",
        "Survival_residual_service": "POINT_OR_ASSUMED_REMAINING_SERVICE", "Unseen_arrivals": "ONLINE_ONLY",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "YES",
        "Random_feasible_set": "NO", "Inner_safe_set": "NO", "Trajectory_calibration": "NO",
        "Intertemporal_conservation": "YES", "Grid_use_output": "NO", "Near_duplicate": "NO",
        "Closest_overlap": "GPU job attained/remaining-service-aware scheduling",
        "Key_difference": "no probabilistic day-ahead flexibility envelope or conformal safety calibration",
    },
    {
        "Paper": "RLSchert: HPC Scheduler Using DRL and Remaining Time Prediction (Fan et al., 2021)",
        "URL": "https://www.mdpi.com/2079-9292/10/16/1928", "Data_center": "HPC", "GPU": "PARTIAL",
        "Job_level_state": "YES", "Survival_residual_service": "POINT_REMAINING_RUNTIME",
        "Unseen_arrivals": "NO_EXPLICIT_FORECAST", "Known_innovation_decomposition": "NO",
        "Scheduler_constraints": "YES", "Random_feasible_set": "NO", "Inner_safe_set": "NO",
        "Trajectory_calibration": "NO", "Intertemporal_conservation": "YES", "Grid_use_output": "NO",
        "Near_duplicate": "NO", "Closest_overlap": "remaining-runtime prediction embedded in scheduler",
        "Key_difference": "policy optimization rather than uncertainty propagation to a deliverable inner set",
    },
    {
        "Paper": "UARP: uncertainty-aware runtime prediction for HPC (Choi & Oh, 2026)",
        "URL": "https://link.springer.com/article/10.1007/s11227-026-08422-8", "Data_center": "HPC", "GPU": "GENERAL_HPC",
        "Job_level_state": "YES", "Survival_residual_service": "MULTI_QUANTILE_RUNTIME",
        "Unseen_arrivals": "NO", "Known_innovation_decomposition": "NO", "Scheduler_constraints": "WALLCLOCK_BUFFER",
        "Random_feasible_set": "NO", "Inner_safe_set": "NO", "Trajectory_calibration": "NO",
        "Intertemporal_conservation": "PARTIAL", "Grid_use_output": "NO", "Near_duplicate": "NO",
        "Closest_overlap": "job-specific runtime uncertainty for scheduling safety",
        "Key_difference": "no arrival innovation split or scheduler-feasible flexibility-set forecast",
    },
    {
        "Paper": "Uncertain FlexOffers (Lilliu et al., ACM e-Energy 2023)",
        "URL": "https://doi.org/10.1145/3575813.3576873", "Data_center": "NO", "GPU": "NO",
        "Job_level_state": "DEVICE_LEVEL", "Survival_residual_service": "NO", "Unseen_arrivals": "GENERIC_UNCERTAINTY",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "GENERIC_ENERGY",
        "Random_feasible_set": "YES", "Inner_safe_set": "PROBABILITY_DEPENDENT",
        "Trajectory_calibration": "NO", "Intertemporal_conservation": "YES", "Grid_use_output": "YES",
        "Near_duplicate": "NO", "Closest_overlap": "scalable uncertainty-aware flexibility representation",
        "Key_difference": "not a GPU workload state forecaster and no blocked trajectory conformal calibration",
    },
    {
        "Paper": "Improved Inner Approximation for Aggregating Power Flexibility (Wen et al., 2023)",
        "URL": "https://arxiv.org/abs/2303.01691", "Data_center": "NO", "GPU": "NO",
        "Job_level_state": "NO", "Survival_residual_service": "NO", "Unseen_arrivals": "NO",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "GRID_DER",
        "Random_feasible_set": "NO", "Inner_safe_set": "YES_GEOMETRIC",
        "Trajectory_calibration": "NO", "Intertemporal_conservation": "PARTIAL", "Grid_use_output": "YES",
        "Near_duplicate": "NO", "Closest_overlap": "feasible flexibility inner approximation",
        "Key_difference": "deterministic DER aggregation rather than learned job-state uncertainty",
    },
    {
        "Paper": "Single Trajectory Conformal Prediction (Lee & Matni, 2024)",
        "URL": "https://arxiv.org/abs/2406.01570", "Data_center": "NO", "GPU": "NO",
        "Job_level_state": "NO", "Survival_residual_service": "NO", "Unseen_arrivals": "NO",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "NO",
        "Random_feasible_set": "GENERAL_PREDICTION_SET", "Inner_safe_set": "RISK_CONTROLLING_SET",
        "Trajectory_calibration": "YES_BLOCKING_THEORY", "Intertemporal_conservation": "NO", "Grid_use_output": "NO",
        "Near_duplicate": "NO", "Closest_overlap": "conformal control with temporally correlated single trajectories",
        "Key_difference": "general theory, not workload/service-set construction",
    },
    {
        "Paper": "Redesigning Data Centers for Renewable Energy / Virtual Battery (Agarwal et al., HotNets 2021)",
        "URL": "https://www.microsoft.com/en-us/research/wp-content/uploads/2021/10/VirtualBattery.pdf",
        "Data_center": "YES", "GPU": "NO", "Job_level_state": "APPLICATION_LEVEL",
        "Survival_residual_service": "NO", "Unseen_arrivals": "NO_EXPLICIT_FORECAST",
        "Known_innovation_decomposition": "NO", "Scheduler_constraints": "YES_POWER_NETWORK_AWARE",
        "Random_feasible_set": "NO", "Inner_safe_set": "NO", "Trajectory_calibration": "NO",
        "Intertemporal_conservation": "YES", "Grid_use_output": "YES", "Near_duplicate": "NO",
        "Closest_overlap": "computation as virtual battery with power-aware scheduling",
        "Key_difference": "architecture/scheduling concept without calibrated probabilistic deliverability set",
    },
]


def main() -> None:
    csv_path = OUT / "V26M_NEAREST_PRIOR_WORK_MATRIX.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ROWS)
    payload = {
        "artifact_id": "V26M_SYSTEMATIC_NOVELTY_AUDIT_V1",
        "oracle_gate_prerequisite_passed": True,
        "search_date": "2026-09-01",
        "venues_searched": ["IEEE", "ACM", "Elsevier", "Springer", "arXiv", "OpenReview", "NeurIPS", "ICML", "ICLR", "KDD", "AISTATS", "UAI", "AAAI"],
        "query_families": ["data-center probabilistic flexibility envelope", "GPU/HPC remaining runtime uncertainty", "scheduler-aware flexibility forecast", "random feasible set and inner approximation", "trajectory conformal flexibility", "known committed workload versus unseen arrivals"],
        "papers_in_nearest_matrix": len(ROWS),
        "near_identical_architecture_found": False,
        "novelty_classification": "PARTIAL_OVERLAP_DISTINCT_COMBINATION",
        "NOVELTY_GATE_PASS": True,
        "WORLD_FIRST": "NOT_YET",
        "distinct_combination": [
            "causal event-censored observable GPU-job state",
            "running residual and pending service uncertainty separated from G/N innovation",
            "job uncertainty propagated through intertemporally coupled scheduler feasibility",
            "trajectory-level calibrated probabilistic inner service set",
        ],
        "strongest_overlap": "Fan & Zhao (2026) combines queue-state constraints, interactive load forecasts, and deliverable data-center regulation; it does not disclose the same job residual-survival/known-innovation decomposition or conformal inner random-set architecture.",
        "claim_limit": "Component methods are established. Only the integrated, trace-audited combination is treated as distinct; no world-first claim is made.",
    }
    (OUT / "V26M_SYSTEMATIC_NOVELTY_AUDIT.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md = """# V26M SAFE-Flex systematic novelty audit

Classification: **PARTIAL_OVERLAP_DISTINCT_COMBINATION**  
Novelty gate: **PASS**  
WORLD_FIRST: **NOT_YET**

The closest 2026 work combines data-center queue-state constraints, interactive load forecasts, chance constraints, and regulation co-optimization. Other papers separately cover probabilistic cloud arrivals, GPU/HPC remaining-runtime prediction, uncertainty-aware flexibility representations, deterministic inner approximations, or trajectory conformal prediction.

No reviewed work joined all four elements used here: causally reconstructed observable GPU-job state; explicit separation of known committed work from the six-hour gap and D-day innovation; propagation of job-level residual/service uncertainty through an intertemporally coupled scheduler service set; and blocked trajectory-level calibration of an inner day-ahead flexibility set.

This is a distinct combination claim, not a claim that its component methods are new and not a world-first claim. The complete capability comparison is in `V26M_NEAREST_PRIOR_WORK_MATRIX.csv`.
"""
    (OUT / "V26M_SYSTEMATIC_NOVELTY_AUDIT.md").write_text(md, encoding="utf-8")
    print(json.dumps({"classification": payload["novelty_classification"], "papers": len(ROWS)}))


if __name__ == "__main__":
    main()

