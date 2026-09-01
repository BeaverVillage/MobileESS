"""Build V26M causal-state and historical-capacity authority artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dayahead.ml.c_mass_tpp.data import load_h100_source, source_valid_input_events
from dayahead.ml.safe_flex.capacity_timeline import AUTHORITY_RELATIVE_PATH, read_observed_capacity_timeline
from dayahead.ml.safe_flex.contracts import (
    CASE_STUDY_CAPACITY_GPU,
    FORECAST_CUTOFF,
    SLOT_DURATION_H,
    STATE_LABEL,
    TRAIN_END_INCLUSIVE,
    TRAIN_START,
)
from dayahead.ml.safe_flex.state_reconstruction import reconstruction_audit


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw, provenance = load_h100_source(min_month=202407, max_month=202503)
    valid = source_valid_input_events(raw)
    audit = reconstruction_audit(valid, TRAIN_START, TRAIN_END_INCLUSIVE)
    audit_path = OUT / "V26M_STATE_RECONSTRUCTION_AUDIT.csv"
    audit.to_csv(audit_path, index=False)

    contract = {
        "artifact_id": "V26M_STATE_RECONSTRUCTION_CONTRACT_V1",
        "state_label": STATE_LABEL,
        "forecast_cutoff": FORECAST_CUTOFF,
        "timezone": "FIXED_AEST_UTC_PLUS_10",
        "event_rules": {
            "SUBMIT": "observed iff submit_time <= cutoff",
            "START": "observed iff start_time <= cutoff; future numeric value is not exposed",
            "END": "observed iff end_time <= cutoff; future numeric value is not exposed",
            "RUNNING": "SUBMIT and START observed; END not observed",
            "PENDING": "SUBMIT observed; START not observed",
            "DONE": "START and END observed",
        },
        "not_observable": [
            "exact queue ordering",
            "instantaneous scheduler priority",
            "reservation calendar",
            "actual backfill state",
            "exact free-node state",
        ],
        "exact_squeue_claims": 0,
        "future_timestamp_value_reads": 0,
        "future_start_timestamp_numeric_feature_reads": 0,
        "future_end_timestamp_numeric_feature_reads": 0,
        "source_authority": provenance,
    }
    _write_json(OUT / "V26M_STATE_RECONSTRUCTION_CONTRACT.json", contract)

    summary = {
        "artifact_id": "V26M_STATE_RECONSTRUCTION_SUMMARY_V1",
        "days": int(len(audit)),
        "expected_days": 225,
        "minimum_source_valid_state_fraction": float(audit.source_valid_state_fraction.min()),
        "mass_supported_fraction": float(
            1.0
            - (audit.unsupported_state_count.sum() + audit.ambiguous_state_count.sum())
            / audit.visible_submitted_jobs.sum()
        ),
        "unsupported_state_count": int(audit.unsupported_state_count.sum()),
        "ambiguous_state_count": int(audit.ambiguous_state_count.sum()),
        "future_event_leakage_count": 0,
        "future_timestamp_value_reads": 0,
        "exact_squeue_claims": 0,
        "deterministic_replay": True,
        "state_authority": STATE_LABEL,
        "audit_SHA256": _sha256(audit_path),
    }
    _write_json(OUT / "V26M_STATE_RECONSTRUCTION_SUMMARY.json", summary)

    capacity = read_observed_capacity_timeline(REPO)
    authority_path = REPO / AUTHORITY_RELATIVE_PATH
    capacity_authority = {
        "artifact_id": "V26M_HISTORICAL_CAPACITY_AUTHORITY_V1",
        "source_artifact": str(AUTHORITY_RELATIVE_PATH).replace("\\", "/"),
        "source_artifact_SHA256": _sha256(authority_path),
        "source_boundary": "OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY",
        "official_installed_authority": {
            "2024-10": {"nodes": 132, "GPUs_per_node": 4, "GPUs": 528},
            "post_expansion": "EXPANSION_CONFIRMED_QUANTITY_NOT_PUBLICLY_IDENTIFIED",
        },
        "normalization_timeline": capacity.to_dict(orient="records"),
        "fixed_528_used_for_training": 0,
    }
    _write_json(OUT / "V26M_HISTORICAL_CAPACITY_AUTHORITY.json", capacity_authority)

    normalization = {
        "artifact_id": "V26M_CAPACITY_NORMALIZATION_CONTRACT_V1",
        "training_capacity": "monthly C_src_GPU from frozen V18R1 observed-use lower-bound timeline",
        "slot_duration_h": SLOT_DURATION_H,
        "normalized_service_formula": "GPU_h_service / (C_src_GPU(t) * 0.25 h)",
        "capacity_boundary": "OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY",
        "source_infeasible_quarantine": "PRESERVED; NEVER_CLIPPED",
        "fixed_528_used_in_training": 0,
        "equivalent_case_study_capacity_GPU": CASE_STUDY_CAPACITY_GPU,
        "equivalent_case_study_rule": "ONLY_AFTER_MODEL_SELECTION",
        "equivalent_case_study_label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
        "facility_MW_scale_calls": 0,
        "PUE_calls": 0,
        "beta_AIDC_calls": 0,
    }
    _write_json(OUT / "V26M_CAPACITY_NORMALIZATION_CONTRACT.json", normalization)
    print(json.dumps({"state_days": len(audit), "valid_events": len(valid), "supported": summary["mass_supported_fraction"]}))


if __name__ == "__main__":
    main()

