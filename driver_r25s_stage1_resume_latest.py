#!/usr/bin/env python3
"""Resume the immutable R25R Stage-1 run from its latest verified POST state.

This driver does not modify R25R science.  It imports the byte-frozen R25R
bundle, verifies the original parent archives and every locally committed issue,
then continues at the first uncommitted issue.  Re-running this R25S driver is
safe: completed issues are retained and an incomplete issue directory is moved
to an audit quarantine before retry.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
import time


HERE = Path(__file__).resolve().parent
WORK = Path.home() / "mobile_ess_work"
ART = WORK / "frozen_artifacts"
R25R_ROOT = WORK / "build7c_r25r_stage1_resume136_retained_optimal_dual"
ROOT = WORK / "build7c_r25s_stage1_resumable"
RUN = ROOT / "stage1_54_of_54"
SCI = ROOT / "science"
SCI_BUNDLE = HERE / "R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz"
PARENT_R25P = ART / "ConversationA_R25P_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T021940.tar.gz"
PARENT_R25Q = ART / "ConversationA_R25Q_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T101350.tar.gz"
EXPECTED = {
    "science_bundle": "4c2e39b4f136f36a6d3c13f61acb93a7f32b256cfc75d06404cef8fe9ddf312d",
    "main": "911abe18479524b8e48cc058c4a6ed3b8ab9ce673d4de78780a71ca3b7f0a5cd",
    "decomp": "cab1b8cef906b08eaaa75d5e044fcb34ffc45183b24c5c4d8cfddb3508c58795",
    "r25p": "0ed41aa7bdc1f055dde5fd7c50e4ceffb4d4cc0a1795d0ec1b37d49481fa9833",
    "r25q": "8d8c8f15bdfbc3e9200aeebb88f8a262f4da2e727d1155ac76b989f42b7cc2b0",
}
THREADS = 4
_RUNTIME_LOCK_HANDLE = None


def acquire_runtime_lock(mode: str) -> None:
    """Prevent concurrent preflight/resume mutation of the R25S runtime."""
    global _RUNTIME_LOCK_HANDLE
    if _RUNTIME_LOCK_HANDLE is not None:
        raise RuntimeError("R25S runtime lock was requested twice in one process")
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("R25S driver must run in WSL/Linux for process locking") from exc
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / ".r25s_stage1_resumable.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip() or "unknown owner"
        handle.close()
        raise RuntimeError(
            "another R25S driver/solver is active; refusing concurrent mutation; "
            f"lock={path} owner={owner}"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps(
            {
                "schema_version": "r25s.runtime_lock.v1",
                "pid": os.getpid(),
                "mode": str(mode),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            sort_keys=True,
        )
        + "\n"
    )
    handle.flush()
    os.fsync(handle.fileno())
    os.set_inheritable(handle.fileno(), True)
    _RUNTIME_LOCK_HANDLE = handle


def runtime_lock_fd() -> int:
    if _RUNTIME_LOCK_HANDLE is None:
        raise RuntimeError("R25S runtime lock is not held")
    return int(_RUNTIME_LOCK_HANDLE.fileno())


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def issue_dir(issue: int) -> Path:
    target = RUN / f"issue_{issue:06d}"
    if target.is_dir():
        return target
    return R25R_ROOT / "stage1_54_of_54" / f"issue_{issue:06d}"


def validate_issue(issue: int) -> dict:
    directory = issue_dir(issue)
    decomp = load_json(directory / "ConversationA_R25M_B6_EXACT_DECOMPOSITION_AUDIT.json")
    term = load_json(directory / "BUILD7BR6_GUROBI_TERMINATION.json")
    transition = load_json(directory / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json")
    exact = load_json(directory / f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json")
    post = load_json(directory / "BUILD7C_POSTCOMMIT_STATE.json")
    try:
        gap = float(decomp["global_certified_gap"])
    except Exception:
        gap = math.inf
    numerical = True
    for key, gate in (("ConstrVio", 1e-6), ("BoundVio", 1e-6), ("IntVio", 1e-5)):
        try:
            numerical = numerical and math.isfinite(float(term[key])) and float(term[key]) <= gate
        except Exception:
            numerical = False
    policy = decomp.get("b6c5r4_policy") or {}
    unlimited_limits = all(
        policy.get(key) is None
        for key in (
            "root_CG_time_limit_s",
            "restricted_integer_time_limit_s",
            "polish_time_limit_s",
            "branch_price_time_limit_s",
            "branch_price_node_limit",
            "branch_price_child_CG_time_limit_s",
            "root_CG_iteration_limit",
        )
    )
    ok = bool(
        decomp.get("revision") == "R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME"
        and decomp.get("pricing_closed") is True
        and decomp.get("certificate_pass") is True
        and gap <= 0.03 + 1e-12
        and policy.get("unlimited_completion") is True
        and unlimited_limits
        and int(term.get("requested_threads", -1)) == THREADS
        and term.get("thread_policy_verified") is True
        and numerical
        and transition.get("status") == "PASS"
        and transition.get("h0_only_committed") is True
        and transition.get("future_actual_arrivals_read") is False
        and exact.get("hard_constraint_pass") is True
        and post.get("sha256") == transition.get("post_state_sha256")
        and isinstance(post.get("state"), dict)
        and int(post["state"].get("issue_step", -1)) == issue + 1
    )
    if not ok:
        raise RuntimeError(f"issue {issue} is not a complete authoritative R25R commit")
    return {
        "issue": issue,
        "global_certified_gap": gap,
        "pre_state_sha256": transition["pre_state_sha256"],
        "post_state_sha256": transition["post_state_sha256"],
        "directory": str(directory),
    }


def verified_commits() -> list[dict]:
    records = []
    expected_pre = "94eb40044d0089ce26fcc298675952a5a154277e48371412c4871edb447b7625"
    for issue in range(136, 167):
        post = issue_dir(issue) / "BUILD7C_POSTCOMMIT_STATE.json"
        if not post.is_file():
            break
        record = validate_issue(issue)
        if record["pre_state_sha256"] != expected_pre:
            raise RuntimeError(f"causal hash chain breaks before issue {issue}")
        expected_pre = record["post_state_sha256"]
        records.append(record)
    expected_issues = list(range(136, 136 + len(records)))
    if [record["issue"] for record in records] != expected_issues:
        raise RuntimeError("committed continuation issues are not contiguous")
    return records


def initialize() -> None:
    if ROOT.exists():
        marker = load_json(ROOT / "R25S_RESUMABLE_MARKER.json")
        if marker.get("schema_version") != "r25s.resumable.v1":
            raise RuntimeError(f"refusing to reuse unrecognized directory: {ROOT}")
        return
    ROOT.mkdir(parents=True)
    RUN.mkdir()
    SCI.mkdir()
    with tarfile.open(SCI_BUNDLE, "r:gz") as archive:
        try:
            archive.extractall(SCI, filter="data")
        except TypeError:
            archive.extractall(SCI)
    write_json(
        ROOT / "R25S_RESUMABLE_MARKER.json",
        {
            "schema_version": "r25s.resumable.v1",
            "immutable_science_sha256": EXPECTED["science_bundle"],
            "source_r25r_root": str(R25R_ROOT),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


def runtime_environment(resume_issue: int, resume_dir: Path, state_hash: str) -> dict[str, str]:
    env = os.environ.copy()
    # Clear every optional limit/stop that could silently weaken the frozen run.
    for key in list(env):
        if key.startswith("MOBILEESS_"):
            env.pop(key)
    env.update(
        {
            "MOBILEESS_OPT_HORIZON_STEPS": "54",
            "MOBILEESS_GUROBI_THREADS": "4",
            "MOBILEESS_GUROBI_ECON_MIPGAP": "0.03",
            "MOBILEESS_GUROBI_ROOT_METHOD": "2",
            "MOBILEESS_GUROBI_MIQCPMETHOD": "-1",
            "MOBILEESS_GUROBI_SOFTMEMLIMIT_GB": "8.0",
            "MOBILEESS_FINAL_HEURISTICS": "0.05",
            "MOBILEESS_EXACT_PCC_LEAF_ELIM": "0",
            "MOBILEESS_EXACT_IMPLIED_BOUNDS": "1",
            "MOBILEESS_BR14_PRODUCTION": "1",
            "MOBILEESS_BULK_MOBILITY_VARS": "1",
            "MOBILEESS_VECTOR_K3_PARETO": "1",
            "MOBILEESS_DISABLE_PARETO_CACHE": "1",
            "MOBILEESS_WORKER_FOUNDATION_CACHE": "0",
            "MOBILEESS_R24_PERMANENT_EXACT_REBASE": "1",
            "MOBILEESS_R25A_FORWARD_BACKWARD_PRUNE": "1",
            "MOBILEESS_R25B_ROUTE_DOMINANCE_AUDIT": "1",
            "MOBILEESS_R25D_RADIAL_GRID_PROJECTION": "1",
            "MOBILEESS_R25E_NODE_ARC_EXACT": "1",
            "MOBILEESS_R25E_PERSISTENT_STATIC_CONTEXT": "1",
            "MOBILEESS_R25G_HYBRID_STAY_BINARY": "1",
            "MOBILEESS_R25H_B1_CERTIFICATE_FOCUS": "1",
            "MOBILEESS_R25I_B2_NUMERICAL_RESCALING": "1",
            "MOBILEESS_R25K_B4_ROOT_BRANCH_STRENGTHENING": "1",
            "MOBILEESS_R25M_B6_EXACT_DECOMPOSITION": "1",
            "MOBILEESS_R25M_B6_KBEST": "64",
            "MOBILEESS_R25M_B6_PRICING_BATCH": "16",
            "MOBILEESS_R25M_B6_RC_AUDIT_TOL": "1e-4",
            "MOBILEESS_R25M_B6_PRICING_TOL": "1e-7",
            "MOBILEESS_R25N_B6C5R2_BARQCP_TOL": "1e-9",
            "MOBILEESS_R25M_B6R3_PRIMAL_KBEST": "96",
            "MOBILEESS_R25N_B6C5R3_PRIMAL_HEURISTICS": "0.20",
            "MOBILEESS_R25M_B6R3_BRANCH_PRICE": "1",
            "MOBILEESS_R25M_B6C2_CHILD_PRICING_BATCH": "16",
            "MOBILEESS_R25M_B6C3_DUAL_STABILIZATION": "0",
            "MOBILEESS_R25M_B6C4_STRONG_BRANCHING": "0",
            "MOBILEESS_R25N_B6C5R3_MOBILITY_FIRST": "1",
            "MOBILEESS_R25N_B6C5R3_FIXED_DUAL_MULTIWAY": "0",
            "MOBILEESS_R25N_B6C5R1_FIXED_DUAL_PREPASS": "0",
            "MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION": "1",
            "MOBILEESS_R25N_B6C5R4_FIXED_INTEGER_QCP_POLISH": "1",
            "MOBILEESS_R25N_B6C5R4_DISABLE_FIXED_DUAL_PREPASS": "1",
            "MOBILEESS_R25N_B6C5R4_POLISH_CONSTRVIO_GATE": "1e-6",
            "MOBILEESS_R25N_B6C5R4_POLISH_BOUNDVIO_GATE": "1e-7",
            "MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION": "1",
            "MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE": "1",
            "MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP": "5e-4",
            "MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET": "2",
            "MOBILEESS_R25Q_RESUME_STATE_PATH": str(resume_dir / "resume_state.json"),
            "MOBILEESS_R25Q_RESUME_HINT_DIR": str(resume_dir),
            "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME": "resume_moves.csv",
            "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME": "resume_mess.csv",
            "MOBILEESS_R25Q_RESUME_SOURCE": f"R25S verified causal POST through issue {resume_issue - 1}",
            "MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES": str(resume_issue - 113),
            "MOBILEESS_RESUME_STATE_SHA256": state_hash,
            "MOBILEESS_ROLL_START": "113",
            "MOBILEESS_ROLL_COUNT": "54",
            "MOBILEESS_RESUME_ISSUE": str(resume_issue),
        }
    )
    return env


def scientific_progress_monitor(stop: threading.Event, first_issue: int) -> None:
    """Report conservative global progress without changing frozen solver state."""

    last_signature = None
    while not stop.wait(5.0):
        try:
            issue = first_issue
            for candidate in range(first_issue, 167):
                directory = RUN / f"issue_{candidate:06d}"
                if directory.is_dir() and not (directory / "BUILD7C_POSTCOMMIT_STATE.json").is_file():
                    issue = candidate
            cg = load_json(RUN / f"issue_{issue:06d}" / "ConversationA_R25M_B6_CG_LIVE.json")
            heartbeat = load_json(RUN / f"issue_{issue:06d}_LIVE_HEARTBEAT.json")
            if not cg or not heartbeat:
                continue
            raw_lb = float(cg["rmp_objective"])
            rc_guard = max(
                float(cg["rc_audit_tolerance"]),
                float(cg["max_existing_lambda_rc_check_error"]),
            )
            mins = [float(value) for value in cg.get("min_reduced_cost", {}).values()]
            pricing_closed = bool(
                int(cg.get("new_columns", -1)) == 0
                and mins
                and all(value >= -rc_guard for value in mins)
            )
            if not pricing_closed:
                continue
            # Exact frozen R25R guarded_full_lb rule: one effective RC guard per
            # MESS plus a tiny objective-scale safety subtraction.
            mess_count = len(cg.get("min_reduced_cost", {}))
            global_lb = raw_lb - (mess_count * rc_guard + max(1e-6, 1e-9 * abs(raw_lb)))
            incumbent = float(heartbeat["objbst"])
            if not (math.isfinite(incumbent) and math.isfinite(global_lb)):
                continue
            if global_lb > incumbent:
                continue
            global_gap = (
                math.inf
                if abs(incumbent) <= 1e-12
                else max(0.0, (incumbent - global_lb) / abs(incumbent))
            )
            if global_lb < 0:
                required = global_lb / 1.03
            elif global_lb > 0:
                required = global_lb / 0.97
            else:
                required = 0.0
            signature = (issue, heartbeat.get("runtime_s"), incumbent, global_lb)
            if signature == last_signature:
                continue
            last_signature = signature
            record = {
                "schema_version": "r25s.scientific_progress.v1",
                "issue": issue,
                "CURRENT_INCUMBENT": incumbent,
                "RMP_NATIVE_GAP": heartbeat.get("relative_gap"),
                "RMP_NATIVE_OBJBOUND": heartbeat.get("objbnd"),
                "RMP_NATIVE_OBJBOUND_IS_GLOBAL_AUTHORITY": False,
                "GLOBAL_LOWER_BOUND": global_lb,
                "GLOBAL_LOWER_BOUND_AUTHORITY": "EXACT_PRICED_ROOT_WITH_FROZEN_NUMERICAL_GUARD",
                "GLOBAL_CERTIFIED_GAP": global_gap,
                "INCUMBENT_REQUIRED_FOR_3PCT": required,
                "GLOBAL_3PCT_REACHED_AT_ROOT_BOUND": global_gap <= 0.03 + 1e-12,
                "solver_runtime_seconds": heartbeat.get("runtime_s"),
            }
            write_json(ROOT / "R25S_SCIENTIFIC_PROGRESS_LIVE.json", record)
            native = heartbeat.get("relative_gap")
            native_text = "NA" if native is None else f"{100.0 * float(native):.3f}%"
            print(
                "[R25S SCIENTIFIC_PROGRESS] "
                f"issue={issue} CURRENT_INCUMBENT={incumbent:.6f} "
                f"RMP_NATIVE_GAP={native_text} GLOBAL_LOWER_BOUND={global_lb:.6f} "
                f"GLOBAL_CERTIFIED_GAP={100.0 * global_gap:.3f}% "
                f"INCUMBENT_REQUIRED_FOR_3PCT={required:.6f}",
                flush=True,
            )
        except Exception:
            # Monitoring is diagnostic only and must never perturb optimization.
            continue


def main() -> int:
    preflight_only = os.environ.get("MOBILEESS_R25S_PREFLIGHT_ONLY", "0") == "1"
    acquire_runtime_lock("PREFLIGHT" if preflight_only else "FULL_RESUME")
    for path, digest in ((SCI_BUNDLE, EXPECTED["science_bundle"]), (PARENT_R25P, EXPECTED["r25p"]), (PARENT_R25Q, EXPECTED["r25q"])):
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError(f"missing or changed frozen authority: {path}")
    if not R25R_ROOT.is_dir():
        raise RuntimeError(f"R25R interrupted runtime root is missing: {R25R_ROOT}")
    initialize()
    if sha(SCI / "main.py") != EXPECTED["main"] or sha(SCI / "r25m_b6_exact_path_decomposition.py") != EXPECTED["decomp"]:
        raise RuntimeError("R25S extracted science differs from frozen R25R")
    checks = []
    for line in (SCI / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split("  ", 1)
            checks.append(sha(SCI / relative) == digest)
    if not checks or not all(checks):
        raise RuntimeError("frozen R25R science CHECKSUMS failed")

    # Copy the original completed continuation once; never copy its incomplete issue.
    for issue in range(136, 167):
        source = R25R_ROOT / "stage1_54_of_54" / f"issue_{issue:06d}"
        target = RUN / f"issue_{issue:06d}"
        if target.exists() or not (source / "BUILD7C_POSTCOMMIT_STATE.json").is_file():
            continue
        shutil.copytree(source, target)

    commits = verified_commits()
    if not commits:
        raise RuntimeError("no verified R25R continuation commits found")
    last_issue = commits[-1]["issue"]
    if last_issue >= 166:
        print("R25S already has verified commits through issue 166; no solve required.")
        return 0
    resume_issue = last_issue + 1
    source_dir = issue_dir(last_issue)
    state_wrapper = load_json(source_dir / "BUILD7C_POSTCOMMIT_STATE.json")
    state_hash = str(state_wrapper["sha256"])
    write_json(
        ROOT / "R25S_RESUME_PREFLIGHT.json",
        {
            "status": "PASS",
            "immutable_r25r_science": True,
            "verified_authoritative_issues": resume_issue - 113,
            "resume_issue": resume_issue,
            "resume_state_sha256": state_hash,
            "remaining_issues": 167 - resume_issue,
            "threads": THREADS,
            "global_gap_target": 0.03,
            "solver_time_limits": None,
            "node_limits": None,
            "exclusive_runtime_lock_held": True,
            "preflight_mutates_issue_directories": False,
        },
    )
    if preflight_only:
        print(
            f"PASS_R25S_PREFLIGHT verified={resume_issue - 113}/54 "
            f"resume_issue={resume_issue} remaining={167 - resume_issue}",
            flush=True,
        )
        return 0

    resume = ROOT / "resume_authority"
    resume.mkdir(exist_ok=True)
    shutil.copy2(source_dir / "BUILD7C_POSTCOMMIT_STATE.json", resume / "resume_state.json")
    shutil.copy2(source_dir / "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv", resume / "resume_moves.csv")
    shutil.copy2(source_dir / "BUILD7B_FULL54_MESS_PLAN.csv", resume / "resume_mess.csv")

    incomplete = RUN / f"issue_{resume_issue:06d}"
    if incomplete.exists():
        quarantine = ROOT / "interrupted_attempts" / f"issue_{resume_issue:06d}_{time.strftime('%Y%m%dT%H%M%S')}"
        quarantine.parent.mkdir(exist_ok=True)
        shutil.move(str(incomplete), str(quarantine))
        print(f"[R25S] moved incomplete issue to {quarantine}", flush=True)
    stale_failure = RUN / "_FAILURE.json"
    if stale_failure.exists():
        failure_archive = ROOT / "interrupted_attempts" / (
            f"failure_before_issue_{resume_issue:06d}_{time.strftime('%Y%m%dT%H%M%S')}.json"
        )
        failure_archive.parent.mkdir(exist_ok=True)
        shutil.move(str(stale_failure), str(failure_archive))

    child = ROOT / "stage1_child.py"
    child.write_text(
        "import importlib.util,sys\n"
        "from pathlib import Path\n"
        "SCI=Path(sys.argv[1]);OUT=Path(sys.argv[2]);WORK=Path(sys.argv[3]);OUT.mkdir(parents=True,exist_ok=True)\n"
        "sys.path.insert(0,str(SCI))\n"
        "spec=importlib.util.spec_from_file_location('r25s_frozen_science',SCI/'main.py')\n"
        "mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)\n"
        "raise SystemExit(int(mod.rolling54_main(OUT,WORK)))\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, "-m", "py_compile", str(child), str(SCI / "main.py")], check=True)
    print(
        f"[R25S] verified {resume_issue - 113}/54; resuming issue {resume_issue}; "
        f"remaining {167 - resume_issue}; frozen AC/QCP/OpenDSS/3% contract unchanged.",
        flush=True,
    )
    stdout = RUN / "R25S_STAGE1_STDOUT_STDERR.txt"
    started = time.time()
    monitor_stop = threading.Event()
    monitor = threading.Thread(
        target=scientific_progress_monitor,
        args=(monitor_stop, resume_issue),
        name="r25s-scientific-progress",
        daemon=True,
    )
    monitor.start()
    with stdout.open("a", buffering=1, encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(child), str(SCI), str(RUN), str(WORK)],
            env=runtime_environment(resume_issue, resume, state_hash),
            pass_fds=(runtime_lock_fd(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                log.write(line)
                print(line, end="", flush=True)
        except KeyboardInterrupt:
            monitor_stop.set()
            process.terminate()
            process.wait(timeout=30)
            monitor.join(timeout=2)
            print("\n[R25S] interrupted; committed POST states remain resumable.", flush=True)
            return 130
        return_code = process.wait()
    monitor_stop.set()
    monitor.join(timeout=2)

    final = load_json(RUN / "_RESULT.json")
    all_commits = verified_commits()
    complete = bool(
        return_code == 0
        and len(all_commits) == 31
        and all_commits[-1]["issue"] == 166
        and final.get("authoritative_54_of_54") is True
        and final.get("all_54_global_3pct_certificates_pass") is True
    )
    summary = {
        "release": "R25S_RESUMABLE_WRAPPER_AROUND_IMMUTABLE_R25R",
        "status": "PASS_STAGE1_FINAL_FREEZE" if complete else "INCOMPLETE_OR_FAIL_CLOSED",
        "immutable_r25r_science": True,
        "parent_r25p_sha256": EXPECTED["r25p"],
        "parent_r25q_sha256": EXPECTED["r25q"],
        "verified_issue_count": 23 + len(all_commits),
        "continuation_records": all_commits,
        "child_return_code": return_code,
        "wall_seconds_this_invocation": time.time() - started,
        "final_result": final,
    }
    write_json(ROOT / "ConversationA_R25S_STAGE1_RUNTIME_RESULT.json", summary)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    bundle = ART / f"ConversationA_R25S_STAGE1_RUNTIME_RESULT_{stamp}.tar.gz"
    with tarfile.open(bundle, "w:gz", compresslevel=1) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and SCI not in path.parents:
                archive.add(path, arcname=path.relative_to(ROOT).as_posix())
    print(f"[R25S_STAGE1_STATUS] {summary['status']}", flush=True)
    print(f"[R25S_VERIFIED_ISSUES] {summary['verified_issue_count']} of 54", flush=True)
    print(f"ONLY_HANDOFF_FILE={bundle}", flush=True)
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
