"""Identity-scoped, wall-only 600s supervisor for the sole bounded comparison."""
import subprocess,sys,time,psutil
from v42_one_tree_bc.files import ROOT,OUT,write
def run():
    start=time.perf_counter()
    with (OUT/'M1_ONE_TREE_BC_EXECUTION.log').open('x',encoding='utf8') as f:
        command=[sys.executable,'-X','utf8',str(ROOT/'benchmark_one_tree_bc.py')]
        p=subprocess.Popen(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        actual=psutil.Process(p.pid);created=actual.create_time();cmd=actual.cmdline()
        write('M1_ONE_TREE_BC_SUPERVISOR_IDENTITY.json',dict(pid=p.pid,created=created,command=cmd,
            wall_cap=600,ownership='This bounded development comparison child only',resource_guard=False))
        try:
            p.wait(timeout=max(.01,599-(time.perf_counter()-start)))
            write('M1_ONE_TREE_BC_SUPERVISOR_RESULT.json',dict(exit=p.returncode,
                continuous_wall=time.perf_counter()-start,time_deadline_kill=False))
        except subprocess.TimeoutExpired:
            actual=psutil.Process(p.pid)
            if actual.create_time()!=created or actual.cmdline()!=cmd:raise RuntimeError('PID_REUSED_NO_ACTION')
            p.kill();p.wait(timeout=1)
            write('M1_ONE_TREE_BC_SUPERVISOR_RESULT.json',dict(exit=p.returncode,
                continuous_wall=time.perf_counter()-start,time_deadline_kill=True,
                reason='Fixed development600s wall authority, no memory/resource threshold'))
            raise RuntimeError('COMPARISON_WALL_EXHAUSTED_NO_RETRY')
    if p.returncode:raise RuntimeError('COMPARISON_FAILED_NO_RETRY:'+str(p.returncode))
if __name__=='__main__':run()
