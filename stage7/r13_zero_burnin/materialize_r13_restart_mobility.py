#!/usr/bin/env python3
"""Materialize only the two production mobility issues needed by each restart test.

Traffic keeps the accepted 576-origin CUDA context for each selected week.  E3/E4
artifacts are then produced only for h0 and h0+1; no controller burn-in or
seven-day evaluation is executed.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import multiprocessing as mp
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


SELECTED = (
    ("W02_2025-01-13", 3456),
    ("W10_2025-03-10", 19584),
    ("W25_2025-06-23", 49824),
    ("W38_2025-09-22", 76032),
)
CONTEXT_STEPS = 576
ISSUE_TO_TRAFFIC_ORIGIN = 631296
H = 54
R = 1656


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_index(path: Path, rows: list[dict]) -> None:
    fields = [
        "issue_step", "origin", "file", "sha256", "rows", "state_free",
        "state_moderate", "state_severe", "safe_max_kWh", "future_actual_target_read",
        "unseen_safe_row_count", "unseen_safe_steps",
    ]
    import csv as csv_module
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv_module.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--r12-authority-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--base-work", type=Path, default=Path("/home/jaewon/mobile_ess_work"))
    parser.add_argument("--cpu-workers", type=int, default=4)
    args = parser.parse_args()
    authority = args.authority_root.resolve()
    r12_root = args.r12_authority_root.resolve()
    output = args.output_root.resolve()
    base = args.base_work.resolve()
    if not 1 <= args.cpu_workers <= 4:
        raise RuntimeError("R13 restart source cpu-workers must be 1..4")
    output.mkdir(parents=True, exist_ok=True)
    (output / "mobility_runtime").mkdir(exist_ok=True)
    (output / "traffic_blocks").mkdir(exist_ok=True)

    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        week_rows = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    for candidate, start in SELECTED:
        if candidate not in week_rows or int(week_rows[candidate]["start_index"]) != start:
            raise RuntimeError(f"preregistered restart axis drift: {candidate}")

    r12 = load_module(r12_root / "materialize_r12_common_mobility_cache.py", "r13_r12_source_core")
    try:
        import lightgbm  # noqa: F401
    except ModuleNotFoundError:
        sys.path.append("/home/jaewon/miniconda3/envs/scats_parser/lib/python3.12/site-packages")
        import lightgbm  # noqa: F401
    r10_path = base / "stage7_t2_precision_repair/A_TO_C_T2_R10_20260815T074441Z/REPAIRED_SOURCE_PACKAGE/main.py"
    if r12.sha256(r10_path) != r12.R10_SHA:
        raise RuntimeError("R10 source SHA drift")
    r10 = r12.load_module(r10_path, "r13_r10_source_core")
    package = r10_path.parent
    r10.CURRENT_PKG = package

    temporary = Path(tempfile.mkdtemp(prefix="r13_restart_mobility_"))
    try:
        r0root = r10.safe_extract(
            package / "embedded/B1D1B2_R0_SOURCE_API_PASS.tar.gz",
            temporary / "r0", r10.R0_SHA,
        )
        block_records = []
        missing = []
        for candidate, start in SELECTED:
            path = output / "traffic_blocks" / f"{candidate}.npz"
            if not path.is_file():
                missing.append(path)
            block_records.append((candidate, start, path))

        if missing:
            import torch
            br3 = r0root / "captured_sources/BR3"
            sys.path.insert(0, str(br3))
            adapter = r12.load_module(br3 / "on_demand_traffic_adapter.py", "r13_traffic_adapter")
            traffic_runner = adapter.import_runner(br3 / "stage_ml10_final_v1_2.py")
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA required for frozen R10 traffic execution")
            adapter.configure_frozen_cuda_execution()
            device = torch.device("cuda")
            stage5, stage6, _stage8, traffic_model, links, preproc = traffic_runner.load_frozen_modules_and_model(
                r10.STAGE9, device
            )
            splits = pd.read_csv(
                r10.STAGE9 / "freeze_assets/dataset/date_splits_2019_2025.csv"
            ).sort_values("date").reset_index(drop=True)
            routes = np.load(
                r10.STAGE9 / "freeze_assets/stage8/optimizer_interface/final_od_k3_sequences.npz",
                allow_pickle=False,
            )
            margins = np.load(
                r10.STAGE9 / "freeze_assets/stage8/optimizer_interface/safe_eta_margin_54.float32.npy",
                allow_pickle=False,
            ).astype(np.float64)
            ff = links["mapping_ff_tt_sec"].to_numpy(np.float64)
            dow = pd.to_datetime(splits["date"]).dt.dayofweek.to_numpy(np.int8)
            frozen = adapter.import_frozen_optimizer_interface(br3 / "traffic_optimizer_interface.py")
            interface = frozen.TrafficOptimizerInterface(
                routes["route_links"], routes["route_mask"], routes["source_index"],
                routes["destination_index"], ff, margins, preproc["historical_median"],
                dow, 0.80, 72,
            )
            for candidate, start, block_path in block_records:
                if block_path.is_file():
                    continue
                issues = np.arange(start, start + CONTEXT_STEPS, dtype=np.int64)
                origins = ISSUE_TO_TRAFFIC_ORIGIN + issues
                adapter.configure_frozen_cuda_execution()
                dataset = adapter.CausalOperationalDataset(
                    stage5, origins, r10.STAGE1, r10.STAGE2A_RUNTIME, splits, preproc
                )
                link, _batch = adapter.predict_link_quantiles(
                    traffic_runner, stage6, traffic_model, dataset, preproc, device,
                    reproduction_batch_size=4,
                )
                metric = np.quantile(link[:, :, :, 1].astype(np.float64), 0.9, axis=2, method="linear")
                states = np.where(metric < r10.TH1, 0, np.where(metric < r10.TH2, 1, 2)).astype(np.int8)
                path_quantiles = np.empty((CONTEXT_STEPS, H, R, 3), dtype=np.float32)
                for local, origin in enumerate(origins):
                    audit = dataset.read_audit[int(origin)]
                    if int(audit["realized_tti_max_index_read"]) > int(origin):
                        raise RuntimeError(f"future traffic actual read: {issues[local]}")
                    path_quantiles[local] = interface.path_quantiles(
                        np.asarray(link[local], np.float32), int(origin)
                    )
                r12.atomic_npz(
                    block_path, issues=issues, origins=origins,
                    path_quantiles_sec=path_quantiles, state_code=states,
                    network_metric_p90_link_q50=metric.astype(np.float32),
                )

        traffic_manifest = []
        for candidate, start, block_path in block_records:
            with np.load(block_path, allow_pickle=False) as block:
                expected = np.arange(start, start + CONTEXT_STEPS, dtype=np.int64)
                if not np.array_equal(block["issues"], expected):
                    raise RuntimeError(f"traffic issue axis drift: {candidate}")
            traffic_manifest.append({
                "candidate_id": candidate, "context_issue_first": start,
                "context_issue_count": CONTEXT_STEPS, "path": str(block_path),
                "sha256": r12.sha256(block_path), "future_actual_used": False,
            })
        write_json(output / "R13_RESTART_TRAFFIC_MANIFEST.json", {
            "status": "PASS", "traffic_model_loads": 1 if missing else 0,
            "accepted_context_steps": 576, "blocks": traffic_manifest,
            "controller_burn_in_steps": 0, "future_actual_used": False,
        })

        runroot = r10.find_exact_mobility_run(base)
        sys.path.insert(0, str(runroot))
        fm = r12.load_module(runroot / "main.py", "r13_frozen_mobility")
        if r12.sha256(runroot / "main.py") != r12.DUALHORIZON_RUNTIME_SHA:
            raise RuntimeError("DUALHORIZON runtime SHA drift")
        contract = json.loads(
            (package / "embedded/STATE74_BRIDGE_CONTRACT.json").read_text(encoding="utf-8")
        )
        setup = r10.setup_e4a(fm, runroot, output, contract)
        key_to_id = {}
        key_rows = []
        for _, record in setup["bank"].iterrows():
            key = (str(record[setup["bank_level"]]), str(record[setup["bank_group"]]))
            if key not in key_to_id:
                key_to_id[key] = len(key_to_id)
                key_rows.append({"template_id": key_to_id[key], "level": key[0], "group": key[1]})
        pd.DataFrame(key_rows).to_csv(output / "R13_E4B_TEMPLATE_KEY_DICTIONARY.csv", index=False)
        setup["static"].to_parquet(output / "R13_ROUTE_STATIC_1656.parquet", index=False)

        r12._CPU_CONTEXT = {
            "fm": fm, "setup": setup, "key_to_id": key_to_id,
            "output": output, "base": base, "regression_r10_overlap": False,
        }
        context = mp.get_context("fork")
        pool = context.Pool(processes=args.cpu_workers, initializer=r12.initialize_cpu_worker)
        rows = []
        try:
            checkpoint, mean, std, e3, device, e3_execution = r10.e3_setup(package, base, fm)
            pending = []
            for candidate, start, block_path in block_records:
                with np.load(block_path, allow_pickle=False) as block:
                    origins = np.asarray(block["origins"], dtype=np.int64)[:2]
                    pathq_rows = np.asarray(block["path_quantiles_sec"], dtype=np.float32)[:2]
                    state_rows = np.asarray(block["state_code"], dtype=np.int8)[:2]
                for local in range(2):
                    issue, origin = start + local, int(origins[local])
                    pathq = pathq_rows[local : local + 1]
                    state = state_rows[local : local + 1]
                    features, timestamps, energy = r10.predict_e3(
                        fm, contract, pathq, state, origin, mean, std, e3, device
                    )
                    result = pool.apply_async(
                        r12.finish_issue_process,
                        ((issue, origin, pathq, state, features, timestamps, energy),),
                    )
                    pending.append((candidate, issue, result))
            pool.close()
            for candidate, issue, result in pending:
                row = result.get()
                if int(row["issue_step"]) != issue:
                    raise RuntimeError("worker issue ordering drift")
                row.pop("cpu_worker_pid")
                row["unseen_safe_steps"] = ";".join(str(x) for x in row["unseen_safe_steps"])
                rows.append(row)
            pool.join()
        except BaseException:
            pool.terminate(); pool.join(); raise

        index = output / "R13_RESTART_MOBILITY_INDEX.csv"
        write_index(index, rows)
        write_json(output / "R13_RESTART_MOBILITY_AUTHORITY.json", {
            "schema_version": "conversation_c.stage7.r13.restart_mobility_authority.v1",
            "status": "PASS",
            "candidate_count": 4,
            "artifact_issue_count": 8,
            "artifact_policy": "h0 and h0+1 only",
            "traffic_context_steps_per_candidate": 576,
            "controller_burn_in_steps": 0,
            "index_path": str(index),
            "index_sha256": r12.sha256(index),
            "template_bank_path": str(output / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"),
            "template_bank_sha256": r12.sha256(output / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"),
            "r10_source_sha256": r12.R10_SHA,
            "dualhorizon_runtime_sha256": r12.DUALHORIZON_RUNTIME_SHA,
            "e3_checkpoint_sha256": r12.sha256(checkpoint),
            "e3_execution": e3_execution,
            "future_actual_used": False,
            "gurobi_executed": False,
            "opendss_executed": False,
        })
        print(json.dumps({"status": "PASS", "mobility_artifacts": len(rows)}, indent=2))
        return 0
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
