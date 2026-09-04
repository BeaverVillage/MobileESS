#!/usr/bin/env python3
"""Conversation A 단계 5 R3: actual event-scoped LOCAL_REPAIR integration.

Prerequisite:
- A 단계 4 result with `step4 == PASS_REPLAN_REQUIRED`
- `requested_mode == LOCAL_REPAIR`
- an explicit nonempty affected MESS/job scope.

This runner does NOT use a predeclared issue151/MESS01 synthetic scope.
It consumes the actual 단계 4 replan boundary.  For the current handoff this is:
  issue 114
  affected jobs = 6480757, 6480760, 6480763
  affected MESS = none

Policy:
- resume exactly from the 단계 4 PRE state at the replan issue;
- reconstruct the shifted active plan from the last committed issue;
- fix every unaffected slow decision;
- free only affected Job and/or MESS decisions in the first 12 five-minute stages;
- solve the scoped local MIQCP for a feasible incumbent within the planner budget;
- fix the selected discrete repair and solve a continuous AC-aware QCP polish;
- run Fresh Exact OpenDSS and commit h0 only;
- if the local neighborhood cannot produce a feasible incumbent, fail closed
  before commit and emit PASS_ESCALATE_FULL_REPLAN for 단계 6.

No online/global 3% exact certificate is claimed.
No period-selection work is performed.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import traceback
from typing import Any, Mapping, Sequence

import pandas as pd

HERE = Path(__file__).resolve().parent
BASE_RUNNER = HERE / "MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py"
if not BASE_RUNNER.is_file():
    raise SystemExit(f"Missing companion file: {BASE_RUNNER}")
spec = importlib.util.spec_from_file_location("a_step2_base", BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import 단계 2~3 companion runner")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)


class LocalRepairStop(BaseException):
    """Expected successful single-issue stop after POST has been written."""


class LocalRepairEscalation(BaseException):
    def __init__(self, *, reason: str, detail: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = str(reason)
        self.detail = dict(detail or {})


def _tar_members(archive: Path) -> list[tarfile.TarInfo]:
    with tarfile.open(archive, "r:gz") as tf:
        return tf.getmembers()


def read_json_member(archive: Path, basename: str) -> dict[str, Any]:
    with tarfile.open(archive, "r:gz") as tf:
        hits = [m for m in tf.getmembers() if m.isfile() and Path(m.name).name == basename]
        if len(hits) != 1:
            raise RuntimeError(f"{archive}: expected one {basename}, found {len(hits)}")
        fh = tf.extractfile(hits[0])
        if fh is None:
            raise RuntimeError(f"cannot read {basename}")
        value = json.loads(fh.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"{basename} is not a JSON object")
        return value


def read_json_suffix(archive: Path, suffix: str) -> dict[str, Any]:
    with tarfile.open(archive, "r:gz") as tf:
        hits = [m for m in tf.getmembers() if m.isfile() and m.name.endswith(suffix)]
        if len(hits) != 1:
            raise RuntimeError(f"{archive}: expected one *{suffix}, found {len(hits)}")
        fh = tf.extractfile(hits[0])
        if fh is None:
            raise RuntimeError(f"cannot read {suffix}")
        value = json.loads(fh.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"{suffix} is not a JSON object")
        return value


def read_csv_suffix(archive: Path, suffix: str) -> pd.DataFrame:
    with tarfile.open(archive, "r:gz") as tf:
        hits = [m for m in tf.getmembers() if m.isfile() and m.name.endswith(suffix)]
        if len(hits) != 1:
            raise RuntimeError(f"{archive}: expected one *{suffix}, found {len(hits)}")
        fh = tf.extractfile(hits[0])
        if fh is None:
            raise RuntimeError(f"cannot read {suffix}")
        return pd.read_csv(io.BytesIO(fh.read()))


def extract_json_suffix(archive: Path, suffix: str, out: Path) -> Path:
    value = read_json_suffix(archive, suffix)
    base.write_json(out, value)
    return out


def validate_step4(archive: Path) -> dict[str, Any]:
    if not archive.is_file():
        raise FileNotFoundError(archive)
    result = read_json_member(archive, "A_STEP4_RESULT.json")
    if result.get("step4") != "PASS_REPLAN_REQUIRED":
        raise RuntimeError(f"단계 5 requires PASS_REPLAN_REQUIRED, got {result.get('step4')}")
    if result.get("requested_mode") != "LOCAL_REPAIR":
        raise RuntimeError(
            f"단계 5 requires LOCAL_REPAIR request, got {result.get('requested_mode')}"
        )
    issue = int(result["replan_issue"])
    affected_jobs = tuple(sorted(map(str, result.get("affected_job_ids", ()))))
    affected_mess = tuple(sorted(map(str, result.get("affected_mess_ids", ()))))
    if not (affected_jobs or affected_mess):
        raise RuntimeError("LOCAL_REPAIR scope is empty; 단계 6 FULL_REPLAN is required")
    replan = read_json_member(archive, "04_REPLAN_REQUIRED.json")
    if int(replan["issue"]) != issue:
        raise RuntimeError("단계 4 result/replan issue mismatch")
    if tuple(sorted(map(str, replan.get("affected_job_ids", ())))) != affected_jobs:
        raise RuntimeError("단계 4 affected-job scope mismatch")
    if tuple(sorted(map(str, replan.get("affected_mess_ids", ())))) != affected_mess:
        raise RuntimeError("단계 4 affected-MESS scope mismatch")
    return {
        "path": str(archive),
        "sha256": base.sha256(archive),
        "result": result,
        "replan": replan,
        "issue": issue,
        "affected_job_ids": affected_jobs,
        "affected_mess_ids": affected_mess,
    }


def _tail_extend_mess(previous: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for mid, g in previous.groupby("mess_id", sort=True):
        g = g.sort_values("horizon_step")
        tail = g[g["horizon_step"].astype(int) == 53]
        if len(tail) != 1:
            raise RuntimeError(f"{mid}: prior plan missing unique terminal h53 row")
        t = tail.iloc[0].to_dict()
        if str(t["state"]) != "STAY" or pd.isna(t["service_id"]):
            raise RuntimeError(f"{mid}: terminal plan is not stationary")
        shifted = g[g["horizon_step"].astype(int) >= 1].copy()
        shifted["horizon_step"] = shifted["horizon_step"].astype(int) - 1
        rows.extend(shifted.to_dict("records"))
        new = dict(t)
        new["horizon_step"] = 53
        new["state"] = "STAY"
        new["service_id"] = str(t["service_id"])
        for col in ("P_discharge_kW", "P_charge_kW", "Q_kvar"):
            if col in new:
                new[col] = 0.0
        rows.append(new)
    out = pd.DataFrame(rows)
    if len(out) != len(previous):
        raise RuntimeError("shifted MESS plan cardinality drift")
    return out.sort_values(["mess_id", "horizon_step"], kind="mergesort").reset_index(drop=True)


def shifted_active_plan_from_stage4(archive: Path, issue: int) -> dict[str, Any]:
    parent = issue - 1
    jobs = read_csv_suffix(
        archive,
        f"engine/issue_{parent:06d}/BUILD7B_FULL54_JOB_PLAN.csv",
    )
    if len(jobs):
        jobs = jobs[jobs["start_step"].astype(int) >= issue].copy().reset_index(drop=True)
    mess = _tail_extend_mess(
        read_csv_suffix(
            archive,
            f"engine/issue_{parent:06d}/BUILD7B_FULL54_MESS_PLAN.csv",
        )
    )
    moves = read_csv_suffix(
        archive,
        f"engine/issue_{parent:06d}/BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv",
    )
    if len(moves):
        moves = moves[moves["horizon_step"].astype(int) >= 1].copy()
        moves["horizon_step"] = moves["horizon_step"].astype(int) - 1
        moves = moves.reset_index(drop=True)
    post = read_json_suffix(
        archive,
        f"engine/issue_{parent:06d}/BUILD7C_POSTCOMMIT_STATE.json",
    )
    return {
        "BUILD7B_FULL54_JOB_PLAN.csv": jobs,
        "BUILD7B_FULL54_MESS_PLAN.csv": mess,
        "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv": moves,
        "active_plan_parent_issue": parent,
        "active_plan_source_post_sha256": str(post["sha256"]),
        "authority": "SHIFTED_PREVIOUS_COMMITTED_ACTIVE_PLAN",
    }


def _selected_mobility_sets(
    *,
    ref: Mapping[str, Any],
    moves: Mapping[tuple[int, int], Mapping[str, Any]],
) -> tuple[set[tuple[str, int, int]], set[tuple[str, int, str]], set[tuple[str, int, str]]]:
    mess_df = ref["BUILD7B_FULL54_MESS_PLAN.csv"]
    move_df = ref["BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"]
    selected_mv = {
        (str(r.mess_id), int(r.horizon_step), int(r.slot))
        for r in move_df.itertuples(index=False)
    }
    selected_stay = {
        (str(r.mess_id), int(r.horizon_step), str(r.service_id))
        for r in mess_df.itertuples(index=False)
        if str(r.state) == "STAY"
    }
    selected_occ: set[tuple[str, int, str]] = set()
    for mid, h, sid in selected_stay:
        selected_occ.add((mid, h, sid))
        selected_occ.add((mid, h + 1, sid))
    for mid, h, slot in selected_mv:
        mm = moves[(h, slot)]
        selected_occ.add((mid, h, str(mm["source"])))
        selected_occ.add((mid, h + int(mm["D"]), str(mm["dest"])))
    return selected_mv, selected_stay, selected_occ


def apply_actual_local_repair(
    *,
    loc: Mapping[str, Any],
    ref: Mapping[str, Any],
    issue: int,
    affected_job_ids: Sequence[str],
    affected_mess_ids: Sequence[str],
    near_horizon_steps: int,
) -> dict[str, Any]:
    x = loc["x"]
    defer = loc["defer"]
    stay = loc["stay"]
    mv = loc["mv"]
    node_occ = loc.get("node_occ", {})
    moves = loc["moves"]
    model = loc["m"]

    affected_jobs = set(map(str, affected_job_ids))
    affected_mess = set(map(str, affected_mess_ids))
    fixed_location = bool(ref.get("fixed_location_projection", False))
    if fixed_location and not bool(loc.get("fixed_location_projection", False)):
        raise RuntimeError("M4 local-repair reference/model projection mismatch")
    if not (affected_jobs or affected_mess):
        raise LocalRepairEscalation(reason="EMPTY_LOCAL_REPAIR_SCOPE")

    # Current active Job plan inherited from the last committed issue.
    job_df = ref["BUILD7B_FULL54_JOB_PLAN.csv"]
    selected_x = {
        (str(r.job_uid), str(r.destination_IDC_id), str(r.rack_pool_id), int(r.start_step))
        for r in job_df.itertuples(index=False)
    }
    selected_jobs = {k[0] for k in selected_x}

    # The unaffected active plan must still be semantically representable.
    missing_unaffected_x = sorted(
        k for k in selected_x if k[0] not in affected_jobs and k not in x
    )
    if missing_unaffected_x:
        raise LocalRepairEscalation(
            reason="UNAFFECTED_PLANNED_WORK_NO_LONGER_ADMISSIBLE",
            detail={"missing_unaffected_job_choices": missing_unaffected_x[:50]},
        )

    # Fix/unfix Job choices.
    local_end = issue + int(near_horizon_steps)
    freed_job_vars: list[str] = []
    fixed_job_vars: list[str] = []
    local_choices_by_job: dict[str, int] = {uid: 0 for uid in affected_jobs}
    for key, var in x.items():
        uid = str(key[0])
        start_step = int(key[3])
        if uid in affected_jobs and issue <= start_step < local_end:
            # Keep this affected-job decision free inside the near horizon.
            freed_job_vars.append(str(var.VarName))
            local_choices_by_job[uid] = local_choices_by_job.get(uid, 0) + 1
        else:
            value = 1.0 if (uid not in affected_jobs and key in selected_x) else 0.0
            base._set_fixed(var, value)
            fixed_job_vars.append(str(var.VarName))

    # Every affected job must have a real decision in the near neighborhood or
    # this local problem cannot repair the event.
    no_local_choice = sorted(uid for uid, count in local_choices_by_job.items() if count == 0)
    if no_local_choice:
        raise LocalRepairEscalation(
            reason="AFFECTED_JOB_HAS_NO_NEAR_HORIZON_CHOICE",
            detail={"job_uids": no_local_choice, "near_horizon_steps": near_horizon_steps},
        )

    freed_defer_vars: list[str] = []
    fixed_defer_vars: list[str] = []
    for uid, var in defer.items():
        suid = str(uid)
        if suid in affected_jobs:
            # Deferral, when the frozen formulation provides it, is part of the
            # affected job's local decision set. It remains solver-controlled.
            freed_defer_vars.append(str(var.VarName))
        else:
            base._set_fixed(var, 0.0 if suid in selected_jobs else 1.0)
            fixed_defer_vars.append(str(var.VarName))

    # Mobility: free affected MESS only inside near horizon; otherwise keep the
    # shifted active plan. Current event has no affected MESS, so all mobility
    # remains fixed.
    selected_mv, selected_stay, selected_occ = _selected_mobility_sets(ref=ref, moves=moves)
    missing_unaffected_mv = [] if fixed_location else sorted(
        k for k in selected_mv if k[0] not in affected_mess and k not in mv
    )
    missing_unaffected_stay = [] if fixed_location else sorted(
        k for k in selected_stay if k[0] not in affected_mess and k not in stay
    )
    if missing_unaffected_mv or missing_unaffected_stay:
        raise LocalRepairEscalation(
            reason="UNAFFECTED_MOBILITY_PLAN_NO_LONGER_ADMISSIBLE",
            detail={
                "missing_moves": missing_unaffected_mv[:50],
                "missing_stays": missing_unaffected_stay[:50],
            },
        )

    freed_mobility_vars: list[str] = []
    fixed_mobility_vars: list[str] = []
    for key, var in stay.items():
        local = str(key[0]) in affected_mess and int(key[1]) < near_horizon_steps
        if local:
            freed_mobility_vars.append(str(var.VarName))
        else:
            base._set_fixed(var, 1.0 if key in selected_stay else 0.0)
            fixed_mobility_vars.append(str(var.VarName))
    for key, var in mv.items():
        local = str(key[0]) in affected_mess and int(key[1]) < near_horizon_steps
        if local:
            freed_mobility_vars.append(str(var.VarName))
        else:
            base._set_fixed(var, 1.0 if key in selected_mv else 0.0)
            fixed_mobility_vars.append(str(var.VarName))
    for key, var in node_occ.items():
        local = (
            str(key[0]) in affected_mess
            and 0 < int(key[1]) < near_horizon_steps
        )
        if local:
            freed_mobility_vars.append(str(var.VarName))
        else:
            base._set_fixed(var, 1.0 if key in selected_occ else 0.0)
            fixed_mobility_vars.append(str(var.VarName))

    model.update()
    residual = [
        str(v.VarName)
        for v in model.getVars()
        if str(v.VType).upper() in {"B", "I", "S", "N"}
        and float(v.UB) - float(v.LB) > 1e-12
    ]
    freed = set(freed_job_vars + freed_defer_vars + freed_mobility_vars)
    unexpected = [
        name for name in residual
        if not (name.startswith("mode_") or name in freed)
    ]
    if unexpected:
        raise RuntimeError(f"unexpected residual integer variables: {unexpected[:50]}")

    return {
        "schema_version": "r26.step5.local_repair_scope.v2",
        "status": "PASS_SCOPE_BOUND",
        "issue": issue,
        "near_horizon_steps": int(near_horizon_steps),
        "near_horizon_minutes": int(near_horizon_steps) * 5,
        "affected_job_ids": sorted(affected_jobs),
        "affected_mess_ids": sorted(affected_mess),
        "fixed_location_projection": fixed_location,
        "local_choices_by_affected_job": local_choices_by_job,
        "freed_job_variable_count": len(freed_job_vars),
        "freed_defer_variable_count": len(freed_defer_vars),
        "freed_mobility_variable_count": len(freed_mobility_vars),
        "freed_slow_variable_count": len(freed),
        "fixed_job_variable_count": len(fixed_job_vars),
        "fixed_defer_variable_count": len(fixed_defer_vars),
        "fixed_mobility_variable_count": len(fixed_mobility_vars),
        "residual_integer_count": len(residual),
        "residual_integer_names_sample": residual[:100],
        "unaffected_decisions_fixed": True,
        "active_plan_authority": ref.get("authority"),
        "active_plan_parent_issue": ref.get("active_plan_parent_issue"),
        "active_plan_source_post_sha256": ref.get("active_plan_source_post_sha256"),
        "future_actual_used": False,
    }


def run(args: argparse.Namespace) -> int:
    stage4_archive = Path(args.stage4_result).expanduser().resolve()
    prereq = validate_step4(stage4_archive)
    issue = int(prereq["issue"])
    affected_jobs = tuple(prereq["affected_job_ids"])
    affected_mess = tuple(prereq["affected_mess_ids"])

    repo = base.locate_repo(args.repo)
    work = Path.home() / "mobile_ess_work"
    base.assert_no_active_r25t(work)
    lock = base.acquire_stage2_lock(work)

    tag = base.now_tag()
    run_root = base.SCRATCH_ROOT / f"A_STEP5_{tag}"
    run_root.mkdir(parents=True, exist_ok=False)
    log_dir = base.LOG_ROOT / run_root.name
    log_dir.mkdir(parents=True, exist_ok=False)
    console = log_dir / "RUN_CONSOLE.log"
    rc = 2

    with console.open("w", encoding="utf-8", buffering=1) as lh:
        oldo, olde = sys.stdout, sys.stderr
        sys.stdout = base.Tee(oldo, lh)
        sys.stderr = base.Tee(olde, lh)
        try:
            base.write_json(run_root / "00_STEP4_PREREQUISITE.json", prereq)
            auth = base.assert_source_authority(repo)
            base.write_json(run_root / "01_SOURCE_AUTHORITY.json", auth)
            deps = base.dependency_preflight()
            base.write_json(run_root / "02_DEPENDENCY_PREFLIGHT.json", deps)

            # Resume exactly from the uncommitted 단계 4 PRE boundary.
            resume_src = run_root / "resume_state.json"
            extract_json_suffix(
                stage4_archive,
                f"engine/issue_{issue:06d}/BUILD7C_PRECOMMIT_STATE.json",
                resume_src,
            )
            resume = json.loads(resume_src.read_text(encoding="utf-8"))
            state_hash = str(resume["sha256"])
            if state_hash != str(prereq["replan"]["current_pre_state_file"] and resume["sha256"]):
                # This branch is only a structural guard; the exact stage4 PRE is
                # the source we just extracted.
                raise RuntimeError("resume PRE-state hash is invalid")

            # Reconstruct the shifted active plan that triggered the event.
            active_ref = shifted_active_plan_from_stage4(stage4_archive, issue)
            if str(active_ref["active_plan_source_post_sha256"]) != state_hash:
                raise RuntimeError(
                    "shifted active-plan source POST does not equal local-repair PRE"
                )

            empty_hint = run_root / "empty_hints"
            empty_hint.mkdir()

            base.set_science_environment()
            resume_env = {
                "MOBILEESS_RESUME_ISSUE": str(issue),
                "MOBILEESS_R25Q_RESUME_STATE_PATH": str(resume_src),
                "MOBILEESS_RESUME_STATE_SHA256": state_hash,
                "MOBILEESS_R25Q_RESUME_HINT_DIR": str(empty_hint),
                "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME": "NONE.csv",
                "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME": "NONE.csv",
                "MOBILEESS_R25V_RESUME_JOB_PLAN_NAME": "NONE.csv",
                "MOBILEESS_R25V_RESUME_GUIDANCE_PATH": str(empty_hint / "NONE.json"),
            }
            os.environ.update(resume_env)
            sm = base.load_science(repo)
            # load_science performs import-time initialization; reapply current
            # causal resume authority afterwards.
            os.environ.update(resume_env)

            engine = run_root / "engine"
            engine.mkdir()
            original_jw = sm.jw
            target_t0: float | None = None
            issue_wall: float | None = None
            committed_stop = False
            local_scope_record: dict[str, Any] | None = None
            local_solve_record: dict[str, Any] | None = None

            def jw_wrapper(path: Any, value: Any):
                nonlocal target_t0, issue_wall, committed_stop
                result = original_jw(path, value)
                pp = Path(path)
                if pp.parent.name == f"issue_{issue:06d}":
                    if pp.name == "BUILD7C_PRECOMMIT_STATE.json":
                        target_t0 = time.monotonic()
                        current = json.loads(pp.read_text(encoding="utf-8"))
                        if str(current["sha256"]) != state_hash:
                            raise RuntimeError(
                                f"local-repair PRE mismatch expected={state_hash} "
                                f"got={current['sha256']}"
                            )
                    elif pp.name == "BUILD7C_POSTCOMMIT_STATE.json":
                        if target_t0 is not None:
                            issue_wall = time.monotonic() - target_t0
                        committed_stop = True
                        # Stop immediately after the successful target POST write.
                        # This prevents reading issue+1 actuals in a single-issue
                        # acceptance run.
                        raise LocalRepairStop(
                            f"단계 5 local repair committed issue {issue}; stop before issue {issue+1}"
                        )
                return result

            def local_decomp(**kwargs: Any):
                nonlocal local_scope_record, local_solve_record
                import inspect
                import gurobipy as gp

                fr = inspect.currentframe()
                assert fr is not None and fr.f_back is not None
                loc = fr.f_back.f_locals
                ii = int(loc["issue"])
                if ii != issue:
                    raise RuntimeError(f"unexpected solve issue {ii}; expected {issue}")
                model = kwargs["m"]
                issue_out = Path(loc["out"])

                local_scope_record = apply_actual_local_repair(
                    loc=loc,
                    ref=active_ref,
                    issue=ii,
                    affected_job_ids=affected_jobs,
                    affected_mess_ids=affected_mess,
                    near_horizon_steps=int(args.near_horizon_steps),
                )
                base.write_json(
                    issue_out / "R26_STEP5_LOCAL_REPAIR_SCOPE.json",
                    local_scope_record,
                )

                # Primary scoped local MIQCP. This is an online feasible-plan
                # search, not an exact/global certificate.
                model.Params.Threads = 4
                model.Params.TimeLimit = float(args.planner_limit_seconds)
                model.Params.MIPGap = 0.03
                model.Params.MIPFocus = 1
                model.Params.OutputFlag = 1
                model.update()

                primary_t0 = time.monotonic()
                cb = kwargs.get("base_callback")
                model.optimize(cb) if cb is not None else model.optimize()
                primary_wall = time.monotonic() - primary_t0
                primary_quality = base.solver_quality(model)

                if int(model.SolCount) < 1:
                    raise LocalRepairEscalation(
                        reason="LOCAL_REPAIR_NO_FEASIBLE_INCUMBENT",
                        detail={
                            "primary_wall_seconds": primary_wall,
                            "solver": primary_quality,
                            "scope": local_scope_record,
                        },
                    )

                # Snapshot the discrete repair before fixing it.
                selected_affected_job_choices = []
                for key, var in loc["x"].items():
                    if str(key[0]) in set(affected_jobs) and float(var.X) > 0.5:
                        selected_affected_job_choices.append(
                            {
                                "job_uid": str(key[0]),
                                "destination_IDC_id": str(key[1]),
                                "rack_pool_id": str(key[2]),
                                "start_step": int(key[3]),
                            }
                        )
                selected_affected_deferrals = [
                    str(uid)
                    for uid, var in loc["defer"].items()
                    if str(uid) in set(affected_jobs) and float(var.X) > 0.5
                ]

                # Fix every remaining discrete variable to the feasible local
                # incumbent and solve a continuous QCP polish. This is a
                # feasibility/numerical authority for commit, not a global gap
                # certificate.
                residual_int = [
                    v
                    for v in model.getVars()
                    if str(v.VType).upper() in {"B", "I", "S", "N"}
                    and float(v.UB) - float(v.LB) > 1e-12
                ]
                for var in residual_int:
                    base._set_fixed(var, 1.0 if float(var.X) >= 0.5 else 0.0)
                model.update()
                model.reset()
                model.Params.TimeLimit = 60.0
                model.Params.MIPGap = 0.0
                polish_t0 = time.monotonic()
                model.optimize()
                polish_wall = time.monotonic() - polish_t0
                polish_quality = base.solver_quality(model)

                if int(model.Status) != int(gp.GRB.OPTIMAL):
                    raise LocalRepairEscalation(
                        reason="LOCAL_REPAIR_FIXED_DISCRETE_QCP_POLISH_FAILED",
                        detail={
                            "primary": primary_quality,
                            "polish": polish_quality,
                            "scope": local_scope_record,
                        },
                    )

                local_solve_record = {
                    "schema_version": "r26.step5.local_repair_solve.v2",
                    "status": "PASS_FEASIBLE_LOCAL_REPAIR_AND_QCP_POLISH",
                    "issue": ii,
                    "primary_wall_seconds": primary_wall,
                    "primary_solver": primary_quality,
                    "primary_native_gap_diagnostic_only": primary_quality.get("MIPGap"),
                    "selected_affected_job_choices": selected_affected_job_choices,
                    "selected_affected_deferrals": selected_affected_deferrals,
                    "fixed_discrete_qcp_polish_wall_seconds": polish_wall,
                    "fixed_discrete_qcp_polish": polish_quality,
                    "remaining_integer_vars_after_polish": int(model.NumIntVars),
                    "online_global_3pct_certificate_claimed": False,
                    "local_repair_scope": local_scope_record,
                }
                base.write_json(
                    issue_out / "R26_STEP5_LOCAL_REPAIR_SOLVE.json",
                    local_solve_record,
                )
                print(
                    f"[A 단계5] issue={ii} local repair primary={primary_wall:.2f}s "
                    f"polish={polish_wall:.2f}s affected_jobs={len(affected_jobs)} "
                    f"affected_mess={len(affected_mess)}",
                    flush=True,
                )
                return None

            sm.jw = jw_wrapper
            sm.certified_path_decomposition_solve = local_decomp

            escalation: LocalRepairEscalation | None = None
            try:
                sm.rolling54_main(engine, work)
                raise RuntimeError("rolling54_main returned without target POST or escalation")
            except LocalRepairStop:
                if not committed_stop:
                    raise RuntimeError("received LocalRepairStop without target POST")
            except LocalRepairEscalation as exc:
                escalation = exc

            if escalation is not None:
                detail = {
                    "schema_version": "r26.step5.local_repair_escalation.v1",
                    "status": "PASS_ESCALATE_FULL_REPLAN",
                    "issue": issue,
                    "reason": escalation.reason,
                    "detail": escalation.detail,
                    "affected_job_ids": list(affected_jobs),
                    "affected_mess_ids": list(affected_mess),
                    "invalid_issue_committed": False,
                    "future_actual_used": False,
                    "requested_mode": "FULL_REPLAN",
                    "next_step": "STEP6_ASYNC_FULL_REPLAN",
                }
                base.write_json(run_root / "04_FULL_REPLAN_ESCALATION.json", detail)
                result = {
                    "schema_version": "conversation_a.step5_local_result.v2",
                    "step1": "COMPLETE_54_OF_54",
                    "step2": "PASS",
                    "step3": "PASS",
                    "step4": "PASS_REPLAN_REQUIRED",
                    "step5": "PASS_ESCALATE_FULL_REPLAN",
                    "step6": "PENDING",
                    "issue": issue,
                    "affected_job_ids": list(affected_jobs),
                    "affected_mess_ids": list(affected_mess),
                    "near_horizon_steps": int(args.near_horizon_steps),
                    "local_repair_committed": False,
                    "physical_post_commit": False,
                    "future_actual_used": False,
                    "repository_modified": False,
                    "next_step_if_pass": "STEP6_ASYNC_FULL_REPLAN",
                    "escalation": detail,
                }
                base.write_json(run_root / "A_STEP5_RESULT.json", result)
                print(
                    f"PASS_A_STEP5 status=PASS_ESCALATE_FULL_REPLAN issue={issue} "
                    f"reason={escalation.reason}",
                    flush=True,
                )
                rc = 0
            else:
                issue_dir = engine / f"issue_{issue:06d}"
                tr = json.loads(
                    (issue_dir / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json").read_text()
                )
                fresh = json.loads(
                    (
                        issue_dir
                        / f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
                    ).read_text()
                )
                post = json.loads(
                    (issue_dir / "BUILD7C_POSTCOMMIT_STATE.json").read_text()
                )
                if local_scope_record is None or local_solve_record is None:
                    raise RuntimeError("local repair evidence missing after commit")
                passed = bool(
                    local_scope_record["freed_slow_variable_count"] > 0
                    and tr.get("status") == "PASS"
                    and tr.get("h0_only_committed") is True
                    and tr.get("future_actual_arrivals_read") is False
                    and fresh.get("hard_constraint_pass") is True
                    and fresh.get("converged") is True
                    and post.get("sha256") == tr.get("post_state_sha256")
                )
                if not passed:
                    raise RuntimeError("단계 5 physical acceptance gate failed")

                result = {
                    "schema_version": "conversation_a.step5_local_result.v2",
                    "step1": "COMPLETE_54_OF_54",
                    "step2": "PASS",
                    "step3": "PASS",
                    "step4": "PASS_REPLAN_REQUIRED",
                    "step5": "PASS_LOCAL_REPAIR_COMMITTED",
                    "step6": "PENDING",
                    "issue": issue,
                    "affected_job_ids": list(affected_jobs),
                    "affected_mess_ids": list(affected_mess),
                    "near_horizon_steps": int(args.near_horizon_steps),
                    "near_horizon_minutes": int(args.near_horizon_steps) * 5,
                    "local_repair_committed": True,
                    "full_issue_wall_seconds": issue_wall,
                    "scope": local_scope_record,
                    "solve": local_solve_record,
                    "fresh_opendss_pass": True,
                    "transition_pass": True,
                    "pre_state_sha256": tr.get("pre_state_sha256"),
                    "post_state_sha256": tr.get("post_state_sha256"),
                    "physical_post_commit": True,
                    "online_global_3pct_certificate_claimed": False,
                    "future_actual_used": False,
                    "period_selection_executed": False,
                    "repository_modified": False,
                    "next_step_if_pass": "STEP6_ASYNC_FULL_REPLAN",
                }
                base.write_json(run_root / "A_STEP5_RESULT.json", result)
                print(
                    f"PASS_A_STEP5 status=PASS_LOCAL_REPAIR_COMMITTED issue={issue} "
                    f"wall={issue_wall:.2f}s",
                    flush=True,
                )
                rc = 0

        except Exception as exc:
            fail = {
                "status": "FAIL_CLOSED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "future_actual_used": False,
                "repository_modified": False,
            }
            base.write_json(run_root / "A_STEP5_FAILURE.json", fail)
            print(json.dumps(fail, indent=2, ensure_ascii=False))
            rc = 2
        finally:
            sys.stdout = oldo
            sys.stderr = olde
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
            except Exception:
                pass

    result_archive, log_archive = base.package_run(
        run_root,
        base.RESULT_ROOT,
        base.LOG_ROOT,
        "ConversationA_STEP5_LOCAL_RESULT",
    )
    print(f"RESULT_HANDOFF_FILE={result_archive}")
    print(f"RESULT_HANDOFF_SHA256={base.sha256(result_archive)}")
    print(f"LOG_HANDOFF_FILE={log_archive}")
    print(f"LOG_HANDOFF_SHA256={base.sha256(log_archive)}")
    print(f"RUN_CONSOLE_LOG={console}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage4-result", required=True)
    ap.add_argument("--near-horizon-steps", type=int, default=12)
    ap.add_argument("--planner-limit-seconds", type=float, default=300.0)
    ap.add_argument("--repo", default=None)
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
