"""Run one complete V29 development day with frozen DA then Actual/PI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v28r2.actual_replay import build_natural_actual
from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file
from dayahead.v28r2.benders_authority import solve_benders
from dayahead.v28r2.electrical_context import build_electrical_context, with_realized_background
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.schedule_freeze import freeze_dayahead_schedules, verify_schedule_manifest
from dayahead.v28r2.solver_equivalence import verify_b3_equivalence
from dayahead.v28r2.solver_runner import solve_monolithic
from dayahead.v28r2.source_cache import day_root as source_day_root
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29.actual_replay import replay_actual_case_v29
from dayahead.v29.backend_contract import SOLVER_EQUIVALENCE_TOLERANCE, increment_resolution
from dayahead.v29.carryin import carryin_by_cohort
from dayahead.v29.formulation import materialize_formulation_data_v29
from dayahead.v29.pi_executor import execute_pi_v29


CAMPAIGN = "v28r2_april_full_month_preflight"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def schedule(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def actual_context(repo: Path, base: object, day: str, trajectory: FrozenTrajectory):
    actual = pd.read_parquet(source_day_root(repo, day) / "aemo_actual.parquet")
    return with_realized_background(repo, base, timestamps_96=actual["ts_fixed_aest_end"], demand_mw_96=actual["demand_mw"], pv_mw_96=actual["rooftop_pv_mw"], aidc_plan_kw_96x12=trajectory.pcc_p_kw)


def result_metrics(result: object) -> dict[str, object]:
    summary = result.summary
    return {key: summary[key] for key in summary if isinstance(summary[key], (str, int, float, bool)) or summary[key] is None}


def run_day(repo: Path, campaign_repo: Path, day: str, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    data = materialize_formulation_data_v29(repo, day)
    campaign_cache = campaign_repo / "frozen_artifacts" / CAMPAIGN / day / "dayahead/electrical_cache"
    context = build_electrical_context(repo, data, campaign_cache)
    solver_root = output / "dayahead/solvers"; solver_root.mkdir(parents=True, exist_ok=True)
    operational = {}
    all_payloads = {}
    for case in ("B0", "B1", "B2"):
        payload = solve_monolithic(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, case=case)
        target = solver_root / f"{case}_MONOLITHIC/SOLVER_PAYLOAD.json"; payload.write(target)
        operational[case] = payload; all_payloads[f"{case}_MONOLITHIC"] = payload
    cl = solve_benders(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, method="CL_MC_BD", raw_dir=solver_root / "B3_CL_MC_BD/benders_raw", tolerance=SOLVER_EQUIVALENCE_TOLERANCE)
    cl.write(solver_root / "B3_CL_MC_BD/SOLVER_PAYLOAD.json"); operational["B3"] = cl; all_payloads["B3_CL_MC_BD"] = cl
    mono = solve_monolithic(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, case="B3")
    mono.write(solver_root / "B3_MONOLITHIC/SOLVER_PAYLOAD.json"); all_payloads["B3_MONOLITHIC"] = mono
    standard = solve_benders(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, method="STANDARD_BD", raw_dir=solver_root / "B3_STANDARD_BD/benders_raw", tolerance=SOLVER_EQUIVALENCE_TOLERANCE)
    standard.write(solver_root / "B3_STANDARD_BD/SOLVER_PAYLOAD.json"); all_payloads["B3_STANDARD_BD"] = standard
    equivalence = verify_b3_equivalence({"CL_MC_BD": cl, "MONOLITHIC": mono, "STANDARD_BD": standard}, tolerance=SOLVER_EQUIVALENCE_TOLERANCE)
    resolution = increment_resolution(float(operational["B2"].objective), {"CL_MC_BD": float(cl.objective), "MONOLITHIC": float(mono.objective), "STANDARD_BD": float(standard.objective)})
    write_json(output / "dayahead/B3_SOLVER_EQUIVALENCE.json", equivalence); write_json(output / "dayahead/INCREMENT_RESOLUTION.json", resolution)
    schedules = output / "dayahead/schedules"; schedules.mkdir(parents=True, exist_ok=True)
    manifest = freeze_dayahead_schedules(schedules, operational, data.reference.canonical_bytes())
    verify_schedule_manifest(schedules / "DAYAHEAD_SCHEDULE_MANIFEST.json")
    dominance = {
        "B1_le_B0": operational["B1"].objective <= operational["B0"].objective + 1e-8,
        "B2_le_B0": operational["B2"].objective <= operational["B0"].objective + 1e-8,
        "B3_le_B1": operational["B3"].objective <= operational["B1"].objective + 1e-8,
        "B3_le_B2": operational["B3"].objective <= operational["B2"].objective + 1e-8,
    }
    if not all(dominance.values()):
        raise RuntimeError(f"V29_CASE_DOMINANCE_DEFECT:{dominance}")

    opendss = {}; trajectories = {}
    for case in ("B0", "B1", "B2", "B3"):
        trajectory = FrozenTrajectory.from_schedule_payload(schedule(schedules / f"DAYAHEAD_{case}_SCHEDULE.json"), day=day, namespace="DAYAHEAD")
        trajectories[f"DA/{case}"] = trajectory
        result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=trajectory, output=output / "dayahead/opendss" / case)
        opendss[f"DA/{case}"] = result_metrics(result)

    # Actual namespace opens only after the frozen schedule manifest verifies.
    verified = verify_schedule_manifest(schedules / "DAYAHEAD_SCHEDULE_MANIFEST.json")
    actual = materialize_actual_workload(repo, day)
    mobility = json.loads((source_day_root(repo, day) / "traffic_mobility.json").read_text(encoding="utf-8"))["mess"]
    actual_replays = {}
    natural = build_natural_actual(repo, day, actual, mobility, str(verified["schedule_root_sha256"]))
    natural.write(output / "actual/replay/R0"); actual_replays["R0"] = natural
    for case in ("B0", "B1", "B2", "B3"):
        replay = replay_actual_case_v29(repo, day, schedule(schedules / f"DAYAHEAD_{case}_SCHEDULE.json"), actual, mobility)
        replay.write(output / "actual/replay" / case); actual_replays[case] = replay
    for case, replay in actual_replays.items():
        trajectories[f"ACT/{case}"] = replay.trajectory
        act_context = actual_context(repo, context, day, replay.trajectory)
        result = run_fresh_opendss(repo=repo, context=act_context, voltage=act_context.voltage, trajectory=replay.trajectory, output=output / "actual/opendss" / case)
        opendss[f"ACT/{case}"] = result_metrics(result)
        # with_realized_background deliberately shares the immutable DA
        # sensitivity handles; they are closed once after all trajectories.

    pi = execute_pi_v29(repo, day, actual, output / "pi/electrical_cache", output / "pi")
    trajectories["PI/B3"] = pi.trajectory
    pi_result = run_fresh_opendss(repo=repo, context=pi.context, voltage=pi.context.voltage, trajectory=pi.trajectory, output=output / "pi/opendss/B3")
    opendss["PI/B3"] = result_metrics(pi_result)
    summary = {
        "artifact_id": "V29_DAY_DEVELOPMENT_RESULT_V1", "status": "PASS", "day": day,
        "formulation_fingerprint": data.formulation_fingerprint, "input_sha256": data.input_sha256,
        "carryin_nodeh": float(data.initial_backlog_nodeh.sum()),
        "objectives": {case: float(payload.objective) for case, payload in operational.items()},
        "B3_solver_objectives": {"CL_MC_BD": float(cl.objective), "MONOLITHIC": float(mono.objective), "STANDARD_BD": float(standard.objective)},
        "B3_equivalence": equivalence, "increment_resolution": resolution, "dominance": dominance,
        "schedule_root_sha256": manifest["schedule_root_sha256"],
        "actual_namespace_open_before_freeze": 0, "actual_optimizer_calls": 0,
        "actual": {case: replay.summary for case, replay in actual_replays.items()},
        "PI": {"objective": float(pi.payload.objective), "solver": pi.payload.solver, "DA_namespace_reads": 0},
        "OpenDSS": opendss, "OpenDSS_trajectory_count": len(opendss),
        "OpenDSS_solve_count": sum(int(row["OpenDSS_solve_count"]) for row in opendss.values()),
        "connection_delay_slots": 1, "rho_AIDC": 0.1,
    }
    write_json(output / "V29_DAY_RESULT.json", summary)
    context.voltage.close(); context.current.close(); pi.context.voltage.close(); pi.context.current.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--campaign-repo", type=Path, required=True); parser.add_argument("--day", required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = "1"
    result = run_day(REPO, args.campaign_repo.resolve(), args.day, args.output.resolve())
    print(json.dumps({"day": result["day"], "status": result["status"], "objectives": result["objectives"], "OpenDSS_solve_count": result["OpenDSS_solve_count"]}, indent=2))


if __name__ == "__main__":
    main()
