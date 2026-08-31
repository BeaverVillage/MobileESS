"""Build an outcome-access ledger without opening any new target data."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    rows = [
        {"period": "2025-04", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": True, "ML_prediction_viewed": True, "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "V18R2_APRIL_DIAGNOSTIC_FORECAST + V17 April results"},
        {"period": "2025-05", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": "uncertain", "ML_prediction_viewed": "uncertain", "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "V16_3_MAY02 artifacts and W18_2025-05-05 result/initializer lineage"},
        {"period": "2025-06", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": "uncertain", "ML_prediction_viewed": "uncertain", "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "V16 June replication references and W25/W26 result lineage"},
        {"period": "2025-07_to_2025-10", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": "lineage/range audit only", "ML_prediction_viewed": False, "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "precode raw/label lineage plus representative-period result artifacts"},
        {"period": "2025-11", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": "lineage/range audit only", "ML_prediction_viewed": False, "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "W44_2025-11-03 human-visible representative-period results; ML evaluation not started"},
        {"period": "2025-12", "raw_data_available": True, "raw_data_accessed": True,
         "target_calculated": "lineage/range audit only", "ML_prediction_viewed": False, "grid_result_viewed": True,
         "human_visible_result": True, "hyperparameter_selection_use": False,
         "scale_selection_use": False, "untouched": False,
         "evidence": "W51_2025-12-22 human-visible representative-period results; ML evaluation not started"},
    ]
    with (OUT / "V20E_TEST_PERIOD_ACCESS_LEDGER.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

    write("V20E_LOCKED_TEST_CANDIDATE_AUDIT.json", {
        "artifact_id": "V20E_LOCKED_TEST_CANDIDATE_AUDIT_V1",
        "raw_Kestrel_availability": "2025-04 through 2025-12 confirmed by frozen preflight inventory",
        "strict_untouched_definition": ["actual target never inspected", "no model performance",
                                        "no tuning", "no grid result", "no scale tuning",
                                        "no human-visible outcome"],
        "candidate_periods_reviewed": [r["period"] for r in rows],
        "eligible_candidate": None,
        "reason": "Every post-April period has prior human-visible scientific/grid/representative-period outcome evidence or direct April target/prediction access.",
        "new_target_reads_by_V20": 0, "new_evaluation_calls": 0,
        "already_observed_period_falsely_labeled_unseen_count": 0,
        "freeze_artifact_created": False,
    })

    review = {
        "artifact_id": "V20E_LOCKED_TEST_FINAL_REVIEW_V1",
        "classification": "E3_NO_UNTOUCHED_PERIOD_AVAILABLE",
        "untouched_period_exists": False, "sealed": False, "dates": None,
        "contamination_status": "POST_APRIL_PERIODS_HAVE_PRIOR_HUMAN_VISIBLE_OUTCOME_OR_RESULT_LINEAGE",
        "LOCKED_TEST_AUTHORITY_READY": False,
        "NO_HUMAN_OUTCOME_ACCESS_certificate": None,
        "new_target_reads_by_V20": 0, "new_ML_evaluations": 0, "new_grid_runs": 0,
        "already_observed_period_falsely_labeled_unseen_count": 0,
    }
    write("V20E_LOCKED_TEST_FINAL_REVIEW.json", review)
    (OUT / "V20E_LOCKED_TEST_FINAL_REVIEW.md").write_text(
        "# V20E untouched locked-test final review\n\n"
        "**E3 — NO_UNTOUCHED_PERIOD_AVAILABLE**\n\n"
        "Kestrel 원자료는 2025년 12월까지 존재하지만 April은 target/예측이 이미 공개됐고, May~December에는 기존 날짜별 human-visible grid 또는 대표기간 결과가 있다. "
        "따라서 strict untouched 정의를 만족하는 기간을 증명할 수 없다. V20은 새 target을 열거나 평가하지 않았고 freeze artifact도 만들지 않았다.\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
