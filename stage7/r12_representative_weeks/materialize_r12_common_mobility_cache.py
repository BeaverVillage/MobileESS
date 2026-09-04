#!/usr/bin/env python3
"""Stream the de-duplicated R12 mobility union into one resumable cache.

This control-plane adapter preserves the SHA-locked R10 numerical functions but
loads the traffic, E3, and E4 models only once.  It deliberately avoids R10's
large in-memory `(issues, 54, 1656, 3)` annual tensor by processing the
accepted R10 576-origin context at a time and atomically committing one issue
artifact at a time.  Smaller origin contexts are forbidden because the exact
regression showed they change the frozen traffic output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import signal
import shutil
import sys
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


R10_SHA = "bbe307835ff97e9e340d294f664c7c0ac5b2c19715af7c5c7f509687aae47fc4"
DUALHORIZON_RUNTIME_SHA = "1b0ac60ae49e1b4573d469e95c2b2857d17dbe64b7184bc81a28d433c02adbcc"
ISSUE_TO_TRAFFIC_ORIGIN = 631296
H = 54
R = 1656

_CPU_CONTEXT: dict[str, object] = {}
_THREADPOOL_LIMIT_GUARD = None


def initialize_cpu_worker() -> None:
    """Bind each forked E4 worker to one native CPU thread."""
    global _THREADPOOL_LIMIT_GUARD
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        from threadpoolctl import threadpool_limits

        _THREADPOOL_LIMIT_GUARD = threadpool_limits(limits=1)
    except ImportError:
        _THREADPOOL_LIMIT_GUARD = None


def current_metadata_with_unseen_safe_fallback(
    fm, static, origins, pathq, state, timestamps, chosen, step_bin, pstep_bin, hs, margin_vec
):
    """Use frozen Safe-horizon keys in-domain and hierarchy fallback out-of-domain.

    An unseen Safe duration must never be clamped into the highest calibrated
    bin.  A collision-proof token makes every horizon-specific bank key miss,
    so the frozen selector descends to its physical-route/global fallback while
    the continuous profile duration remains L=ceil(T_safe/300).
    """
    safe_eta = pathq[:, :, :, 2].astype(np.float64) + np.asarray(margin_vec, np.float64)[None, :, None]
    safe_steps = np.ceil(safe_eta / 300.0 - 1e-12).astype(int)
    unseen = sorted(set(safe_steps.reshape(-1).tolist()) - set(pstep_bin))
    extended = dict(pstep_bin)
    for step in unseen:
        extended[int(step)] = f"__UNSEEN_SAFE_L{int(step):04d}__"
    metadata = fm.current_metadata_frame(
        static, origins, pathq, state, timestamps, chosen, step_bin, extended, hs, margin_vec
    )
    return metadata, unseen


def finish_issue_process(task: tuple[int, int, np.ndarray, np.ndarray, object, np.ndarray, np.ndarray]) -> dict[str, object]:
    """Run E4/metadata/compression in a real CPU worker process."""
    issue, origin, pathq, state, features, timestamps, energy = task
    fm = _CPU_CONTEXT["fm"]
    setup = _CPU_CONTEXT["setup"]
    key_to_id = _CPU_CONTEXT["key_to_id"]
    output = _CPU_CONTEXT["output"]
    base = _CPU_CONTEXT["base"]
    regression_r10_overlap = bool(_CPU_CONTEXT["regression_r10_overlap"])

    metadata, unseen_safe_steps = current_metadata_with_unseen_safe_fallback(
        fm,
        setup["static"], np.asarray([origin]), pathq, state, timestamps,
        setup["chosen"], setup["step_bin"], setup["pstep_bin"],
        setup["hs"], setup["margin_vec"],
    )
    combined = fm.build_combined_feature_frame(features, metadata)
    scale = fm.infer_scale(
        setup["model_path"], setup["scale_model"], setup["scale_names"],
        setup["scale_transform"], combined, features,
    )
    flat = energy.reshape(-1, 3).astype(np.float64)
    q50, q90 = flat[:, 1], flat[:, 2]
    _temporal, _spatial, safe, _axis, _level, _group, _margin, _block, _rank = fm.apply_temporal_current(
        metadata, setup["temporal_lookup"], q50, q90, scale,
        setup["tie"], setup["spatial_base"],
    )
    levels, groups, _blocks = fm.select_current_templates(
        metadata, setup["bank"], setup["bank_level"], setup["bank_group"], None
    )
    if unseen_safe_steps:
        unseen_mask = metadata["profile_safe_horizon_steps"].isin(unseen_safe_steps).to_numpy()
        invalid_levels = sorted(
            set(np.asarray(levels, dtype=object)[unseen_mask].tolist())
            - {"physical_route", "global"}
        )
        if invalid_levels:
            raise RuntimeError(
                f"unseen Safe horizon selected a horizon-dependent template {invalid_levels}"
            )
    template_id = np.asarray(
        [key_to_id[(str(level), str(group))] for level, group in zip(levels, groups)],
        dtype=np.int32,
    )
    relative = f"mobility_runtime/issue_{issue:06d}_origin_{origin}.npz"
    artifact = output / relative
    atomic_npz(
        artifact,
        issue_step=np.asarray([issue], np.int32),
        origin=np.asarray([origin], np.int64),
        path_quantiles_sec=pathq[0].astype(np.float32),
        energy_quantiles_kWh=energy.reshape(H, R, 3).astype(np.float32),
        safe_energy_kWh=safe.reshape(H, R).astype(np.float32),
        route_safe_eta_sec=metadata["route_safe_eta_sec"].to_numpy(np.float32).reshape(H, R),
        energy_horizon_steps=metadata["energy_horizon_steps"].to_numpy(np.int16).reshape(H, R),
        profile_safe_horizon_steps=metadata["profile_safe_horizon_steps"].to_numpy(np.int16).reshape(H, R),
        e4b_template_id=template_id.reshape(H, R),
        state_code=state[0].astype(np.int8),
    )
    if regression_r10_overlap:
        expected = (
            base
            / "stage7_t2_precision_repair/A_TO_C_T2_R10_20260815T074441Z/"
            "CORRECTED_T2_MOBILITY_PAYLOAD/LONG576_MOBILITY_OUTPUT/mobility_runtime"
            / artifact.name
        )
        with np.load(artifact, allow_pickle=False) as actual_npz, np.load(expected, allow_pickle=False) as expected_npz:
            if actual_npz.files != expected_npz.files:
                raise RuntimeError(f"R10 regression key drift: {issue}")
            for key in actual_npz.files:
                if not np.array_equal(actual_npz[key], expected_npz[key]):
                    raise RuntimeError(f"R10 regression array drift: issue={issue} key={key}")
    return {
        "issue_step": issue, "origin": origin, "file": relative,
        "sha256": sha256(artifact), "rows": int(H * R),
        "state_free": int(np.sum(state == 0)),
        "state_moderate": int(np.sum(state == 1)),
        "state_severe": int(np.sum(state == 2)),
        "safe_max_kWh": float(np.max(safe)),
        "future_actual_target_read": False,
        "cpu_worker_pid": os.getpid(),
        "unseen_safe_row_count": int(
            metadata["profile_safe_horizon_steps"].isin(unseen_safe_steps).sum()
        ),
        "unseen_safe_steps": unseen_safe_steps,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def required_issues(authority_root: Path) -> np.ndarray:
    with (authority_root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    issues = np.unique(
        np.concatenate(
            [
                np.arange(
                    int(row["burn_in_start_index"]),
                    int(row["start_index"]),
                    dtype=np.int64,
                )
                for row in rows
            ]
        )
    )
    if len(issues) != 6912 or np.any(np.diff(issues) < 1):
        raise RuntimeError("R12 Stage 7 burn-in source union drift")
    return issues


def read_resume(index_path: Path, cache_root: Path, issues: np.ndarray) -> list[dict[str, str]]:
    if not index_path.is_file():
        return []
    with index_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [int(row["issue_step"]) for row in rows] != issues[: len(rows)].tolist():
        raise RuntimeError("common-cache partial index is not an exact union prefix")
    for row in rows:
        # The boundary-evidence columns were added after the first 1,253
        # production rows.  That prefix ended immediately before the first
        # unseen Safe step (issue 19109), so absent historical values are
        # exactly zero/empty rather than inferred numerical results.
        row.setdefault("unseen_safe_row_count", "0")
        row.setdefault("unseen_safe_steps", "")
        path = cache_root / row["file"]
        if not path.is_file() or sha256(path) != row["sha256"]:
            raise RuntimeError(f"committed cache entry SHA drift: {path}")
    return rows


def write_index(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = [
        "issue_step", "origin", "file", "sha256", "rows", "state_free",
        "state_moderate", "state_severe", "safe_max_kWh", "future_actual_target_read",
        "unseen_safe_row_count", "unseen_safe_steps",
    ]
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def quarantine_uncommitted(output: Path, rows: list[dict[str, str]]) -> dict[str, object]:
    """Move only files not bound by the committed prefix index."""
    committed = {str(row["file"]) for row in rows}
    candidates: list[Path] = []
    runtime = output / "mobility_runtime"
    if runtime.is_dir():
        candidates.extend(
            path for path in runtime.iterdir()
            if path.is_file()
            and (
                path.name.endswith(".tmp")
                or path.name.endswith(".npz.tmp")
                or (path.name.startswith("issue_") and path.suffix == ".npz" and str(path.relative_to(output)) not in committed)
            )
        )
    for path in (output / "R12_COMMON_MOBILITY_INDEX.partial.csv.tmp", output / "R12_COMMON_MOBILITY_INDEX.csv.tmp"):
        if path.is_file():
            candidates.append(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    quarantine = output / "interrupted_attempts" / stamp
    moved: list[dict[str, object]] = []
    for source in sorted(set(candidates)):
        relative = source.relative_to(output)
        destination = quarantine / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256(source)
        size = source.stat().st_size
        os.replace(source, destination)
        moved.append({
            "source": str(relative),
            "quarantined_path": str(destination),
            "sha256": digest,
            "bytes": size,
        })
    audit = {
        "schema_version": "conversation_c.stage7.r12.interrupted_source_quarantine.v1",
        "status": "PASS",
        "committed_index_rows": len(rows),
        "uncommitted_files_found": len(moved),
        "moved": moved,
        "completed_artifacts_moved": False,
    }
    if moved:
        write_json(quarantine / "QUARANTINE_AUDIT.json", audit)
    audit_path = output / "R12_INTERRUPTED_SOURCE_QUARANTINE_AUDIT.json"
    write_json(audit_path, audit)
    return audit


def atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--base-work", default="/home/jaewon/mobile_ess_work")
    parser.add_argument("--batch-size", type=int, default=576)
    parser.add_argument("--diagnostic-limit", type=int)
    parser.add_argument("--regression-r10-overlap", action="store_true")
    parser.add_argument("--phase", choices=("traffic", "full"), default="traffic")
    parser.add_argument("--cpu-workers", type=int, default=14)
    parser.add_argument("--audit-quarantine-only", action="store_true")
    parser.add_argument("--stage2a-runtime-override")
    args = parser.parse_args()
    if args.batch_size != 576:
        raise RuntimeError("R12 freezes the accepted R10 origin-context batch at exactly 576")
    if args.regression_r10_overlap and args.phase != "full":
        raise RuntimeError("R10 overlap regression requires --phase full")
    if not 1 <= args.cpu_workers <= 14:
        raise RuntimeError("cpu-workers must be 1..14")

    # The accepted R10 CUDA authority was produced by the Kestrel environment
    # (torch 2.12.1).  That environment intentionally lacks LightGBM, which is
    # imported by the frozen E4 module.  Append only the existing scats-parser
    # site directory after Kestrel's own site-packages; this supplies LightGBM
    # without shadowing Kestrel's torch/numpy numerical runtime.
    try:
        import lightgbm  # noqa: F401
    except ModuleNotFoundError:
        fallback_site = Path(
            "/home/jaewon/miniconda3/envs/scats_parser/lib/python3.12/site-packages"
        )
        sys.path.append(str(fallback_site))
        import lightgbm  # noqa: F401

    authority = Path(args.authority_root).resolve()
    output = Path(args.output_root).resolve()
    base = Path(args.base_work).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = output / "mobility_runtime"
    cache.mkdir(exist_ok=True)
    index_partial = output / "R12_COMMON_MOBILITY_INDEX.partial.csv"
    index_final = output / "R12_COMMON_MOBILITY_INDEX.csv"

    context_issues = required_issues(authority)
    production_count = len(context_issues)
    if args.regression_r10_overlap:
        if args.diagnostic_limit is not None:
            raise RuntimeError("regression-r10-overlap and diagnostic-limit are mutually exclusive")
        context_issues = np.arange(113, 689, dtype=np.int64)
    elif args.diagnostic_limit is not None:
        if args.diagnostic_limit < 1 or args.diagnostic_limit > production_count:
            raise RuntimeError("invalid diagnostic-limit")
        if args.diagnostic_limit % 576:
            raise RuntimeError("diagnostic-limit must be a multiple of 576")
        context_issues = context_issues[: args.diagnostic_limit]
    artifact_issues = context_issues[:54] if args.regression_r10_overlap else context_issues

    r10_path = base / "stage7_t2_precision_repair/A_TO_C_T2_R10_20260815T074441Z/REPAIRED_SOURCE_PACKAGE/main.py"
    if sha256(r10_path) != R10_SHA:
        raise RuntimeError("R10 source SHA drift")
    r10 = load_module(r10_path, "r12_r10_streaming_authority")
    package = r10_path.parent
    r10.CURRENT_PKG = package
    stage2a_override_sha256 = None
    if args.stage2a_runtime_override:
        stage2a_override = Path(args.stage2a_runtime_override).resolve()
        q2_override = stage2a_override / "scats_forecast/q2_global_volume_forecast_offsets1_19.float32.npy"
        if not q2_override.is_file():
            raise RuntimeError("stage2a runtime override is missing the causal Q2 forecast")
        r10.STAGE2A_RUNTIME = stage2a_override
        stage2a_override_sha256 = sha256(q2_override)

    rows = read_resume(index_partial, output, artifact_issues)
    quarantine_audit = quarantine_uncommitted(output, rows)
    if args.audit_quarantine_only:
        print(json.dumps(quarantine_audit, indent=2, sort_keys=True))
        return 0
    pending = artifact_issues[len(rows) :]
    if len(pending) == 0:
        if args.diagnostic_limit is None and not args.regression_r10_overlap:
            shutil.copy2(index_partial, index_final)
        existing_authority = output / "R12_COMMON_MOBILITY_CACHE_AUTHORITY.json"
        if not existing_authority.is_file():
            raise RuntimeError("complete mobility index exists without a PASS cache authority")
        existing = json.loads(existing_authority.read_text(encoding="utf-8"))
        if existing.get("status") != "PASS":
            raise RuntimeError("complete mobility index has a non-PASS cache authority")
        bound_index = index_final if index_final.is_file() else index_partial
        if existing.get("index_sha256") != sha256(bound_index):
            raise RuntimeError("complete mobility cache index SHA drift")
        return 0

    temporary_root = Path(tempfile.mkdtemp(prefix="r12_common_mobility_"))
    try:
        r0root = r10.safe_extract(
            package / "embedded/B1D1B2_R0_SOURCE_API_PASS.tar.gz",
            temporary_root / "r0",
            r10.R0_SHA,
        )
        traffic_root = output / "traffic_blocks"
        traffic_root.mkdir(exist_ok=True)
        expected_block_paths = [
            traffic_root / f"traffic_block_{batch_start//576:03d}.npz"
            for batch_start in range(0, len(context_issues), args.batch_size)
        ]
        missing_blocks = [path for path in expected_block_paths if not path.is_file()]
        if args.phase == "full" and missing_blocks:
            raise RuntimeError(
                "phase full requires a complete traffic cache from a separate phase traffic process"
            )

        traffic_model_loads = 0
        if missing_blocks:
            import torch

            br3 = r0root / "captured_sources/BR3"
            sys.path.insert(0, str(br3))
            adapter = load_module(br3 / "on_demand_traffic_adapter.py", "r12_traffic_adapter")
            traffic_runner = adapter.import_runner(br3 / "stage_ml10_final_v1_2.py")
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA required for frozen R10 traffic execution")
            adapter.configure_frozen_cuda_execution()
            device = torch.device("cuda")
            stage5, stage6, _stage8, traffic_model, links, preproc = traffic_runner.load_frozen_modules_and_model(
                r10.STAGE9, device
            )
            splits = pd.read_csv(r10.STAGE9 / "freeze_assets/dataset/date_splits_2019_2025.csv").sort_values("date").reset_index(drop=True)
            routes = np.load(r10.STAGE9 / "freeze_assets/stage8/optimizer_interface/final_od_k3_sequences.npz", allow_pickle=False)
            margins = np.load(r10.STAGE9 / "freeze_assets/stage8/optimizer_interface/safe_eta_margin_54.float32.npy", allow_pickle=False).astype(np.float64)
            ff = links["mapping_ff_tt_sec"].to_numpy(np.float64)
            dow = pd.to_datetime(splits["date"]).dt.dayofweek.to_numpy(np.int8)
            frozen = adapter.import_frozen_optimizer_interface(br3 / "traffic_optimizer_interface.py")
            interface = frozen.TrafficOptimizerInterface(
                routes["route_links"], routes["route_mask"], routes["source_index"],
                routes["destination_index"], ff, margins, preproc["historical_median"], dow, 0.80, 72,
            )
            traffic_model_loads = 1

        # Phase A: reproduce the original R10 ordering exactly.  Traffic is
        # completed and persisted before E3/E4 are even loaded onto the GPU.
        traffic_blocks: list[dict[str, object]] = []
        for batch_start in range(0, len(context_issues), args.batch_size):
            batch_issues = context_issues[batch_start : batch_start + args.batch_size]
            if len(batch_issues) != 576:
                raise RuntimeError("R12 common union must partition into exact 576-origin contexts")
            batch_origins = ISSUE_TO_TRAFFIC_ORIGIN + batch_issues
            block_path = traffic_root / f"traffic_block_{batch_start//576:03d}.npz"
            if block_path.is_file():
                with np.load(block_path, allow_pickle=False) as block:
                    if not np.array_equal(block["issues"], batch_issues):
                        raise RuntimeError(f"traffic block axis drift: {block_path}")
                    if not np.isfinite(block["path_quantiles_sec"]).all():
                        raise RuntimeError(f"traffic block nonfinite: {block_path}")
            else:
                adapter.configure_frozen_cuda_execution()
                dataset = adapter.CausalOperationalDataset(
                    stage5, batch_origins, r10.STAGE1, r10.STAGE2A_RUNTIME, splits, preproc
                )
                link, _batch = adapter.predict_link_quantiles(
                    traffic_runner, stage6, traffic_model, dataset, preproc, device,
                    reproduction_batch_size=4,
                )
                metric = np.quantile(link[:, :, :, 1].astype(np.float64), 0.9, axis=2, method="linear")
                states = np.where(metric < r10.TH1, 0, np.where(metric < r10.TH2, 1, 2)).astype(np.int8)
                path_quantiles = np.empty((576, H, R, 3), dtype=np.float32)
                for local, origin in enumerate(batch_origins):
                    audit = dataset.read_audit[int(origin)]
                    if int(audit["realized_tti_max_index_read"]) > int(origin):
                        raise RuntimeError(f"future traffic actual read: {batch_issues[local]}")
                    path_quantiles[local] = interface.path_quantiles(
                        np.asarray(link[local], np.float32), int(origin)
                    )
                atomic_npz(
                    block_path,
                    issues=batch_issues.astype(np.int64),
                    origins=batch_origins.astype(np.int64),
                    path_quantiles_sec=path_quantiles,
                    state_code=states,
                    network_metric_p90_link_q50=metric.astype(np.float32),
                )
            traffic_blocks.append({
                "block": batch_start // 576,
                "path": str(block_path),
                "sha256": sha256(block_path),
                "issue_first": int(batch_issues[0]),
                "issue_last": int(batch_issues[-1]),
                "issue_count": 576,
            })
            write_json(output / "R12_TRAFFIC_BLOCK_PROGRESS.json", {
                "status": "PASS" if batch_start + 576 == len(context_issues) else "MATERIALIZING",
                "completed_blocks": len(traffic_blocks),
                "required_blocks": len(context_issues) // 576,
                "future_actual_target_read": False,
            })
        write_json(output / "R12_TRAFFIC_BLOCK_MANIFEST.json", {
            "status": "PASS",
            "phase_order": "TRAFFIC_COMPLETE_BEFORE_E3_E4_LOAD",
            "blocks": traffic_blocks,
            "future_actual_target_read": False,
        })

        if args.phase == "traffic":
            write_json(output / "R12_COMMON_TRAFFIC_CACHE_AUTHORITY.json", {
                "schema_version": "conversation_c.stage7.r12.common_traffic_cache.v1",
                "status": "PASS",
                "issue_count": len(context_issues),
                "block_count": len(traffic_blocks),
                "block_steps": 576,
                "traffic_model_loads": traffic_model_loads,
                "e3_e4_executed": False,
                "downstream_policy": "E3/E4 issue artifacts are generated once into the shared CAS by a dedicated prefetch worker",
                "future_actual_target_read": False,
                "gurobi_executed": False,
                "opendss_executed": False,
                "stage2a_runtime_root": str(r10.STAGE2A_RUNTIME),
                "stage2a_q2_sha256": stage2a_override_sha256,
            })
            return 0

        # Phase B: load E3/E4 once, then stream the frozen traffic blocks.
        runroot = r10.find_exact_mobility_run(base)
        sys.path.insert(0, str(runroot))
        fm = load_module(runroot / "main.py", "r12_frozen_mobility")
        if sha256(runroot / "main.py") != DUALHORIZON_RUNTIME_SHA:
            raise RuntimeError("DUALHORIZON runtime SHA drift")
        contract = json.loads((package / "embedded/STATE74_BRIDGE_CONTRACT.json").read_text(encoding="utf-8"))
        setup = r10.setup_e4a(fm, runroot, output, contract)

        key_to_id: dict[tuple[str, str], int] = {}
        key_rows: list[dict[str, object]] = []
        for _, record in setup["bank"].iterrows():
            key = (str(record[setup["bank_level"]]), str(record[setup["bank_group"]]))
            if key not in key_to_id:
                key_to_id[key] = len(key_to_id)
                key_rows.append({"template_id": key_to_id[key], "level": key[0], "group": key[1]})
        pd.DataFrame(key_rows).to_csv(output / "R12_E4B_TEMPLATE_KEY_DICTIONARY.csv", index=False)
        setup["static"].to_parquet(output / "R12_ROUTE_STATIC_1656.parquet", index=False)

        pending_set = set(int(x) for x in pending)
        artifact_set = set(int(x) for x in artifact_issues)

        global _CPU_CONTEXT
        _CPU_CONTEXT = {
            "fm": fm,
            "setup": setup,
            "key_to_id": key_to_id,
            "output": output,
            "base": base,
            "regression_r10_overlap": args.regression_r10_overlap,
        }
        fork_context = mp.get_context("fork")
        pool = fork_context.Pool(
            processes=args.cpu_workers,
            initializer=initialize_cpu_worker,
        )
        worker_pids = sorted(process.pid for process in pool._pool if process.pid is not None)
        if len(worker_pids) != args.cpu_workers or len(set(worker_pids)) != args.cpu_workers:
            pool.terminate()
            pool.join()
            raise RuntimeError("R12 failed to start the requested CPU process pool")

        # Critical CUDA safety order: CPU workers fork before the parent loads
        # E3 onto CUDA.  Children never import or access the parent's CUDA state.
        checkpoint, mean, std, e3, e3_device, e3_execution = r10.e3_setup(package, base, fm)
        observed_worker_pids: set[int] = set()
        unseen_safe_row_count = sum(int(row.get("unseen_safe_row_count", 0)) for row in rows)
        unseen_safe_steps_observed = {
            int(step)
            for row in rows
            for step in str(row.get("unseen_safe_steps", "")).split(";")
            if step
        }

        def commit_completed(issue: int, result) -> None:
            nonlocal unseen_safe_row_count
            row = result.get()
            if int(row["issue_step"]) != issue:
                raise RuntimeError("R12 CPU worker returned an out-of-order issue")
            worker_pid = int(row.pop("cpu_worker_pid"))
            if worker_pid not in worker_pids:
                raise RuntimeError("R12 result came from an unbound replacement worker")
            observed_worker_pids.add(worker_pid)
            issue_unseen_count = int(row["unseen_safe_row_count"])
            issue_unseen_steps = [int(x) for x in row["unseen_safe_steps"]]
            unseen_safe_row_count += issue_unseen_count
            unseen_safe_steps_observed.update(issue_unseen_steps)
            row["unseen_safe_row_count"] = issue_unseen_count
            row["unseen_safe_steps"] = ";".join(str(x) for x in issue_unseen_steps)
            rows.append(row)
            write_index(index_partial, rows)
            write_json(output / "R12_COMMON_MOBILITY_PROGRESS.json", {
                "status": "MATERIALIZING",
                "completed_issue_count": len(rows),
                "required_issue_count": len(artifact_issues),
                "last_completed_issue": issue,
                "gpu_producer_count": 1,
                "cpu_worker_count": args.cpu_workers,
                "cpu_worker_execution": "FORK_PROCESS_POOL_PRE_CUDA",
                "os_process_count": 1 + args.cpu_workers,
                "max_inflight_issues": args.cpu_workers,
                "shared_e4_authority_via_fork_cow": True,
                "unseen_safe_horizon_fallback_rows": unseen_safe_row_count,
                "unseen_safe_horizon_steps": sorted(unseen_safe_steps_observed),
                "future_actual_target_read": False,
            })

        inflight: deque[tuple[int, object]] = deque()
        try:
            for block_record in traffic_blocks:
                with np.load(Path(block_record["path"]), allow_pickle=False) as block:
                    block_issues = np.asarray(block["issues"], dtype=np.int64)
                    block_origins = np.asarray(block["origins"], dtype=np.int64)
                    block_pathq = np.asarray(block["path_quantiles_sec"], dtype=np.float32)
                    block_states = np.asarray(block["state_code"], dtype=np.int8)
                for local, (issue_value, origin_value) in enumerate(zip(block_issues, block_origins)):
                    issue, origin = int(issue_value), int(origin_value)
                    if issue not in pending_set or issue not in artifact_set:
                        continue
                    pathq = block_pathq[local : local + 1]
                    state = block_states[local : local + 1]
                    features, timestamps, energy = r10.predict_e3(
                        fm, contract, pathq, state, origin, mean, std, e3, e3_device
                    )
                    inflight.append((
                        issue,
                        pool.apply_async(
                            finish_issue_process,
                            ((issue, origin, pathq, state, features, timestamps, energy),),
                        ),
                    ))
                    if len(inflight) >= args.cpu_workers:
                        commit_issue, result = inflight.popleft()
                        commit_completed(commit_issue, result)
            pool.close()
            while inflight:
                commit_issue, result = inflight.popleft()
                commit_completed(commit_issue, result)
            pool.join()
        except BaseException:
            pool.terminate()
            pool.join()
            raise

        complete = len(rows) == len(artifact_issues)
        if complete and args.diagnostic_limit is None and not args.regression_r10_overlap:
            shutil.copy2(index_partial, index_final)
        write_json(output / "R12_COMMON_MOBILITY_CACHE_AUTHORITY.json", {
            "schema_version": "conversation_c.stage7.r12.common_mobility_cache.v1",
            "status": "PASS" if complete else "INCOMPLETE_RESUMABLE",
            "diagnostic_only": args.diagnostic_limit is not None or args.regression_r10_overlap,
            "r10_overlap_regression": args.regression_r10_overlap,
            "r10_overlap_array_exact": True if args.regression_r10_overlap and complete else None,
            "issue_count": len(rows),
            "production_required_issue_count": production_count,
            "index_path": str(index_final if index_final.is_file() else index_partial),
            "index_sha256": sha256(index_final if index_final.is_file() else index_partial),
            "template_bank_path": str(output / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"),
            "template_bank_sha256": sha256(output / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"),
            "r10_source_sha256": R10_SHA,
            "dualhorizon_runtime_sha256": DUALHORIZON_RUNTIME_SHA,
            "unseen_safe_horizon_membership_gate": False,
            "unseen_safe_horizon_fallback": "FROZEN_HIERARCHY_PHYSICAL_ROUTE_THEN_GLOBAL_NO_CLAMP",
            "unseen_safe_horizon_fallback_rows": unseen_safe_row_count,
            "unseen_safe_horizon_steps": sorted(unseen_safe_steps_observed),
            "continuous_safe_duration_resampling": True,
            "traffic_e3_e4_model_loads_per_process": 1,
            "gpu_producer_count": 1,
            "cpu_worker_count": args.cpu_workers,
            "cpu_worker_execution": "FORK_PROCESS_POOL_PRE_CUDA",
            "os_process_count": 1 + args.cpu_workers,
            "cpu_worker_pids": worker_pids,
            "observed_worker_pids": sorted(observed_worker_pids),
            "shared_e4_authority_via_fork_cow": True,
            "workers_forked_before_parent_e3_cuda_load": True,
            "ordered_prefix_index_commit": True,
            "streaming_batch_size": args.batch_size,
            "e3_checkpoint_sha256": sha256(checkpoint),
            "e3_execution": e3_execution,
            "future_actual_target_read": False,
            "gurobi_executed": False,
            "opendss_executed": False,
        })
        return 0 if complete else 2
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
