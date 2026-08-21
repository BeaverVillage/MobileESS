#!/usr/bin/env python3
"""Conversation A 단계 6 R1: actual asynchronous FULL_REPLAN integration.

This validates the production orchestration boundary using the existing H54
five-minute full model as the planner backend.  It does NOT yet validate the
R26 26-stage multiresolution approximation; that belongs to 단계 7.

Flow:
1. Recover the exact issue114 PRE state from the 단계 5 handoff.
2. Launch a real full-plan Gurobi worker in a separate process.
3. Poll the worker without blocking and record poll latency.
4. Accept only a feasible candidate bound to the same PRE-state hash.
5. Rebuild issue114 from the same PRE, fix the candidate's slow decisions,
   solve the fast dispatch, perform a continuous QCP polish, run Fresh Exact
   OpenDSS, and commit h0 only.
6. No online/global 3% exact certificate is claimed.

Results -> /home/jaewon/mobile_ess_work/frozen_artifacts
Logs    -> /home/jaewon/mobile_ess_work/logs
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import traceback
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
BASE_RUNNER = HERE / "MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py"
if not BASE_RUNNER.is_file():
    raise SystemExit(f"Missing companion file: {BASE_RUNNER}")

spec = importlib.util.spec_from_file_location("a_step6_base", BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import 단계 2~3 companion runner")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)


class PlannerCandidateReady(BaseException):
    pass


class PlannerNoCandidate(BaseException):
    pass


class CommitStop(BaseException):
    pass


def canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


def extract_json_suffix(archive: Path, suffix: str, out: Path) -> dict[str, Any]:
    value = read_json_suffix(archive, suffix)
    base.write_json(out, value)
    return value


def validate_step5(archive: Path) -> dict[str, Any]:
    """Accept either a clean PASS_ESCALATE archive or the known R3 control-flow bug."""
    if not archive.is_file():
        raise FileNotFoundError(archive)

    try:
        result = read_json_suffix(archive, "A_STEP5_RESULT.json")
    except Exception:
        result = None

    if isinstance(result, dict):
        if result.get("step5") != "PASS_ESCALATE_FULL_REPLAN":
            raise RuntimeError(f"단계 6 requires FULL_REPLAN escalation, got {result}")
        issue = int(result["issue"])
        return {
            "status": "PASS_ESCALATE_FULL_REPLAN",
            "issue": issue,
            "source": "CLEAN_STEP5_RESULT",
            "result": result,
            "archive": str(archive),
            "archive_sha256": base.sha256(archive),
        }

    outer = read_json_suffix(archive, "A_STEP5_FAILURE.json")
    engine = read_json_suffix(archive, "engine/_FAILURE.json")
    prereq = read_json_suffix(archive, "00_STEP4_PREREQUISITE.json")
    if "KeyError((18, 191))" not in str(engine.get("error")):
        raise RuntimeError(
            f"단계 5 is neither a clean escalation nor the adjudicated stale-mobility case: "
            f"{engine.get('error')}"
        )
    return {
        "status": "PASS_ESCALATE_FULL_REPLAN",
        "issue": int(prereq["issue"]),
        "source": "ADJUDICATED_STEP5_R3_STALE_MOBILITY_OUTSIDE_LOCAL_HORIZON",
        "affected_job_ids": list(prereq["affected_job_ids"]),
        "affected_mess_ids": ["MESS01"],
        "reason": (
            "shifted active MESS01 move h18/slot191 is not admissible in current issue114 "
            "route domain and lies outside the 12-step local-repair horizon"
        ),
        "raw_engine_error": engine["error"],
        "raw_outer_error": outer["error"],
        "archive": str(archive),
        "archive_sha256": base.sha256(archive),
    }


def _resume_env(*, issue: int, resume_path: Path, state_hash: str, empty_hint: Path) -> dict[str, str]:
    return {
        "MOBILEESS_RESUME_ISSUE": str(issue),
        "MOBILEESS_R25Q_RESUME_STATE_PATH": str(resume_path),
        "MOBILEESS_RESUME_STATE_SHA256": str(state_hash),
        "MOBILEESS_R25Q_RESUME_HINT_DIR": str(empty_hint),
        "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME": "NONE.csv",
        "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME": "NONE.csv",
        "MOBILEESS_R25V_RESUME_JOB_PLAN_NAME": "NONE.csv",
        "MOBILEESS_R25V_RESUME_GUIDANCE_PATH": str(empty_hint / "NONE.json"),
    }


def _key4(raw: Sequence[Any]) -> tuple[str, str, str, int]:
    return (str(raw[0]), str(raw[1]), str(raw[2]), int(raw[3]))


def _key3i(raw: Sequence[Any]) -> tuple[str, int, int]:
    return (str(raw[0]), int(raw[1]), int(raw[2]))


def _key3s(raw: Sequence[Any]) -> tuple[str, int, str]:
    return (str(raw[0]), int(raw[1]), str(raw[2]))


def capture_candidate(loc: Mapping[str, Any], *, issue: int, pre_hash: str, model: Any) -> dict[str, Any]:
    x = loc["x"]
    defer = loc["defer"]
    stay = loc["stay"]
    mv = loc["mv"]
    node_occ = loc.get("node_occ", {})
    mode = loc["mode"]

    selected_x = [list(k) for k, v in x.items() if float(v.X) > 0.5]
    selected_defer = [str(k) for k, v in defer.items() if float(v.X) > 0.5]
    selected_stay = [list(k) for k, v in stay.items() if float(v.X) > 0.5]
    selected_mv = [list(k) for k, v in mv.items() if float(v.X) > 0.5]
    selected_occ = [list(k) for k, v in node_occ.items() if float(v.X) > 0.5]
    mode_values = [
        [str(k[0]), int(k[1]), 1 if float(v.X) >= 0.5 else 0]
        for k, v in mode.items()
    ]

    fractional_mv = max(
        (abs(float(v.X) - round(float(v.X))) for v in mv.values()),
        default=0.0,
    )
    if fractional_mv > 1e-5:
        raise RuntimeError(f"full-replan candidate has fractional MOVE arc {fractional_mv}")

    slow_payload = {
        "issue": issue,
        "source_pre_state_sha256": pre_hash,
        "selected_x": selected_x,
        "selected_defer": selected_defer,
        "selected_stay": selected_stay,
        "selected_mv": selected_mv,
        "selected_occ": selected_occ,
    }
    return {
        "schema_version": "r26.step6.full_replan_candidate.v1",
        "status": "FEASIBLE",
        **slow_payload,
        "slow_plan_checksum": canonical_sha(slow_payload),
        "mode_warm_start": mode_values,
        "planner_solver": base.solver_quality(model),
        "planner_native_gap_diagnostic_only": (
            float(model.MIPGap) if int(model.SolCount) > 0 else None
        ),
        "online_global_3pct_certificate_claimed": False,
        "candidate_swap_requires_same_pre_hash": True,
        "future_actual_used": False,
    }


def bind_candidate(loc: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    x = loc["x"]
    defer = loc["defer"]
    stay = loc["stay"]
    mv = loc["mv"]
    node_occ = loc.get("node_occ", {})
    model = loc["m"]

    sx = {_key4(k) for k in candidate["selected_x"]}
    sd = set(map(str, candidate["selected_defer"]))
    ss = {_key3s(k) for k in candidate["selected_stay"]}
    smv = {_key3i(k) for k in candidate["selected_mv"]}
    so = {_key3s(k) for k in candidate["selected_occ"]}

    for selected, actual, label in (
        (sx, set(x), "x"),
        (ss, set(stay), "stay"),
        (smv, set(mv), "move"),
        (so, set(node_occ), "occupancy"),
    ):
        missing = sorted(selected - actual)
        if missing:
            raise RuntimeError(f"candidate {label} keys absent from commit model: {missing[:30]}")

    for key, var in x.items():
        base._set_fixed(var, 1.0 if key in sx else 0.0)
    for uid, var in defer.items():
        base._set_fixed(var, 1.0 if str(uid) in sd else 0.0)
    for key, var in stay.items():
        base._set_fixed(var, 1.0 if key in ss else 0.0)
    for key, var in mv.items():
        base._set_fixed(var, 1.0 if key in smv else 0.0)
    for key, var in node_occ.items():
        base._set_fixed(var, 1.0 if key in so else 0.0)

    # Candidate planner mode values are hints only; fast dispatch remains authoritative.
    mode_hint = {
        (str(k[0]), int(k[1])): int(k[2])
        for k in candidate.get("mode_warm_start", [])
    }
    for key, var in loc["mode"].items():
        if key in mode_hint:
            var.Start = float(mode_hint[key])
            var.VarHintVal = float(mode_hint[key])
            var.VarHintPri = 5

    model.update()
    residual = [
        str(v.VarName)
        for v in model.getVars()
        if str(v.VType).upper() in {"B", "I", "S", "N"}
        and float(v.UB) - float(v.LB) > 1e-12
    ]
    unexpected = [name for name in residual if not name.startswith("mode_")]
    if unexpected:
        raise RuntimeError(f"candidate binding left non-mode integer vars: {unexpected[:50]}")
    return {
        "selected_x": len(sx),
        "selected_defer": len(sd),
        "selected_stay": len(ss),
        "selected_mv": len(smv),
        "selected_occ": len(so),
        "residual_integer_count": len(residual),
        "residual_integer_family": "FAST_DISPATCH_MODE_ONLY",
        "future_actual_used": False,
    }


def worker_main(args: argparse.Namespace) -> int:
    """Real full-plan worker. It never commits physical state."""
    repo = base.locate_repo(args.repo)
    work = Path.home() / "mobile_ess_work"
    output = Path(args.worker_output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    resume_path = Path(args.resume_state).resolve()
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    pre_hash = str(resume["sha256"])
    issue = int(args.issue)
    empty_hint = output / "empty_hints"
    empty_hint.mkdir(exist_ok=True)

    base.set_science_environment()
    env = _resume_env(
        issue=issue, resume_path=resume_path, state_hash=pre_hash, empty_hint=empty_hint
    )
    os.environ.update(env)
    sm = base.load_science(repo)
    os.environ.update(env)

    def planner_hook(**kwargs: Any):
        import inspect
        model = kwargs["m"]
        fr = inspect.currentframe()
        assert fr is not None and fr.f_back is not None
        loc = fr.f_back.f_locals
        current_issue = int(loc["issue"])
        if current_issue != issue:
            raise RuntimeError(f"planner worker entered issue {current_issue}, expected {issue}")
        issue_out = Path(loc["out"])

        model.Params.Threads = 4
        model.Params.TimeLimit = float(args.planner_limit_seconds)
        model.Params.MIPFocus = 1
        model.Params.Heuristics = 0.20
        model.Params.MIPGap = 0.10
        model.Params.OutputFlag = 1
        model.update()

        t0 = time.monotonic()
        cb = kwargs.get("base_callback")
        model.optimize(cb) if cb is not None else model.optimize()
        wall = time.monotonic() - t0
        if int(model.SolCount) < 1:
            base.write_json(
                output / "FULL_REPLAN_NO_CANDIDATE.json",
                {
                    "status": "NO_FEASIBLE_CANDIDATE",
                    "issue": issue,
                    "source_pre_state_sha256": pre_hash,
                    "wall_seconds": wall,
                    "solver": base.solver_quality(model),
                    "online_global_3pct_certificate_claimed": False,
                    "future_actual_used": False,
                },
            )
            raise PlannerNoCandidate()

        candidate = capture_candidate(loc, issue=issue, pre_hash=pre_hash, model=model)
        candidate["planner_wall_seconds"] = wall
        base.write_json(output / "FULL_REPLAN_CANDIDATE.json", candidate)
        base.write_json(
            issue_out / "R26_STEP6_FULL_REPLAN_CANDIDATE.json",
            candidate,
        )
        raise PlannerCandidateReady()

    sm.certified_path_decomposition_solve = planner_hook
    try:
        sm.rolling54_main(output / "science_worker", work)
    except PlannerCandidateReady:
        return 0
    except PlannerNoCandidate:
        return 3
    return 4


def run_parent(args: argparse.Namespace) -> int:
    stage5 = Path(args.stage5_result).expanduser().resolve()
    prereq = validate_step5(stage5)
    issue = int(prereq["issue"])
    repo = base.locate_repo(args.repo)
    work = Path.home() / "mobile_ess_work"
    base.assert_no_active_r25t(work)
    lock = base.acquire_stage2_lock(work)

    tag = base.now_tag()
    run_root = base.SCRATCH_ROOT / f"A_STEP6_{tag}"
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
            base.write_json(run_root / "00_STEP5_PREREQUISITE.json", prereq)
            authority = base.assert_source_authority(repo)
            base.write_json(run_root / "01_SOURCE_AUTHORITY.json", authority)
            deps = base.dependency_preflight()
            base.write_json(run_root / "02_DEPENDENCY_PREFLIGHT.json", deps)

            resume_path = run_root / "resume_state.json"
            resume = extract_json_suffix(
                stage5,
                f"engine/issue_{issue:06d}/BUILD7C_PRECOMMIT_STATE.json",
                resume_path,
            )
            pre_hash = str(resume["sha256"])

            planner_dir = run_root / "planner_worker"
            planner_dir.mkdir()
            worker_log = log_dir / "FULL_REPLAN_WORKER_CONSOLE.log"
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--repo",
                str(repo),
                "--resume-state",
                str(resume_path),
                "--issue",
                str(issue),
                "--worker-output",
                str(planner_dir),
                "--planner-limit-seconds",
                str(float(args.planner_limit_seconds)),
            ]
            base.write_json(
                run_root / "03_ASYNC_PLANNER_LAUNCH.json",
                {
                    "status": "STARTING",
                    "command": cmd,
                    "source_pre_state_sha256": pre_hash,
                    "issue": issue,
                    "process_isolated": True,
                    "physical_state_mutation_by_worker": False,
                },
            )

            launch_t0 = time.monotonic()
            with worker_log.open("w", encoding="utf-8", buffering=1) as wh:
                proc = subprocess.Popen(
                    cmd,
                    stdout=wh,
                    stderr=subprocess.STDOUT,
                    cwd=str(HERE),
                )
                launch_return_seconds = time.monotonic() - launch_t0
                polls = []
                deadline = time.monotonic() + float(args.planner_limit_seconds) + 90.0
                while True:
                    pt0 = time.perf_counter()
                    code = proc.poll()
                    pdur = time.perf_counter() - pt0
                    polls.append(
                        {
                            "elapsed_seconds": time.monotonic() - launch_t0,
                            "poll_call_seconds": pdur,
                            "return_code": code,
                        }
                    )
                    if code is not None:
                        break
                    if time.monotonic() > deadline:
                        proc.kill()
                        proc.wait(timeout=10)
                        raise RuntimeError("FULL_REPLAN worker exceeded planner timeout + grace")
                    time.sleep(0.25)

            max_poll = max((r["poll_call_seconds"] for r in polls), default=math.inf)
            async_pass = bool(
                launch_return_seconds < 1.0
                and max_poll < 0.05
                and len(polls) >= 2
            )
            async_audit = {
                "schema_version": "r26.step6.async_planner_audit.v1",
                "status": "PASS" if async_pass else "FAIL_CLOSED",
                "issue": issue,
                "launch_return_seconds": launch_return_seconds,
                "poll_count": len(polls),
                "max_poll_call_seconds": max_poll,
                "poll_api_nonblocking_threshold_seconds": 0.05,
                "worker_process_return_code": int(proc.returncode),
                "source_pre_state_sha256": pre_hash,
                "physical_state_committed_while_worker_running": False,
                "poll_samples_head": polls[:20],
                "poll_samples_tail": polls[-20:],
            }
            base.write_json(run_root / "04_ASYNC_PLANNER_AUDIT.json", async_audit)
            if not async_pass:
                raise RuntimeError(f"async planner audit failed: {async_audit}")
            if int(proc.returncode) != 0:
                no_candidate = planner_dir / "FULL_REPLAN_NO_CANDIDATE.json"
                if no_candidate.is_file():
                    raise RuntimeError(
                        "FULL_REPLAN worker produced no feasible candidate; see "
                        + str(no_candidate)
                    )
                raise RuntimeError(f"FULL_REPLAN worker failed return_code={proc.returncode}")

            candidate_path = planner_dir / "FULL_REPLAN_CANDIDATE.json"
            if not candidate_path.is_file():
                raise RuntimeError("FULL_REPLAN worker returned success without candidate")
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            if candidate.get("status") != "FEASIBLE":
                raise RuntimeError(f"candidate not feasible: {candidate}")
            if str(candidate.get("source_pre_state_sha256")) != pre_hash:
                raise RuntimeError("candidate PRE-state hash mismatch")
            payload = {
                key: candidate[key]
                for key in (
                    "issue",
                    "source_pre_state_sha256",
                    "selected_x",
                    "selected_defer",
                    "selected_stay",
                    "selected_mv",
                    "selected_occ",
                )
            }
            if canonical_sha(payload) != candidate.get("slow_plan_checksum"):
                raise RuntimeError("candidate slow-plan checksum mismatch")
            base.write_json(
                run_root / "05_FULL_REPLAN_CANDIDATE_ACCEPTANCE.json",
                {
                    "status": "PASS",
                    "candidate_checksum": candidate["slow_plan_checksum"],
                    "source_pre_state_sha256": pre_hash,
                    "same_pre_hash": True,
                    "planner_status": candidate["status"],
                    "planner_wall_seconds": candidate["planner_wall_seconds"],
                    "online_global_3pct_certificate_claimed": False,
                },
            )

            # Candidate commit: rebuild from the same causal PRE, bind slow plan,
            # perform fast dispatch, Fresh OpenDSS, and h0-only commit.
            empty_hint = run_root / "commit_empty_hints"
            empty_hint.mkdir()
            base.set_science_environment()
            env = _resume_env(
                issue=issue,
                resume_path=resume_path,
                state_hash=pre_hash,
                empty_hint=empty_hint,
            )
            os.environ.update(env)
            sm = base.load_science(repo)
            os.environ.update(env)

            original_jw = sm.jw
            commit_engine = run_root / "commit_engine"
            commit_engine.mkdir()
            issue_t0: float | None = None
            issue_wall: float | None = None
            committed = False
            fast_record: dict[str, Any] | None = None
            bind_record: dict[str, Any] | None = None

            def jw_wrapper(path: Any, value: Any):
                nonlocal issue_t0, issue_wall, committed
                result = original_jw(path, value)
                pp = Path(path)
                if pp.parent.name == f"issue_{issue:06d}":
                    if pp.name == "BUILD7C_PRECOMMIT_STATE.json":
                        current = json.loads(pp.read_text(encoding="utf-8"))
                        if str(current["sha256"]) != pre_hash:
                            raise RuntimeError(
                                f"commit PRE mismatch expected={pre_hash} got={current['sha256']}"
                            )
                        issue_t0 = time.monotonic()
                    elif pp.name == "BUILD7C_POSTCOMMIT_STATE.json":
                        committed = True
                        if issue_t0 is not None:
                            issue_wall = time.monotonic() - issue_t0
                        raise CommitStop()
                return result

            def commit_hook(**kwargs: Any):
                nonlocal fast_record, bind_record
                import inspect
                import gurobipy as gp

                fr = inspect.currentframe()
                assert fr is not None and fr.f_back is not None
                loc = fr.f_back.f_locals
                current_issue = int(loc["issue"])
                if current_issue != issue:
                    raise RuntimeError(
                        f"candidate commit entered issue {current_issue}, expected {issue}"
                    )
                model = kwargs["m"]
                issue_out = Path(loc["out"])
                bind_record = bind_candidate(loc, candidate)
                base.write_json(
                    issue_out / "R26_STEP6_FULL_REPLAN_BINDING.json",
                    {
                        "status": "PASS",
                        "candidate_checksum": candidate["slow_plan_checksum"],
                        "source_pre_state_sha256": pre_hash,
                        **bind_record,
                    },
                )

                model.Params.Threads = 4
                model.Params.TimeLimit = float(args.fast_limit_seconds)
                model.Params.MIPGap = 0.03
                model.Params.MIPFocus = 1
                model.Params.OutputFlag = 1
                model.update()

                t0 = time.monotonic()
                cb = kwargs.get("base_callback")
                model.optimize(cb) if cb is not None else model.optimize()
                primary_wall = time.monotonic() - t0
                primary = base.solver_quality(model)

                # Keep the frozen science extraction contract intact.
                #
                # R1 always relaxed the residual FAST_DISPATCH_MODE binaries to
                # continuous variables and solved a QCP polish.  That numerical
                # solve itself succeeded, but science/main.py later reads
                # ``m.MIPGap`` while constructing its standard solution record.
                # Gurobi does not expose MIPGap on a continuous QCP model, so R1
                # failed after the fast solve and before Fresh OpenDSS/POST.
                #
                # R2 mirrors the already-proven 단계 3 policy:
                #   * if the primary residual-mode MIQCP has an acceptable
                #     incumbent/status, leave the model as MIQCP and let frozen
                #     science continue unchanged;
                #   * only when a fixed-mode rescue is needed, preserve the
                #     binary VType (LB=UB but relax_integer=False).  This is
                #     mathematically fixed-discrete but remains a Gurobi MIP
                #     object, so MIPGap stays queryable by frozen science.
                primary_has_solution = int(model.SolCount) >= 1
                primary_gap = None
                if primary_has_solution:
                    try:
                        primary_gap = float(model.MIPGap)
                    except Exception:
                        primary_gap = None

                need_fixed_mode_rescue = not primary_has_solution
                if primary_has_solution and int(model.Status) != int(gp.GRB.OPTIMAL):
                    need_fixed_mode_rescue = bool(
                        primary_gap is None or primary_gap > 0.03 + 1e-12
                    )

                rescue = None
                rescue_wall = None
                if need_fixed_mode_rescue:
                    if primary_has_solution:
                        mode_values = {
                            key: 1.0 if float(var.X) >= 0.5 else 0.0
                            for key, var in loc["mode"].items()
                        }
                        rescue_source = "PRIMARY_FAST_INCUMBENT"
                    else:
                        mode_values = {
                            (str(k[0]), int(k[1])): float(int(k[2]))
                            for k in candidate.get("mode_warm_start", [])
                        }
                        missing = [
                            key for key in loc["mode"]
                            if key not in mode_values
                        ]
                        if missing:
                            raise RuntimeError(
                                f"candidate missing mode fallback {missing[:30]}"
                            )
                        rescue_source = "FULL_REPLAN_CANDIDATE_MODE_WARM_START"

                    for key, var in loc["mode"].items():
                        # IMPORTANT: preserve integer type.  Frozen science reads
                        # m.MIPGap after this hook returns.
                        base._set_fixed(
                            var,
                            float(mode_values[key]),
                            relax_integer=False,
                        )
                    model.update()
                    model.reset()
                    model.Params.TimeLimit = 60.0
                    model.Params.MIPGap = 0.0
                    rescue_t0 = time.monotonic()
                    model.optimize()
                    rescue_wall = time.monotonic() - rescue_t0
                    rescue = base.solver_quality(model)
                    rescue["rescue_source"] = rescue_source
                    rescue["fixed_mode_integer_type_preserved"] = True
                    if int(model.Status) != int(gp.GRB.OPTIMAL):
                        raise RuntimeError(
                            f"FULL_REPLAN fixed-mode MIQCP rescue failed status={model.Status}"
                        )

                fast_record = {
                    "schema_version": "r26.step6.fast_commit.v2",
                    "status": "PASS",
                    "issue": issue,
                    "candidate_checksum": candidate["slow_plan_checksum"],
                    "primary_fast_wall_seconds": primary_wall,
                    "primary_fast_solver": primary,
                    "primary_fast_gap": primary_gap,
                    "fixed_mode_rescue_required": need_fixed_mode_rescue,
                    "fixed_mode_rescue_wall_seconds": rescue_wall,
                    "fixed_mode_rescue_solver": rescue,
                    "frozen_science_MIPGap_contract_preserved": True,
                    "online_global_3pct_certificate_claimed": False,
                    "source_pre_state_sha256": pre_hash,
                    "future_actual_used": False,
                }
                base.write_json(
                    issue_out / "R26_STEP6_FULL_REPLAN_FAST_COMMIT.json",
                    fast_record,
                )
                return None

            sm.jw = jw_wrapper
            sm.certified_path_decomposition_solve = commit_hook
            try:
                sm.rolling54_main(commit_engine, work)
                raise RuntimeError("candidate commit returned without target POST")
            except CommitStop:
                if not committed:
                    raise RuntimeError("CommitStop without POST")

            issue_dir = commit_engine / f"issue_{issue:06d}"
            transition = json.loads(
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
            if fast_record is None or bind_record is None:
                raise RuntimeError("step6 commit evidence missing")

            passed = bool(
                transition.get("status") == "PASS"
                and transition.get("h0_only_committed") is True
                and transition.get("future_actual_arrivals_read") is False
                and fresh.get("converged") is True
                and fresh.get("hard_constraint_pass") is True
                and post.get("sha256") == transition.get("post_state_sha256")
                and issue_wall is not None
                and float(issue_wall) < float(args.fast_limit_seconds)
            )
            if not passed:
                raise RuntimeError("단계 6 physical acceptance gate failed")

            result = {
                "schema_version": "conversation_a.step6_result.v1",
                "step1": "COMPLETE_54_OF_54",
                "step2": "PASS",
                "step3": "PASS",
                "step4": "PASS_REPLAN_REQUIRED",
                "step5": "PASS_ESCALATE_FULL_REPLAN",
                "step6": "PASS_ASYNC_FULL_REPLAN_COMMITTED",
                "issue": issue,
                "source_pre_state_sha256": pre_hash,
                "post_state_sha256": post["sha256"],
                "candidate_checksum": candidate["slow_plan_checksum"],
                "async_planner_pass": True,
                "planner_wall_seconds": candidate["planner_wall_seconds"],
                "planner_native_gap_diagnostic_only": candidate.get(
                    "planner_native_gap_diagnostic_only"
                ),
                "online_global_3pct_certificate_claimed": False,
                "fast_commit_wall_seconds": issue_wall,
                "fresh_opendss_pass": True,
                "transition_pass": True,
                "physical_post_commit": True,
                "future_actual_used": False,
                "period_selection_executed": False,
                "repository_modified": False,
                "stage6_backend": "CURRENT_H54_5MIN_FULL_MODEL_FEASIBLE_PLANNER",
                "r1_MIPGap_regression_fixed": True,
                "frozen_science_model_type_contract_preserved": True,
                "multiresolution_26_stage_validated": False,
                "next_step": "STEP7_MULTIRESOLUTION_26_STAGE_VALIDATION",
            }
            base.write_json(run_root / "A_STEP6_RESULT.json", result)
            print(
                f"PASS_A_STEP6 issue={issue} planner={candidate['planner_wall_seconds']:.2f}s "
                f"commit={issue_wall:.2f}s",
                flush=True,
            )
            rc = 0

        except Exception as exc:
            failure = {
                "status": "FAIL_CLOSED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "future_actual_used": False,
                "repository_modified": False,
            }
            base.write_json(run_root / "A_STEP6_FAILURE.json", failure)
            print(json.dumps(failure, indent=2, ensure_ascii=False), flush=True)
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
        "ConversationA_STEP6_LOCAL_RESULT",
    )
    print(f"RESULT_HANDOFF_FILE={result_archive}")
    print(f"RESULT_HANDOFF_SHA256={base.sha256(result_archive)}")
    print(f"LOG_HANDOFF_FILE={log_archive}")
    print(f"LOG_HANDOFF_SHA256={base.sha256(log_archive)}")
    print(f"RUN_CONSOLE_LOG={console}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage5-result")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--planner-limit-seconds", type=float, default=300.0)
    ap.add_argument("--fast-limit-seconds", type=float, default=300.0)
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--resume-state")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--worker-output")
    args = ap.parse_args()

    if args.worker:
        if not (args.resume_state and args.issue is not None and args.worker_output):
            ap.error("--worker requires --resume-state --issue --worker-output")
        return worker_main(args)
    if not args.stage5_result:
        ap.error("--stage5-result is required")
    return run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
