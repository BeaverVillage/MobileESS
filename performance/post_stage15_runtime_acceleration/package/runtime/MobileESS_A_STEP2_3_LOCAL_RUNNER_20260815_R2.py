#!/usr/bin/env python3
"""Conversation A local 단계 2~3 runner for Mobile ESS K9-H7.

Purpose
-------
This file is intentionally runnable from Windows Downloads through WSL. It does
not modify the Git repository, does not use Codex, and does not alter frozen
단계 1 science. It uses the frozen science source as a read-only model builder,
intercepts the exact decomposition call *before* its expensive 단계 1 solve,
fixes the frozen issue-113 slow/discrete Route/Work plan, solves the conditioned
fast AC-aware model with real Gurobi, then lets the existing rolling transition
code execute Fresh Exact OpenDSS and commit exactly h0.

Outputs are written to an isolated run directory and packaged as one tar.gz next
to this script so the user can upload the single handoff archive back to ChatGPT.

This runner makes NO online/global-3%-optimality claim. The 3% value, when used
as a Gurobi stopping tolerance in the reduced conditioned model, is only an
operational solve tolerance. The frozen R25T 단계 1 54/54 certificate remains a
separate offline authority.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from typing import Any, Mapping

EXPECTED_PR2_HEAD = "358a2699501d7465a543179c2ad40db64a383cf9"
EXPECTED_SOURCE_SHA256 = {
    "science/main.py": "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9",
    "science/EXACT_GRID_RUNNER_24SERVICE.py": "591fda942a67c878332b0bfd485852c771cf2a4fc110fb7b073567833610f850",
    "science/BUILD7B_CONTRACT.json": "4e3802e04bd4fee9a4a164f6e866bb028670b81fcd1d6cb5df7b89f9be3d4fb2",
    "science/embedded/BUILD7BR4_PASS_AUTHORITY.tar.gz": "d164d0349d998c88df43c6cf759ffa3f6c278e96f61b7e157a5176920a6aba47",
}
STAGE1_FINAL_ARCHIVE_SHA256 = "4bedaab45a4270b4c4bdc5d6f744c0a4060a7f6b05cfac82db037c44453964fb"
STAGE1_FINAL_ARCHIVE_NAME = "ConversationA_R25T_STAGE1_RUNTIME_RESULT_20260815T021614.tar.gz"
PYTHON_AUTHORITY = "/home/jaewon/miniconda3/envs/power_v61/bin/python"

RESULT_ROOT = Path("/home/jaewon/mobile_ess_work/frozen_artifacts")
LOG_ROOT = Path("/home/jaewon/mobile_ess_work/logs")
SCRATCH_ROOT = Path("/home/jaewon/mobile_ess_work/conversation_a_step_runs")


class ExpectedStop(RuntimeError):
    pass


class Tee(io.TextIOBase):
    def __init__(self, *streams: io.TextIOBase) -> None:
        self.streams = streams

    def write(self, s: str) -> int:
        for stream in self.streams:
            stream.write(s)
            stream.flush()
        return len(s)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def now_tag() -> str:
    return dt.datetime.now().strftime("%Y%m%dT%H%M%S")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if cp.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
    return cp.stdout.strip()


def locate_repo(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("MOBILEESS_REPO")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            Path("/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS/github_MobileESS"),
            Path("/mnt/c/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/github_MobileESS"),
            Path.home() / "MobileESS",
            Path.home() / "mobile_ess_work" / "github_MobileESS",
        ]
    )
    for path in candidates:
        if (path / ".git").exists() and (path / "science/main.py").is_file():
            return path.resolve()
    raise FileNotFoundError(
        "MobileESS Git repository not found. Use --repo /path/to/github_MobileESS."
    )


def assert_source_authority(repo: Path) -> dict[str, Any]:
    records = []
    failures = []
    for rel, expected in EXPECTED_SOURCE_SHA256.items():
        path = repo / rel
        actual = sha256(path) if path.is_file() else None
        ok = actual == expected
        records.append(
            {
                "path": rel,
                "exists": path.is_file(),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "pass": ok,
            }
        )
        if not ok:
            failures.append(rel)
    if failures:
        raise RuntimeError("Frozen source SHA mismatch: " + ", ".join(failures))
    head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain=v1")
    return {
        "expected_pr2_head": EXPECTED_PR2_HEAD,
        "actual_git_head": head,
        "head_matches_expected_pr2": head == EXPECTED_PR2_HEAD,
        "working_tree_dirty": bool(status),
        "working_tree_status": status.splitlines()[:100],
        "frozen_source_records": records,
        "frozen_source_bytes_verified": True,
        "repository_modified_by_runner": False,
    }


def assert_no_active_r25t(work: Path) -> None:
    lock_path = work / ".r25t_stage1_global_bound_portfolio.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip()
            raise RuntimeError(f"Active R25T lock detected: {owner}") from exc
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def acquire_stage2_lock(work: Path):
    path = work / ".conversation_a_stage2_local.lock"
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip()
        raise RuntimeError(f"Another Conversation-A 단계 2 runner is active: {owner}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "started": dt.datetime.now().isoformat()}) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def find_stage1_archive(work: Path) -> dict[str, Any]:
    candidates = [
        work / "frozen_artifacts" / STAGE1_FINAL_ARCHIVE_NAME,
        Path("/mnt/c/Users/kjw39/Downloads") / STAGE1_FINAL_ARCHIVE_NAME,
    ]
    for p in candidates:
        if p.is_file():
            actual = sha256(p)
            return {
                "path": str(p),
                "sha256": actual,
                "expected_sha256": STAGE1_FINAL_ARCHIVE_SHA256,
                "pass": actual == STAGE1_FINAL_ARCHIVE_SHA256,
            }
    return {
        "path": None,
        "sha256": None,
        "expected_sha256": STAGE1_FINAL_ARCHIVE_SHA256,
        "pass": False,
        "note": "Archive not required to build issue113 because the frozen embedded PASS authority is used, but final Stage1 archive presence is recorded when available.",
    }


def dependency_preflight() -> dict[str, Any]:
    result = {"python_executable": sys.executable, "expected_python": PYTHON_AUTHORITY}
    for name in ("numpy", "pandas", "gurobipy", "opendssdirect", "pyarrow"):
        try:
            mod = __import__(name)
            result[name] = {"available": True, "version": getattr(mod, "__version__", None)}
        except Exception as exc:
            result[name] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    missing = [k for k, v in result.items() if isinstance(v, dict) and v.get("available") is False]
    if missing:
        raise RuntimeError("Missing runtime dependencies: " + ", ".join(missing))
    try:
        import gurobipy as gp
        m = gp.Model("A_STAGE2_LICENSE_CHECK")
        m.Params.OutputFlag = 0
        x = m.addVar(lb=0.0, ub=1.0)
        m.setObjective(x)
        m.optimize()
        result["gurobi_license_check"] = {
            "status": int(m.Status),
            "sol_count": int(m.SolCount),
            "pass": int(m.SolCount) >= 1,
        }
        m.dispose()
    except Exception as exc:
        raise RuntimeError(f"Gurobi license smoke failed: {exc}") from exc
    return result


def set_science_environment() -> None:
    # Clear inherited MobileESS switches to avoid accidental cross-run policy leakage.
    for key in list(os.environ):
        if key.startswith("MOBILEESS_"):
            os.environ.pop(key, None)
    os.environ.update(
        {
            "MOBILEESS_OPT_HORIZON_STEPS": "54",
            "MOBILEESS_ROLL_ISSUE": "113",
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
            # Keep this ON only to enter the existing pre-solve handoff point.
            # The runner replaces the decomposition function with a slow-plan
            # conditioning solve; no R25T branch-price/global certificate is run.
            "MOBILEESS_R25M_B6_EXACT_DECOMPOSITION": "1",
            "MOBILEESS_R25M_B6_KBEST": "64",
            "MOBILEESS_R25M_B6_PRICING_BATCH": "32",
            "MOBILEESS_R25M_B6_RC_AUDIT_TOL": "1e-4",
            "MOBILEESS_R25M_B6_PRICING_TOL": "1e-7",
            "MOBILEESS_R25N_B6C5R2_BARQCP_TOL": "1e-9",
            "MOBILEESS_R25M_B6R3_PRIMAL_KBEST": "64",
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
            # This is an R26 operational replay, not a Stage1 finalization run.
            "MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION": "0",
            "MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE": "1",
            "MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP": "5e-4",
            "MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET": "0",
            "MOBILEESS_R25X_SPARSE_TAIL_PRICING_BATCH": "64",
            "MOBILEESS_R25X_SPARSE_TAIL_MAX_ACTIVE_MESS": "2",
            "MOBILEESS_R25T_GLOBAL_PORTFOLIO": "0",
            "MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART": "0",
            "MOBILEESS_ROLL_START": "113",
            "MOBILEESS_ROLL_COUNT": "54",
            "MOBILEESS_RESUME_ISSUE": "113",
        }
    )


def load_science(repo: Path):
    set_science_environment()
    science = repo / "science"
    sys.path.insert(0, str(science))
    sys.path.insert(0, str(repo))
    spec = importlib.util.spec_from_file_location("mobileess_a_stage2_science_main", science / "main.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to import frozen science/main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tar_member_bytes(archive: Path, basename: str) -> bytes:
    hits = []
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            if Path(member.name).name == basename and member.isfile():
                hits.append(member)
        if len(hits) != 1:
            raise RuntimeError(f"{archive.name}: expected one {basename}, found {len(hits)}")
        fh = tf.extractfile(hits[0])
        if fh is None:
            raise RuntimeError(f"Cannot read {basename} from {archive}")
        return fh.read()


def load_issue113_reference(repo: Path, temp: Path) -> dict[str, Any]:
    import pandas as pd
    archive = repo / "science/embedded/BUILD7BR4_PASS_AUTHORITY.tar.gz"
    if sha256(archive) != EXPECTED_SOURCE_SHA256["science/embedded/BUILD7BR4_PASS_AUTHORITY.tar.gz"]:
        raise RuntimeError("Embedded issue113 PASS archive SHA drift")
    names = [
        "BUILD7B_FULL54_JOB_PLAN.csv",
        "BUILD7B_FULL54_MESS_PLAN.csv",
        "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv",
    ]
    out = {}
    for name in names:
        path = temp / name
        path.write_bytes(_tar_member_bytes(archive, name))
        out[name] = pd.read_csv(path)
    # Optional reference diagnostics if present.
    for name in (
        "BUILD7BR6_GUROBI_TERMINATION.json",
        "BUILD7C_R7_ECONOMIC_GAP_SEMANTICS_AUDIT.json",
    ):
        try:
            raw = _tar_member_bytes(archive, name)
            out[name] = json.loads(raw.decode("utf-8"))
        except Exception:
            pass
    return out


def build_reference_index(work: Path) -> dict[int, Path]:
    index: dict[int, list[Path]] = {}
    for root in work.glob("build7c_*/stage1_54_of_54"):
        if not root.is_dir():
            continue
        for issue_dir in root.glob("issue_??????"):
            try:
                issue = int(issue_dir.name.split("_")[-1])
            except Exception:
                continue
            needed = [
                issue_dir / "BUILD7B_FULL54_JOB_PLAN.csv",
                issue_dir / "BUILD7B_FULL54_MESS_PLAN.csv",
                issue_dir / "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv",
                issue_dir / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",
            ]
            if all(p.is_file() for p in needed):
                index.setdefault(issue, []).append(issue_dir)
    selected: dict[int, Path] = {}
    def score(path: Path) -> tuple[int, float]:
        s = str(path).lower()
        priority = 0
        for key, val in (("r25t", 60), ("r25s", 50), ("r25r", 40), ("r25q", 30), ("r25p", 20)):
            if key in s:
                priority = max(priority, val)
        return priority, path.stat().st_mtime
    for issue, paths in index.items():
        good = []
        for path in paths:
            try:
                cert = json.loads((path / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json").read_text())
                if cert.get("status") == "PASS" and cert.get("h0_only_committed") is True:
                    good.append(path)
            except Exception:
                continue
        if good:
            selected[issue] = max(good, key=score)
    return selected


def load_reference_issue(issue: int, repo: Path, temp: Path, ref_index: Mapping[int, Path]) -> dict[str, Any]:
    import pandas as pd
    if issue == 113:
        return load_issue113_reference(repo, temp)
    directory = ref_index.get(issue)
    if directory is None:
        raise RuntimeError(f"No authoritative reference-plan directory found for issue {issue}")
    result = {
        "BUILD7B_FULL54_JOB_PLAN.csv": pd.read_csv(directory / "BUILD7B_FULL54_JOB_PLAN.csv"),
        "BUILD7B_FULL54_MESS_PLAN.csv": pd.read_csv(directory / "BUILD7B_FULL54_MESS_PLAN.csv"),
        "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv": pd.read_csv(directory / "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"),
        "reference_directory": str(directory),
    }
    for name in ("BUILD7BR6_GUROBI_TERMINATION.json", "BUILD7C_R7_ECONOMIC_GAP_SEMANTICS_AUDIT.json"):
        path = directory / name
        if path.is_file():
            try:
                result[name] = json.loads(path.read_text())
            except Exception:
                pass
    return result


def _set_fixed(var: Any, value: float, *, relax_integer: bool = True) -> None:
    value = float(value)
    lb = float(var.LB)
    ub = float(var.UB)
    if value < lb - 1e-8 or value > ub + 1e-8:
        raise RuntimeError(f"Fix value {value} violates {var.VarName} bounds [{lb},{ub}]")
    var.LB = value
    var.UB = value
    if relax_integer and str(var.VType).upper() in {"B", "I", "S", "N"}:
        var.VType = "C"


def apply_reference_slow_plan(build_locals: Mapping[str, Any], ref: Mapping[str, Any]) -> dict[str, Any]:
    x = build_locals["x"]
    defer = build_locals["defer"]
    stay = build_locals["stay"]
    mv = build_locals["mv"]
    node_occ = build_locals.get("node_occ", {})
    moves = build_locals["moves"]
    model = build_locals["m"]

    job_df = ref["BUILD7B_FULL54_JOB_PLAN.csv"]
    mess_df = ref["BUILD7B_FULL54_MESS_PLAN.csv"]
    move_df = ref["BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"]

    selected_x = {
        (str(r.job_uid), str(r.destination_IDC_id), str(r.rack_pool_id), int(r.start_step))
        for r in job_df.itertuples(index=False)
    }
    x_keys = set(x)
    missing_selected_x = sorted(selected_x - x_keys)
    if missing_selected_x:
        raise RuntimeError(f"Reference Job choices absent from current model: {missing_selected_x[:10]}")
    for key, var in x.items():
        _set_fixed(var, 1.0 if key in selected_x else 0.0)

    selected_jobs = {key[0] for key in selected_x}
    for job_uid, var in defer.items():
        _set_fixed(var, 0.0 if str(job_uid) in selected_jobs else 1.0)

    selected_mv = {
        (str(r.mess_id), int(r.horizon_step), int(r.slot))
        for r in move_df.itertuples(index=False)
    }
    missing_mv = sorted(selected_mv - set(mv))
    if missing_mv:
        raise RuntimeError(f"Reference MOVE choices absent from current model: {missing_mv[:10]}")
    for key, var in mv.items():
        _set_fixed(var, 1.0 if key in selected_mv else 0.0)

    selected_stay = set()
    for r in mess_df.itertuples(index=False):
        if str(r.state) == "STAY":
            selected_stay.add((str(r.mess_id), int(r.horizon_step), str(r.service_id)))
    missing_stay = sorted(selected_stay - set(stay))
    if missing_stay:
        raise RuntimeError(f"Reference STAY choices absent from current model: {missing_stay[:10]}")
    for key, var in stay.items():
        _set_fixed(var, 1.0 if key in selected_stay else 0.0)

    selected_occ = set()
    for mid, h, sid in selected_stay:
        selected_occ.add((mid, h, sid))
        selected_occ.add((mid, h + 1, sid))
    for mid, h, slot in selected_mv:
        mm = moves[(h, slot)]
        selected_occ.add((mid, h, str(mm["source"])))
        selected_occ.add((mid, h + int(mm["D"]), str(mm["dest"])))
    if node_occ:
        missing_occ = sorted(selected_occ - set(node_occ))
        if missing_occ:
            raise RuntimeError(f"Derived reference occupancy absent from model: {missing_occ[:10]}")
        for key, var in node_occ.items():
            _set_fixed(var, 1.0 if key in selected_occ else 0.0)

    model.update()
    int_names = [str(v.VarName) for v in model.getVars() if str(v.VType).upper() in {"B", "I", "S", "N"} and float(v.UB)-float(v.LB)>1e-12]
    unexpected = [name for name in int_names if not name.startswith("mode_")]
    if unexpected:
        raise RuntimeError(f"Residual non-mode integer variables after slow binding: {unexpected[:30]}")
    return {
        "job_choice_variables_fixed": len(x),
        "defer_variables_fixed": len(defer),
        "stay_variables_fixed": len(stay),
        "move_variables_fixed": len(mv),
        "occupancy_variables_fixed": len(node_occ),
        "selected_job_choices": len(selected_x),
        "selected_stay": len(selected_stay),
        "selected_move": len(selected_mv),
        "selected_occupancy": len(selected_occ),
        "residual_integer_count": len(int_names),
        "residual_integer_names_sample": int_names[:50],
        "residual_integer_family": "FAST_DISPATCH_MODE_ONLY" if not unexpected else "UNEXPECTED",
        "slow_plan_authority": "FROZEN_STAGE1_REFERENCE_PLAN",
        "future_actual_used": False,
    }


def fix_reference_modes(build_locals: Mapping[str, Any], ref: Mapping[str, Any]) -> dict[Any, tuple[float, float, str]]:
    mode = build_locals["mode"]
    mess_df = ref["BUILD7B_FULL54_MESS_PLAN.csv"]
    rows = {(str(r.mess_id), int(r.horizon_step)): r for r in mess_df.itertuples(index=False)}
    saved = {}
    for key, var in mode.items():
        saved[var] = (float(var.LB), float(var.UB), str(var.VType))
        r = rows.get((str(key[0]), int(key[1])))
        if r is None:
            raise RuntimeError(f"Reference MESS row missing for mode {key}")
        z = 1.0 if float(r.P_discharge_kW) > 1e-8 else 0.0
        _set_fixed(var, z)
    build_locals["m"].update()
    return saved


def restore_modes(model: Any, saved: Mapping[Any, tuple[float, float, str]]) -> None:
    for var, (lb, ub, vtype) in saved.items():
        var.LB = lb
        var.UB = ub
        var.VType = vtype
    model.update()
    model.reset()


def extract_mess_diagnostics(build_locals: Mapping[str, Any], ref: Mapping[str, Any]) -> dict[str, Any]:
    """Audit fixed-plan equivalence at the *committed causal boundary*.

    R26 commits h0 only.  Future h1..h53 continuous dispatch/debt trajectories
    are not physical state and can be non-unique even when the same discrete
    Route/Work/mode plan is fixed.  Therefore the hard equivalence gate is:
      - h0 Pcharge/Pdischarge,
      - E at h1 (the next causal SOC state),
      - DE at h1 (the next causal support-debt state).
    Full-horizon P/Q/SOC/DE differences remain diagnostic and are preserved in
    the audit.  Q is also diagnostic because continuous reactive dispatch can
    be degenerate while Fresh OpenDSS remains the physical hard gate.
    """
    mess_df = ref["BUILD7B_FULL54_MESS_PLAN.csv"]
    Pdis = build_locals["Pdis"]
    Pchg = build_locals["Pchg"]
    Q = build_locals["Q"]
    E = build_locals["E"]
    DE = build_locals["DE"]
    pscale = float(build_locals.get("_c5r4_power_scale_kw_per_model_unit", 1.0))
    escale = float(build_locals.get("_c5r4_energy_scale_kwh_per_model_unit", 1.0))
    rows = []
    full_worst = {
        "P_discharge_kW": 0.0,
        "P_charge_kW": 0.0,
        "SOC_kWh": 0.0,
        "support_energy_debt_kWh": 0.0,
    }
    commit_worst = {
        "h0_P_discharge_kW": 0.0,
        "h0_P_charge_kW": 0.0,
        "h1_SOC_kWh": 0.0,
        "h1_support_energy_debt_kWh": 0.0,
    }

    for r in mess_df.itertuples(index=False):
        mid = str(r.mess_id)
        h = int(r.horizon_step)
        state = str(r.state)
        sid = str(r.service_id)
        pd = pc = q = 0.0
        if state == "STAY":
            pd = pscale * float(Pdis[(mid,h,sid)].X)
            pc = pscale * float(Pchg[(mid,h,sid)].X)
            q = pscale * float(Q[(mid,h,sid)].X)
        soc = escale * float(E[(mid,h)].X)
        debt = escale * float(DE[(mid,h)].X)
        rec = {
            "mess_id": mid,
            "horizon_step": h,
            "state": state,
            "P_discharge_ref": float(r.P_discharge_kW),
            "P_discharge_new": pd,
            "P_charge_ref": float(r.P_charge_kW),
            "P_charge_new": pc,
            "Q_ref": float(r.Q_kvar),
            "Q_new": q,
            "SOC_ref": float(r.SOC_kWh),
            "SOC_new": soc,
            "support_debt_ref": float(r.support_energy_debt_kWh),
            "support_debt_new": debt,
        }
        rec["P_discharge_abs_error"] = abs(rec["P_discharge_ref"] - pd)
        rec["P_charge_abs_error"] = abs(rec["P_charge_ref"] - pc)
        rec["Q_abs_error"] = abs(rec["Q_ref"] - q)
        rec["SOC_abs_error"] = abs(rec["SOC_ref"] - soc)
        rec["support_debt_abs_error"] = abs(rec["support_debt_ref"] - debt)

        full_worst["P_discharge_kW"] = max(
            full_worst["P_discharge_kW"], rec["P_discharge_abs_error"]
        )
        full_worst["P_charge_kW"] = max(
            full_worst["P_charge_kW"], rec["P_charge_abs_error"]
        )
        full_worst["SOC_kWh"] = max(full_worst["SOC_kWh"], rec["SOC_abs_error"])
        full_worst["support_energy_debt_kWh"] = max(
            full_worst["support_energy_debt_kWh"], rec["support_debt_abs_error"]
        )

        if h == 0:
            commit_worst["h0_P_discharge_kW"] = max(
                commit_worst["h0_P_discharge_kW"], rec["P_discharge_abs_error"]
            )
            commit_worst["h0_P_charge_kW"] = max(
                commit_worst["h0_P_charge_kW"], rec["P_charge_abs_error"]
            )
        if h == 1:
            commit_worst["h1_SOC_kWh"] = max(
                commit_worst["h1_SOC_kWh"], rec["SOC_abs_error"]
            )
            commit_worst["h1_support_energy_debt_kWh"] = max(
                commit_worst["h1_support_energy_debt_kWh"],
                rec["support_debt_abs_error"],
            )
        rows.append(rec)

    hard_pass = (
        commit_worst["h0_P_discharge_kW"] <= 0.05
        and commit_worst["h0_P_charge_kW"] <= 0.05
        and commit_worst["h1_SOC_kWh"] <= 0.02
        and commit_worst["h1_support_energy_debt_kWh"] <= 0.02
    )
    return {
        "status": "PASS" if hard_pass else "FAIL_CLOSED",
        "hard_pass": hard_pass,
        "hard_gate_scope": "CAUSAL_H0_COMMIT_BOUNDARY_ONLY",
        "tolerance": {
            "P_kW": 0.05,
            "SOC_kWh": 0.02,
            "support_debt_kWh": 0.02,
        },
        "commit_boundary_worst_errors": commit_worst,
        "full_horizon_diagnostic_worst_errors": full_worst,
        "future_h1_to_h53_continuous_plan_is_committed": False,
        "full_horizon_support_debt_is_not_required_to_match_reference": True,
        "Q_is_diagnostic_due_to_possible_continuous_degeneracy": True,
        "worst_Q_kvar_error": max((r["Q_abs_error"] for r in rows), default=0.0),
        "rows": rows,
    }

def solver_quality(model: Any) -> dict[str, Any]:
    out = {
        "status_code": int(model.Status),
        "sol_count": int(model.SolCount),
        "runtime_seconds": float(model.Runtime),
        "node_count": float(getattr(model, "NodeCount", 0.0)),
        "num_vars": int(model.NumVars),
        "num_int_vars": int(model.NumIntVars),
        "num_qconstrs": int(model.NumQConstrs),
        "threads": int(model.Params.Threads),
    }
    if model.SolCount:
        for attr in ("ObjVal", "ObjBound", "MIPGap", "ConstrVio", "BoundVio", "IntVio"):
            try:
                out[attr] = float(getattr(model, attr))
            except Exception:
                pass
    return out


def _copy_runtime_logs(run_root: Path, log_dir: Path) -> list[dict[str, Any]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(run_root.rglob("*.log")):
        rel = path.relative_to(run_root)
        dst = log_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        records.append(
            {
                "source_relative_path": rel.as_posix(),
                "stored_path": str(dst),
                "sha256": sha256(dst),
                "bytes": dst.stat().st_size,
            }
        )
    return records


def _package_directory(source: Path, archive: Path, *, exclude_logs: bool = False) -> Path:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with tarfile.open(archive, "w:gz") as tf:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            if "gurobi_nodefiles" in path.parts:
                continue
            if exclude_logs and path.suffix.lower() == ".log":
                continue
            tf.add(
                path,
                arcname=str(Path(source.name) / path.relative_to(source)),
                recursive=False,
            )
    return archive


def package_run(run_root: Path, result_root: Path, log_root: Path, prefix: str) -> tuple[Path, Path]:
    """Freeze result and log handoffs into the user-requested authority folders."""
    result_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    tag = run_root.name

    run_log_dir = log_root / tag
    runtime_logs = _copy_runtime_logs(run_root, run_log_dir)
    console_candidate = run_log_dir / "RUN_CONSOLE.log"
    # RUN_CONSOLE.log is written directly under LOG_ROOT by run(), so record it.
    if console_candidate.is_file():
        runtime_logs.append(
            {
                "source_relative_path": "RUN_CONSOLE.log",
                "stored_path": str(console_candidate),
                "sha256": sha256(console_candidate),
                "bytes": console_candidate.stat().st_size,
            }
        )

    log_manifest = {
        "schema_version": "conversation_a.local_log_manifest.v2",
        "run": tag,
        "log_root": str(run_log_dir),
        "logs": runtime_logs,
    }
    write_json(run_root / "LOG_MANIFEST.json", log_manifest)
    write_json(run_log_dir / "LOG_MANIFEST.json", log_manifest)

    result_archive = result_root / f"{prefix}_{tag}.tar.gz"
    _package_directory(run_root, result_archive, exclude_logs=True)
    result_digest = sha256(result_archive)
    (result_root / f"{result_archive.name}.sha256.txt").write_text(
        f"{result_digest}  {result_archive.name}\n", encoding="utf-8"
    )

    log_archive = log_root / f"{prefix.replace('RESULT','LOGS')}_{tag}.tar.gz"
    _package_directory(run_log_dir, log_archive, exclude_logs=False)
    log_digest = sha256(log_archive)
    (log_root / f"{log_archive.name}.sha256.txt").write_text(
        f"{log_digest}  {log_archive.name}\n", encoding="utf-8"
    )
    return result_archive, log_archive

def run(args: argparse.Namespace) -> int:
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    repo = locate_repo(args.repo)
    work = Path.home() / "mobile_ess_work"
    assert_no_active_r25t(work)
    stage2_lock = acquire_stage2_lock(work)
    tag = now_tag()
    run_root = SCRATCH_ROOT / f"A_STEP2_3_{tag}"
    run_root.mkdir(parents=True, exist_ok=False)
    log_dir = LOG_ROOT / run_root.name
    log_dir.mkdir(parents=True, exist_ok=False)
    console_log = log_dir / "RUN_CONSOLE.log"
    rc = 2
    with console_log.open("w", encoding="utf-8", buffering=1) as log_handle:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = Tee(old_out, log_handle)
        sys.stderr = Tee(old_err, log_handle)
        try:
            print("Role: Mobile ESS K9-H7 Conversation A local 단계 2~3 runner", flush=True)
            print(f"RUN_ROOT={run_root}", flush=True)
            authority = assert_source_authority(repo)
            write_json(run_root / "00_SOURCE_AUTHORITY.json", authority)
            print(f"REPO={repo}")
            print(f"GIT_HEAD={authority['actual_git_head']}")
            if not authority["head_matches_expected_pr2"]:
                print("[WARN] Git HEAD differs from PR#2 handoff head, but frozen science bytes match exactly.")
            deps = dependency_preflight()
            write_json(run_root / "01_DEPENDENCY_PREFLIGHT.json", deps)
            stage1 = find_stage1_archive(work)
            write_json(run_root / "02_STAGE1_FINAL_ARCHIVE_AUDIT.json", stage1)
            if stage1.get("path") and not stage1.get("pass"):
                raise RuntimeError("Stage1 final archive exists but SHA-256 does not match frozen authority")

            sm = load_science(repo)
            temp_ref = run_root / "reference_issue113"
            temp_ref.mkdir()
            ref_index = build_reference_index(work)
            write_json(run_root / "03_REFERENCE_PLAN_INDEX.json", {str(k): str(v) for k,v in sorted(ref_index.items())})

            original_decomp = sm.certified_path_decomposition_solve
            original_build_full = sm.build_full
            original_jw = sm.jw
            hook_state: dict[str, Any] = {
                "target_issue": int(args.issue),
                "mode": args.mode,
                "issue_results": [],
                "expected_stop": False,
                "issue_started_monotonic": None,
                "equivalence_seconds": 0.0,
                "operational_issue_wall_seconds": None,
            }

            def build_full_wrapper(*bargs: Any, **bkwargs: Any):
                # build_full signature: scope,b4,op1,issue,...
                issue = int(bargs[3] if len(bargs) > 3 else bkwargs["issue"])
                if args.mode == "stage2_3" and issue > int(args.issue):
                    hook_state["expected_stop"] = True
                    raise ExpectedStop(f"단계 2~3 single-issue boundary reached before issue {issue}")
                return original_build_full(*bargs, **bkwargs)


            def jw_wrapper(path: Any, value: Any):
                result = original_jw(path, value)
                try:
                    pp = Path(path)
                    target_parent = f"issue_{int(args.issue):06d}"
                    if (
                        pp.name == "BUILD7C_PRECOMMIT_STATE.json"
                        and pp.parent.name == target_parent
                        and hook_state["issue_started_monotonic"] is None
                    ):
                        hook_state["issue_started_monotonic"] = time.monotonic()
                    if (
                        pp.name == "BUILD7C_POSTCOMMIT_STATE.json"
                        and pp.parent.name == target_parent
                        and hook_state["issue_started_monotonic"] is not None
                        and hook_state["operational_issue_wall_seconds"] is None
                    ):
                        hook_state["operational_issue_wall_seconds"] = (
                            time.monotonic()
                            - float(hook_state["issue_started_monotonic"])
                            - float(hook_state["equivalence_seconds"])
                        )
                except Exception:
                    pass
                return result

            def conditioned_decomp(**kwargs: Any):
                import inspect
                import gurobipy as gp
                frame = inspect.currentframe()
                assert frame is not None and frame.f_back is not None
                build_frame = frame.f_back
                loc = build_frame.f_locals
                issue = int(loc["issue"])
                model = kwargs["m"]
                issue_out = Path(loc["out"])
                issue_out.mkdir(parents=True, exist_ok=True)
                ref = load_reference_issue(issue, repo, temp_ref, ref_index)
                bind = apply_reference_slow_plan(loc, ref)
                write_json(issue_out / "R26_STAGE2_SLOW_BINDING_AUDIT.json", {"issue": issue, **bind})
                print(
                    f"[A Stage2] issue={issue} slow plan fixed; residual integer vars={bind['residual_integer_count']}",
                    flush=True,
                )

                # Stage-2 fixed-all-discrete equivalence gate is required on the
                # first requested issue only. It proves the extraction/binding path
                # against the frozen issue113 continuous values without committing.
                if issue == int(args.issue):
                    saved = fix_reference_modes(loc, ref)
                    model.Params.Threads = 4
                    model.Params.TimeLimit = 300.0
                    model.Params.MIPGap = 0.0
                    eq_t0 = time.monotonic()
                    model.optimize()
                    eq_elapsed = time.monotonic() - eq_t0
                    if int(model.Status) != int(gp.GRB.OPTIMAL) or int(model.SolCount) < 1:
                        raise RuntimeError(f"Fixed-all-discrete equivalence QCP did not solve OPTIMAL; status={model.Status}")
                    eq = extract_mess_diagnostics(loc, ref)
                    eq["issue"] = issue
                    eq["solver"] = solver_quality(model)
                    eq["wall_seconds"] = eq_elapsed
                    hook_state["equivalence_seconds"] = float(eq_elapsed)
                    eq["all_slow_and_mode_discrete_fixed"] = True
                    eq["fresh_opendss_executed_in_equivalence_subsolve"] = False
                    write_json(issue_out / "R26_STAGE2_FIXED_PLAN_EQUIVALENCE.json", eq)
                    if not eq["hard_pass"]:
                        raise RuntimeError("Fixed-plan numerical equivalence hard gate failed")
                    restore_modes(model, saved)

                # Stage-3 operational conditioned solve: only the slow route/work
                # decisions are fixed. The charge/discharge mode binaries remain
                # real fast-layer integer decisions and are audited as such.
                model.Params.Threads = 4
                model.Params.TimeLimit = float(args.fast_limit_seconds)
                model.Params.MIPGap = 0.03
                model.Params.MIPFocus = 1
                model.Params.OutputFlag = 1
                model.update()
                pre_int = [str(v.VarName) for v in model.getVars() if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12]
                bad_int = [name for name in pre_int if not name.startswith("mode_")]
                if bad_int:
                    raise RuntimeError(f"Unexpected residual integer variables: {bad_int[:30]}")
                t0 = time.monotonic()
                callback = kwargs.get("base_callback")
                if callback is None:
                    model.optimize()
                else:
                    model.optimize(callback)
                primary_wall = time.monotonic() - t0
                primary = solver_quality(model)
                if int(model.SolCount) < 1:
                    raise RuntimeError("Conditioned fast solve produced no feasible solution")

                # Online R26 does not require a global 3% certificate.  The frozen
                # 단계 1 extraction code, however, will only continue after an
                # OPTIMAL model or its historical reduced-problem tolerance.  If a
                # runtime-limited fast MIQCP already has a feasible incumbent but
                # has not closed that legacy tolerance, freeze only the residual
                # fast-mode incumbent and perform a continuous QCP polish.  This
                # changes no h0 slow plan and makes no global-bound claim.
                polish = None
                need_polish = int(model.Status) != int(gp.GRB.OPTIMAL)
                try:
                    need_polish = need_polish and float(model.MIPGap) > 0.03 + 1e-12
                except Exception:
                    need_polish = need_polish
                if need_polish:
                    mode_vars = list(loc["mode"].values())
                    incumbent_modes = {v: 1.0 if float(v.X) >= 0.5 else 0.0 for v in mode_vars}
                    for v, z in incumbent_modes.items():
                        _set_fixed(v, z)
                    model.update(); model.reset()
                    model.Params.TimeLimit = max(30.0, float(args.fast_limit_seconds) - primary_wall)
                    pt0 = time.monotonic(); model.optimize(); polish_wall = time.monotonic() - pt0
                    polish = solver_quality(model)
                    polish["wall_seconds"] = polish_wall
                    polish["residual_fast_modes_fixed_to_feasible_incumbent"] = True
                    if int(model.Status) != int(gp.GRB.OPTIMAL):
                        raise RuntimeError(f"Feasible-mode continuous QCP polish failed status={model.Status}")
                wall = time.monotonic() - t0
                q = solver_quality(model)
                q.update(
                    {
                        "issue": issue,
                        "wall_seconds": wall,
                        "primary_fast_miqcp": primary,
                        "primary_fast_miqcp_wall_seconds": primary_wall,
                        "incumbent_mode_polish": polish,
                        "slow_plan_fixed": True,
                        "remaining_integer_family_before_optional_polish": "FAST_DISPATCH_MODE_ONLY",
                        "remaining_integer_names_sample": pre_int[:50],
                        "online_global_3pct_certificate_claimed": False,
                        "r25t_restricted_or_compact_bound_used_as_online_authority": False,
                        "fast_runtime_threshold_seconds": float(args.fast_limit_seconds),
                    }
                )
                write_json(issue_out / "R26_STAGE3_CONDITIONED_FAST_SOLVE.json", q)
                # build_full is allowed to continue through its existing extraction,
                # numerical checks, Fresh OpenDSS, and h0 state-transition code.
                hook_state["issue_results"].append(q)
                return None

            sm.certified_path_decomposition_solve = conditioned_decomp
            sm.build_full = build_full_wrapper
            sm.jw = jw_wrapper
            engine_out = run_root / "engine"
            engine_out.mkdir()
            engine_rc = sm.rolling54_main(engine_out, work)
            write_json(run_root / "04_ENGINE_RETURN.json", {"return_code": int(engine_rc), "expected_stop": hook_state["expected_stop"]})

            # 단계 2~3 single-issue mode deliberately stops before constructing
            # the next issue. Validate that issue113 itself fully committed.
            issue = int(args.issue)
            issue_dir = engine_out / f"issue_{issue:06d}"
            transition_path = issue_dir / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json"
            exact_path = issue_dir / f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
            post_path = issue_dir / "BUILD7C_POSTCOMMIT_STATE.json"
            if not (transition_path.is_file() and exact_path.is_file() and post_path.is_file()):
                raise RuntimeError("단계 3 commit artifacts are incomplete")
            transition = json.loads(transition_path.read_text())
            exact = json.loads(exact_path.read_text())
            post = json.loads(post_path.read_text())
            fast = json.loads((issue_dir / "R26_STAGE3_CONDITIONED_FAST_SOLVE.json").read_text())
            eq = json.loads((issue_dir / "R26_STAGE2_FIXED_PLAN_EQUIVALENCE.json").read_text())
            stage2_pass = bool(eq.get("hard_pass") and fast.get("sol_count",0) >= 1)
            operational_issue_wall = hook_state.get("operational_issue_wall_seconds")
            stage3_pass = bool(
                transition.get("status") == "PASS"
                and transition.get("h0_only_committed") is True
                and transition.get("future_actual_arrivals_read") is False
                and exact.get("hard_constraint_pass") is True
                and post.get("sha256") == transition.get("post_state_sha256")
                and operational_issue_wall is not None
                and float(operational_issue_wall) < float(args.fast_limit_seconds)
            )
            status = {
                "schema_version": "conversation_a.stage2_3_local_result.v1",
                "step1": "COMPLETE_54_OF_54",
                "step2": "PASS" if stage2_pass else "FAIL_CLOSED",
                "step3": "PASS" if stage3_pass else "FAIL_CLOSED",
                "step4": "PENDING",
                "step5": "PENDING",
                "step6": "PENDING",
                "issue": issue,
                "conditioned_solver_runtime_seconds": fast.get("wall_seconds"),
                "operational_issue_wall_seconds_excluding_stage2_equivalence": operational_issue_wall,
                "runtime_gate_seconds": float(args.fast_limit_seconds),
                "conditioned_remaining_integer_count": fast.get("num_int_vars"),
                "conditioned_num_qconstrs": fast.get("num_qconstrs"),
                "fresh_opendss_pass": exact.get("hard_constraint_pass"),
                "post_state_sha256": post.get("sha256"),
                "physical_commit": stage3_pass,
                "future_actual_used": False,
                "period_selection_executed": False,
                "repository_modified": False,
                "next_step_if_pass": "STEP4_FIXED_SLOW_PLAN_54_ISSUE_CAUSAL_REPLAY",
            }
            write_json(run_root / "A_STEP2_3_RESULT.json", status)
            if not (stage2_pass and stage3_pass):
                raise RuntimeError(f"단계 2~3 acceptance failed: {status}")
            print("PASS_A_STEP2_AND_STEP3", flush=True)
            rc = 0
        except ExpectedStop as exc:
            # Normally consumed inside rolling54_main, but keep defensive path.
            print(f"[EXPECTED STOP] {exc}")
            rc = 0
        except Exception as exc:
            failure = {
                "status": "FAIL_CLOSED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "repository_modified": False,
                "future_actual_used": False,
            }
            write_json(run_root / "A_STEP2_3_FAILURE.json", failure)
            print(json.dumps(failure, indent=2, ensure_ascii=False), flush=True)
            rc = 2
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            try:
                fcntl.flock(stage2_lock.fileno(), fcntl.LOCK_UN)
                stage2_lock.close()
            except Exception:
                pass

    # Always package forensic output, including failures.
    result_archive, log_archive = package_run(
        run_root, RESULT_ROOT, LOG_ROOT, "ConversationA_STEP2_3_LOCAL_RESULT"
    )
    print(f"RESULT_HANDOFF_FILE={result_archive}")
    print(f"RESULT_HANDOFF_SHA256={sha256(result_archive)}")
    print(f"LOG_HANDOFF_FILE={log_archive}")
    print(f"LOG_HANDOFF_SHA256={sha256(log_archive)}")
    print(f"RUN_CONSOLE_LOG={console_log}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("stage2_3",), default="stage2_3")
    ap.add_argument("--issue", type=int, default=113)
    ap.add_argument("--fast-limit-seconds", type=float, default=300.0)
    ap.add_argument("--repo", default=None)
    args = ap.parse_args()
    if args.issue != 113:
        raise SystemExit("This first 단계 2~3 release is frozen to issue113; use Stage4 runner for the 54-issue replay.")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
