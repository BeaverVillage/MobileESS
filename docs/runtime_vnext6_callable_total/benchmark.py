from paths import *
import os,time,subprocess,threading,concurrent.futures,multiprocessing
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='1'
import numpy as np,pandas as pd,lightgbm as lgb,psutil

def fit_task(args):
    family,tau,y,device,params=args
    started=time.perf_counter();target=np.log1p(y) if family=='M2' else y
    m=lgb.LGBMRegressor(objective='quantile',alpha=tau,**params,device_type=device).fit(np.ones((len(y),1)),target).booster_
    pred=m.predict(np.ones((len(y),1)),num_threads=1)
    if family=='M2':pred=np.expm1(pred)
    return dict(family=family,tau=tau,fit_seconds=time.perf_counter()-started,model=m.model_to_string(),prediction=float(pred[0]),trees=m.num_trees())
class Monitor:
    def __init__(self):self.rows=[];self.stop=False;self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        root=psutil.Process();psutil.cpu_percent()
        while not self.stop:
            try:
                ram=sum(p.memory_info().rss for p in [root]+root.children(recursive=True) if p.is_running())/2**20
                out=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,creationflags=0x08000000)
                vals=out.stdout.strip().split(',');gpu=float(vals[0]) if len(vals)==2 else np.nan;vram=float(vals[1]) if len(vals)==2 else np.nan
                self.rows.append(dict(cpu_percent=psutil.cpu_percent(),process_tree_RAM_MiB=ram,gpu_percent=gpu,VRAM_MiB=vram))
            except (psutil.Error,ValueError):pass
            time.sleep(.1)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*a):self.stop=True;self.thread.join()
def main():
    f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');y=f[f.role.eq('TRAIN')].runtime_seconds.to_numpy()[:50000]
    p=read(ROOT/'EXPERIMENT_PROTOCOL.json')['lgbm'];rows=[];outputs={};telemetry=[]
    for name,device,workers in [('CPU_SINGLE','cpu',1),('CPU_MULTIPROCESS','cpu',4),('GPU','gpu',1)]:
        tasks=[(family,tau,y,device,p) for family in ['M1','M2'] for tau in [.5,.9]]
        started=time.perf_counter();error=None;result=[]
        with Monitor() as monitor:
            try:
                if workers==1:result=[fit_task(a) for a in tasks]
                else:
                    with concurrent.futures.ProcessPoolExecutor(4,mp_context=multiprocessing.get_context('spawn')) as pool:result=list(pool.map(fit_task,tasks))
            except Exception as exc:error=f'{type(exc).__name__}: {exc}'
            elapsed=time.perf_counter()-started
        telemetry.extend([dict(backend=name,**r) for r in monitor.rows]);outputs[name]=result
        base=outputs['CPU_SINGLE'];diff=max([abs(a['prediction']-b['prediction']) for a,b in zip(result,base)],default=np.nan)
        pinball=[];coverage=[]
        for a,b in zip(result,base):
            e=y-a['prediction'];eb=y-b['prediction'];tau=a['tau'];pb=np.maximum(tau*e,(tau-1)*e).mean();pbb=np.maximum(tau*eb,(tau-1)*eb).mean()
            pinball.append(abs(pb-pbb)/max(pbb,1e-9));coverage.append(abs(np.mean(e<=0)-np.mean(eb<=0)))
        equivalent=error is None and diff<=.1 and max(pinball,default=1)<=.001 and max(coverage,default=1)<=.001
        row=dict(backend=name,workers=workers,threads_per_fit=1,N=len(y),fits=len(result),wall_seconds=elapsed,fit_seconds_sum=sum(r['fit_seconds'] for r in result),
          cpu_percent_mean=np.mean([r['cpu_percent'] for r in monitor.rows]) if monitor.rows else None,
          RAM_MiB_peak=max([r['process_tree_RAM_MiB'] for r in monitor.rows],default=None),gpu_percent_peak=max([r['gpu_percent'] for r in monitor.rows],default=None),VRAM_MiB_peak=max([r['VRAM_MiB'] for r in monitor.rows],default=None),
          max_prediction_difference_seconds=diff,max_relative_pinball_difference=max(pinball,default=None),max_coverage_difference=max(coverage,default=None),equivalent=equivalent,error=error)
        rows.append(row);print(name,elapsed,error,flush=True)
    pd.DataFrame(rows).to_csv(ROOT/'TRAIN_BACKEND_BENCHMARK.csv',index=False);pd.DataFrame(telemetry).to_csv(ROOT/'TRAIN_BACKEND_TELEMETRY.csv',index=False)
    cpu=min([r for r in rows if r['backend']!='GPU' and r['equivalent']],key=lambda r:r['wall_seconds']);gpu=rows[-1]
    selected=gpu if gpu['equivalent'] and gpu['wall_seconds']<.8*cpu['wall_seconds'] else cpu
    write('TRAIN_BACKEND_SELECTION.json',dict(selected=selected['backend'],benchmark=record(ROOT/'TRAIN_BACKEND_BENCHMARK.csv'),params=p,
      workload='Strict constant-input model. No informative tree splits; process startup can dominate. Not transferable to full-feature runtime or CC4.',
      CPU_utilization='system aggregate, RAM process-tree sum (may double-count shared pages); GPU/VRAM whole device incl display; sampling ~0.1s plus nvidia-smi latency',
      versions=dict(python=__import__('platform').python_version(),numpy=np.__version__,pandas=pd.__version__,lightgbm=lgb.__version__),results=[{k:v for k,v in r.items() if k!='model'} for r in outputs[selected['backend']]]))
if __name__=='__main__':main()
