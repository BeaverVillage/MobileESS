from common import *
import time,os,subprocess,threading,platform
import psutil,lightgbm as lgb
from concurrent.futures import ProcessPoolExecutor
_data=None
def init():
    global _data
    x=np.load(PREV/'FEATURES.npz');y=np.load(PREV/'TARGETS.npz')
    _data=({a:x[a] for a in ['T2_F0','T3_F2']},{k:y[k] for k in y.files if k!='days'})
def task(args):
    arm,i,model,backend=args;x,ydata=_data;x=x[arm];t=arm[:2];y=ydata[t]
    mature=pd.Series(pd.to_datetime(ydata['maturity_'+t].max(1),utc=True));tr=c.member(i,mature)
    groups=np.array_split(np.arange(y.shape[1]),4) if model=='M1' else [np.arange(y.shape[1])]
    q=np.zeros((y.shape[1],2));fit_seconds=[];hashes=[]
    params=c.PARAMS.copy()
    if backend=='GPU':params.update(device_type='gpu',gpu_use_dp=True)
    started=time.perf_counter()
    for slots in groups:
        xx=x[tr][:,slots].reshape(-1,x.shape[-1]);yy=np.log1p(y[tr][:,slots].ravel());ww=np.repeat(c.weights(tr,i),len(slots))
        for k,tau in enumerate([.5,.9]):
            at=time.perf_counter();m=lgb.LGBMRegressor(objective='quantile',alpha=tau,**params).fit(xx,yy,sample_weight=ww).booster_
            fit_seconds.append(time.perf_counter()-at);q[slots,k]=np.maximum(0,np.expm1(m.predict(x[i,slots],num_threads=1)))
            hashes.append(hashlib.sha256(m.model_to_string().encode()).hexdigest())
    q[:,1]=np.maximum(q[:,0],q[:,1]);return dict(arm=arm,i=i,model=model,q=q,fit_seconds=fit_seconds,seconds=time.perf_counter()-started,model_sha256=hashes)
def gpu_info():
    try:
        r=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode:return None
        return [float(v.strip()) for v in r.stdout.splitlines()[0].split(',')]
    except Exception:return None
class Monitor:
    def __init__(self):self.rows=[];self.stop=threading.Event();self.p=psutil.Process()
    def start(self):psutil.cpu_percent();self.th=threading.Thread(target=self.loop,daemon=True);self.th.start()
    def loop(self):
        while not self.stop.is_set():
            rss=0
            for p in [self.p]+self.p.children(recursive=True):
                try:rss+=p.memory_info().rss
                except psutil.Error:pass
            g=gpu_info();self.rows.append(dict(time=time.time(),cpu_percent_system=psutil.cpu_percent(),process_tree_RSS_MiB=rss/2**20,system_used_RAM_MiB=psutil.virtual_memory().used/2**20,gpu_util_percent=g[0] if g else np.nan,gpu_VRAM_MiB=g[1] if g else np.nan))
            self.stop.wait(.5)
    def end(self):self.stop.set();self.th.join()
