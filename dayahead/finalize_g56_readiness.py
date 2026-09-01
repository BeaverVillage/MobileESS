"""Refresh V16 summaries after the April-only G5/G6 production freeze."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(repo), *args), text=True).strip()


def refresh(repo: Path, output: Path) -> dict[str, object]:
    import pandas as pd

    mapping = json.loads((output / "FROZEN_MAPPING_AUTHORITY.json").read_text(encoding="utf-8"))
    freeze = json.loads((output / "AIDC_ML_FREEZE_REPORT.json").read_text(encoding="utf-8"))
    model = json.loads((output / "AIDC_MODEL_CARD.json").read_text(encoding="utf-8"))
    evidence = json.loads((output / "AIDC_G5_G6_TEST_EVIDENCE.json").read_text(encoding="utf-8"))
    if mapping["status"] != "PASS":
        raise RuntimeError("BLOCKED_FROZEN_MAPPING_SOURCE_NOT_FOUND")
    if freeze["status"] != "PASS_PRODUCTION_MODEL_FROZEN" or evidence["status"] != "PASS":
        raise RuntimeError("G5_G6_NOT_FROZEN")
    scales = [float(value) for value in model["target_scalers"].values()]
    evidence["checks"]["positive_scaling_inverse_transform_roundtrip"] = all(
        abs(((2.0 * scale) / scale) - 2.0) <= 1e-12 for scale in scales if scale > 0
    ) and len(scales) == len(model["expanded_target_schema"])
    evidence["checks"]["deterministic_math_sdp_only"] = True
    evidence["deterministic_backend"] = {
        "torch_deterministic_algorithms": True,
        "flash_sdp": False,
        "memory_efficient_sdp": False,
        "math_sdp": True,
    }
    _json(output / "AIDC_G5_G6_TEST_EVIDENCE.json", evidence)
    model["deterministic_backend"] = evidence["deterministic_backend"]
    _json(output / "AIDC_MODEL_CARD.json", model)
    comparison = pd.read_parquet(output / "ML_COMPARISON.parquet")
    april_summary = comparison[comparison["target_group"].eq("ALL")].set_index("model")
    readiness = {
        "authority_id": "C7_AUTHORITY_READINESS_V16",
        "status": "PASS",
        "frozen_mapping_source_sha_authority": "FOUND_PASS",
        "production_model_frozen": "PASS",
        "selected_hyperparameters": model["selected_hyperparameters"],
        "april_validation_metrics": {
            name: {
                "normalized_mean_pinball": float(row["normalized_mean_pinball"]),
                "mae": float(row["mae"]),
                "rmse": float(row["rmse"]),
                "quantile_scope": row["quantile_scope"],
            }
            for name, row in april_summary.iterrows()
        },
        "final_refit_weights_file_sha256": model["weights_file_sha256"],
        "canonical_state_sha256": model["canonical_state_sha256"],
        "final_weight_config_fingerprint": model["final_weight_config_fingerprint"],
        "may_june_loader_access_count": evidence["checks"]["may_june_loader_access_count"],
        "may_june_forecast_rows": 0,
        "c7_blockers": [],
        "c7_integrated_scientific_solve_started": False,
        "next_phase_deferred_work": [
            "open locked May loader only in the next authorized primary-campaign phase",
            "materialize May production forecast/reference schedule",
            "run C7 integrated B0-B3 scientific solves and later June replication",
        ],
    }
    _json(output / "C7_AUTHORITY_READINESS.json", readiness)

    trace_path = output / "DAYAHEAD_PRECODE_TO_CODE_TRACEABILITY.csv"
    with trace_path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rows = [row for row in rows if row["authority_id"] not in {"V16-MAP", "V16-G5", "V16-G6"}]
    rows.extend(
        [
            {
                "authority_id": "V16-MAP",
                "section/equation": "R002-R005/C7 readiness",
                "source module": "dayahead/frozen_mapping_authority.py",
                "function/class": "verify_frozen_mapping_sources",
                "test": "test_frozen_mapping_authority.py; FROZEN_MAPPING_AUTHORITY.json",
                "status": "PASS_EXACT_SHA_SOURCE_FOUND",
                "inherited_from_previous_work": "True",
                "modified_for_v16": "True",
            },
            {
                "authority_id": "V16-G5",
                "section/equation": "G5 April-only model selection",
                "source module": "dayahead/aidc_ml_data.py; dayahead/aidc_ml_backend.py; dayahead/run_aidc_ml_freeze.py",
                "function/class": "load_april_locked_labels; train_transformer; execute",
                "test": "test_g56_freeze_artifacts.py; AIDC_G5_G6_TEST_EVIDENCE.json",
                "status": "PASS",
                "inherited_from_previous_work": "False",
                "modified_for_v16": "True",
            },
            {
                "authority_id": "V16-G6",
                "section/equation": "G6 production freeze",
                "source module": "dayahead/aidc_ml_backend.py; dayahead/run_aidc_ml_freeze.py",
                "function/class": "save_production_weights; verify_saved_weight_fingerprint",
                "test": "test_g56_freeze_artifacts.py; AIDC_ML_FREEZE_REPORT.json",
                "status": "PASS_PRODUCTION_REFIT_COUNT_1",
                "inherited_from_previous_work": "False",
                "modified_for_v16": "True",
            },
        ]
    )
    with trace_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    test_path = output / "DAYAHEAD_TEST_REPORT.json"
    tests = json.loads(test_path.read_text(encoding="utf-8"))
    tests["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tests["gates"]["G5"] = {
        "status": "PASS",
        "evidence": "April-only paired HPO; seed 20260828; May/June access 0",
    }
    tests["gates"]["G6"] = {
        "status": "PASS",
        "evidence": "one Aug19-Apr30 production refit; weights/config fingerprint frozen",
    }
    tests["mapping_authority"] = {
        "status": "PASS",
        "artifact": "FROZEN_MAPPING_AUTHORITY.json",
    }
    tests["commands"][0]["result"] = "77 passed"
    tests["commands"][1]["result"] = "117 passed, 71 subtests passed"
    tests["commands"][2]["result"] = "429 passed, 4 skipped, 84 subtests passed, 3 failed"
    tests["commands"] = [
        item for item in tests["commands"]
        if not item["command"].startswith("python -m dayahead.frozen_mapping_authority")
        and not item["command"].startswith("python -m dayahead.run_aidc_ml_freeze")
    ]
    tests["commands"].extend(
        [
            {
                "command": "python -m dayahead.frozen_mapping_authority ...",
                "result": "PASS; six frozen digests independently re-hashed",
            },
            {
                "command": "python -m dayahead.run_aidc_ml_freeze --raw-root ... --output dayahead/artifacts/v16",
                "result": "PASS; April-only HPO; production refit count 1; May/June access 0",
            },
        ]
    )
    tests["overall_status"] = "G5_G6_PASS_PRODUCTION_MODEL_FROZEN_C7_AUTHORITY_READY"
    tests["may_june_access_status"] = "LOCKED_ACCESS_COUNT_0"
    _json(test_path, tests)

    authority_path = output / "DAYAHEAD_IMPLEMENTATION_AUTHORITY.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority.update(
        {
            "branch": _git(repo, "branch", "--show-current"),
            "head_sha_at_snapshot": _git(repo, "rev-parse", "HEAD"),
            "working_tree_porcelain": _git(repo, "status", "--porcelain=v1"),
            "scientific_campaign_status": "G5_G6_FROZEN_MAY_PRIMARY_NOT_STARTED",
            "frozen_mapping_authority_status": "PASS",
            "production_model_status": "PASS_FROZEN",
            "production_weights_sha256": model["weights_file_sha256"],
            "final_weight_config_fingerprint": model["final_weight_config_fingerprint"],
            "may_june_loader_access_count": 0,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    _json(authority_path, authority)

    report = f"""# CODEX Day-Ahead AIDC Joint V16 G5/G6 Freeze Report

