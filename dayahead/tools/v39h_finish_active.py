"""Attach to the two existing workers, then finish by certificate assembly.

No day or migration optimization is launched here. Never retry a solver.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39h_shadow as h
from dayahead.tools import v39h_shadow_report as report
from threadpoolctl import threadpool_limits

ATTACHED={"2025-05-25":7200,"2025-05-26":44608}

def alive_workers():
    command="Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_v39h_shadow.py --day*' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    text=subprocess.check_output(["powershell","-NoProfile","-Command",command],text=True,encoding="utf-8",errors="replace").strip()
    rows=json.loads(text) if text else []
    if isinstance(rows,dict):rows=[rows]
    alive={}
    for row in rows:
        for day,pid in ATTACHED.items():
            if row["ProcessId"]==pid:
                assert row["CommandLine"].endswith("--day "+day)
                alive[day]=pid
    return alive

def run():
    start=h.read(h.ROOT/"V39H_START_STATE.json");assembled=set()
    while True:
        running=alive_workers();results={};per_day={};failures={}
        for day in h.DAYS:
            out=h.ROOT/"days"/day;path=out/"V39H_SHADOW_A_RESULT.json"
            if day in ATTACHED and day not in running and day not in assembled:
                # A worker can have completed all proofs but failed in old
                # reporting code. Assembly recovers only a certified witness.
                report.assemble_day(day);assembled.add(day)
            if path.exists():
                result=h.read(path)
                assert result["shadow_status"] in ("OPTIMAL","INFEASIBLE")
                results[day]=result
            p=h.read(out/"V39H_DAY_PROGRESS.json")
            if day in results:p.pop("error",None)
            elif day not in running:failures[day]=p.get("error","No completed proof")
            per_day[day]=p
        elapsed=(datetime.fromisoformat(h.now())-datetime.fromisoformat(start["start_time"])).total_seconds()
        h.atomic(h.ROOT/"progress/V39H_PROGRESS.json",{"phase":"RUNNING_EXACT_LEX" if running else "FINAL_ASSEMBLY","start_time":start["start_time"],"last_update":h.now(),"elapsed":elapsed,"elapsed_seconds":elapsed,
            "completed_days":sorted(results),"running_days":sorted(running),"pending_days":[],"failed_days":failures,"worker_PIDs":running,"per_day":per_day,
            "baseline_migrations":105,"current_postrepair_migrations":sum(r["post_candidate_migration_count"] for r in results.values()),
            "counts_scope":"completed certified days only until all 13 complete","temporal_repair_only_days":sum(r["temporal_repair_sufficient"] for r in results.values()),
            "remaining_migration_days":sum(r["post_candidate_migration_count"]>0 for r in results.values()),"resumable":True,"max_parallel_day_workers":4,"Threads_per_model":4,
            "new_migration_solves":0,"controller":"ATTACHED_TO_EXISTING_WORKERS_NO_RESTART"})
        assert not failures,failures
        if not running:break
        time.sleep(10)
    assert len(results)==13
    report.aggregate()
    # 34 completed tests are reused. Only the final 13-day evidence test and
    # the newly added exact witness-cache guardrail remain.
    previous=h.read(h.ROOT/"V39H_GUARDRAIL_REGRESSION_TEST_REPORT.json")
    assert previous["status"]=="PASS"
    temporary=Path("C:/codex_mobileess_workspace")/f"v39h_tests_completion_{os.getpid()}"
    assert not temporary.exists()
    cmd=[sys.executable,"-m","pytest","tests/dayahead/test_v39h_shadow.py","-k","test_final_results_work_no_migration_and_optimality or test_completed_grid_witness_reuse_is_bound_to_schedule","-q","--basetemp",str(temporary)]
    test=subprocess.run(cmd,cwd=h.REPO,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,OPENBLAS_NUM_THREADS="4",OMP_NUM_THREADS="4",MKL_NUM_THREADS="4"))
    h.atomic(h.ROOT/"V39H_TEST_REPORT.json",{"status":"PASS" if test.returncode==0 else "FAIL","total_tests":36,"reused_passed_guardrail_regression_tests":34,"completion_tests":2,
        "previous_report_SHA256":h.grid.sha(h.ROOT/"V39H_GUARDRAIL_REGRESSION_TEST_REPORT.json"),"command":cmd,"returncode":test.returncode,"stdout":test.stdout,"stderr":test.stderr,"new_full_day_optimization_runs":0})
    print(test.stdout,flush=True);assert test.returncode==0,test.stderr
    report.finalize()

if __name__=="__main__":
    with threadpool_limits(limits=4):run()
