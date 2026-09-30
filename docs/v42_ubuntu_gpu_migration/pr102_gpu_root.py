"""Unchanged PR102 full F2 build, then its continuous P1 GPU diagnostic only."""
import os,sys,json,time,subprocess,threading,re,hashlib,gc
from pathlib import Path
import psutil,gurobipy as gp
H=Path.home();ROOT=H/'mobileess_worktrees/pr102';OUT=H/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration'
sys.path.insert(0,str(ROOT))
from v42_boundary.boundaries import load_native
from v42_exact.support import ExactFactory
from v42_exact.native import build
from v42_exact.common import atomic
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
receipt=json.loads((OUT.parent/'v42_root_lp_compression_a1/LEGACY_PRESERVATION_AUDIT.json').read_text())
drift=[r['path'] for r in receipt['files'] if sha(ROOT/r['path'])!=r['sha256']]
assert not drift,drift
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()=='cd7e40762097b6c20303bd2238edf7ffeba87aa4'
class Context:
    folder=H/'mobileess_worktrees/PR102_GPU_ROOT_LOCAL'
    def check(self):pass
    def progress(self,r):atomic(self.folder/'build_progress.json',r)
ctx=Context();ctx.folder.mkdir(exist_ok=True)
t=time.perf_counter();bundle,jobs,bounds,seconds,r,raw=load_native();load=time.perf_counter()-t
f=ExactFactory(r,max(b.latest_completion for b in bounds.values()));graphs={};original={};t=time.perf_counter()
for index,(uid,j) in enumerate(sorted(jobs.items())):
    graphs[uid]=f.graph(j,bounds[uid]);original[uid]=f.original.graph(j,bounds[uid])
    if index%100==0:print('GRAPH',index,time.perf_counter()-t,flush=True)
data=(bundle,jobs,bounds,r,raw,graphs,original,dict(data_prep_seconds=load,graph_seconds=time.perf_counter()-t))
print('FULL_PR102_F2_BUILD',flush=True);m,variables,levels,controls,bindings=build(ctx,data,'F2')
actual=dict(binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs)
expected=dict(binaries=2796366,continuous=5124335,constraints=9358534,nonzeros=100455768)
stats=json.loads((ctx.folder/'F2_MODEL_COMPLETE.json').read_text());atomic(OUT/'UBUNTU_PR102_STRUCTURE_COMPARISON.json',dict(PASS=actual==expected,actual=actual,expected=expected,build=stats,head='cd7e40762097b6c20303bd2238edf7ffeba87aa4',source_hashes_match=True,optimizer_called=False))
assert actual==expected,(actual,expected)
m.setObjective(levels[0][1]);m.update();fingerprint=hex(m.Fingerprint);lp=m.relax()
m.dispose();del m,variables,levels,controls,bindings,data,graphs,original;gc.collect()
log=OUT/'PR102_GPU_ROOT.log'
if log.exists():raise RuntimeError('DO_NOT_OVERWRITE_BENCHMARK')
settings=dict(Method=6,PDHGGPU=1,Threads=1,Seed=20260929,TimeLimit=3600)
for k,v in settings.items():lp.setParam(k,v)
lp.Params.OutputFlag=1;lp.Params.LogFile=str(log)
defaults={k:lp.getParamInfo(k)[2] for k in ('Crossover','FeasibilityTol','OptimalityTol','PDHGAbsTol','PDHGRelTol','PDHGConvTol','Presolve')}
atomic(OUT/'GPU_ROOT_PREREGISTRATION.json',dict(settings=settings,inherited_defaults=defaults,model_fingerprint=fingerprint,continuous_P1_relaxation=True,scientific_policy_result=False,no_production_A1=True,time_scope='continuous LP optimize including LP presolve and inherited crossover; not directly matched to prior native MIP root time'))
stop=threading.Event();samples=[]
def monitor():
    while not stop.is_set():
        q=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True)
        try:used,total,util=map(int,q.stdout.strip().split(','));samples.append(dict(monotonic=time.monotonic(),memory_used_bytes=used*1048576,total_bytes=total*1048576,utilization_percent=util,RSS_bytes=psutil.Process().memory_info().rss))
        except Exception:pass
        if samples and len(samples)%5==0:atomic(ctx.folder/'GPU_MEMORY_PROGRESS.json',dict(last=samples[-1],peak_total_gpu_used_bytes=max(s['memory_used_bytes'] for s in samples)))
        stop.wait(1)
thread=threading.Thread(target=monitor,daemon=True);thread.start();started=time.perf_counter();error=None
try:lp.optimize()
except gp.GurobiError as e:error=dict(code=e.errno,message=str(e))
finally:stop.set();thread.join(timeout=3)
wall=time.perf_counter()-started;text=log.read_text() if log.exists() else '';optimal=lp.Status==gp.GRB.OPTIMAL
fallback='running on CPU instead' in text;oom=bool(re.search('out of memory|insufficient memory|CUDA.*memory|GPU.*memory.*fail',text,re.I))
result=dict(attempted=True,full_may=True,model=actual,head='cd7e40762097b6c20303bd2238edf7ffeba87aa4',model_fingerprint=fingerprint,LP_fingerprint=hex(lp.Fingerprint),status=lp.Status,optimal=optimal,supported=optimal and 'Start PDHG on GPU' in text and not fallback and not oom,GPU_PDHG_log='Start PDHG on GPU' in text,GPU_model_log='GPU model:' in text,fallback=fallback,OOM=oom,error=error,wall_seconds=wall,solver_runtime=lp.Runtime,objective=lp.ObjVal if lp.SolCount else None,PDHG_iterations=lp.PDHGIterCount,iterations=lp.IterCount,max_violation=lp.MaxVio if lp.SolCount else None,crossover_inherited=defaults['Crossover'],crossover_lines=[s for s in text.splitlines() if 'rossover' in s],warnings=[s for s in text.splitlines() if re.search('warning|numerical|memory',s,re.I)],peak_total_GPU_used_bytes=max((s['memory_used_bytes'] for s in samples),default=None),GPU_memory_scope='total GPU used includes display and other apps; not solver allocation alone',prior_CPU_native_MIP_root_seconds=1557.90,prior_CPU_native_MIP_root_objective=.6716023396111563,speedup=None,speedup_scope='not a controlled same-algorithm comparison',settings=settings,defaults=defaults,scientific_policy_result=False)
atomic(OUT/'PR102_GPU_ROOT_BENCHMARK.json',result);atomic(OUT/'GPU_ROOT_MEMORY_SAMPLES.json',samples);lp.dispose();print('BENCHMARK_COMPLETE',json.dumps(result),flush=True)
assert not [r['path'] for r in receipt['files'] if sha(ROOT/r['path'])!=r['sha256']]
