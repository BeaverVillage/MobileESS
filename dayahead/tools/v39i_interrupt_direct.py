"""User-authorized switch from direct min-max B&B to threshold feasibility."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39i_minmax as i
h=i.h


def main():
    state=h.read(i.ROOT/"V39I_PROGRESS.json");targets=state["worker_PIDs"]
    assert set(targets)<=set(i.DAYS)
    saved={}
    for day,pid in targets.items():
        command=subprocess.check_output(["powershell","-NoProfile","-Command",f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],text=True,encoding="utf-8",errors="replace").strip()
        assert "run_v39i_minmax.py" in command and f"--day {day}" in command,command
        source=h.ROOT/"days"/day/"V39H_SHADOW_SCHEDULE.parquet"
        destination=i.ROOT/"days"/day/"V39I_SAVED_V39H_UPPER_BOUND_SCHEDULE.parquet"
        if not destination.exists():shutil.copy2(source,destination)
        assert h.grid.sha(source)==h.grid.sha(destination)
        saved[day]={"PID":pid,"command":command,"V39H_upper_bound_schedule_SHA256":h.grid.sha(source)}
    i.atomic(i.ROOT/"V39I_THRESHOLD_SWITCH_PROTECTED_CHECKPOINTS.json",{"saved":saved,"user_authorized":True})
    kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.FreeConsole();attempts=[]
    for day,pid in targets.items():
        attached=bool(kernel.AttachConsole(pid));item={"day":day,"PID":pid,"attached":attached,"CTRL_C_sent":False}
        if attached:
            try:
                pids=(wintypes.DWORD*32)();count=kernel.GetConsoleProcessList(pids,32);members=set(pids[:count])
                item["console_members"]=sorted(members)
                assert count<=32 and members<={pid,os.getpid()},members
                kernel.SetConsoleCtrlHandler(None,True)
                item["CTRL_C_sent"]=bool(kernel.GenerateConsoleCtrlEvent(0,0))
            finally:kernel.FreeConsole()
        attempts.append(item)
    i.atomic(i.ROOT/"V39I_DIRECT_INTERRUPT_AUDIT.json",{"attempts":attempts,"reason":"User requested exact monotone integer threshold feasibility binary search; no completed primary or migration result is repeated."})
    print(attempts,flush=True)


if __name__=="__main__":main()
