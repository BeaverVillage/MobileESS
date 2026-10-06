"""One wall-only deadline supervisor, no resource based action."""
import subprocess,sys,time,json,psutil
from audit_grid_rowgen import ROOT,OUT,write

def run():
    start=time.perf_counter()
    log=OUT/'MICROBENCHMARK_EXECUTION.log'
    with log.open('x',encoding='utf8') as f:
        command=[sys.executable,'-X','utf8',str(ROOT/'benchmark_grid_rowgen.py')]
        p=subprocess.Popen(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        identity=psutil.Process(p.pid);created=identity.create_time();cmd=identity.cmdline()
        write('WALL_SUPERVISOR_IDENTITY.json',dict(pid=p.pid,created=created,command=cmd,shared_cap=600,
            ownership='this bounded benchmark child only',memory_policy='none',resource_guard=False))
        try:
            p.wait(timeout=max(.01,599-time.perf_counter()+start))
            write('WALL_SUPERVISOR_RESULT.json',dict(exit=p.returncode,wall=time.perf_counter()-start,time_deadline_kill=False))
        except subprocess.TimeoutExpired:
            actual=psutil.Process(p.pid)
            if actual.create_time()!=created or actual.cmdline()!=cmd:raise RuntimeError('PROCESS_IDENTITY_CHANGED_NO_KILL')
            p.kill();p.wait(timeout=1)
            write('WALL_SUPERVISOR_RESULT.json',dict(exit=p.returncode,wall=time.perf_counter()-start,time_deadline_kill=True,
                reason='600s development wall authority, never a RAM/resource decision'))
            raise RuntimeError('BOUNDED_COMPARISON_WALL_EXHAUSTED')
    if p.returncode:raise RuntimeError('BENCHMARK_CHILD_FAILED_'+str(p.returncode))
if __name__=='__main__':run()
