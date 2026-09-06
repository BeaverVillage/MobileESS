"""Protect completed proofs and attempt a scoped Windows console interrupt."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39h_shadow as h

def run():
    saved={}
    for day,stage,pid,primary in [("2025-05-25",1,7200,29568),("2025-05-26",2,44608,13086)]:
        out=h.ROOT/"days"/day;source=out/f"V39H_STAGE_{stage}_SCHEDULE.parquet"
        b=h.pd.read_parquet(source);assert int(b.occupancy_deviation_GPU_slots.sum())==primary
        destination=out/"V39H_FAST_CLOSE_SAVED_WITNESS.parquet"
        if not destination.exists():shutil.copy2(source,destination)
        assert h.grid.sha(source)==h.grid.sha(destination)
        saved[day]={"PID":pid,"source":str(source),"saved_witness":str(destination),"witness_SHA256":h.grid.sha(source),
            "objective_certificate_SHA256":h.grid.sha(out/"V39H_OBJECTIVE_CERTIFICATES.json"),"primary":primary,
            "saved_changed_jobs":int(b.start_delay_slots.ne(0).sum()),"saved_GPU_weighted_delay":int((b.requested_gpus*b.start_delay_slots).sum())}
    h.atomic(h.ROOT/"V39H_FAST_CLOSE_PROTECTED_CHECKPOINTS.json",{"saved":saved,"protected_before_interrupt":True})
    kernel=ctypes.WinDLL("kernel32",use_last_error=True);attempts=[]
    # Detach this short-lived helper only; error 5 otherwise means the helper
    # itself already has a console, not that the target was interrupted.
    kernel.FreeConsole()
    for day,record in saved.items():
        pid=record["PID"];ctypes.set_last_error(0)
        attached=bool(kernel.AttachConsole(pid));error=ctypes.get_last_error()
        item={"day":day,"PID":pid,"AttachConsole":attached,"Windows_error":error,"CTRL_C_sent":False}
        if attached:
            try:
                pids=(wintypes.DWORD*32)();count=kernel.GetConsoleProcessList(pids,32);members=set(pids[:count])
                item["console_members"]=sorted(members)
                if count<=32 and members<={7200,44608,os.getpid()}:
                    kernel.SetConsoleCtrlHandler(None,True)
                    item["CTRL_C_sent"]=bool(kernel.GenerateConsoleCtrlEvent(0,0))
                else:item["reason"]="Refused a console-wide interrupt involving unrelated processes"
            finally:kernel.FreeConsole()
        else:item["reason"]="No safely attachable console; workers were launched CREATE_NO_WINDOW and expose no external Model.terminate handle"
        attempts.append(item)
    h.atomic(h.ROOT/"V39H_FAST_CLOSE_INTERRUPT_ATTEMPTS.json",{"attempts":attempts,"saved_witness_fallback_authorized":True})
    print(attempts)

if __name__=="__main__":run()
