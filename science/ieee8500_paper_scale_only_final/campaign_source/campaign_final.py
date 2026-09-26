"""Sequential May-1 campaign: B0, B2, B1, B3; Actual gates each policy."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

H = Path(__file__).absolute().parent
LOGS = H / "logs"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = H / path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Windows readers/OneDrive can briefly deny replacement of an open JSON.
    # Retry the atomic rename; never abort a running scientific stage for this.
    for attempt in range(100):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt==99:raise
            time.sleep(.02)


def gate(path, key="status", expected="PASS"):
    value = read(H / path)
    assert value[key] == expected, (path, value.get(key))
    return value


def run(stage, script, *args, policy):
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"{stage}_{time.time_ns()}.log"
    with log.open("x", encoding="utf-8") as output:
        command = [sys.executable, "-B", "-u", script, *args]
        process = subprocess.Popen(command, cwd=H, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        started = time.time()
        while process.poll() is None:
            save("CAMPAIGN_STATUS.json", dict(status="RUNNING", stage=stage, policy=policy,
                worker_pid=process.pid, supervisor_pid=os.getpid(), started_unix=started,
                elapsed_seconds=time.time()-started, log=str(log), order=["B0","B2","B1","B3"]))
            time.sleep(5)
        code = process.wait()
    save(f"{stage}_STAGE_RUNTIME.json", dict(exit_code=code, wall_seconds=time.time()-started,
         log=str(log), worker_pid=process.pid, command=command))
    assert code == 0, (stage, code, log)


def main():
    freeze = gate("FINAL_CANDIDATE_FREEZE.json", "status", "FROZEN_FOR_B2_PREFLIGHT")
    assert (freeze["BG_SCALE"],freeze["AIDC_ABSOLUTE_SCALE"],freeze["MESS_SCALE"]) == (.552,2.4,2.)
    gate("B0/COMPLETE.json")
    gate("B0/FRESH_GATE.json")
    gate("Actual/B0_GATE.json")
    gate("B2_PERFORMANCE_PREFLIGHT.json")
    gate("MESS_NO_CUTOFF_AUDIT.json")
    gate("PRODUCTION_CONTEXT_PREFLIGHT.json")
    gate("B2_PRELAUNCH_DECISION.json", "status", "READY_FOR_FULL_B2_SEARCH")
    assert (H / "B2_preflight/STAY_EXACT_DIAGNOSTIC.json").exists()
    retry=(H / "B2/STARTED.json").exists()
    if retry:
        failure=read(H / "B2_FAILURE.json")
        assert "NUMERICAL_REPAIR_PROOF.json" in failure["traceback"]
        assert not (H / "B2/beam").exists() and not (H / "B2/FINAL_AUTHORITY.json").exists()
        assert (H / "diagnostic_attempts/B2_PREPARATION_ATTEMPT_01_MISSING_RECOVERY_PROOF.json").exists()
    save("CAMPAIGN_RESTARTED_AFTER_PREPARATION_FAIL.json" if retry else "CAMPAIGN_STARTED.json",
         dict(date="2025-05-01", order=["B0","B2","B1","B3"],
         BG=.552,AIDC=2.4,MESS=2.,workers=1,threads=4,started_unix=time.time(),
         B0_DA_Fresh_Actual="PASS",no_artificial_MESS_work_or_wall_cutoff=True,
         preparation_retry_only=retry))

    run("B2_ROUTE_PQ", "mess_worker.py", "B2", policy="B2")
    gate("B2/COMPLETE.json")
    gate("B2/independent_clean_exact/AC_VALIDATION.json")
    gate("B2/Fresh/AC_VALIDATION.json")
    run("B2_ACTUAL", "actual_worker.py", "B2", policy="B2")
    assert gate("Actual/B2/COMPLETE.json", "AC_feasible", True)

    run("B1_AIDC", "production_worker.py", "B1", policy="B1")
    gate("B1/COMPLETE.json")
    gate("B1/Fresh/AC_VALIDATION.json")
    run("B1_ACTUAL", "actual_worker.py", "B1", policy="B1")
    assert gate("Actual/B1/COMPLETE.json", "AC_feasible", True)

    run("B3_A1_AIDC", "production_worker.py", "B3_A1", policy="B3")
    gate("B3_A1/COMPLETE.json")
    run("B3_M1_ROUTE_PQ", "production_worker.py", "B3_M1", policy="B3")
    gate("B3_M1/COMPLETE.json")
    run("B3_A2_AIDC", "production_worker.py", "B3_A2", policy="B3")
    gate("B3_A2/COMPLETE.json")
    run("B3_M2_PQ", "mf_worker.py", policy="B3")
    gate("B3/COMPLETE.json")
    gate("B3/final_exact/AC_VALIDATION.json")
    gate("B3/Fresh/AC_VALIDATION.json")
    run("B3_ACTUAL", "actual_worker.py", "B3", policy="B3")
    assert gate("Actual/B3/COMPLETE.json", "AC_feasible", True)

    run("FINAL_REPORT", "report_final_campaign.py", policy="REPORT")
    gate("FINAL_CAMPAIGN_RESULT.json")
    save("CAMPAIGN_STATUS.json", dict(status="COMPLETE", stage="FINISHED", policy="REPORT",
         order=["B0","B2","B1","B3"], completed_unix=time.time(), supervisor_pid=os.getpid()))


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        save("CAMPAIGN_FAILURE.json", dict(error=repr(exc), traceback=traceback.format_exc(),
             recorded_unix=time.time()))
        save("CAMPAIGN_STATUS.json", dict(status="FAILED", stage="STOPPED", error=repr(exc),
             recorded_unix=time.time(), supervisor_pid=os.getpid()))
        raise
