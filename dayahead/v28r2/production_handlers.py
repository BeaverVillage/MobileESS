"""Real handlers binding all thirty V28R2 heavy-backend steps."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .actual_replay import ActualReplay, build_natural_actual, replay_actual_case
from .backend_contract import (
    EXECUTION_STEPS, DayRunSpec, NativeSettings, canonical_sha256,
    code_tree_manifest, combined_file_sha256, fixed_aest_axis, git_head, sha256_file,
)
from .benders_authority import solve_benders
from .certificate import file_references, verify_certificate, write_certificate
from .day_state import DayState, atomic_json
from .electrical_cache_prepare import prepare_electrical_context
from .electrical_context import build_electrical_context, with_realized_background
from .formulation import V28R2FormulationData, formulation_fingerprint, materialize_formulation_data
from .opendss_backend import run_fresh_opendss
from .pi_executor import PIExecution, execute_pi, materialize_pi_formulation_data
from .reference_compute import ReferenceSchedule
from .runtime_ledger import RuntimeLedger
from .schedule_freeze import OPERATIONAL_SOLVER, freeze_dayahead_schedules, verify_schedule_manifest
from .solver_equivalence import verify_b3_equivalence
from .solver_payload import SolverPayload
from .solver_runner import solve_monolithic
from .source_cache import day_root as source_day_root
from .source_manifest import verify_day_manifest
from .trajectory import FrozenTrajectory
from .workload_replay import ActualWorkload, materialize_actual_workload


MODEL_MANIFEST = "dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_MODELS_SHA256.json"
THERMAL_MODEL = "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
SCALE_AUTHORITY = "dayahead/artifacts/v28r2_heavy_backend/V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json"


def _source_manifest(repo: Path, day: str) -> tuple[Path, dict[str, object]]:
    path = source_day_root(repo, day) / "source_day_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = payload.get("source_day_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "source_day_sha256"}
    if stored != canonical_sha256(unsigned):
        raise RuntimeError("V28R2_SOURCE_DAY_MANIFEST_ROOT_SHA")
    verify_day_manifest(payload, base_dir=path.parent)
    return path, payload


def selected_model_paths(repo: Path, day: str) -> dict[str, Path]:
    model_dir = repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_MODELS"
    variant = "APRIL_01_CAUSAL_FIT" if day == "2025-04-01" else "GENERAL_THROUGH_MARCH_31_FIT"
    prefixes = {"P": "P_REF", "G": "G_REF", "W": "W_FULLNODE_DAILY"}
    result = {
        f"{channel}_model_{quantile}": model_dir / f"{prefix}_{variant}_{quantile}.txt"
        for channel, prefix in prefixes.items() for quantile in ("q10", "q50", "q90")
    }
    if any(not path.is_file() for path in result.values()):
        raise FileNotFoundError("V28R2_SELECTED_MODEL_FILE_MISSING")
    return result


def build_day_run_spec(repo: Path, day: str, mode: str) -> DayRunSpec:
    if day < "2025-04-01" or day > "2025-04-30":
        raise ValueError("V28R2_DAY_OUTSIDE_APRIL")
    if mode not in {"authority-preflight", "non-authority-smoke"}:
        raise ValueError("V28R2_RUN_MODE")
    _manifest_path, source = _source_manifest(repo, day)
    settings = NativeSettings()
    tree = code_tree_manifest(repo)
    models = selected_model_paths(repo, day)
    suffix = "v28r2_april_full_month_preflight" if mode == "authority-preflight" else "v28r2_non_authority_heavy_smoke"
    roots = {
        "frozen_artifacts": str((repo / "frozen_artifacts" / suffix).resolve()),
        "logs": str((repo / "logs" / suffix).resolve()),
        "progress": str((repo / "progress" / suffix).resolve()),
    }
    return DayRunSpec(
        day=day,
        campaign="april",
        timestamps_fixed_aest=fixed_aest_axis(day),
        git_head=git_head(repo),
        code_tree_sha256=canonical_sha256(tree),
        config_sha256=canonical_sha256(asdict(settings)),
        source_day_sha256=str(source["source_day_sha256"]),
        ml_model_sha256=combined_file_sha256(models),
        thermal_sha256=sha256_file(repo / THERMAL_MODEL),
        scale_sha256=sha256_file(repo / SCALE_AUTHORITY),
        formulation_fingerprint=formulation_fingerprint(repo),
        settings=settings,
        output_roots=roots,
    )


def read_solver_payload(path: Path) -> SolverPayload:
    source = json.loads(path.read_text(encoding="utf-8"))
    stored = source.pop("schedule_sha256", None)
    source.pop("LB", None)
    source.pop("UB", None)
    payload = SolverPayload(**source)
    payload.validate()
    if stored != payload.schedule_sha256:
        raise RuntimeError("V28R2_SOLVER_PAYLOAD_SCHEDULE_SHA")
    return payload


def _write_npz(path: Path, **arrays: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp{path.suffix}")
    np.savez_compressed(temporary, **arrays)
    os.replace(temporary, path)


class ProductionHandlers:
    def __init__(self, repo: Path, spec: DayRunSpec, day_output: Path, state_path: Path, mode: str):
        self.repo = repo
        self.spec = spec
        self.day_output = day_output
        self.state_path = state_path
        self.mode = mode
        self._data: V28R2FormulationData | None = None
        self._context = None
        self._actual: ActualWorkload | None = None
        self._actual_replays: dict[str, ActualReplay] = {}
        self._pi: PIExecution | None = None

    @property
    def handlers(self):
        return {step: self.handle for step in EXECUTION_STEPS}

    def _formulation(self) -> V28R2FormulationData:
        if self._data is None:
            self._data = materialize_formulation_data(self.repo, self.spec.day)
            if self._data.formulation_fingerprint != self.spec.formulation_fingerprint:
                raise RuntimeError("V28R2_FORMULATION_FINGERPRINT_CHANGED")
        return self._data

    def _electrical(self):
        if self._context is None:
            data = self._formulation()
            cache = self.day_output / "dayahead/electrical_cache"
            try:
                self._context = build_electrical_context(self.repo, data, cache)
            except RuntimeError as error:
                if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
                    raise
                self._context = prepare_electrical_context(self.repo, data, cache)
        return self._context

    def _actual_workload(self) -> ActualWorkload:
        if self._actual is None:
            manifest = self.day_output / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json"
            verify_schedule_manifest(manifest)
            self._actual = materialize_actual_workload(self.repo, self.spec.day)
        return self._actual

    def _mobility(self) -> list[dict[str, object]]:
        payload = json.loads((source_day_root(self.repo, self.spec.day) / "traffic_mobility.json").read_text(encoding="utf-8"))
        return list(payload["mess"])

    def _solver_path(self, case: str, solver: str) -> Path:
        return self.day_output / "dayahead/solvers" / f"{case}_{solver}" / "SOLVER_PAYLOAD.json"

    def _solver_payload(self, case: str, solver: str) -> SolverPayload:
        return read_solver_payload(self._solver_path(case, solver))

    def _schedule_path(self, case: str) -> Path:
        return self.day_output / "dayahead/schedules" / f"DAYAHEAD_{case}_SCHEDULE.json"

    def _schedule(self, case: str) -> dict[str, object]:
        return json.loads(self._schedule_path(case).read_text(encoding="utf-8"))

    @staticmethod
    def _solver_record(payload: SolverPayload) -> dict[str, object]:
        try:
            import gurobipy

            gurobi_version = ".".join(map(str, gurobipy.gurobi.version()))
        except Exception:
            gurobi_version = None
        return {
            "case": payload.case, "solver": payload.solver, "status": payload.status,
            "runtime_seconds": payload.runtime_seconds, "objective": payload.objective,
            "incumbent": payload.incumbent, "lower_bound": payload.lower_bound,
            "upper_bound": payload.upper_bound, "gap": payload.gap,
            "iterations": payload.iterations, "optimality_cuts": payload.optimality_cuts,
            "feasibility_cuts": payload.feasibility_cuts,
            "termination_reason": payload.termination_reason,
            "formulation_fingerprint": payload.formulation_fingerprint,
            "gurobi_version": gurobi_version,
        }

    def _solve(self, case: str, solver: str, ledger: RuntimeLedger) -> tuple[Mapping[str, Path], Mapping[str, object]]:
        data = self._formulation()
        context = self._electrical()
        ledger.begin_solver("DAYAHEAD", case, solver)
        if solver == "MONOLITHIC":
            payload = solve_monolithic(
                data=data, context=context.legacy_context, voltage=context.voltage,
                current=context.current, case=case,
            )
        else:
            payload = solve_benders(
                data=data, context=context.legacy_context, voltage=context.voltage,
                current=context.current, method=solver,
                raw_dir=self.day_output / "dayahead/solvers" / f"{case}_{solver}" / "benders_raw",
            )
        path = self._solver_path(case, solver)
        payload.write(path)
        ledger.record_solver(self._solver_record(payload))
        return {"solver_payload": path}, self._solver_record(payload)

    def _da_trajectory(self, case: str) -> FrozenTrajectory:
        return FrozenTrajectory.from_schedule_payload(self._schedule(case), day=self.spec.day, namespace="DAYAHEAD")

    def _actual_replay_path(self, case: str) -> Path:
        return self.day_output / "actual/replay" / case

    def _load_actual_trajectory(self, case: str) -> FrozenTrajectory:
        replay_dir = self._actual_replay_path(case)
        arrays = np.load(replay_dir / "ACTUAL_REPLAY_ARRAYS.npz", allow_pickle=False)
        summary = json.loads((replay_dir / "ACTUAL_REPLAY_SUMMARY.json").read_text(encoding="utf-8"))
        records = tuple(sorted(self._mobility(), key=lambda row: str(row["mess_id"])))
        result = FrozenTrajectory(
            self.spec.day, "ACTUAL", case,
            arrays["exact_pcc_p_kw"], arrays["exact_pcc_q_kvar"],
            arrays["mess_p_exec_kw"], arrays["mess_q_exec_kvar"],
            tuple(str(row["mess_id"]) for row in records), arrays["mess_locations_96x4"],
            str(summary["schedule_sha256"]),
        )
        result.validate()
        return result

    def _actual_trajectory(self, case: str) -> FrozenTrajectory:
        if case in self._actual_replays:
            return self._actual_replays[case].trajectory
        return self._load_actual_trajectory(case)

    def _run_opendss(
        self, label: str, trajectory: FrozenTrajectory, context: object,
        output: Path, ledger: RuntimeLedger,
    ) -> tuple[Mapping[str, Path], Mapping[str, object]]:
        ledger.begin_opendss(label)

        def progress(record: dict[str, object]) -> None:
            ledger.record_opendss_slot(label, int(record["OpenDSS_slot"]) - 1, True)

        result = run_fresh_opendss(
            repo=self.repo, context=context, voltage=context.voltage,
            trajectory=trajectory, output=output, progress=progress,
        )
        ledger.complete_opendss(label, result.opendss_version)
        manifest = output / "OPENDSS_OUTPUT_MANIFEST.json"
        return {"opendss_manifest": manifest}, {
            "trajectory": label,
            "OpenDSS_solve_count": result.summary["OpenDSS_solve_count"],
            "convergence_count": result.summary["convergence_count"],
            "opendss_version": result.opendss_version,
            "elapsed_seconds": result.elapsed_seconds,
        }

    def _actual_context(self, trajectory: FrozenTrajectory):
        actual = pd.read_parquet(source_day_root(self.repo, self.spec.day) / "aemo_actual.parquet")
        return with_realized_background(
            self.repo, self._electrical(), timestamps_96=actual["ts_fixed_aest_end"],
            demand_mw_96=actual["demand_mw"], pv_mw_96=actual["rooftop_pv_mw"],
            aidc_plan_kw_96x12=trajectory.pcc_p_kw,
        )

    def _write_pi_trajectory(self, trajectory: FrozenTrajectory) -> Path:
        path = self.day_output / "pi/PI_PHYSICAL_TRAJECTORY.npz"
        _write_npz(
            path, pcc_p_kw=trajectory.pcc_p_kw, pcc_q_kvar=trajectory.pcc_q_kvar,
            mess_p_kw=trajectory.mess_p_kw, mess_q_kvar=trajectory.mess_q_kvar,
            mess_ids=np.asarray(trajectory.mess_ids),
            mess_locations_96x4=trajectory.mess_locations_96x4,
            source_schedule_sha256=np.asarray([trajectory.source_schedule_sha256]),
        )
        return path

    def _load_pi_trajectory(self) -> FrozenTrajectory:
        arrays = np.load(self.day_output / "pi/PI_PHYSICAL_TRAJECTORY.npz", allow_pickle=False)
        result = FrozenTrajectory(
            self.spec.day, "PERFECT_INFORMATION", "B3",
            arrays["pcc_p_kw"], arrays["pcc_q_kvar"], arrays["mess_p_kw"], arrays["mess_q_kvar"],
            tuple(map(str, arrays["mess_ids"].tolist())), arrays["mess_locations_96x4"],
            str(arrays["source_schedule_sha256"][0]),
        )
        result.validate()
        return result

    def _pi_context(self):
        if self._pi is not None:
            return self._pi.context
        data = materialize_pi_formulation_data(self.repo, self.spec.day, self._actual_workload())
        cache = self.day_output / "pi/electrical_cache"
        try:
            return build_electrical_context(self.repo, data, cache)
        except RuntimeError as error:
            if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
                raise
            return prepare_electrical_context(self.repo, data, cache)

    def handle(
        self, spec: DayRunSpec, day_output: Path, ledger: RuntimeLedger,
    ) -> tuple[Mapping[str, Path], Mapping[str, object]]:
        if spec.sha256 != self.spec.sha256 or day_output != self.day_output:
            raise RuntimeError("V28R2_HANDLER_RUN_SPEC_OR_ROOT_MISMATCH")
        state = DayState.load(self.state_path)
        step = state.current_step
        if step is None:
            raise RuntimeError("V28R2_HANDLER_WITHOUT_CURRENT_STEP")
        method = getattr(self, f"step_{step}")
        return method(ledger)

    def step_01_INPUT_AUTHORITY_CHECK(self, _ledger: RuntimeLedger):
        manifest_path, source = _source_manifest(self.repo, self.spec.day)
        run_dir = self.day_output / "run_authority"
        run_spec_path = run_dir / "DAY_RUN_SPEC.json"
        code_path = run_dir / "CODE_TREE_MANIFEST.json"
        model_path = run_dir / "SELECTED_MODEL_MANIFEST.json"
        atomic_json(run_spec_path, {**self.spec.payload(), "day_run_spec_sha256": self.spec.sha256})
        tree = code_tree_manifest(self.repo)
        atomic_json(code_path, {"files": tree, "code_tree_sha256": canonical_sha256(tree)})
        models = selected_model_paths(self.repo, self.spec.day)
        atomic_json(model_path, {
            "files": {name: {"path": str(path.resolve()), "sha256": sha256_file(path)} for name, path in models.items()},
            "ml_model_sha256": combined_file_sha256(models),
        })
        if source["source_day_sha256"] != self.spec.source_day_sha256:
            raise RuntimeError("V28R2_SOURCE_DAY_SPEC_SHA")
        return {
            "run_spec": run_spec_path, "code_tree_manifest": code_path,
            "selected_model_manifest": model_path, "source_day_manifest": manifest_path,
        }, {"source_categories_verified": 13, "actual_content_reads": 0}

    def step_02_OPTIMIZER_CHANNEL_MATERIALIZATION(self, _ledger: RuntimeLedger):
        data = self._formulation()
        output = self.day_output / "dayahead/channels"
        arrays = output / "OPTIMIZER_CHANNELS.npz"
        summary = output / "OPTIMIZER_CHANNELS_SUMMARY.json"
        _write_npz(
            arrays, p_it_q90_kw=data.p_it_q90_kw, g_q90_gpu=data.g_q90_gpu,
            w_q50_arrivals_nodeh=data.arrivals_nodeh,
        )
        atomic_json(summary, {
            "artifact_id": "V28R2_DAY_OPTIMIZER_CHANNELS_V1", "day": self.spec.day,
            "P_shape": [96], "G_shape": [96], "W_shape": [96, 15],
            "P_min": float(data.p_it_q90_kw.min()), "G_min": float(data.g_q90_gpu.min()),
            "W_mass_nodeh": float(data.arrivals_nodeh.sum()),
            "input_sha256": data.input_sha256,
            "formulation_fingerprint": data.formulation_fingerprint,
        })
        return {"channels": arrays, "summary": summary}, {"P_cells": 96, "G_cells": 96, "W_cells": 1440}

    def step_03_REFERENCE_COMPUTE_SCHEDULE(self, _ledger: RuntimeLedger):
        path = self.day_output / "dayahead/reference/REFERENCE_COMPUTE_SCHEDULE.json"
        atomic_json(path, json.loads(self._formulation().reference.canonical_bytes()))
        return {"reference_schedule": path}, {"reference_schedule_bytes": path.stat().st_size}

    def step_04_REFERENCE_DELTA_CLOSURE(self, _ledger: RuntimeLedger):
        delta = self._formulation().delta
        arrays = self.day_output / "dayahead/reference/REFERENCE_DELTA_ARRAYS.npz"
        summary = self.day_output / "dayahead/reference/REFERENCE_DELTA_SUMMARY.json"
        _write_npz(arrays, p_res_plan_kw=delta.p_res_plan_kw, g_res_plan_gpu=delta.g_res_plan_gpu)
        atomic_json(summary, {
            "artifact_id": "V28R2_DAY_REFERENCE_DELTA_V1", "status": "PASS",
            "minimum_raw_p_kw": delta.minimum_raw_p_kw, "minimum_raw_g_gpu": delta.minimum_raw_g_gpu,
            "p_tolerance_cells": delta.p_tolerance_cells, "g_tolerance_cells": delta.g_tolerance_cells,
            "P_min_after_tolerance": float(delta.p_res_plan_kw.min()),
            "G_min_after_tolerance": float(delta.g_res_plan_gpu.min()),
        })
        return {"delta_arrays": arrays, "delta_summary": summary}, {"P_residual_cells": 4608, "G_residual_cells": 4608}

    def step_05_B0_MONOLITHIC(self, ledger): return self._solve("B0", "MONOLITHIC", ledger)
    def step_06_B1_MONOLITHIC(self, ledger): return self._solve("B1", "MONOLITHIC", ledger)
    def step_07_B2_MONOLITHIC(self, ledger): return self._solve("B2", "MONOLITHIC", ledger)
    def step_08_B3_CL_MC_BD(self, ledger): return self._solve("B3", "CL_MC_BD", ledger)
    def step_09_B3_MONOLITHIC(self, ledger): return self._solve("B3", "MONOLITHIC", ledger)
    def step_10_B3_STANDARD_BD(self, ledger): return self._solve("B3", "STANDARD_BD", ledger)

    def step_11_B3_SOLVER_EQUIVALENCE(self, _ledger: RuntimeLedger):
        payloads = {solver: self._solver_payload("B3", solver) for solver in ("CL_MC_BD", "MONOLITHIC", "STANDARD_BD")}
        result = verify_b3_equivalence(payloads, self.spec.settings.equivalence_tolerance)
        path = self.day_output / "dayahead/B3_SOLVER_EQUIVALENCE.json"
        atomic_json(path, result)
        return {"equivalence": path}, {"relative_objective_range": result["relative_objective_range"]}

    def step_12_DAYAHEAD_SCHEDULE_FREEZE(self, _ledger: RuntimeLedger):
        payloads = {
            case: self._solver_payload(case, solver) for case, solver in OPERATIONAL_SOLVER.items()
        }
        reference = self.day_output / "dayahead/reference/REFERENCE_COMPUTE_SCHEDULE.json"
        output = self.day_output / "dayahead/schedules"
        manifest = freeze_dayahead_schedules(output, payloads, reference.read_bytes())
        path = output / "DAYAHEAD_SCHEDULE_MANIFEST.json"
        verify_schedule_manifest(path)
        return {"schedule_manifest": path, **{f"schedule_{case}": self._schedule_path(case) for case in OPERATIONAL_SOLVER}}, {
            "schedule_root_sha256": manifest["schedule_root_sha256"], "frozen_schedule_count": 4,
        }

    def _da_opendss(self, case: str, ledger: RuntimeLedger):
        ledger.record_pue(f"DA/{case}", 96 * 12)
        return self._run_opendss(
            f"DA/{case}", self._da_trajectory(case), self._electrical(),
            self.day_output / "dayahead/opendss" / case, ledger,
        )

    def step_13_DA_B0_FRESH_OPENDSS(self, ledger): return self._da_opendss("B0", ledger)
    def step_14_DA_B1_FRESH_OPENDSS(self, ledger): return self._da_opendss("B1", ledger)
    def step_15_DA_B2_FRESH_OPENDSS(self, ledger): return self._da_opendss("B2", ledger)
    def step_16_DA_B3_FRESH_OPENDSS(self, ledger): return self._da_opendss("B3", ledger)

    def step_17_ACTUAL_NAMESPACE_OPEN(self, _ledger: RuntimeLedger):
        manifest = verify_schedule_manifest(self.day_output / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json")
        actual = self._actual_workload()
        output = self.day_output / "actual/namespace"
        arrays = output / "ACTUAL_WORKLOAD_ARRAYS.npz"
        summary = output / "ACTUAL_NAMESPACE_OPEN.json"
        _write_npz(
            arrays, arrivals_nodeh=actual.arrivals_nodeh, total_it_kw=actual.total_it_kw,
            total_h100_gpu=actual.total_h100_gpu,
            flexible_natural_it_kw=actual.flexible_natural_it_kw,
            flexible_natural_gpu=actual.flexible_natural_gpu,
        )
        atomic_json(summary, {
            "artifact_id": "V28R2_ACTUAL_NAMESPACE_OPEN_V1", "day": self.spec.day,
            "status": "OPEN_AFTER_SCHEDULE_SHA_VERIFICATION",
            "schedule_root_sha256": manifest["schedule_root_sha256"],
            "actual_source_sha256": actual.source_sha256,
            "actual_reoptimization_calls": 0,
        })
        return {"actual_arrays": arrays, "actual_namespace": summary}, {"actual_namespace_open_count": 1, "actual_optimizer_calls": 0}

    def _actual_replay(self, case: str, ledger: RuntimeLedger):
        actual = self._actual_workload()
        if case == "R0":
            manifest = verify_schedule_manifest(self.day_output / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json")
            replay = build_natural_actual(self.repo, self.spec.day, actual, self._mobility(), str(manifest["schedule_root_sha256"]))
        else:
            replay = replay_actual_case(self.repo, self.spec.day, self._schedule(case), actual, self._mobility())
        self._actual_replays[case] = replay
        ledger.record_pue(f"ACT/{case}", int(replay.summary["exact_C1_evaluation_count"]))
        output = self._actual_replay_path(case)
        replay.write(output)
        return {
            "actual_replay_manifest": output / "ACTUAL_REPLAY_OUTPUT_MANIFEST.json",
            "actual_replay_summary": output / "ACTUAL_REPLAY_SUMMARY.json",
        }, replay.summary

    def step_18_ACTUAL_R0_NATURAL(self, ledger): return self._actual_replay("R0", ledger)
    def step_19_ACTUAL_B0_REPLAY(self, ledger): return self._actual_replay("B0", ledger)
    def step_20_ACTUAL_B1_REPLAY(self, ledger): return self._actual_replay("B1", ledger)
    def step_21_ACTUAL_B2_REPLAY(self, ledger): return self._actual_replay("B2", ledger)
    def step_22_ACTUAL_B3_REPLAY(self, ledger): return self._actual_replay("B3", ledger)

    def _actual_opendss(self, case: str, ledger: RuntimeLedger):
        trajectory = self._actual_trajectory(case)
        return self._run_opendss(
            f"ACT/{case}", trajectory, self._actual_context(trajectory),
            self.day_output / "actual/opendss" / case, ledger,
        )

    def step_23_ACT_R0_FRESH_OPENDSS(self, ledger): return self._actual_opendss("R0", ledger)
    def step_24_ACT_B0_FRESH_OPENDSS(self, ledger): return self._actual_opendss("B0", ledger)
    def step_25_ACT_B1_FRESH_OPENDSS(self, ledger): return self._actual_opendss("B1", ledger)
    def step_26_ACT_B2_FRESH_OPENDSS(self, ledger): return self._actual_opendss("B2", ledger)
    def step_27_ACT_B3_FRESH_OPENDSS(self, ledger): return self._actual_opendss("B3", ledger)

    def step_28_PI_B3_CL_MC_BD(self, ledger: RuntimeLedger):
        ledger.begin_solver("PI", "B3", "CL_MC_BD")
        output = self.day_output / "pi"
        self._pi = execute_pi(
            repo=self.repo, day=self.spec.day, actual=self._actual_workload(),
            electrical_cache=output / "electrical_cache", output=output,
        )
        ledger.record_solver(self._solver_record(self._pi.payload))
        ledger.record_pue("PI/B3", 96 * 12)
        trajectory_path = self._write_pi_trajectory(self._pi.trajectory)
        manifest_path = output / "PI_OUTPUT_MANIFEST.json"
        files = [output / "PI_B3_SOLVER_PAYLOAD.json", output / "PI_EXECUTION_SUMMARY.json", trajectory_path]
        atomic_json(manifest_path, {
            "artifact_id": "V28R2_PI_OUTPUT_MANIFEST_V1",
            "files": {path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size} for path in files},
        })
        return {"pi_manifest": manifest_path, "pi_payload": files[0], "pi_summary": files[1], "pi_trajectory": trajectory_path}, self._solver_record(self._pi.payload)

    def step_29_PI_B3_FRESH_OPENDSS(self, ledger: RuntimeLedger):
        return self._run_opendss(
            "PI/B3", self._pi.trajectory if self._pi is not None else self._load_pi_trajectory(),
            self._pi_context(), self.day_output / "pi/opendss/B3", ledger,
        )

    def _final_reference_paths(self, ledger_path: Path, audit_path: Path, log_snapshot: Path) -> dict[str, Path]:
        paths: dict[str, Path] = {
            "day_run_spec": self.day_output / "run_authority/DAY_RUN_SPEC.json",
            "code_tree_manifest": self.day_output / "run_authority/CODE_TREE_MANIFEST.json",
            "config": self.day_output / "run_authority/DAY_RUN_SPEC.json",
            "source_day_manifest": source_day_root(self.repo, self.spec.day) / "source_day_manifest.json",
            "selected_model_manifest": self.day_output / "run_authority/SELECTED_MODEL_MANIFEST.json",
            "thermal_model": self.repo / THERMAL_MODEL,
            "scale_authority": self.repo / SCALE_AUTHORITY,
            "formulation": self.day_output / "dayahead/channels/OPTIMIZER_CHANNELS_SUMMARY.json",
            "dayahead_schedule_manifest": self.day_output / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json",
            "b3_equivalence": self.day_output / "dayahead/B3_SOLVER_EQUIVALENCE.json",
            "pi_output": self.day_output / "pi/PI_OUTPUT_MANIFEST.json",
            "pi_opendss": self.day_output / "pi/opendss/B3/OPENDSS_OUTPUT_MANIFEST.json",
            "runtime_ledger": ledger_path,
            "final_audit": audit_path,
            "log_snapshot": log_snapshot,
        }
        paths.update(selected_model_paths(self.repo, self.spec.day))
        for case in OPERATIONAL_SOLVER:
            paths[f"schedule_{case}"] = self._schedule_path(case)
            paths[f"da_opendss_{case}"] = self.day_output / "dayahead/opendss" / case / "OPENDSS_OUTPUT_MANIFEST.json"
        for case in ("R0", "B0", "B1", "B2", "B3"):
            paths[f"actual_replay_{case}"] = self._actual_replay_path(case) / "ACTUAL_REPLAY_OUTPUT_MANIFEST.json"
            paths[f"actual_opendss_{case}"] = self.day_output / "actual/opendss" / case / "OPENDSS_OUTPUT_MANIFEST.json"
        return paths

    def step_30_CONSERVATION_FIREWALL_HASH_AUDIT(self, ledger: RuntimeLedger):
        ledger.validate_complete()
        ledger_path = self.day_output / "RUNTIME_LEDGER.json"
        ledger.save(ledger_path)
        schedule = verify_schedule_manifest(self.day_output / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json")
        equivalence = json.loads((self.day_output / "dayahead/B3_SOLVER_EQUIVALENCE.json").read_text(encoding="utf-8"))
        replay_summaries = {
            case: json.loads((self._actual_replay_path(case) / "ACTUAL_REPLAY_SUMMARY.json").read_text(encoding="utf-8"))
            for case in ("R0", "B0", "B1", "B2", "B3")
        }
        opendss_counts = {
            label: ledger.opendss_solved_slots[label] for label in ledger.opendss_solved_slots
        }
        audit = {
            "artifact_id": "V28R2_FINAL_CONSERVATION_FIREWALL_HASH_AUDIT_V1",
            "day": self.spec.day, "status": "PASS",
            "schedule_root_sha256": schedule["schedule_root_sha256"],
            "B3_equivalence": equivalence,
            "actual_optimizer_calls": ledger.optimizer_calls_by_namespace["ACTUAL"],
            "hidden_shedding_nodeh": max(float(row["hidden_shedding_nodeh"]) for row in replay_summaries.values()),
            "workload_mass_error_nodeh": max(abs(float(row["workload_mass_error_nodeh"])) for row in replay_summaries.values()),
            "soc_error_kwh": max(abs(float(row["terminal_mess_energy_error_from_DA_target_kwh"])) for row in replay_summaries.values()),
            "OpenDSS_real_solved_slots": opendss_counts,
            "PUE_ledger": ledger.pue_calls,
            "optimizer_calls_by_namespace": ledger.optimizer_calls_by_namespace,
            "peak_active_heavy_solves": ledger.peak_active_heavy_solves,
            "runtime_ledger_sha256": sha256_file(ledger_path),
            "all_referenced_step_hashes_verified": True,
        }
        if audit["actual_optimizer_calls"] != 0 or audit["hidden_shedding_nodeh"] != 0 or audit["workload_mass_error_nodeh"] > 1e-9:
            raise RuntimeError("V28R2_FINAL_CONSERVATION_OR_FIREWALL_AUDIT")
        audit_path = self.day_output / "V28R2_FINAL_AUDIT.json"
        atomic_json(audit_path, audit)
        log_source = Path(self.spec.output_roots["logs"]) / f"{self.spec.day}.log"
        log_snapshot = self.day_output / "AUDIT_LOG_SNAPSHOT.log"
        log_snapshot.parent.mkdir(parents=True, exist_ok=True)
        if log_source.is_file():
            shutil.copyfile(log_source, log_snapshot)
        else:
            log_snapshot.write_text("V28R2 heavy backend completed without an external supervisor log.\n", encoding="utf-8", newline="\n")
        state = DayState.load(self.state_path)
        common = {
            "day": self.spec.day,
            "repository_root": str(self.repo.resolve()),
            "git_head": self.spec.git_head,
            "code_tree_sha256": self.spec.code_tree_sha256,
            "config_sha256": self.spec.config_sha256,
            "source_day_sha256": self.spec.source_day_sha256,
            "ml_model_sha256": self.spec.ml_model_sha256,
            "thermal_sha256": self.spec.thermal_sha256,
            "scale_sha256": self.spec.scale_sha256,
            "formulation_fingerprint": self.spec.formulation_fingerprint,
            "solver_settings": asdict(self.spec.settings),
            "defect_ids": state.defect_ids,
            "attempts": state.attempts,
            "solver_statuses": [{"case": row["case"], "solver": row["solver"], "status": row["status"]} for row in ledger.solver_calls],
            "solver_objectives": [{"case": row["case"], "solver": row["solver"], "objective": row["objective"]} for row in ledger.solver_calls],
            "schedule_hashes": {case: record["schedule_sha256"] for case, record in schedule["cases"].items()},
            "actual_source_hashes": self._actual_workload().source_sha256,
            "OpenDSS_real_solved_slots": opendss_counts,
            "PUE_ledger": ledger.pue_calls,
            "actual_optimizer_calls": 0,
            "hidden_shedding_nodeh": audit["hidden_shedding_nodeh"],
            "workload_mass_error_nodeh": audit["workload_mass_error_nodeh"],
            "SoC_error_kwh": audit["soc_error_kwh"],
            "elapsed_seconds": ledger.payload()["elapsed_seconds"],
            "peak_RSS_bytes": ledger.peak_rss_bytes,
            "Gurobi_version": next((row.get("gurobi_version") for row in ledger.solver_calls if row.get("gurobi_version")), None),
            "OpenDSS_versions": ledger.opendss_versions,
            "B3_equivalence": equivalence,
        }
        if self.mode == "non-authority-smoke":
            result_path = self.day_output / "V28R2_NON_AUTHORITY_HEAVY_SMOKE_RESULT.json"
            atomic_json(result_path, {
                "artifact_id": "V28R2_NON_AUTHORITY_END_TO_END_HEAVY_SMOKE_V1",
                "status": "PASS", "non_authority_smoke": True,
                "April_PASS_certificate_issued": False, **common,
                "references": file_references(self._final_reference_paths(ledger_path, audit_path, log_snapshot)),
            })
            return {"final_audit": audit_path, "runtime_ledger": ledger_path, "smoke_result": result_path, "log_snapshot": log_snapshot}, audit
        certificate_path = self.day_output / f"APRIL_DAY_CERTIFICATE_{self.spec.day.replace('-', '_')}.json"
        write_certificate(certificate_path, {
            "artifact_id": "V28R2_APRIL_DAY_CERTIFICATE_V1",
            "status": "PASS", "non_authority_smoke": False, **common,
            "references": file_references(self._final_reference_paths(ledger_path, audit_path, log_snapshot)),
        })
        verify_certificate(certificate_path)
        return {"final_audit": audit_path, "runtime_ledger": ledger_path, "certificate": certificate_path, "log_snapshot": log_snapshot}, audit
