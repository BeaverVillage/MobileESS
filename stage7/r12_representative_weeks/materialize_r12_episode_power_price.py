#!/usr/bin/env python3
"""Materialize only the 12 Stage-7 burn-in P/Q/PV and price source slices."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np


FORECAST_SHA = "d0e10553851cd9cbaf08cd01009915454d2c81eb0366e36fdd916a54b039fb65"
R7_SOURCE_SHA = "f712d096e9b8ae5efc12ad01aef6ca28ce5d5cb313a2b22f8db1a5765ffeb735"
H = 54


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def materialize_price(forecast: Path, issues: np.ndarray, output: Path) -> dict:
    target = issues[:, None] + np.arange(H, dtype=np.int32)[None, :]
    with np.load(forecast, allow_pickle=False) as source:
        values = {
            quantile: np.asarray(source[quantile][issues, :, 2], dtype=np.float32)
            for quantile in ("q10", "q50", "q90")
        }
    if any(value.shape != (576, H) or not np.isfinite(value).all() for value in values.values()):
        raise RuntimeError("R12 price shape/finite failure")
    if np.any(values["q10"] > values["q50"]) or np.any(values["q50"] > values["q90"]):
        raise RuntimeError("R12 price quantile crossing")
    np.savez_compressed(output, issues=issues, target_steps=target, **values)
    return {
        "status": "PASS",
        "path": str(output),
        "sha256": sha256(output),
        "shape": [576, H],
        "source": str(forecast),
        "source_sha256": FORECAST_SHA,
        "future_actual_used": False,
    }


def materialize_power(r7, forecast: Path, kernel: Path, work: Path,
                      issues: np.ndarray, output_dir: Path) -> dict:
    r7.ISSUES = issues
    r7.materialize_full(forecast, kernel, work, output_dir)
    generated = output_dir / "LONG576_CAUSAL_FEEDER_PQPV_Q10_Q50_Q90.npz"
    output = output_dir / "R12_CAUSAL_FEEDER_PQPV_Q10_Q50_Q90.npz"
    generated.replace(output)
    with np.load(output, allow_pickle=False) as source:
        if not np.array_equal(np.asarray(source["issues"], dtype=np.int32), issues):
            raise RuntimeError("R12 power issue axis drift")
        if not np.array_equal(
            np.asarray(source["target_steps"], dtype=np.int32),
            issues[:, None] + np.arange(H, dtype=np.int32)[None, :],
        ):
            raise RuntimeError("R12 power target axis drift")
    return {
        "status": "PASS",
        "path": str(output),
        "sha256": sha256(output),
        "shape_per_role": [576, H, 131, 3],
        "generator_source": str(Path(r7.__file__)),
        "generator_source_sha256": R7_SOURCE_SHA,
        "forecast_sha256": FORECAST_SHA,
        "future_actual_used": False,
    }


def build_r7_context(r7):
    temporary_roots: list[Path] = []
    failure_temp, failure_root, failure = r7.extract_failure()
    temporary_roots.append(failure_temp)
    _package, _source, forecast, _config, _binding = r7.source_package(failure_root)
    kernel, _engine = r7.kernel_from_r3r4_trace(failure)
    work = Path(tempfile.mkdtemp(prefix="r12_r7_work_"))
    temporary_roots.append(work)
    r7.extract_handoff(failure_root, work)
    return forecast, kernel, work, temporary_roots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--base-work", default="/home/jaewon/mobile_ess_work")
    parser.add_argument("--candidate-ids", nargs="*", default=[])
    args = parser.parse_args()
    authority = Path(args.authority_root).resolve()
    output_root = Path(args.output_root).resolve()
    base = Path(args.base_work).resolve()
    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = list(csv.DictReader(stream))
    selected = set(args.candidate_ids) if args.candidate_ids else {row["candidate_id"] for row in weeks}
    unknown = selected - {row["candidate_id"] for row in weeks}
    if unknown:
        raise RuntimeError(f"unknown representative weeks: {sorted(unknown)}")

    forecast = base / "execution_packages/Mobile_ESS_stage_p6a4h1b_p7a3f1b_conditional_dag_parallel_v3_0_1/assets/forecast/P6A3_FULL_YEAR_CAUSAL_FORECAST.npz"
    r7_path = base / "stage7_t2_power_price_r7/A_TO_C_T2_R7_20260815T052954Z/power/source_tree/main.py"
    if sha256(forecast) != FORECAST_SHA or sha256(r7_path) != R7_SOURCE_SHA:
        raise RuntimeError("R12 frozen power/price source SHA drift")
    r7 = load_module(r7_path, "r12_r7_power")
    resolved_forecast, kernel, work, temporary_roots = build_r7_context(r7)
    if sha256(resolved_forecast) != FORECAST_SHA:
        raise RuntimeError("R12 R7 resolved forecast SHA drift")
    completed: list[str] = []
    try:
        for row in weeks:
            candidate = row["candidate_id"]
            if candidate not in selected:
                continue
            episode = output_root / candidate
            authority_path = episode / "R12_EPISODE_SOURCE_AUTHORITY.json"
            if authority_path.is_file():
                existing = json.loads(authority_path.read_text(encoding="utf-8"))
                if existing.get("status") == "PASS" and existing.get("candidate_id") == candidate:
                    completed.append(candidate)
                    continue
                raise RuntimeError(f"existing non-PASS episode source: {episode}")
            if episode.exists():
                raise RuntimeError(f"uncommitted episode source directory requires manual quarantine: {episode}")
            (episode / "power").mkdir(parents=True)
            (episode / "price").mkdir()
            start = int(row["burn_in_start_index"])
            stop = int(row["start_index"])
            issues = np.arange(start, stop, dtype=np.int32)
            if issues.shape != (576,):
                raise RuntimeError(f"R12 burn-in length drift: {candidate}")
            power = materialize_power(r7, resolved_forecast, kernel, work, issues, episode / "power")
            price_path = episode / "price/R12_CAUSAL_PRICE_Q10_Q50_Q90.npz"
            price = materialize_price(forecast, issues, price_path)
            record = {
                "schema_version": "conversation_c.stage7.r12.episode_source_authority.v1",
                "status": "PASS",
                "candidate_id": candidate,
                "burn_in_start_index": start,
                "evaluation_start_index": stop,
                "issue_count": 576,
                "horizon_steps": H,
                "power": power,
                "price": price,
                "mobility_source": "R12 common mobility CAS; bound by runner",
                "future_actual_used": False,
                "pilot_splice_used": False,
                "evaluation_steps_materialized": 0,
            }
            write_json(authority_path, record)
            completed.append(candidate)
    finally:
        for temporary in temporary_roots:
            shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({"status": "PASS", "candidate_ids": completed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
