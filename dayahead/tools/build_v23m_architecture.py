"""Freeze the V23M ACQ/RACQ architecture and training policy contracts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    recurrence = json.loads((OUT / "V23M_RECURRENCE_SIGNAL_AUDIT.json").read_text(encoding="utf-8"))
    gate = bool(recurrence["RACQ_RECURRENCE_GATE_PASS"])
    write("V23M_RACQ_FLEX_ARCHITECTURE_CONTRACT.json", {
        "artifact_id": "V23M_RACQ_FLEX_ARCHITECTURE_CONTRACT_V1",
        "proposed_model_name": "RACQ-Flex" if gate else "ACQ-Flex",
        "RACQ_RECURRENCE_GATE_PASS": gate,
        "recurrence_branch_status": "ACTIVE" if gate else "DISABLED_BY_PREREGISTERED_GATE",
        "modules": {
            "A": "hourly DeepSets plus causal decay-GRU",
            "B": "all-motif chunked attention memory; experimental only when recurrence gate fails",
            "C": "recurring/innovation decomposition; disabled in ACQ fallback",
            "D": "hurdle Bernoulli plus zero-truncated negative binomial count",
            "E": "two-component LogNormal body plus bounded-shape GPD tail",
            "F": "low-rank 24x6x5 cohort decoder",
            "G": "exactly coherent 96x6x5 allocation",
            "H": "differentiable fluid EDF and frozen exact scheduler adapter",
            "I": "frozen tier-to-power IT projection; PUE excluded from ML loss",
        },
        "mass_identity_tolerance_GPU_h": 1e-9,
        "motif_top_K": None,
        "all_active_motifs_required": True,
        "C_MODEL_GPU_equivalent": 528,
        "C_MODEL_interpretation": "CASE_STUDY_ONLY_NOT_MELBOURNE_INSTALLED_CAPACITY",
    })
    configs = [json.loads((ROOT / "dayahead" / "ml" / "racq_flex" / "configs" / f"{name}.json").read_text()) for name in "ABCD"]
    write("V23M_TRAINING_POLICY_FREEZE.json", {
        "artifact_id": "V23M_TRAINING_POLICY_FREEZE_V1",
        "frozen_before_outer_CV": True,
        "model_family_evaluated": "RACQ-Flex" if gate else "ACQ-Flex",
        "configs": configs,
        "optimizer": "AdamW",
        "max_epochs": 100,
        "min_epochs": 15,
        "early_stopping_patience": 10,
        "gradient_clip_norm": 1.0,
        "weight_decay_inner_candidates": [0.0001, 0.001],
        "seeds": [20260901, 20260902, 20260903],
        "seed_cherry_pick": False,
        "queue_power_loss_configs": {"QP0":[0.0,0.0],"QP1":[0.05,0.0],"QP2":[0.05,0.05],"QP3":[0.10,0.05]},
        "selection_metrics": "TRAINING_ONLY_SCALE_INDEPENDENT_ML_METRICS",
        "April_reads_before_freeze": 0,
        "grid_objective_reads_for_selection": 0,
        "result_based_retuning": 0,
    })
    print(json.dumps({"model_family": "RACQ-Flex" if gate else "ACQ-Flex", "configs": len(configs)}))


if __name__ == "__main__":
    main()
