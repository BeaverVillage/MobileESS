"""Materialize the V16 April-only C7/C8/C9 pre-production evidence."""

from __future__ import annotations

import json
from pathlib import Path

from .authority import sha256_file
from .preproduction_integration import OPERATING_DAY, reference_bytes, run_preproduction_gate


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts" / "v16"


def _write_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_json(path: Path, payload: object) -> None:
    _write_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _reference_fidelity_diagnostic(path: Path) -> dict[str, object]:
    import pandas as pd

    frame = pd.read_parquet(path)
    dates = pd.to_datetime(frame["forecast_day"])
    if dates.min().date().isoformat() < "2025-04-01" or dates.max().date().isoformat() > "2025-04-30":
        raise ValueError("REFERENCE_FIDELITY_MAY_JUNE_ACCESS_PROHIBITED")
    rows = frame[
        (frame["model"] == "Proposed AIDC RC-MQT")
        & (frame["quantile"] == 0.5)
        & (frame["target"].isin(["P_IT_REF", "G_REF"]))
    ].copy()
    metrics: dict[str, object] = {}
    for target, group in rows.groupby("target"):
        absolute = (group["prediction"] - group["actual"]).abs()
        denominator = max(float(group["actual"].abs().mean()), 1e-9)
        metrics[str(target)] = {
            "mae": float(absolute.mean()),
            "normalized_mae": float(absolute.mean()) / denominator,
            "sample_count": int(len(group)),
        }
    return {
        "authority_id": "REFERENCE_BASELINE_FIDELITY_DIAGNOSTIC_V1",
        "status": "MATERIALIZED_DIAGNOSTIC_ONLY",
        "data_scope": ["VALIDATION_2025APR"],
        "permitted_development_scope": ["TRAIN_2024AUG19_2025MAR31", "VALIDATION_2025APR"],
        "metrics": metrics,
        "acceptance_threshold": None,
        "tuning_authority": False,
        "gating_authority": False,
        "configuration_mutation_call_sites": 0,
        "may_june_loader_access_count": 0,
        "source_artifact_sha256": sha256_file(path),
    }


def _write_sha256_manifest() -> None:
    entries = []
    for path in sorted(ARTIFACTS.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "DAYAHEAD_SHA256SUMS.txt":
            entries.append(f"{sha256_file(path)}  {path.name}")
    _write_bytes(ARTIFACTS / "DAYAHEAD_SHA256SUMS.txt", ("\n".join(entries) + "\n").encode("utf-8"))


def main() -> int:
    fixture, report = run_preproduction_gate(
        forecast_path=ARTIFACTS / "AIDC_APRIL_VALIDATION_FORECAST.parquet",
        mapping_authority_path=ARTIFACTS / "FROZEN_MAPPING_AUTHORITY.json",
        production_config_path=ARTIFACTS / "AIDC_PRODUCTION_CONFIG.json",
        production_weights_path=ARTIFACTS / "AIDC_RC_MQT_PRODUCTION_SEED20260828.pt",
    )
    reference = reference_bytes(fixture.reference_payload)
    b0 = ARTIFACTS / f"C7_REFERENCE_SCHEDULE_B0_{OPERATING_DAY}.json"
    b2 = ARTIFACTS / f"C7_REFERENCE_SCHEDULE_B2_{OPERATING_DAY}.json"
    _write_bytes(b0, reference)
    _write_bytes(b2, reference)
    if b0.read_bytes() != b2.read_bytes() or sha256_file(b0) != sha256_file(b2):
        raise RuntimeError("B0_B2_REFERENCE_SCHEDULE_IDENTITY_FAILED")
    report["c7"]["reference_schedule_sha256"] = sha256_file(b0)
    feasible_set = {
        "authority_id": "C7_INTEGRATED_FEASIBLE_SET_AUTHORITY_V1",
        "namespace": report["namespace"],
        "scientific_eligible": False,
        "operating_day": OPERATING_DAY,
        "reference_schedule_sha256": sha256_file(b0),
        "constraint_contracts": [
            "REFERENCE_COMPUTE_SCHEDULE_V2",
            "AIDC_REFERENCE_DELTA_V1_NONNEGATIVE",
            "REFERENCE_MATCHED_SERVICE_CONSERVATION_V1",
            "MESS_ROUTE_SOC_P_Q_SAFE_MOBILITY",
            "PHASE_PRESENT_MASK_V1",
            "96_TIME_LOCAL_PHASE_AWARE_LINDISTFLOW_LP_V1",
        ],
        "monolithic_objective_authority": report["c7"]["monolithic"],
        "may_june_loader_access_count": 0,
    }
    _write_json(ARTIFACTS / "C7_INTEGRATED_FEASIBLE_SET_AUTHORITY.json", feasible_set)
    _write_json(ARTIFACTS / "C7_C8_C9_PREPRODUCTION_REPORT.json", report)
    _write_json(
        ARTIFACTS / "REFERENCE_BASELINE_FIDELITY.json",
        _reference_fidelity_diagnostic(ARTIFACTS / "AIDC_APRIL_VALIDATION_FORECAST.parquet"),
    )
    _write_sha256_manifest()
    print(json.dumps({
        "status": report["status"],
        "reference_sha256": report["c7"]["reference_schedule_sha256"],
        "monolithic_objective": report["c7"]["monolithic"]["objective"],
        "standard": report["c9"]["standard"],
        "cl_mc_bd": report["c9"]["cl_mc_bd"],
        "G11": report["gates"]["G11"],
        "G12": report["gates"]["G12"],
    }, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