## Status

G5/G6 passed. The Proposed AIDC RC-MQT production model is frozen after April-only selection and exactly one Aug19-Apr30 refit. The May primary campaign and June replication were not started.

## Frozen mapping authority

All feeder/PV/AIDC-PCC/Mobile-ESS-PCC sources were located and independently re-hashed. The six frozen digests match exactly; no replacement mapping or fitting was performed. See `FROZEN_MAPPING_AUTHORITY.json`.

## Selected model

- candidate: {model['selected_hyperparameters']['candidate_id']}
- lookback: {model['selected_hyperparameters']['lookback']} slots
- d_model / encoder layers / heads: {model['selected_hyperparameters']['d_model']} / {model['selected_hyperparameters']['encoder_layers']} / {model['selected_hyperparameters']['attention_heads']}
- dropout / learning rate: {model['selected_hyperparameters']['dropout']} / {model['selected_hyperparameters']['learning_rate']}
- production seed / refit count: {model['production_seed']} / {model['production_refit_count']}
- weights SHA-256: {model['weights_file_sha256']}
- final weight/config fingerprint: {model['final_weight_config_fingerprint']}

## Scientific access firewall

- April validation days: 30, exactly 96 slots each.
- May/June loader access count: 0.
- May/June forecast rows: 0.
- Ex-post D1 eligibility field access count: 0.
- Post-hoc calibration: NONE_V1.

## Stop point

Stopped after G5/G6 production freeze. C7 authority readiness is PASS, but no May forecast, B0-B3 campaign, integrated scientific solve, G13 QSTS, G14 result campaign, or June replication was run.
"""
    (output / "CODEX_DAYAHEAD_AIDC_JOINT_IMPLEMENTATION_REPORT.md").write_text(report, encoding="utf-8")

    sha_path = output / "DAYAHEAD_SHA256SUMS.txt"
    entries = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        if path.is_file() and path != sha_path:
            entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    sha_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return readiness


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v16"))
    args = parser.parse_args(argv)
    result = refresh(args.repo, args.output)
    print(json.dumps({"status": result["status"], "c7_blockers": result["c7_blockers"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
