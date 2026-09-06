"""Preregistered candidate fits and DEVELOPMENT-only pipeline selection."""
from .common import *
from .models import fit_classical,fit_neural,save_params,load_params
from .distributions import scenarios,predictive_summary
from .metrics import aggregate,gates,calibration,calibrate,cumulative_metrics
import argparse,time
NAMES=['B0','B1','B2','B3','B4','B5','P1']

def authority():
    r=read('V40R4_PREREGISTRATION.json');c=read('V40R4_PREREGISTRATION_COMMIT_RECEIPT.json')['commit']
    assert git('merge-base','--is-ancestor',c,'HEAD')==''
    raw=subprocess.check_output(['git','show',c+':dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_PREREGISTRATION.json'],cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest()==sha(OUT/'V40R4_PREREGISTRATION.json')
    for p,h in r['frozen_hashes'].items():assert sha(ROOT/p)==h,('FROZEN_FILE_CHANGED',p)
    return r,c
def load():
    r,c=authority();a=np.load(OUT/'prepared.npz');i=pd.read_parquet(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    m={n:((i.role==n)&i.stage_maturity_eligible).to_numpy() for n in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']}
    return r,c,a,i,m
def raw_quantiles(p,days,M,seed=SEED,cumulative=False,score=None):
    quant=[];curves=[]
    for day in days:
        draw=scenarios(p,np.arange(int(day)*48,(int(day)+1)*48),M,seed+7919*int(day))
        if score is not None:draw=calibrate(draw,score)
        quant.append(predictive_summary(draw))
        if cumulative:curves.append(predictive_summary(np.cumsum(draw,axis=0)))
    q=np.stack(quant)
    return (q,np.stack(curves)) if cumulative else q
def rank(metric):return (metric['primary'],metric['missed_burst_GPUh'],metric.get('cumulative_WAPE',np.inf))

def fit_stage():
    reg,commit,a,info,m=load();dev=np.flatnonzero(m['DEVELOPMENT']);dates=info.operating_day.to_numpy();M=reg['scenario_count']
    pre=read('V40R4_PREFIT_TEST_REPORT.json');assert pre['failed']==pre['errors']==0
    # September provisional C1 fit must mature before October starts; October selects pipelines.
    provisional=m['DEVELOPMENT'] & info.operating_day.lt('2024-10-01').to_numpy() & info.target_label_available_at.le(pd.Timestamp('2024-09-30 08:00',tz='UTC')).to_numpy()
    select=m['DEVELOPMENT'] & info.operating_day.ge('2024-10-01').to_numpy()
    assert provisional.sum()>5 and select.sum()>5
    for name in NAMES:
        directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
        if (directory/'result.json').exists():continue
        trials=[];num=1 if name in ['B0','B1'] else 2
        for trial in range(num):
            dump(f'fits/{name}/trial_{trial}_start.json',{'commit':commit,'seed':SEED,'time_UTC':datetime.now(timezone.utc),'trial':trial,'candidate':name})
            if name=='B0':p={'kind':'ZERO'};meta={'fit_time_seconds':0.,'parameter_fits':0,'device':'cpu','seed':SEED,'trial':trial}
            elif name=='B1':
                f=a['future'].reshape(-1,15);p={'kind':'SEASONAL','values':f[:,[7,9,11,13]]*reg['burst_GPUh'],'valid':f[:,[8,10,12,14]]>0}
                meta={'fit_time_seconds':0.,'parameter_fits':0,'device':'cpu','seed':SEED,'trial':trial}
            elif name=='P1':p,meta=fit_neural(trial,a,m,reg,directory)
            else:p,meta=fit_classical(name,trial,a,m,reg,directory)
            save_params(directory/f'trial_{trial}_params.npz',p)
            before=time.monotonic();q,cq=raw_quantiles(p,dev,M,cumulative=True)
            np.save(directory/f'trial_{trial}_development_q.npy',q)
            calix=provisional[dev];selix=select[dev];ys=a['target'][dev]
            score=calibration(ys[calix],q[calix,:,1]) if name!='B0' else 0.
            choices=[]
            for method in ['C0'] if name=='B0' else ['C0','C1']:
                prediction=q if method=='C0' else calibrate(q,score)
                met=aggregate(ys[selix],prediction[selix],reg['burst_GPUh'])
                cc=cq[selix] if method=='C0' else raw_quantiles(p,dev[selix],M,cumulative=True,score=score)[1]
                met['cumulative_WAPE']=cumulative_metrics(ys[selix],cc)['WAPE']
                gate=gates(ys[selix],prediction[selix],reg['burst_GPUh'],dates[dev][selix],raw=q[selix] if method=='C1' else None)
                choices.append({'method':method,'provisional_score':score if method=='C1' else 0.,'metrics':met,'gates':gate,'trial':trial})
            meta.update(development_choices=choices,development_simulation_seconds=time.monotonic()-before,preregistration_commit=commit)
            dump(f'fits/{name}/trial_{trial}_result.json',meta);trials.append(meta)
            print(name,'trial',trial,[(v['method'],round(v['metrics']['primary'],5),v['gates']['all_pass']) for v in choices],flush=True)
        all_choices=[v for t in trials for v in t['development_choices']];safe=[v for v in all_choices if v['gates']['all_pass']]
        selected=min(safe or all_choices,key=lambda v:(*rank(v['metrics']),v['trial'],v['method']))
        selectedp=load_params(directory/f'trial_{selected["trial"]}_params.npz');save_params(directory/'selected_params.npz',selectedp)
        dump(f'fits/{name}/result.json',{'status':'COMPLETE_DEVELOPMENT_ONLY','name':name,'trials':trials,'selected':selected,
          'selected_params_SHA256':sha(directory/'selected_params.npz'),'preregistration_commit':commit,'final_evaluation_metrics_read':False})
        print(name,'selected',selected['trial'],selected['method'],flush=True)
    dump('V40R4_B6_BODY_EVT_REPORT.json',{'status':'EVT_TAIL_NOT_SUPPORTED','executed':False,'reason':'TRAIN-only threshold admission failed; no forecast fitting for B6',
       'diagnostic':'V40R4_TAIL_THRESHOLD_SELECTION.json'})

def convergence_stage():
    reg,commit,a,info,m=load();indices=np.array(reg['MC_check_flat_intervals']);report={};levels=[.5,.9,.95]
    for name in NAMES:
        p=load_params(OUT/'fits'/name/'selected_params.npz');s=scenarios(p,indices,10000,SEED+71)
        ref=np.quantile(s,levels,axis=1).T;rows=[]
        for M in [1000,2500,5000,10000]:
            q=np.quantile(s[:,:M],levels,axis=1).T;rel=np.abs(q-ref)/(1+ref)
            rows.append({'M':M,'quantiles':q,'mean_relative_error':rel.mean(0),'P95_relative_error':np.quantile(rel,.95,axis=0),'max_absolute_difference_GPUh':np.abs(q-ref).max(0)})
        independent=np.quantile(scenarios(p,indices,10000,SEED+72),levels,axis=1).T
        rel=np.abs(independent-ref)/(1+ref)
        # Near-zero medians use the registered 1 GPUh denominator stabilization.
        passed=bool(np.all(rel.mean(0)<=np.array([.10,.10,.15])) and np.all(np.quantile(rel,.95,axis=0)<=np.array([.30,.30,.40])))
        report[name]={'nested_prefixes':rows,'reference_10000_quantiles':ref,'independent_10000_quantiles':independent,
          'independent_mean_relative_difference':rel.mean(0),'independent_P95_relative_difference':np.quantile(rel,.95,axis=0),
          'convergence_pass':passed,'final_M':10000,'no_count_truncation':True}
        print('MC convergence',name,passed,rel.mean(0).round(4),flush=True)
    dump('V40R4_MONTE_CARLO_CONVERGENCE.json',{'models':report,'quantiles':levels,'flat_intervals':indices,
      'context_selection':'Evenly spaced TRAIN and CALIBRATION index positions before fitting; no evaluation context used','fixed_M':10000,
      'no_post_fit_M_change':True,'convergence_failure_effect':'Model ineligible; no extra scenario search after result'})
    first=read('fits/P1/result.json');trial=first['selected']['trial'];p,meta=fit_neural(trial,a,m,reg,OUT/'fits/P1',tag='independent_repeat')
    save_params(OUT/'fits/P1/independent_repeat_params.npz',p)
    original=load_params(OUT/'fits/P1/selected_params.npz');diff={k:{'max':float(np.abs(p[k]-original[k]).max()),'mean':float(np.abs(p[k]-original[k]).mean())} for k in p if isinstance(p[k],np.ndarray)}
    q=raw_quantiles(p,np.flatnonzero(m['DEVELOPMENT']),10000);oq=raw_quantiles(original,np.flatnonzero(m['DEVELOPMENT']),10000)
    yd=a['target'][m['DEVELOPMENT']]
    dump('V40R4_REPRODUCIBILITY.json',{'P1_runs_total':2,'same_seed':SEED,'repeat_training':meta,'parameter_differences':diff,
      'prediction_max_difference_GPUh':np.abs(q-oq).max(),'prediction_mean_difference_GPUh':np.abs(q-oq).mean(),
      'primary_original':aggregate(yd,oq,reg['burst_GPUh'])['primary'],'primary_repeat':aggregate(yd,q,reg['burst_GPUh'])['primary'],
      'no_repeat_selection':True,'GPU_bitwise_determinism_not_assumed':True})

def freeze_stage():
    reg,commit,a,info,m=load();mc=read('V40R4_MONTE_CARLO_CONVERGENCE.json')['models'];records={}
    for name in NAMES:
        r=read(f'fits/{name}/result.json');s=r['selected'];records[name]={'selected':s,'MC_pass':mc[name]['convergence_pass'],
          'development_eligible':s['gates']['all_pass'] and mc[name]['convergence_pass'],'params_SHA256':r['selected_params_SHA256']}
    bases=[n for n in NAMES if n!='P1'];eligible=[n for n in bases if records[n]['development_eligible']]
    best=min(eligible or bases,key=lambda n:(*rank(records[n]['selected']['metrics']),reg['simplicity_order'].index(n)))
    dump('V40R4_STRONGEST_BASELINE_SELECTION.json',{'strongest_baseline':best,'frozen_before_final_exposed_comparison':True,
      'development_only':True,'development_selection_month':'2024-10','no_eligible_development_baseline':not eligible,
      'candidates':records,'preregistration_commit':commit,'time_UTC':datetime.now(timezone.utc),
      'next_step':'Commit this file and model settings before running final exposed evaluation'})
    print('Development strongest baseline frozen:',best,'Commit required before evaluation.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['fit','convergence','freeze']);args=p.parse_args()
    {'fit':fit_stage,'convergence':convergence_stage,'freeze':freeze_stage}[args.stage]()
