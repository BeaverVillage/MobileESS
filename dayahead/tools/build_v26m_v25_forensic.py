"""Create read-only V25M forensic artifacts without opening April raw members."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dayahead.ml.safe_flex.v25_forensic import canonical_field_forensic, q50_reconciliation_forensic


ROOT = Path(__file__).resolve().parents[2]
V25 = ROOT / "dayahead/artifacts/v25m_beacon_flex"
OUT = ROOT / "dayahead/artifacts/v26m_safe_flex"


def write(name: str, payload: object) -> None:
    """Write one V26M non-authority forensic record."""

    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """Audit the V25 summary mapping and April Q50 collapse mechanism."""

    canonical = pd.read_csv(V25 / "V25M_BASELINE_HARMONIZATION_RESULTS.csv")
    final = json.loads((V25 / "V25M_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    field = canonical_field_forensic(canonical)
    field_payload = {
        "artifact_id": "V26M_V25M_CANONICAL_FIELD_FORENSIC_V1", "authority": "NON_AUTHORITY_DIAGNOSTIC",
        "V25_historical_artifacts_modified": False, "V25_serialized_canonical_benchmarks": final["canonical_benchmarks"],
        **field, "result_class": "SUMMARY_MAPPING_DEFECT_ONLY",
        "explanation": "V25 evaluation took min(canonical.Mean_WAPE) across every row. The B3 quantile row copied Q50 into its point-prediction column, so 0.890250 was serialized as best conventional Mean_WAPE although the best eligible conditional-mean diagnostic was weekday-factorized 0.946736.",
    }
    write("V26M_V25M_CANONICAL_FIELD_FORENSIC.json", field_payload)
    reconciled = pd.read_csv(V25 / "V25M_BASE_RECONCILIATION_RESULTS.csv")
    daily = pd.read_csv(V25 / "V25M_CANONICAL_BASELINE_DAILY_OOF.csv")
    collapsed, summary = q50_reconciliation_forensic(reconciled, daily)
    april = json.loads((V25 / "V25M_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    april_rows = [{"date": row["date"], "base_mean_GPU_h": row["base_mean_GPU_h"], "reconciled_base_Q50_GPU_h": row["base_Q50_GPU_h"],
                   "reconciled_base_Q90_GPU_h": row["base_Q90_GPU_h"], "near_zero_Q50": row["base_Q50_GPU_h"] < 1e-8}
                  for row in april["dates"]]
    payload = {
        "artifact_id": "V26M_V25M_APRIL_BASE_Q50_FORENSIC_V1", "authority": "NON_AUTHORITY_DIAGNOSTIC",
        "V25_historical_artifacts_modified": False, "April_raw_members_opened_by_V26_forensic": 0,
        "April_raw_B3_Q50_serialized_in_V25": False, "April_rows": april_rows, "training_OOF_mechanism_audit": summary,
        "collapsed_training_examples": collapsed[["date", "selected_method", "raw_mean_GPU_h", "raw_B3_Q50_GPU_h", "Q50_GPU_h", "Q90_GPU_h"]].to_dict(orient="records"),
        "ruled_out": {"serialization_nan_or_inf": True, "interpolation_only": True, "random_numeric_failure": True},
        "cause": "BASE_RECONCILIATION_PATHOLOGY_CONFIRMED_ON_OOF; APRIL_RAW_B3_Q50_NOT_PRESERVED_SO_EXCLUSIVE_APRIL_CAUSE_NOT_CLAIMED",
        "result_class": "BASE_RECONCILIATION_DEFECT_FOUND",
        "SAFE_Flex_input_rule": "USE_VALIDATED_RAW_B2_B3_LINEAGE; DO_NOT_BLINDLY_REUSE_BR_A_RECONCILED_APRIL_DISTRIBUTION",
    }
    write("V26M_V25M_APRIL_BASE_Q50_FORENSIC.json", payload)
    print(json.dumps({"canonical": field_payload["result_class"], "q50": payload["result_class"], "collapsed_OOF": len(collapsed), "April_raw_reads": 0}))


if __name__ == "__main__":
    main()
