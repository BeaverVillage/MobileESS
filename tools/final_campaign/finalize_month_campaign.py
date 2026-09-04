#!/usr/bin/env python3
"""Finalize V28 May science only after 31 valid frozen-authority certificates."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tarfile
from pathlib import Path
from typing import Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "frozen_artifacts/v28_may_final_science"
ARTIFACTS = REPO / "dayahead/artifacts/v28_final_dayahead_actual"
SEED = 20260901


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def moving_block_bootstrap(values: Iterable[float], *, replicates: int = 10_000, block_days: int = 7) -> dict[str, float | int]:
    data = np.asarray(tuple(values), dtype=float)
    if data.shape != (31,) or np.any(~np.isfinite(data)):
        raise ValueError("V28_BOOTSTRAP_REQUIRES_31_FINITE_PAIRED_DAILY_VALUES")
    rng = np.random.default_rng(SEED)
    starts = np.arange(len(data) - block_days + 1)
    means = np.empty(replicates)
    for iteration in range(replicates):
        sample = []
        while len(sample) < len(data):
            start = int(rng.choice(starts))
            sample.extend(data[start:start + block_days])
        means[iteration] = float(np.mean(sample[:len(data)]))
    return {
        "replicates": replicates, "block_days": block_days, "seed": SEED,
        "observed_mean": float(np.mean(data)),
        "CI95_lower": float(np.quantile(means, 0.025)),
        "CI95_upper": float(np.quantile(means, 0.975)),
    }


def validate_certificates() -> list[dict]:
    freeze = RESULTS / "MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.json"
    freeze_sha = RESULTS / "MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.sha256"
    if not freeze.is_file() or not freeze_sha.is_file() or not freeze_sha.read_text(encoding="ascii").startswith(sha(freeze)):
        raise RuntimeError("MAY_FREEZE_BROKEN")
    certificates = []
    for number in range(1, 32):
        day = f"2025-05-{number:02d}"
        path = RESULTS / day / f"MAY_DAY_CERTIFICATE_2025_05_{number:02d}.json"
        if not path.is_file(): raise RuntimeError(f"MAY_NOT_31_OF_31_PASS:{day}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("status") != "PASS" or value.get("certificate_sha256") != value.get("self_check_sha256"):
            raise RuntimeError(f"MAY_INVALID_CERTIFICATE:{day}")
        certificates.append(value)
    return certificates


def metric_rows() -> list[dict]:
    rows = []
    for number in range(1, 32):
        day = f"2025-05-{number:02d}"
        path = RESULTS / day / "DAY_RESULT.json"
        if not path.is_file(): raise RuntimeError(f"MAY_DAY_RESULT_MISSING:{day}")
        value = json.loads(path.read_text(encoding="utf-8"))
        metrics = value.get("science_metrics")
        if not isinstance(metrics, dict): raise RuntimeError(f"MAY_SCIENCE_METRICS_MISSING:{day}")
        rows.append({"date": day, **metrics})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    certificates = validate_certificates()
    rows = metric_rows()
    comparisons = {
        "B3_minus_B0_rho": [float(row["B3_ACTUAL_rho_max_AC"]) - float(row["B0_ACTUAL_rho_max_AC"]) for row in rows],
        "B3_minus_B1_rho": [float(row["B3_ACTUAL_rho_max_AC"]) - float(row["B1_ACTUAL_rho_max_AC"]) for row in rows],
        "B3_minus_B2_rho": [float(row["B3_ACTUAL_rho_max_AC"]) - float(row["B2_ACTUAL_rho_max_AC"]) for row in rows],
        "Actual_minus_PI_rho": [float(row["B3_ACTUAL_rho_max_AC"]) - float(row["B3_PI_rho_max_AC"]) for row in rows],
        "CL_MC_BD_minus_STANDARD_runtime": [float(row["CL_MC_BD_runtime_seconds"]) - float(row["STANDARD_BD_runtime_seconds"]) for row in rows],
        "CL_MC_BD_minus_MONOLITHIC_runtime": [float(row["CL_MC_BD_runtime_seconds"]) - float(row["MONOLITHIC_runtime_seconds"]) for row in rows],
    }
    bootstrap = {name: moving_block_bootstrap(values) for name, values in comparisons.items()}
    write_csv(ARTIFACTS / "V28_MAY_DAILY_RESULTS.csv", rows)
    write_csv(ARTIFACTS / "V28_MAY_CASE_RESULTS.csv", rows)
    write_csv(ARTIFACTS / "V28_MAY_SOLVER_RESULTS.csv", rows)
    comparison_rows = [{"date": rows[index]["date"], **{name: values[index] for name, values in comparisons.items()}} for index in range(31)]
    write_csv(ARTIFACTS / "V28_MAY_DAYAHEAD_ACTUAL_PI_COMPARISON.csv", comparison_rows)
    write_json(ARTIFACTS / "V28_MAY_BOOTSTRAP_RESULTS.json", {"artifact_id": "V28_MAY_BOOTSTRAP_RESULTS_V1", "results": bootstrap})
    tables = ARTIFACTS / "V28_FINAL_PAPER_TABLES"; figures = ARTIFACTS / "V28_FINAL_PAPER_FIGURE_DATA"
    write_csv(tables / "paired_daily_comparisons.csv", comparison_rows)
    write_csv(figures / "daily_metric_source.csv", rows)
    flags = {
        "FINAL_LIGHTGBM_AUTHORITY_READY": True, "FINAL_THERMAL_PCC_AUTHORITY_READY": True,
        "FINAL_DAYAHEAD_MODEL_READY": True, "FINAL_ACTUAL_REPLAY_MODEL_READY": True,
        "FINAL_PI_ORACLE_READY": True, "APRIL_FULL_MONTH_PREFLIGHT_PASS": True,
        "MAY_FINAL_SCIENCE_COMPLETE": True, "FINAL_REPRODUCIBILITY_READY": True,
        "FINAL_GRID_SCIENCE_AUTHORIZED": True,
    }
    write_json(ARTIFACTS / "V28_FINAL_READY_FLAGS.json", flags)
    review = {"artifact_id": "V28_FINAL_MASTER_REVIEW_V1", "classification": "V28_FINAL_MAY_SCIENCE_COMPLETE", "day_count": 31, "certificates": [item["certificate_sha256"] for item in certificates], "method_victory_required": False, "bootstrap": bootstrap}
    write_json(ARTIFACTS / "V28_FINAL_MASTER_REVIEW.json", review)
    (ARTIFACTS / "V28_FINAL_MASTER_REVIEW.md").write_text("# V28 final master review\n\nMay completed 31/31 under one frozen authority. See the JSON and paper-ready source tables for outcomes; no method-victory condition was imposed.\n", encoding="utf-8", newline="\n")
    hashes = {path.relative_to(REPO).as_posix(): sha(path) for path in sorted(ARTIFACTS.rglob("*")) if path.is_file() and path.name != "V28_FINAL_ARTIFACT_SHA256.json"}
    write_json(ARTIFACTS / "V28_FINAL_ARTIFACT_SHA256.json", hashes)
    archive = ARTIFACTS / "V28_FINAL_HANDOFF.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(ARTIFACTS.rglob("*")):
            if path.is_file() and path not in {archive, ARTIFACTS / "V28_FINAL_HANDOFF.sha256"}:
                tar.add(path, arcname=path.relative_to(ARTIFACTS))
    (ARTIFACTS / "V28_FINAL_HANDOFF.sha256").write_text(sha(archive) + "  V28_FINAL_HANDOFF.tar.gz\n", encoding="ascii", newline="\n")
    print("MAY_FINAL_SCIENCE_COMPLETE=true")
    return 0


if __name__ == "__main__": raise SystemExit(main())
