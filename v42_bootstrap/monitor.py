"""Read-only supplemental snapshots when root simplex emits no MIP callbacks."""
import re,time
import psutil
from v42_root.common import *

PATTERN=re.compile(r'^\s*(\d+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+(\d+)s\s*$',re.M)

def run():
    folder=LOCAL/'M1';pid=int((LOCAL/'M1_PID.txt').read_text());process=psutil.Process(pid)
    targets=[60,300,600,1200,1800]
    atomic(folder/'MONITOR_STARTED.json',dict(pid=pid,read_only=True,solver_access=False,model_or_parameter_changes=False))
    while process.is_running() and not (folder/'FINISHED.json').exists():
        active=read(folder/'ACTIVE.json');elapsed=active['spent_seconds']+time.time()-(folder/'ACTIVE.json').stat().st_mtime
        log=(folder/'GUROBI.log').read_text(encoding='utf8',errors='replace')
        roots=[dict(iterations=int(r[1]),simplex_phase_objective=float(r[2]),primal_infeasibility=float(r[3]),dual_infeasibility=float(r[4]),native_component_seconds=int(r[5])) for r in PATTERN.finditer(log)]
        for target in targets:
            path=folder/f'SUPPLEMENTAL_SNAPSHOT_{target}.json'
            if path.exists() or (folder/f'SNAPSHOT_{target}.json').exists():continue
            if elapsed<target:continue
            past=[r for r in roots if r['native_component_seconds']+active['spent_seconds']>=target]
            retrospective=elapsed-target>10 and bool(past)
            root=past[0] if retrospective else (roots[-1] if roots else None)
            row=dict(requested_optimize_seconds=target,component=active['component'],phase='ROOT_LP' if root else 'NATIVE_SOLVE',
                     optimize_seconds=active['spent_seconds']+root['native_component_seconds'] if retrospective else elapsed,
                     RSS_bytes=None if retrospective else process.memory_info().rss,root_log_observation=root,
                     retrospective_from_native_log=retrospective,RSS_unavailable_for_historical_log=retrospective,
                     last_solver_callback=read(folder/'PROGRESS.json') if (folder/'PROGRESS.json').exists() else None,
                     simplex_phase_objective_is_not_certified_MIP_bound=True,solver_or_model_changes=False)
            atomic(path,row)
        time.sleep(.5)
    atomic(folder/'MONITOR_FINISHED.json',dict(read_only=True,solver_or_model_changes=False))

if __name__=='__main__':run()
