#!/usr/bin/env python3
"""Resume Stage-1 with the R25T exact global-bound portfolio.

R25T preserves the completed R25R/R25S causal POST chain and changes solver
orchestration only for the first uncommitted issue.  The restricted path master
is a bounded incumbent generator.  Final authority is the maximum of the exact
all-column priced-root lower bound and the original compact MIQCP native bound.
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
SOURCE_SCI = HERE / "science"
WORK = Path.home() / "mobile_ess_work"
ART = WORK / "frozen_artifacts"
R25R_ROOT = WORK / "build7c_r25r_stage1_resume136_retained_optimal_dual"
R25S_ROOT = WORK / "build7c_r25s_stage1_resumable"
ROOT = WORK / "build7c_r25t_b6c6_stage1_global_bound_portfolio"
RUN = ROOT / "stage1_54_of_54"
SCI = ROOT / "science"
PARENT_R25P = ART / "ConversationA_R25P_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T021940.tar.gz"
PARENT_R25Q = ART / "ConversationA_R25Q_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T101350.tar.gz"
EXPECTED = {
    "main": "a44ea59574395e30127b889eb38f379853b5773b202339f2a0d683a7ded81230",
    "decomp": "109645df1662513eb312bc46761976fc9e0db81169e70ca0451d07425f09b937",
    "checksums": "9325e5a65131c11c6eff46ef2a8c4406e9fa0c0b8f286d083e397e875b0ebb3f",
    "r25p": "0ed41aa7bdc1f055dde5fd7c50e4ceffb4d4cc0a1795d0ec1b37d49481fa9833",
    "r25q": "8d8c8f15bdfbc3e9200aeebb88f8a262f4da2e727d1155ac76b989f42b7cc2b0",
}
LEGACY_R25T_DECOMP_SHA256 = "fd606351cbd17b7cfc63a79d08177e3d3a8485bab86f3870e352bb2eab3a3786"
COPY_AUDIT_R25T_DECOMP_SHA256 = "f4434abd4ef98cdc66fb3148dc8497f11dba706499069aafdeba8290205995ab"
THREADS = 4
_RUNTIME_LOCK_HANDLE = None


def acquire_runtime_lock(mode: str) -> None:
    """Hold one exclusive lock for the complete driver/child lifetime.

    The lock lives outside ``ROOT`` so a second invocation cannot refresh the
    science copy or quarantine an issue directory while Gurobi is using its log
    and nodefile paths.  The descriptor is explicitly inherited by the child,
    which also protects an orphaned solve if the parent driver is killed.
    """
    global _RUNTIME_LOCK_HANDLE
    if _RUNTIME_LOCK_HANDLE is not None:
        raise RuntimeError("R25T runtime lock was requested twice in one process")
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("R25T driver must run in WSL/Linux for process locking") from exc
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / ".r25t_stage1_global_bound_portfolio.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip() or "unknown owner"
        handle.close()
        raise RuntimeError(
            "another R25T driver/solver is active; refusing concurrent mutation; "
            f"lock={path} owner={owner}"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps(
            {
                "schema_version": "r25t.runtime_lock.v1",
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
        raise RuntimeError("R25T runtime lock is not held")
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


def verify_science_manifest(root: Path) -> None:
    manifest = root / "CHECKSUMS.sha256"
    if not manifest.is_file() or sha(manifest) != EXPECTED["checksums"]:
        raise RuntimeError(f"R25T science manifest missing or changed: {manifest}")
    rows = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise RuntimeError("R25T science manifest is empty")
    for row in rows:
        digest, relative = row.split("  ", 1)
        target = root / relative
        if not target.is_file() or sha(target) != digest:
            raise RuntimeError(f"R25T science manifest mismatch: {relative}")


def prior_issue_dir(issue: int) -> Path | None:
    for base in (R25S_ROOT, R25R_ROOT):
        candidate = base / "stage1_54_of_54" / f"issue_{issue:06d}"
        if (candidate / "BUILD7C_POSTCOMMIT_STATE.json").is_file():
            return candidate
    return None


def issue_dir(issue: int) -> Path:
    target = RUN / f"issue_{issue:06d}"
    if target.is_dir():
        return target
    prior = prior_issue_dir(issue)
    return prior if prior is not None else target


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
    revision = decomp.get("revision")
    if revision == "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO":
        portfolio = decomp.get("r25t_global_portfolio_policy") or {}
        compact = decomp.get("compact_exact_global_phase") or {}
        solver_policy_ok = bool(
            portfolio.get("enabled") is True
            and portfolio.get("restricted_master_objbound_global_authority") is False
            and portfolio.get("overall_exact_completion_time_limit_s") is None
            and compact.get("certificate_pass") is True
            and compact.get("compact_objbound_is_global_authority") is True
            and compact.get("restricted_objbound_promoted") is False
        )
    else:
        policy = decomp.get("b6c5r4_policy") or {}
        solver_policy_ok = bool(
            revision == "R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME"
            and policy.get("unlimited_completion") is True
            and all(
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
        )
    ok = bool(
        solver_policy_ok
        and decomp.get("pricing_closed") is True
        and decomp.get("certificate_pass") is True
        and gap <= 0.03 + 1e-12
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
        raise RuntimeError(f"issue {issue} is not a complete authoritative R25R/R25T commit")
    return {
        "issue": issue,
        "revision": revision,
        "global_certified_gap": gap,
        "pre_state_sha256": transition["pre_state_sha256"],
        "post_state_sha256": transition["post_state_sha256"],
        "directory": str(directory),
    }


def verified_commits() -> list[dict]:
    records = []
    expected_pre = "94eb40044d0089ce26fcc298675952a5a154277e48371412c4871edb447b7625"
    for issue in range(136, 167):
        if not (issue_dir(issue) / "BUILD7C_POSTCOMMIT_STATE.json").is_file():
            break
        record = validate_issue(issue)
        if record["pre_state_sha256"] != expected_pre:
            raise RuntimeError(f"causal hash chain breaks before issue {issue}")
        expected_pre = record["post_state_sha256"]
        records.append(record)
    return records


def initialize() -> None:
    if ROOT.exists():
        marker = load_json(ROOT / "R25T_RESUMABLE_MARKER.json")
        if marker.get("schema_version") not in ("r25t.resumable.v1", "r25t.resumable.v2"):
            raise RuntimeError(f"refusing to reuse unrecognized directory: {ROOT}")
        prior_decomp = marker.get("source_decomp_sha256")
        if prior_decomp not in (
            EXPECTED["decomp"],
            LEGACY_R25T_DECOMP_SHA256,
            COPY_AUDIT_R25T_DECOMP_SHA256,
        ):
            raise RuntimeError("existing R25T runtime uses a different solver authority")
        if not SCI.is_dir():
            raise RuntimeError(f"existing R25T runtime is missing science directory: {SCI}")
        # In-place R25T audit repair: completed causal commits remain immutable,
        # while the runtime science copy is refreshed from the hash-locked source.
        # This migration changes no feasible set, objective, or lower-bound rule.
        shutil.copytree(
            SOURCE_SCI,
            SCI,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        write_json(
            ROOT / "R25T_RESUMABLE_MARKER.json",
            {
                "schema_version": "r25t.resumable.v2",
                "source_main_sha256": EXPECTED["main"],
                "source_decomp_sha256": EXPECTED["decomp"],
                "solver_revision": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
                "created_at": marker.get("created_at"),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "upgraded_from_decomp_sha256": prior_decomp if prior_decomp != EXPECTED["decomp"] else None,
                "upgrade_scope": "solver orchestration and runtime safety only; mathematical authority unchanged",
            },
        )
        return
    if not SOURCE_SCI.is_dir():
        raise RuntimeError(f"missing R25T science source: {SOURCE_SCI}")
    ROOT.mkdir(parents=True)
    RUN.mkdir()
    shutil.copytree(SOURCE_SCI, SCI, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    write_json(
        ROOT / "R25T_RESUMABLE_MARKER.json",
        {
            "schema_version": "r25t.resumable.v2",
            "source_main_sha256": EXPECTED["main"],
            "source_decomp_sha256": EXPECTED["decomp"],
            "solver_revision": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


def runtime_environment(resume_issue: int, resume_dir: Path, state_hash: str) -> dict[str, str]:
    env = os.environ.copy()
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
            "MOBILEESS_R25N_B6C5R4_POLISH_CONSTR_GATE": "1e-6",
            "MOBILEESS_R25N_B6C5R4_POLISH_BOUND_GATE": "1e-7",
            "MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION": "1",
            "MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE": "1",
            "MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP": "5e-4",
            "MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET": "2",
            "MOBILEESS_R25T_GLOBAL_PORTFOLIO": "1",
            "MOBILEESS_R25T_PRIMAL_MIN_SECONDS": "60",
            "MOBILEESS_R25T_PRIMAL_STALL_SECONDS": "120",
            "MOBILEESS_R25T_PRIMAL_MAX_SECONDS": "600",
            "MOBILEESS_R25T_PRIMAL_MAX_NODES": "200000",
            "MOBILEESS_R25T_MEANINGFUL_IMPROVEMENT_FRACTION": "0.02",
            "MOBILEESS_R25T_COMPACT_MIPFOCUS": "3",
            "MOBILEESS_R25Q_RESUME_STATE_PATH": str(resume_dir / "resume_state.json"),
            "MOBILEESS_R25Q_RESUME_HINT_DIR": str(resume_dir),
            "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME": "resume_moves.csv",
            "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME": "resume_mess.csv",
            "MOBILEESS_R25Q_RESUME_SOURCE": f"R25T verified causal POST through issue {resume_issue - 1}",
            "MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES": str(resume_issue - 113),
            "MOBILEESS_RESUME_STATE_SHA256": state_hash,
            "MOBILEESS_ROLL_START": "113",
            "MOBILEESS_ROLL_COUNT": "54",
            "MOBILEESS_RESUME_ISSUE": str(resume_issue),
        }
    )
    return env


def scientific_progress_monitor(stop: threading.Event, first_issue: int) -> None:
    last_signature = None
    while not stop.wait(5.0):
        try:
            issue = first_issue
            for candidate in range(first_issue, 167):
                directory = RUN / f"issue_{candidate:06d}"
                if directory.is_dir() and not (directory / "BUILD7C_POSTCOMMIT_STATE.json").is_file():
                    issue = candidate
            directory = RUN / f"issue_{issue:06d}"
            compact = load_json(directory / "ConversationA_R25T_COMPACT_EXACT_LIVE.json")
            if compact:
                phase = "COMPACT_EXACT_BB"
                incumbent = float(compact["incumbent"])
                global_lb = float(compact["combined_global_lower_bound"])
                global_gap = float(compact["global_certified_gap"])
                native_gap = None
                runtime = compact.get("runtime_s")
            else:
                cg = load_json(directory / "ConversationA_R25M_B6_CG_LIVE.json")
                heartbeat = load_json(RUN / f"issue_{issue:06d}_LIVE_HEARTBEAT.json")
                if not cg or not heartbeat:
                    continue
                raw_lb = float(cg["rmp_objective"])
                guard = max(float(cg["rc_audit_tolerance"]), float(cg["max_existing_lambda_rc_check_error"]))
                mins = [float(value) for value in cg.get("min_reduced_cost", {}).values()]
                if not (int(cg.get("new_columns", -1)) == 0 and mins and all(value >= -guard for value in mins)):
                    continue
                global_lb = raw_lb - (len(mins) * guard + max(1e-6, 1e-9 * abs(raw_lb)))
                incumbent = float(heartbeat["objbst"])
                global_gap = max(0.0, (incumbent - global_lb) / abs(incumbent))
                native_gap = heartbeat.get("relative_gap")
                runtime = heartbeat.get("runtime_s")
                phase = "BOUNDED_RESTRICTED_PRIMAL"
            required = global_lb / 1.03 if global_lb < 0 else global_lb / 0.97 if global_lb > 0 else 0.0
            signature = (issue, phase, runtime, incumbent, global_lb)
            if signature == last_signature:
                continue
            last_signature = signature
            record = {
                "schema_version": "r25t.scientific_progress.v1",
                "issue": issue,
                "PHASE": phase,
                "CURRENT_INCUMBENT": incumbent,
                "RMP_NATIVE_GAP": native_gap,
                "RMP_NATIVE_OBJBOUND_IS_GLOBAL_AUTHORITY": False,
                "GLOBAL_LOWER_BOUND": global_lb,
                "GLOBAL_CERTIFIED_GAP": global_gap,
                "INCUMBENT_REQUIRED_FOR_3PCT": required,
                "GLOBAL_3PCT_REACHED": global_gap <= 0.03 + 1e-12,
                "solver_runtime_seconds": runtime,
            }
            write_json(ROOT / "R25T_SCIENTIFIC_PROGRESS_LIVE.json", record)
            native_text = "NA" if native_gap is None else f"{100.0 * float(native_gap):.3f}%"
            print(
                "[R25T SCIENTIFIC_PROGRESS] "
                f"issue={issue} PHASE={phase} CURRENT_INCUMBENT={incumbent:.6f} "
                f"RMP_NATIVE_GAP={native_text} GLOBAL_LOWER_BOUND={global_lb:.6f} "
                f"GLOBAL_CERTIFIED_GAP={100.0 * global_gap:.3f}% "
                f"INCUMBENT_REQUIRED_FOR_3PCT={required:.6f}",
                flush=True,
            )
        except Exception:
            continue


def main() -> int:
    preflight_only = os.environ.get("MOBILEESS_R25T_PREFLIGHT_ONLY", "0") == "1"
    acquire_runtime_lock("PREFLIGHT" if preflight_only else "FULL_RESUME")
    for path, digest in ((PARENT_R25P, EXPECTED["r25p"]), (PARENT_R25Q, EXPECTED["r25q"])):
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError(f"missing or changed frozen parent authority: {path}")
    if sha(SOURCE_SCI / "main.py") != EXPECTED["main"] or sha(SOURCE_SCI / "r25m_b6_exact_path_decomposition.py") != EXPECTED["decomp"]:
        raise RuntimeError("R25T source hash differs from the reviewed authority")
    verify_science_manifest(SOURCE_SCI)
    initialize()
    if sha(SCI / "main.py") != EXPECTED["main"] or sha(SCI / "r25m_b6_exact_path_decomposition.py") != EXPECTED["decomp"]:
        raise RuntimeError("copied R25T runtime science differs from source authority")
    verify_science_manifest(SCI)

    # Import every contiguous completed predecessor once.  Incomplete directories
    # are never copied, and an existing R25T commit always wins.
    for issue in range(136, 167):
        target = RUN / f"issue_{issue:06d}"
        if target.exists():
            continue
        source = prior_issue_dir(issue)
        if source is None:
            break
        shutil.copytree(source, target)

    commits = verified_commits()
    if not commits:
        raise RuntimeError("no verified R25R/R25S continuation commits found")
    last_issue = commits[-1]["issue"]
    if last_issue >= 166:
        print("R25T already has verified commits through issue 166; no solve required.")
        return 0
    resume_issue = last_issue + 1
    source_dir = issue_dir(last_issue)
    state_wrapper = load_json(source_dir / "BUILD7C_POSTCOMMIT_STATE.json")
    state_hash = str(state_wrapper["sha256"])
    write_json(
        ROOT / "R25T_RESUME_PREFLIGHT.json",
        {
            "status": "PASS",
            "solver_revision": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
            "verified_authoritative_issues": resume_issue - 113,
            "resume_issue": resume_issue,
            "resume_state_sha256": state_hash,
            "remaining_issues": 167 - resume_issue,
            "threads": THREADS,
            "global_gap_target": 0.03,
            "overall_solver_time_limit": None,
            "restricted_primal_phase": {"min_s": 60, "stall_s": 120, "max_s": 600, "max_nodes": 200000},
            "AC_QCP_changed": False,
            "exclusive_runtime_lock_held": True,
            "preflight_mutates_issue_directories": False,
        },
    )
    # This return must remain before resume-authority writes, incomplete-issue
    # quarantine, child generation, and process launch.  Preflight is diagnostic
    # and can never rename paths belonging to a solver.
    if preflight_only:
        print(f"PASS_R25T_PREFLIGHT verified={resume_issue - 113}/54 resume_issue={resume_issue} remaining={167 - resume_issue}", flush=True)
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
        print(f"[R25T] moved incomplete issue to {quarantine}", flush=True)
    stale_failure = RUN / "_FAILURE.json"
    if stale_failure.exists():
        archive = ROOT / "interrupted_attempts" / f"failure_before_issue_{resume_issue:06d}_{time.strftime('%Y%m%dT%H%M%S')}.json"
        archive.parent.mkdir(exist_ok=True)
        shutil.move(str(stale_failure), str(archive))

    child = ROOT / "stage1_child.py"
    child.write_text(
        "import importlib.util,sys\n"
        "from pathlib import Path\n"
        "SCI=Path(sys.argv[1]);OUT=Path(sys.argv[2]);WORK=Path(sys.argv[3]);OUT.mkdir(parents=True,exist_ok=True)\n"
        "sys.path.insert(0,str(SCI))\n"
        "spec=importlib.util.spec_from_file_location('r25t_science',SCI/'main.py')\n"
        "mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)\n"
        "raise SystemExit(int(mod.rolling54_main(OUT,WORK)))\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, "-m", "py_compile", str(child), str(SCI / "main.py"), str(SCI / "r25m_b6_exact_path_decomposition.py")], check=True)
    print(
        f"[R25T] verified {resume_issue - 113}/54; resuming issue {resume_issue}; remaining {167 - resume_issue}; "
        "AC/QCP/OpenDSS/global-3% contract unchanged.",
        flush=True,
    )
    stdout = RUN / "R25T_STAGE1_STDOUT_STDERR.txt"
    started = time.time()
    monitor_stop = threading.Event()
    monitor = threading.Thread(target=scientific_progress_monitor, args=(monitor_stop, resume_issue), daemon=True)
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
            print("\n[R25T] interrupted; committed POST states remain resumable.", flush=True)
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
        "release": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
        "status": "PASS_STAGE1_FINAL_FREEZE" if complete else "INCOMPLETE_OR_FAIL_CLOSED",
        "parent_r25p_sha256": EXPECTED["r25p"],
        "parent_r25q_sha256": EXPECTED["r25q"],
        "source_decomp_sha256": EXPECTED["decomp"],
        "verified_issue_count": 23 + len(all_commits),
        "continuation_records": all_commits,
        "child_return_code": return_code,
        "wall_seconds_this_invocation": time.time() - started,
        "final_result": final,
    }
    write_json(ROOT / "ConversationA_R25T_STAGE1_RUNTIME_RESULT.json", summary)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    bundle = ART / f"ConversationA_R25T_STAGE1_RUNTIME_RESULT_{stamp}.tar.gz"
    with tarfile.open(bundle, "w:gz", compresslevel=1) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and SCI not in path.parents:
                archive.add(path, arcname=path.relative_to(ROOT).as_posix())
    print(f"[R25T_STAGE1_STATUS] {summary['status']}", flush=True)
    print(f"[R25T_VERIFIED_ISSUES] {summary['verified_issue_count']} of 54", flush=True)
    print(f"ONLY_HANDOFF_FILE={bundle}", flush=True)
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
