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
    ) -> PhysicalCommit:
        raw = self.exact.solve_step(
            self.paths,
            issue,
            {
                "facility_p_kw": list(facility_p_kw),
                "facility_q_kvar": list(facility_q_kvar),
                "mess_location_service_id": list(mess_location),
                "mess_p_kw": list(mess_p_kw),
                "mess_q_kvar": list(mess_q_kvar),
                "mess_parked": [True] * 4,
                "mess_plugged": [True] * 4,
                "mess_grid_connected": [True] * 4,
                "mess_in_transit": [False] * 4,
            },
        )
        violation_count = sum(
            int(raw[key])
            for key in (
                "voltage_violation_count",
                "line_violation_count",
                "transformer_kva_violation_count",
                "transformer_current_violation_count",
            )
        ) + (0 if raw["root_sign_pass"] else 1)
        exact_result = ExactAcResult(
            passed=bool(raw["hard_constraint_pass"]),
            status="PASS_FRESH_EXACT_OPENDSS" if raw["hard_constraint_pass"] else "FAIL_FRESH_EXACT_OPENDSS",
            fresh_instance=True,
            exact_three_phase_authority=True,
            minimum_voltage_pu=float(raw["voltage_min_pu"]),
            maximum_voltage_pu=float(raw["voltage_max_pu"]),
            maximum_line_loading_fraction=float(raw["line_max_loading_pu"]),
            maximum_transformer_loading_fraction=max(
                float(raw["transformer_max_kva_loading_pu"]),
                float(raw["transformer_max_current_loading_pu"]),
            ),
            final_ac_violation_count=violation_count,
        )
        return PhysicalCommit(exact_result, raw, False, True)


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
        payload = {
            "issue": issue,
            "power_block_authority_sha256": sha256(root / "BLOCK_AUTHORITY.json"),
            "arriving_job_uids": sorted(job.job_uid for job in arrivals.get(issue, ())),
        }
        frames.append(CausalExperimentFrame(
            issue=issue,
            current_price_aud_per_mwh=float(price_horizon[0]),
            horizon_price_median_aud_per_mwh=float(statistics.median(price_horizon.tolist())),
            q50_background_p_kw=float(np.asarray(block["p"][row, 0], dtype=float).sum()),
            q50_background_q_kvar=float(np.asarray(block["q"][row, 0], dtype=float).sum()),
            arrivals=tuple(sorted(arrivals.get(issue, ()), key=lambda job: job.job_uid)),
            exogenous_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
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
    if int(pre["state"]["issue_step"]) > args.start_issue:
        raise RuntimeError("canonical PRE starts after requested issue")
    # Bounded PFR9 may begin at the first nonempty causal arrival.  The physical
    # state remains the frozen cold PRE because no prior jobs or control outcomes
    # are imported; this is an explicit bounded regression, not a scientific episode.
    initial = RuntimeInitialState(
        issue=args.start_issue,
        state_sha256=str(pre["state_sha256"]),
        mess_energy_kwh={key: float(value) for key, value in pre["state"]["mess_E_kWh"].items()},
        mess_location={key: str(value["service_id"]) for key, value in pre["state"]["mess_state"].items()},
    )
    frames = _frames(
        shared=args.shared_root.resolve(), start_issue=args.start_issue, count=args.count,
        independent_jobs=args.independent_jobs.resolve(), canonical_jobs=args.canonical_jobs.resolve(),
    )
    evaluation_contract = {
        "gpu_capacity_per_idc_modeled": 256,
        "facility_power_factor_assumption": 1.0,
        "mess_discharge_kw_when_enabled": 20.0,
        "maximum_refresh_steps": 6,
        "future_actual_used": False,
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
        "bounded_regression_not_full_scientific_episode": args.count < 2016,
        "future_actual_used": False,
    }
    (output / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": matrix["status"], "markers": matrix["valid_commit_markers"], "output": str(output)}))
    if matrix["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
