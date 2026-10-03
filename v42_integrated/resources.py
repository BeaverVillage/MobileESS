"""Execution evidence; independent workers alone never block this lane."""
import datetime
import psutil

def snapshot():
    memory=psutil.virtual_memory(); swap=psutil.swap_memory(); processes=[]
    for p in psutil.process_iter(['pid','name','cmdline','cpu_percent','memory_info']):
        try:
            n=(p.info['name'] or '').lower()
            if any(k in n for k in ('python','gurobi')):
                processes.append(dict(pid=p.pid,name=p.info['name'],command_line=p.info['cmdline'],cpu_percent=p.info['cpu_percent'],RSS_bytes=p.info['memory_info'].rss if p.info['memory_info'] else None))
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),CPU_utilization_percent=psutil.cpu_percent(interval=.2),logical_cores=psutil.cpu_count(),available_logical_cores=len(psutil.Process().cpu_affinity()),RAM_used_bytes=memory.used,RAM_free_bytes=memory.available,swap_total_bytes=swap.total,swap_used_bytes=swap.used,swap_in_bytes=swap.sin,swap_out_bytes=swap.sout,active_Python_solver_processes=processes,RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,independent_parallel_work_allowed=True,integrated_heavy_lane='SEQUENTIAL',BLAS_OpenMP_threads=1)
