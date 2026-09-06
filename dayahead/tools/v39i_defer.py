"""Explicit user stop of nonblocking V39I; preserve all diagnostic evidence."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39i_minmax as i
h=i.h


def stop():
    state=h.read(i.ROOT/"V39I_PROGRESS.json");targets=state["worker_PIDs"]
    assert set(targets)<=set(i.DAYS)
    for day,pid in targets.items():
        command=subprocess.check_output(["powershell","-NoProfile","-Command",f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],text=True,encoding="utf-8",errors="replace")
        assert "run_v39i_threshold.py" in command and f"--day {day}" in command
    kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.FreeConsole();attempts=[]
    for day,pid in targets.items():
        attached=bool(kernel.AttachConsole(pid));record={"day":day,"PID":pid,"attached":attached,"CTRL_C_sent":False}
        if attached:
            try:
                pids=(wintypes.DWORD*32)();count=kernel.GetConsoleProcessList(pids,32);members=set(pids[:count])
                assert count<=32 and members<={pid,os.getpid()}
                record["console_members"]=sorted(members);kernel.SetConsoleCtrlHandler(None,True)
                record["CTRL_C_sent"]=bool(kernel.GenerateConsoleCtrlEvent(0,0))
            finally:kernel.FreeConsole()
        attempts.append(record)
    i.atomic(i.ROOT/"V39I_DEFER_INTERRUPT_AUDIT.json",{"user_authorized":True,"attempts":attempts,"timestamp":h.now(),
        "stop_reason":"DEFERRED_NONBLOCKING_SERVICE_DELAY_DIAGNOSTIC","unfinished_thresholds_are_UNKNOWN":True})
    print(attempts,flush=True)


def finalize():
    from dayahead.tools import v39i_report as report
    preserved=report.preservation()
    status={"V39I_DIAGNOSTIC_COMPLETE":"NO","V39I_STOP_REASON":"DEFERRED_NONBLOCKING_SERVICE_DELAY_DIAGNOSTIC",
        "V39I_PRODUCTION_BLOCKER":"NO","PRODUCTION_SCIENCE_CHANGED":"NO",
        "MAY25_V39H_WITNESS_MAX_ADDED_DELAY_MIN":5745,"MAY26_V39H_WITNESS_MAX_ADDED_DELAY_MIN":3840,
        "MAY25_EXACT_MIN_MAX_DELAY_MIN":None,"MAY26_EXACT_MIN_MAX_DELAY_MIN":None,
        "EXACT_MIN_MAX_DELAY_CERTIFIED":False,"SERVICE_ACCEPTABILITY_THRESHOLD_INVENTED":False,
        "unfinished_threshold_outcomes":{"2025-05-25":{"threshold_slots":196,"outcome":"UNKNOWN"},
            "2025-05-26":{"threshold_slots":144,"outcome":"UNKNOWN"}},
        "saved_direct_lower_bound_slots":{"2025-05-25":10,"2025-05-26":34},
        "solver_processes_stopped":True,"stopped_at":h.now(),"preservation_at_stop":preserved,
        "scope":"Production-science-unchanged flag is the V39I stop-time audit, before the separately authorized production refreeze."}
    i.atomic(i.ROOT/"V39I_DEFERRED_FINAL_STATUS.json",status)
    i.atomic(i.ROOT/"V39I_FINAL_STATUS.json",status)
    i.atomic(i.ROOT/"V39I_PROGRESS.json",{"phase":"STOPPED_DEFERRED_NONBLOCKING","completed_days":[],"running_days":[],
        "worker_PIDs":{},"failed_days":{},"last_update":h.now(),"intentional_user_stop":True,"diagnostic_complete":False})
    for day in i.DAYS:i.progress(i.ROOT/"days"/day,"STOPPED_DEFERRED_NONBLOCKING",unfinished_threshold_outcome="UNKNOWN")
    paths=[p for p in i.ROOT.rglob("*") if p.is_file() and p.name!="V39I_DEFERRED_EVIDENCE_SHA_MANIFEST.json"]
    i.atomic(i.ROOT/"V39I_DEFERRED_EVIDENCE_SHA_MANIFEST.json",{"SHA256":{str(p.relative_to(i.ROOT)):h.grid.sha(p) for p in paths},
        "preserved_at":h.now(),"no_artifacts_deleted":True})
    print({k:v for k,v in status.items() if k!="preservation_at_stop"},flush=True)


if __name__=="__main__":finalize() if "--finalize" in sys.argv else stop()
