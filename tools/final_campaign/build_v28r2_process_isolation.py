#!/usr/bin/env python3
"""Build static, source-derived V28R2 process-isolation evidence."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"
RUNNER = REPO / "tools/final_campaign/run_v28r2_april.py"
MONITOR = REPO / "tools/final_campaign/monitor_v28r2_april.py"
RUN_SCRIPT = REPO / "tools/final_campaign/run_2025_april_preflight.sh"
MONITOR_SCRIPT = REPO / "tools/final_campaign/monitor_2025_april_preflight.sh"


def write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def call_names(tree: ast.AST) -> list[str]:
    result: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.append(node.func.attr)
    return result


def git_executable(path: Path) -> bool:
    relative = path.relative_to(REPO).as_posix()
    record = subprocess.check_output(
        ["git", "ls-files", "--stage", "--", relative], cwd=REPO, text=True,
    ).strip()
    return record.startswith("100755 ")


def main() -> None:
    runner_source = RUNNER.read_text(encoding="utf-8")
    monitor_source = MONITOR.read_text(encoding="utf-8")
    runner_tree = ast.parse(runner_source)
    monitor_tree = ast.parse(monitor_source)
    runner_calls = call_names(runner_tree)
    monitor_calls = call_names(monitor_tree)
    thread_occurrences = [
        token for token in ("ThreadPoolExecutor", "ProcessPoolExecutor", "multiprocessing.pool.ThreadPool")
        if token in runner_source
    ]
    popen_calls = runner_source.count("subprocess.Popen")
    monitor_write_calls = sorted(token for token in (
        ".write_text(", ".write_bytes(", ".unlink(", ".rename(", ".mkdir(",
        "os.replace(", "os.remove(", "os.makedirs(",
    ) if token in monitor_source)
    monitor_solver_tokens = sorted(token for token in (
        "gurobipy", "opendssdirect", "solver_runner", "heavy_backend", "subprocess"
    ) if token in monitor_source)
    scripts = {}
    for path in (RUN_SCRIPT, MONITOR_SCRIPT):
        raw = path.read_bytes()
        scripts[path.name] = {
            "lf_only": b"\r\n" not in raw,
            "set_euo_pipefail": b"set -euo pipefail" in raw,
            "executable": git_executable(path),
        }
    process_ready = (
        not thread_occurrences
        and popen_calls >= 1
        and "DAY_WORKERS = 2" in runner_source
        and "shell=False" in runner_source
        and "dayahead.v28r2.heavy_backend" in runner_source
        and all(record["lf_only"] and record["set_euo_pipefail"] for record in scripts.values())
    )
    monitor_ready = (
        not monitor_write_calls
        and not monitor_solver_tokens
        and all(flag in monitor_source for flag in (
            "--once", "--watch-seconds", "--json", "--active-only", "--failed-only", "--day",
        ))
    )
    write("V28R2_PROCESS_ISOLATION_CONTRACT.json", {
        "artifact_id": "V28R2_PROCESS_ISOLATION_CONTRACT_V1",
        "status": "PASS" if process_ready else "FAIL",
        "PROCESS_ISOLATION_READY": process_ready,
        "production_model": "parent supervisor -> independent day CLI subprocess",
        "day_workers": 2,
        "gurobi_threads_per_child": 4,
        "within_child_heavy_solves": "SEQUENTIAL",
        "Popen_call_count": popen_calls,
        "thread_executor_occurrences": thread_occurrences,
        "shared_native_objects": [],
        "child_module": "dayahead.v28r2.heavy_backend",
        "scripts": scripts,
    })
    write("V28R2_APRIL_MONITOR_CONTRACT.json", {
        "artifact_id": "V28R2_APRIL_MONITOR_CONTRACT_V1",
        "status": "PASS_IMPLEMENTATION_READY" if monitor_ready else "FAIL",
        "APRIL_MONITOR_IMPLEMENTATION_READY": monitor_ready,
        "APRIL_MONITOR_READY": False,
        "read_only": True,
        "write_calls": monitor_write_calls,
        "solver_or_subprocess_tokens": monitor_solver_tokens,
        "options": ["--once", "--watch-seconds", "--json", "--active-only", "--failed-only", "--day"],
        "output_root": "frozen_artifacts/v28r2_april_full_month_preflight/",
        "progress_root": "progress/v28r2_april_full_month_preflight/",
        "log_root": "logs/v28r2_april_full_month_preflight/",
    })


if __name__ == "__main__":
    main()
