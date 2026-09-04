from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "dayahead" / "artifacts" / "v17_candidate" / "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW.json"


def load() -> dict:
    return json.loads(FINAL.read_text(encoding="utf-8"))


def test_final_classification_and_active_boundary() -> None:
    final = load()
    assert final["primary_classification"] == "V17_AIDC_POWER_V3R1_E_SEMANTICALLY_INCOMPATIBLE"
    assert final["U1_CLASSIFICATION"] == "MARGINAL_POWER_NOT_IDENTIFIABLE"
    assert final["U2_CLASSIFICATION"] == "SEMANTICALLY_INCOMPATIBLE"
    assert final["U3_CLASSIFICATION"] == "MARGINAL_POWER_NOT_IDENTIFIABLE"
    assert final["V3R1_authority_minted"] is False
    assert final["active_final_AIDC_power_boundary"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert final["READY_FOR_APRIL_RESUME"] is True


def test_final_preservation_and_no_science_rerun() -> None:
    final = load()
    assert final["start_gate"]["prechange_preservation"]["pass"] is True
    assert final["start_gate"]["prechange_preservation"]["record_count"] == 247
    assert final["same_7day_V3R1_science"]["performed"] is False
    assert final["RCMQT_V3R1"]["performed"] is False
    assert final["remaining_April_day_runs"] == 0
    assert final["May_scientific_input_reads"] == 0
    assert final["June_scientific_input_reads"] == 0


def test_final_artifact_hash_manifest_complete() -> None:
    final = load()
    assert len(final["artifact_sha256"]) == 15
    for record in final["artifact_sha256"].values():
        assert record["bytes"] > 0
        assert len(record["sha256"]) == 64
