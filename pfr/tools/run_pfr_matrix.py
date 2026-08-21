"""Run PFR B0-B7 against causal representative-week data and Fresh OpenDSS."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from pfr.methods import ExperimentAuthority, MethodFactory
from pfr.optimization import GurobiFastControlOptimizer
from pfr.power import H100UtilizationPowerCurve
from pfr.runtime import (
    CausalExperimentFrame,
    MobilityRouteForecast,
    OperationalTrainingJob,
    PhysicalCommit,
    PfrRuntimeRunner,
    RuntimeInitialState,
)
from pfr.safety import ExactAcResult


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_exact_module(repo: Path, exact_package_root: Path):
    science = repo / "science"
    support = exact_package_root.resolve()
    if not (support / "opendss_metrics_common.py").is_file():
        raise RuntimeError("exact package lacks opendss_metrics_common.py")
    sys.path.insert(0, str(support))
    sys.path.insert(0, str(science))
    return importlib.import_module("EXACT_GRID_RUNNER_24SERVICE")


class ExactOpenDssBackend:
    def __init__(self, exact: Any, paths: Mapping[str, str]) -> None:
        self.exact = exact
        self.paths = dict(paths)

    def verify_fresh(
        self,
        *,
        issue: int,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
        robust_background_p_kw: Sequence[Sequence[float]],
        robust_background_q_kvar: Sequence[Sequence[float]],
        robust_pv_available_kw: Sequence[Sequence[float]],
    ) -> PhysicalCommit:
        state = {
                "facility_p_kw": list(facility_p_kw),
                "facility_q_kvar": list(facility_q_kvar),
                "mess_location_service_id": list(mess_location),
                "mess_p_kw": list(mess_p_kw),
                "mess_q_kvar": list(mess_q_kvar),
                "mess_parked": [not value for value in mess_in_transit],
                "mess_plugged": [not value for value in mess_in_transit],
                "mess_grid_connected": [not value for value in mess_in_transit],
                "mess_in_transit": list(mess_in_transit),
        }
        raw = self.exact.solve_step(self.paths, issue, state)
        robust = raw
        if robust_background_p_kw:
            robust_state = dict(state)
            robust_state.update({
                "background_p_kw": robust_background_p_kw,
                "background_q_kvar": robust_background_q_kvar,
                "pv_available_kw": robust_pv_available_kw,
            })
            robust = self.exact.solve_step(self.paths, issue, robust_state)
        violation_count = sum(
            int(raw[key]) + int(robust[key])
            for key in (
                "voltage_violation_count",
                "line_violation_count",
                "transformer_kva_violation_count",
                "transformer_current_violation_count",
            )
        ) + (0 if raw["root_sign_pass"] else 1) + (0 if robust["root_sign_pass"] else 1)
        passed = bool(raw["hard_constraint_pass"] and robust["hard_constraint_pass"])
        if passed:
            exact_status = "PASS_FRESH_EXACT_OPENDSS_ROBUST_GRID"
        elif not raw["root_sign_pass"]:
            exact_status = "FAIL_FRESH_EXACT_OPENDSS_ACTUAL_ROOT_SIGN"
        else:
            exact_status = "FAIL_FRESH_EXACT_OPENDSS_ROBUST_GRID"
        exact_result = ExactAcResult(
            passed=passed,
            status=exact_status,
            fresh_instance=True,
            exact_three_phase_authority=True,
            minimum_voltage_pu=min(float(raw["voltage_min_pu"]), float(robust["voltage_min_pu"])),
            maximum_voltage_pu=max(float(raw["voltage_max_pu"]), float(robust["voltage_max_pu"])),
            maximum_line_loading_fraction=max(float(raw["line_max_loading_pu"]), float(robust["line_max_loading_pu"])),
            maximum_transformer_loading_fraction=max(
                float(raw["transformer_max_kva_loading_pu"]),
                float(raw["transformer_max_current_loading_pu"]),
                float(robust["transformer_max_kva_loading_pu"]),
                float(robust["transformer_max_current_loading_pu"]),
            ),
            final_ac_violation_count=violation_count,
        )
        combined = dict(raw)
        combined.update({
            "robust_grid_fresh_opendss": bool(robust_background_p_kw),
            "robust_grid_hard_constraint_pass": bool(robust["hard_constraint_pass"]),
            "robust_grid_voltage_min_pu": float(robust["voltage_min_pu"]),
            "robust_grid_voltage_max_pu": float(robust["voltage_max_pu"]),
            "robust_grid_line_max_loading_pu": float(robust["line_max_loading_pu"]),
            "robust_grid_transformer_max_loading_pu": max(
                float(robust["transformer_max_kva_loading_pu"]),
                float(robust["transformer_max_current_loading_pu"]),
            ),
        })
        return PhysicalCommit(exact_result, combined, False, True)


def _load_curve(path: Path) -> H100UtilizationPowerCurve:
    data = json_load(path)
    curve = H100UtilizationPowerCurve(
        tuple(map(float, data["utilization_fraction"])),
        tuple(map(float, data["per_gpu_power_kw_p95_envelope"])),
        str(data["source_sha256"]),
        tuple(item["sha256"] for item in data["source_members"] if item["included_in_statistics"]),
        str(data["work_fraction_semantics"]),
    )
    curve.validate()
    return curve


def _runtime_initial_state(pre: Mapping[str, Any], start_issue: int) -> RuntimeInitialState:
    """Accept legacy runtime PRE or the v13.2 independent-daily manifest."""
    if "canonical_pre" in pre:
        canonical = pre["canonical_pre"]
        energy = canonical["mess_energy_kwh"]
        locations = canonical["mess_locations"]
        if len(energy) != 4 or len(locations) != 4:
            raise RuntimeError("v13.2 canonical PRE must contain exactly four MESS")
        if canonical.get("ai_queue_empty") is not True or canonical.get("ai_running_empty") is not True:
            raise RuntimeError("v13.2 daily PRE must start with empty controllable AI state")
        if canonical.get("wan_inventory_empty") is not True or canonical.get("wan_pipeline_empty") is not True:
            raise RuntimeError("v13.2 daily PRE must start with empty WAN state")
        if canonical.get("active_slow_plan") is not None:
            raise RuntimeError("v13.2 daily PRE must not carry an active slow plan")
        return RuntimeInitialState(
            issue=start_issue,
            state_sha256=str(pre["canonical_pre_sha256"]),
            mess_energy_kwh={f"MESS{i + 1:02d}": float(value) for i, value in enumerate(energy)},
            mess_location={f"MESS{i + 1:02d}": str(value) for i, value in enumerate(locations)},
        )

    if int(pre["state"]["issue_step"]) > start_issue:
        raise RuntimeError("canonical PRE starts after requested issue")
    return RuntimeInitialState(
        issue=start_issue,
        state_sha256=str(pre["state_sha256"]),
        mess_energy_kwh={key: float(value) for key, value in pre["state"]["mess_E_kWh"].items()},
        mess_location={key: str(value["service_id"]) for key, value in pre["state"]["mess_state"].items()},
    )


def _block(shared: Path, issue: int) -> Path:
    if issue < 0:
        raise RuntimeError("issue must be non-negative")
    block = issue // 576
    start = block * 576
    return shared / "power_price" / f"block_{block:02d}_{start}_{start + 575}"


def _frames(
    *,
    shared: Path,
    start_issue: int,
    count: int,
    independent_jobs: Path,
    canonical_jobs: Path,
    mobility_paths: Mapping[int, Path],
    route_rows: Sequence[Mapping[str, Any]],
    mobility_template_bank: Mapping[int, tuple[float, ...]],
    workload_reserve_gpu: Mapping[str, float],
) -> list[CausalExperimentFrame]:
    independent = pd.read_parquet(independent_jobs)
    canonical_fields = [
        "job_uid", "source_record_id", "runtime_seconds_source", "CPU_request_share_upper_component_kW",
        "input_bytes", "job_power_prefreeze_authorized",
    ]
    canonical = pd.read_parquet(canonical_jobs, columns=canonical_fields)
    if canonical["job_uid"].astype(str).duplicated().any():
        raise RuntimeError("canonical job_uid is not unique")
    canonical["job_uid"] = canonical["job_uid"].astype(str)
    independent["job_uid"] = independent["job_uid"].astype(str)
    selected = independent[
        (independent["arrival_step"].astype(int) >= start_issue)
        & (independent["arrival_step"].astype(int) < start_issue + count)
    ].merge(canonical, on="job_uid", how="left", validate="many_to_one", suffixes=("", "_canonical"))
    if selected["runtime_seconds_source"].isna().any() or not selected["job_power_prefreeze_authorized"].fillna(False).all():
        raise RuntimeError("runtime job cohort lacks source-matched authorized power/work records")
    arrivals: dict[int, list[OperationalTrainingJob]] = {}
    for record in selected.to_dict(orient="records"):
        input_value = record.get("input_bytes_canonical", record.get("input_bytes"))
        input_bytes = None if pd.isna(input_value) else int(input_value)
        job = OperationalTrainingJob(
            job_uid=str(record["job_uid"]),
            origin_idc=str(record["origin_IDC_id"]),
            arrival_step=int(record["arrival_step"]),
            latest_start_step=int(record["latest_start_step"]),
            deadline_step=int(record["latest_completion_step"]),
            requested_gpu=int(record["requested_gpu"]),
            runtime_seconds_source=float(record["runtime_seconds_source"]),
            cpu_request_share_kw=float(record["CPU_request_share_upper_component_kW"]),
            input_bytes=input_bytes,
            source_record_id=str(record["source_record_id"]),
        )
        job.validate()
        arrivals.setdefault(job.arrival_step, []).append(job)
    frames = []
    cache: dict[Path, dict[str, np.ndarray]] = {}
    for issue in range(start_issue, start_issue + count):
        root = _block(shared, issue)
        if root not in cache:
            cache[root] = {
                "issues": np.load(root / "power__issues.npy", mmap_mode="r"),
                "p": np.load(root / "power__q50_net_background_p_kw.npy", mmap_mode="r"),
                "q": np.load(root / "power__q50_background_q_kvar.npy", mmap_mode="r"),
                "upper_p": np.load(root / "power__q90_gross_background_p_kw.npy", mmap_mode="r"),
                "upper_q": np.load(root / "power__q90_background_q_kvar.npy", mmap_mode="r"),
                "lower_pv": np.load(root / "power__q10_pv_available_kw.npy", mmap_mode="r"),
                "price_issues": np.load(root / "price__issues.npy", mmap_mode="r"),
                "price": np.load(root / "price__q50.npy", mmap_mode="r"),
            }
        block = cache[root]
        hits = np.flatnonzero(np.asarray(block["issues"], dtype=np.int64) == issue)
        price_hits = np.flatnonzero(np.asarray(block["price_issues"], dtype=np.int64) == issue)
        if len(hits) != 1 or len(price_hits) != 1:
            raise RuntimeError(f"causal source cardinality failure issue={issue}")
        row, price_row = int(hits[0]), int(price_hits[0])
        price_horizon = np.asarray(block["price"][price_row], dtype=float)
        mobility_path = mobility_paths.get(issue)
        if mobility_path is None:
            raise RuntimeError(f"missing causal mobility source issue={issue}")
        with np.load(mobility_path, allow_pickle=False) as mobility:
            eta = np.asarray(mobility["path_quantiles_sec"][0], dtype=float)
            energy = np.asarray(mobility["energy_quantiles_kWh"][0], dtype=float)
            safe_energy = np.asarray(mobility["safe_energy_kWh"][0], dtype=float)
            safe_eta = np.asarray(mobility["route_safe_eta_sec"][0], dtype=float)
            template_ids = np.asarray(mobility["e4b_template_id"][0], dtype=int)
            profile_steps = np.asarray(mobility["profile_safe_horizon_steps"][0], dtype=int)
        routes = []
        for static in route_rows:
            if static["destination_service_id"] not in {f"IDC{i:02d}" for i in range(1, 13)}:
                continue
            slot = int(static["slot"])
            routes.append(MobilityRouteForecast(
                source_service_id=str(static["source_service_id"]),
                destination_service_id=str(static["destination_service_id"]),
                od_index=int(static["od_index"]),
                rank=int(static["rank"]),
                q50_eta_seconds=float(eta[slot, 1]),
                safe_eta_seconds=float(safe_eta[slot]),
                q50_energy_kwh=float(energy[slot, 1]),
                safe_energy_kwh=float(safe_energy[slot]),
                profile_template_id=int(template_ids[slot]),
                profile_horizon_steps=int(profile_steps[slot]),
            ))
        robust_p = np.asarray(block["upper_p"][row, 0], dtype=float)
        robust_q = np.asarray(block["upper_q"][row, 0], dtype=float)
        robust_pv = np.asarray(block["lower_pv"][row, 0], dtype=float)
        payload = {
            "issue": issue,
            "power_block_authority_sha256": sha256(root / "BLOCK_AUTHORITY.json"),
            "arriving_job_uids": sorted(job.job_uid for job in arrivals.get(issue, ())),
            "mobility_issue_sha256": sha256(mobility_path),
            "factorized_uncertainty_bound": True,
        }
        frames.append(CausalExperimentFrame(
            issue=issue,
            current_price_aud_per_mwh=float(price_horizon[0]),
            horizon_price_median_aud_per_mwh=float(statistics.median(price_horizon.tolist())),
            q50_background_p_kw=float(np.asarray(block["p"][row, 0], dtype=float).sum()),
            q50_background_q_kvar=float(np.asarray(block["q"][row, 0], dtype=float).sum()),
            arrivals=tuple(sorted(arrivals.get(issue, ()), key=lambda job: job.job_uid)),
            exogenous_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            grid_upper_background_p_kw=float((robust_p - robust_pv).sum()),
            grid_upper_background_q_kvar=float(robust_q.sum()),
            robust_background_p_kw=tuple(tuple(map(float, values)) for values in robust_p),
            robust_background_q_kvar=tuple(tuple(map(float, values)) for values in robust_q),
            robust_pv_available_kw=tuple(tuple(map(float, values)) for values in robust_pv),
            workload_reserve_gpu=dict(workload_reserve_gpu),
            mobility_routes=tuple(routes),
            mobility_template_bank=mobility_template_bank,
        ))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--candidate-id", default="JAN2025_DAY01")
    parser.add_argument("--start-issue", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--exact-package-root", type=Path, required=True)
    parser.add_argument("--authority-package-root", type=Path, required=True)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--initial-state", type=Path, required=True)
    parser.add_argument("--independent-jobs", type=Path, required=True)
    parser.add_argument("--canonical-jobs", type=Path, required=True)
    parser.add_argument("--power-curve", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, action="append", required=True)
    parser.add_argument("--route-catalog", type=Path, required=True)
    parser.add_argument("--mobility-template-bank", type=Path, required=True)
    parser.add_argument("--workload-uncertainty", type=Path, required=True)
    parser.add_argument("--factorized-uncertainty", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive")
    repo = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    exact = _load_exact_module(repo, args.exact_package_root)
    source_work = output / "_exact_source_work"
    if source_work.exists():
        shutil.rmtree(source_work)
    source_work.mkdir(parents=True)
    paths = exact.prepare_sources(
        args.authority_package_root.resolve(), source_work,
        v2038_root=str(args.exact_package_root.resolve()),
        primary_root=str(args.primary_root.resolve()),
    )
    pre = json_load(args.initial_state)
    initial = _runtime_initial_state(pre, args.start_issue)
    factorized = json_load(args.factorized_uncertainty)
    workload_uncertainty = json_load(args.workload_uncertainty)
    if factorized.get("status") != "PASS" or workload_uncertainty.get("status") != "PASS":
        raise RuntimeError("PFR3 factorized/workload authority is not PASS")
    mobility_paths = {}
    for root in args.mobility_root:
        for path in (root / "mobility_runtime").glob("issue_*.npz"):
            issue = int(path.name.split("_")[1])
            if issue in mobility_paths:
                raise RuntimeError(f"duplicate mobility issue {issue}")
            mobility_paths[issue] = path
    route_catalog = json_load(args.route_catalog)
    route_rows = route_catalog.get("routes", ())
    if route_catalog.get("status") != "PASS" or len(route_rows) != 1656:
        raise RuntimeError("frozen K=3 route catalog is incomplete")
    template_frame = pd.read_parquet(args.mobility_template_bank)
    template_columns = [f"u{index:03d}" for index in range(129)]
    mobility_template_bank = {
        index: tuple(float(row[column]) for column in template_columns)
        for index, row in template_frame.iterrows()
    }
    frames = _frames(
        shared=args.shared_root.resolve(), start_issue=args.start_issue, count=args.count,
        independent_jobs=args.independent_jobs.resolve(), canonical_jobs=args.canonical_jobs.resolve(),
        mobility_paths=mobility_paths,
        route_rows=route_rows,
        mobility_template_bank=mobility_template_bank,
        workload_reserve_gpu={
            key: float(value) for key, value in workload_uncertainty["idc_gpu_reserve"].items()
        },
    )
    evaluation_contract = {
        "gpu_capacity_per_idc_modeled": 256,
        "facility_power_factor_assumption": 1.0,
        "mess_discharge_kw_when_enabled": 20.0,
        "maximum_refresh_steps": 6,
        "future_actual_used": False,
        "factorized_uncertainty_sha256": sha256(args.factorized_uncertainty),
        "workload_uncertainty_sha256": sha256(args.workload_uncertainty),
        "route_catalog_sha256": sha256(args.route_catalog),
        "mobility_template_bank_sha256": sha256(args.mobility_template_bank),
    }
    contract_sha = hashlib.sha256(json.dumps(evaluation_contract, sort_keys=True).encode()).hexdigest()
    authority = ExperimentAuthority(
        exogenous_inputs_sha256=sha256(args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"),
        initial_state_sha256=sha256(args.initial_state),
        grid_model_sha256=sha256(Path(paths["assets"]) / "IEEE123Master.dss"),
        jobs_sha256=sha256(args.canonical_jobs),
        wan_sha256=sha256(repo / "pfr/contracts/DATA_GAPS_AND_NONAUTHORITATIVE_FIELDS.json"),
        evaluation_coefficients_sha256=contract_sha,
        physical_ratings_sha256=sha256(Path(paths["assets"]) / "Generated_Planning_Line_Ratings_u080.dss"),
    )
    runner = PfrRuntimeRunner(
        power_curve=_load_curve(args.power_curve),
        physical_backend=ExactOpenDssBackend(exact, paths),
        fast_optimizer=GurobiFastControlOptimizer(),
    )
    matrix = runner.run_matrix(
        configs=MethodFactory(authority).all(),
        frames=frames,
        initial=initial,
        representative_week_id=args.candidate_id,
        output=output,
    )
    manifest = {
        "status": matrix["status"],
        "candidate_id": args.candidate_id,
        "start_issue": args.start_issue,
        "count": args.count,
        "shared_authority_fingerprint": authority.fingerprint,
        "evaluation_contract": evaluation_contract,
        "actual_gurobi_used": matrix["all_actual_gurobi"],
        "actual_fresh_opendss_used": matrix["all_fresh_exact_opendss"],
        "opendss_metrics_common_sha256": sha256(args.exact_package_root / "opendss_metrics_common.py"),
        "full_scientific_daily_episode_issues": 288,
        "bounded_regression_not_full_scientific_episode": args.count != 288,
        "independent_daily_cold_start": "canonical_pre" in pre,
        "cross_day_endogenous_state_carryover": False,
        "controller_burn_in_steps": 0,
        "factorized_uncertainty_decision_use": {
            "U_mob": "K3_ROUTE_MIQP_AND_E4_TRANSIT_SOC",
            "U_work": "SITE_GPU_CAPACITY_AND_PLAN_VALIDITY_RISK",
            "U_grid": "ROBUST_Q90_LOAD_Q10_PV_Q90_Q_FRESH_OPENDSS",
        },
        "future_actual_used": False,
    }
    (output / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": matrix["status"], "markers": matrix["valid_commit_markers"], "output": str(output)}))
    if matrix["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