def main():
    verify_previous();days=['2024-09-15','2024-10-15']
    batch=[(arm,int(np.searchsorted(c.DAYS,day)),model) for day in days for arm in ['T2_F0','T3_F2'] for model in ['M0','M1']]
    write('BENCHMARK_PROTOCOL.json',dict(time=pd.Timestamp.now(tz='UTC'),current_delivery_sha256=sha(PREV/'DELIVERY_MANIFEST.json'),batch=[dict(arm=a,day=c.DAYS[i],model=m) for a,i,m in batch],backends=['CPU_SINGLE','CPU_MULTIPROCESS_4','GPU'],CPU_n_jobs=1,GPU_policy='Installed build only; device_type=gpu, double precision requested; no rebuild. Existing deterministic/force_col_wise flags retained and recorded, without claiming GPU determinism.',parameters=c.PARAMS,prediction_tolerance=dict(atol=1e-8,rtol=1e-8),metric_absolute_tolerance=1e-6,minimum_speedup_to_change=.10,selection='Fastest equivalent CPU backend; GPU requires supported batch, prediction/metric equivalence and >=10% speedup versus fastest equivalent CPU.',telemetry='0.5s target polling; nvidia-smi overhead included in wall time for every backend. GPU utilization/VRAM and CPU are system/device-wide; process-tree RSS may double-count shared pages. Single pass, fixed order; no claims about thermal limits or run-to-run variance.',code_sha256=sha(Path(__file__))))
    write('BENCHMARK_ENVIRONMENT.json',dict(python=sys.version,platform=platform.platform(),lightgbm=lgb.__version__,numpy=np.__version__,pandas=pd.__version__,psutil=psutil.__version__,physical_cores=psutil.cpu_count(False),logical_cores=psutil.cpu_count(),RAM_bytes=psutil.virtual_memory().total,nvidia=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],capture_output=True,text=True).stdout,lightgbm_library=str(lgb.basic._LIB._name),lightgbm_library_sha256=sha(lgb.basic._LIB._name)))
    summaries=[];alltelemetry=[];reference=None;details=[]
    for name,workers,device in [('CPU_SINGLE',1,'CPU'),('CPU_MULTIPROCESS',4,'CPU'),('GPU',1,'GPU')]:
        print('BENCHMARK_START',name,flush=True);mon=Monitor();mon.start();start=time.perf_counter();error=None;result=[]
        try:
            args=[(*b,device) for b in batch]
            if workers==1:
                init();result=[task(a) for a in args]
            else:
                with ProcessPoolExecutor(max_workers=workers,initializer=init) as pool:result=list(pool.map(task,args))
        except Exception as e:error=repr(e)
        elapsed=time.perf_counter()-start;mon.end();tele=pd.DataFrame(mon.rows);tele['backend']=name;alltelemetry.extend(tele.to_dict('records'))
        diff=0.;metricdiff=0.;equiv=error is None;source_equal=True
        if error is None:
            if reference is None:reference=result
            for j,r in enumerate(result):
                ref=reference[j]['q'];difference=float(abs(r['q']-ref).max());diff=max(diff,difference);equiv &= bool(np.allclose(r['q'],ref,atol=1e-8,rtol=1e-8))
                saved=np.load(PREV/'runs'/r['model']/r['arm']/(c.DAYS[r['i']]+'.npz'))['q'];source_equal &= bool(np.array_equal(r['q'],saved))
                yy=_data[1][r['arm'][:2]][r['i']:r['i']+1];burst=np.quantile(_data[1][r['arm'][:2]][c.TRAIN],.95)
                actual=c.metrics(yy,r['q'][None],burst);baseline=c.metrics(yy,ref[None],burst)
                for key in ['Q50_MAE','Q50_pinball','Q90_pinball','Q90_coverage','requirement_ratio']:
                    delta=float(actual[key]-baseline[key]);metricdiff=max(metricdiff,abs(delta));details.append(dict(backend=name,arm=r['arm'],day=c.DAYS[r['i']],model=r['model'],metric=key,value=actual[key],reference=baseline[key],delta=delta))
                np.savez_compressed(ROOT/(name+'_'+r['arm']+'_'+r['model']+'_'+c.DAYS[r['i']]+'.npz'),q=r['q'],fit_seconds=r['fit_seconds'],model_sha256=r['model_sha256'])
            equiv &= metricdiff<=1e-6
        times=[v for r in result for v in r['fit_seconds']]
        summaries.append(dict(backend=name,workers=workers,n_jobs=1,status='UNAVAILABLE' if error else 'COMPLETE',error=error,total_wall_seconds=elapsed,mean_fit_seconds=np.mean(times) if times else np.nan,P95_fit_seconds=np.quantile(times,.95) if times else np.nan,completed_tasks=len(result),completed_quantile_fits=len(times),mean_CPU_utilization_percent=tele.cpu_percent_system.mean(),mean_GPU_utilization_percent=tele.gpu_util_percent.mean(),peak_RAM_MiB=tele.process_tree_RSS_MiB.max(),peak_VRAM_MiB=tele.gpu_VRAM_MiB.max(),max_prediction_abs_diff=diff if error is None else np.nan,max_metric_abs_diff=metricdiff if error is None else np.nan,prediction_equivalence=equiv,bitwise_source_replay=source_equal if error is None else False))
        print('BENCHMARK_DONE',name,elapsed,error,flush=True)
    csv('COMPUTE_BACKEND_BENCHMARK.csv',summaries);csv('BENCHMARK_TELEMETRY.csv',alltelemetry);csv('BENCHMARK_METRIC_DIFFERENCES.csv',details)
    frame=pd.DataFrame(summaries);cpu=frame[frame.backend.ne('GPU')&frame.prediction_equivalence];best=cpu.sort_values('total_wall_seconds').iloc[0];single=frame[frame.backend.eq('CPU_SINGLE')].iloc[0]
    if best.backend!='CPU_SINGLE' and best.total_wall_seconds>.9*single.total_wall_seconds:best=single
    gpu=frame[frame.backend.eq('GPU')].iloc[0]
    if gpu.prediction_equivalence and gpu.total_wall_seconds<=.9*best.total_wall_seconds:best=gpu
    write('COMPUTE_BACKEND_SELECTION.json',dict(time=pd.Timestamp.now(tz='UTC'),SELECTED_BACKEND=best.backend,workers=int(best.workers),n_jobs=1,PREDICTION_EQUIVALENCE_VERIFIED=bool(best.prediction_equivalence),CPU_MULTIPROCESS_BENCHMARKED=True,GPU_LIGHTGBM_BENCHMARKED='UNAVAILABLE' if gpu.status=='UNAVAILABLE' else True,benchmark_sha256=sha(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv'),protocol_sha256=sha(ROOT/'BENCHMARK_PROTOCOL.json'),speedup_vs_CPU_SINGLE=float(single.total_wall_seconds/best.total_wall_seconds),GPU_build_unchanged=True,environment_changed=False,scope='Representative pre-evaluation batch; no hardware-general speed claim'))
    print('BENCHMARK_FROZEN',best.backend,flush=True)
if __name__=='__main__':main()
