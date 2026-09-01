"""Run the four isolated V29 development/regression day processes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")
NAME = "v29_development_regression_apr01_04"


def write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run_one(campaign: Path, day: str) -> dict[str, object]:
    output = REPO / "frozen_artifacts" / NAME / day
    log = REPO / "logs" / NAME / f"{day}.log"
    progress = REPO / "progress" / NAME / f"{day}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    write(progress, {"day": day, "status": "RUNNING", "process_isolated": True, "gurobi_threads": 4})
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    command = [sys.executable, str(REPO / "tools/v29/run_v29_day.py"), "--campaign-repo", str(campaign), "--day", day, "--output", str(output)]
    with log.open("w", encoding="utf-8", newline="\n") as stream:
        completed = subprocess.run(command, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False)
    status = "PASS" if completed.returncode == 0 and (output / "V29_DAY_RESULT.json").is_file() else "FAIL"
    result = {"day": day, "status": status, "returncode": completed.returncode, "output": str(output), "log": str(log), "process_isolated": True, "gurobi_threads": 4}
    write(progress, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--campaign-repo", type=Path, required=True); args = parser.parse_args()
    campaign = args.campaign_repo.resolve(); results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_one, campaign, day): day for day in DAYS}
        for future in as_completed(futures):
            result = future.result(); results.append(result); print(json.dumps(result), flush=True)
    results.sort(key=lambda row: row["day"])
    write(REPO / "progress" / NAME / "SUMMARY.json", {"evaluation": "V29_DEVELOPMENT_REGRESSION_APR01_04", "results": results, "status": "PASS" if all(row["status"] == "PASS" for row in results) else "FAIL"})
    if any(row["status"] != "PASS" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
