#!/usr/bin/env python3
"""Materialize four 576-issue evaluation-prefix source contexts for restart tests."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np


SELECTED = ("W02_2025-01-13", "W10_2025-03-10", "W25_2025-06-23", "W38_2025-09-22")
FORECAST_SHA = "d0e10553851cd9cbaf08cd01009915454d2c81eb0366e36fdd916a54b039fb65"
R7_SOURCE_SHA = "f712d096e9b8ae5efc12ad01aef6ca28ce5d5cb313a2b22f8db1a5765ffeb735"
H = 54


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--r12-authority-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--base-work", type=Path, default=Path("/home/jaewon/mobile_ess_work"))
    args = parser.parse_args()
    authority, r12_root, output, base = map(Path.resolve, (
        args.authority_root, args.r12_authority_root, args.output_root, args.base_work
    ))
    r12 = load_module(r12_root / "materialize_r12_episode_power_price.py", "r13_r12_power_core")
    forecast = base / "execution_packages/Mobile_ESS_stage_p6a4h1b_p7a3f1b_conditional_dag_parallel_v3_0_1/assets/forecast/P6A3_FULL_YEAR_CAUSAL_FORECAST.npz"
    r7_path = base / "stage7_t2_power_price_r7/A_TO_C_T2_R7_20260815T052954Z/power/source_tree/main.py"
    if r12.sha256(forecast) != FORECAST_SHA or r12.sha256(r7_path) != R7_SOURCE_SHA:
        raise RuntimeError("frozen R7 power/price SHA drift")
    r7 = load_module(r7_path, "r13_r7_power")
    resolved_forecast, kernel, work, temporary_roots = r12.build_r7_context(r7)
    if r12.sha256(resolved_forecast) != FORECAST_SHA:
        raise RuntimeError("resolved forecast SHA drift")
    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    completed = []
    try:
        for candidate in SELECTED:
            row = weeks[candidate]
            start = int(row["start_index"])
            issues = np.arange(start, start + 576, dtype=np.int32)
            episode = output / candidate
            authority_path = episode / "R13_RESTART_SOURCE_AUTHORITY.json"
            if authority_path.is_file():
                existing = json.loads(authority_path.read_text(encoding="utf-8"))
                if existing.get("status") == "PASS" and existing.get("candidate_id") == candidate:
                    completed.append(candidate); continue
                raise RuntimeError(f"existing non-PASS source: {candidate}")
            if episode.exists():
                raise RuntimeError(f"uncommitted source directory requires quarantine: {episode}")
            (episode / "power").mkdir(parents=True)
            (episode / "price").mkdir()
            power = r12.materialize_power(r7, resolved_forecast, kernel, work, issues, episode / "power")
            price = r12.materialize_price(
                forecast, issues, episode / "price/R13_CAUSAL_PRICE_Q10_Q50_Q90.npz"
            )
            record = {
                "schema_version": "conversation_c.stage7.r13.restart_source_authority.v1",
                "status": "PASS", "candidate_id": candidate,
                "evaluation_start_index": start,
                "materialized_evaluation_prefix_steps": 576,
                "controller_burn_in_steps": 0,
                "restart_test_consumed_offsets": [0, 1],
                "horizon_steps": H,
                "power": power, "price": price,
                "mobility_source": "R13 restart mobility authority; bound by production runner",
                "future_actual_used": False, "pilot_splice_used": False,
            }
            r12.write_json(authority_path, record)
            completed.append(candidate)
    finally:
        for path in temporary_roots:
            shutil.rmtree(path, ignore_errors=True)
    print(json.dumps({"status": "PASS", "candidate_ids": completed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
