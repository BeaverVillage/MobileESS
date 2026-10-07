from practical_support import *
import psutil

def owned_controller_alive():
    names={'external_controller.py','primal_external_controller.py','numeric_external_controller.py','archived_external_controller.py','cold_barrier_external_controller.py','accuracy_barrier_external_controller.py'}
    known={(OUT/name).resolve() for name in names}
    for p in psutil.process_iter(['pid']):
        if p.pid==os.getpid():continue
        try:
            cmd=p.cmdline();cwd=Path(p.cwd()).resolve()
            if cwd!=ROOT.resolve() or len(cmd)<2:continue
            script=Path(cmd[1]);script=(cwd/script).resolve() if not script.is_absolute() else script.resolve()
            if script in known:return dict(PID=p.pid,create_time=p.create_time(),script=script.name,cwd=str(cwd))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return None
