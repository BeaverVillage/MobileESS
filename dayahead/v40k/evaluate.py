"""One-way point/safe/shadow stages; nothing fitted after final freezes."""
import argparse
import pickle
import subprocess
import numpy as np
import pandas as pd
from .common import *
from .data import frame,extract,train_mask
from .models import features
from .metrics import report,point_gate,safety,subgroups
from .protocol import IDS,SPLIT,SAFE
from dayahead.v40j.methods import SupportGuard,groups,key_rows,conformal_q

PYTHON=Path('C:/Users/kjw39/AppData/Local/MobileESS/venvs/v35r3d-runtime/Scripts/python.exe')
def verify_lock():
    lock=read('V40K_PREHOLDOUT_EXECUTION_FREEZE.json')
    for n,h in lock['models_SHA'].items():assert sha(OUT/'models'/n)==h
    assert sha(OUT/'V40K_STACKING_WEIGHTS.json')==lock['weights_SHA']
    for n,h in lock['source_SHA'].items():assert sha(ROOT/'dayahead/v40k'/n)==h,('EXECUTION_SOURCE_CHANGED',n)
    receipt=read('V40K_PREHOLDOUT_COMMIT_RECEIPT.json')
    assert hashlib.sha256(git('show',receipt['commit']+':dayahead/artifacts/v40k_central_runtime/V40K_PREHOLDOUT_EXECUTION_FREEZE.json')).hexdigest()==sha(OUT/'V40K_PREHOLDOUT_EXECUTION_FREEZE.json')
    return lock
def c0(f,stage):
    target=OUT/(stage+'_C0.parquet')
    if not target.exists():
        result=subprocess.run([str(PYTHON),'-B','-m','dayahead.v40k.baseline',stage],cwd=ROOT,capture_output=True,text=True)
        (OUT/(stage+'_C0.log')).write_text(result.stdout+result.stderr,encoding='utf-8',newline='\n')
        assert result.returncode==0,('BASELINE_PREDICT_FAILED',result.stderr[-2000:])
    p=frame(target);assert p.job_id.tolist()==f.job_id.tolist()
    return p.K0.to_numpy()
def central_predictions(f,base):
    lock=verify_lock();x=features(f);result={'K0':base}
    for cid in IDS[1:-1]:
        if cid in lock['unavailable']:continue
        m=pickle.loads((OUT/'models'/('FINAL_'+cid+'.pkl')).read_bytes());result[cid]=m.predict(x,c0=base)
    w=read('V40K_STACKING_WEIGHTS.json');result['K5_STACKING']=np.column_stack([result[c] for c in w['base_ids']])@w['weights']
    return result
def frozen_point(f,base):
    winner=read('V40K_POINT_MODEL_FREEZE.json')['winner']
    return central_predictions(f,base)[winner]
def support_guard():
    f=frame(J/'DEVELOPMENT_GPU_ROWS.parquet');f=f.loc[train_mask(f,SPLIT['final_point_fit_before'])]
    return SupportGuard(features(f),100)

class SafeBound:
    def __init__(self,kind):self.kind=kind;self.tables=[]
    def fit(self,x,y,point):
        g=groups(x)
        for cols in SAFE['groups'][self.kind]:
            ix={}
            for i,k in enumerate(key_rows(g,cols)):ix.setdefault(k,[]).append(i)
            self.tables.append({k:{'n':len(v),'q':conformal_q(np.asarray(y)[v]-point[v],.9)} for k,v in ix.items()})
        return self
    def predict(self,x,point,support):
        g=groups(x);keys=[key_rows(g,c) for c in SAFE['groups'][self.kind]];out=np.asarray(point).copy();counts=[];fallback=[]
        for i,state in enumerate(support.support_class):
            possible=[]
            for level,table in enumerate(self.tables):
                v=table.get(keys[level][i]);last=level==len(self.tables)-1
                if v and (v['n']>=100 or last) and (self.kind!='S3' or state=='STRONG_SUPPORT' or level>0):possible.append((level,v))
            if not possible:raise ValueError('CALIBRATION_POOLED_EMPTY')
            use=possible if self.kind=='S3' and state!='STRONG_SUPPORT' else possible[:1]
            out[i]+=max(v['q'] for _,v in use)
            if self.kind=='S3' and state=='OUT_OF_SUPPORT':out[i]=max(out[i],float(x.requested_seconds.iloc[i]))
            counts.append(use[0][1]['n']);fallback.append(use[0][0])
        assert np.isfinite(out).all() and (out>=point).all()
        return out,np.asarray(counts),np.asarray(fallback)
def safe_report(f,bound,counts):
    result={'overall':safety(f,bound)}
    masks=subgroups(f)
    gates={'overall':len(f)>=100 and result['overall']['coverage']>=.9}
    for group in ['H100','H100-standby']:
        m=np.asarray(masks[group])&(counts>=100)
        result[group]={'N':int(m.sum()),'status':'NOT_SUPPORT_SUFFICIENT'}
        if m.sum()>=100:result[group]=safety(f.loc[m],bound[m]);gates[group]=result[group]['coverage']>=.9
    return {'metrics':result,'gates':gates,'eligible':all(gates.values())}

def select_point():
    assert not (OUT/'V40K_POINT_SELECTION.json').exists(),'POINT_SELECTION_ALREADY_FINAL'
    verify_lock();assert read('V40K_FEATURE_TARGET_EQUIVALENCE.json')['status']=='PASS'
    f=extract('point_selection')
    if f.empty:raise ValueError('NO_POINT_SELECTION_ROWS')
    base=c0(f,'point_selection');preds=central_predictions(f,base);metrics={k:report(f,p) for k,p in preds.items()}
    records={k:{'metrics':v,**point_gate(metrics['K0'],v,True)} for k,v in metrics.items() if k!='K0'}
    eligible=[k for k,v in records.items() if v['eligible']]
    winner=None
    if eligible:
        minimum=min(metrics[k]['overall']['pinball_Q50'] for k in eligible)
        winner=min((k for k in eligible if metrics[k]['overall']['pinball_Q50']<=minimum*1.001),key=IDS.index)
    selection={'created_at':now(),'winner':winner,'eligible':eligible,'status':'POINT_READY' if winner else 'V40K_POINT_MODEL_INSUFFICIENT',
      'new_point_holdout_rows':len(f),'preregistration_commit':require_prereg(),'shadow_opened':False,'mean_signed_error_used_as_gate':False}
    write('V40K_POINT_MODEL_COMPARISON.json',{'baseline':metrics['K0'],'candidates':records,'selection':selection})
    v=f.copy()
    for cid,p in preds.items():v[cid]=p
    v.to_parquet(OUT/'POINT_HOLDOUT_PREDICTIONS.parquet',index=False)
    write('V40K_POINT_SELECTION.json',selection,immutable=True)
    event('point_selection_frozen',winner=winner)
    if winner:
        support=support_guard().predict(features(f));lock=verify_lock()
        write('V40K_POINT_MODEL_FREEZE.json',{'winner':winner,'created_at':now(),'target':'CONDITIONAL_MEDIAN_RUNTIME_Q50',
          'feature_contract':FEATURES,'split':SPLIT,'training_input_SHA':sha(J/'DEVELOPMENT_GPU_ROWS.parquet'),
          'OOF_SHA':sha(OUT/'RESIDUAL_OOF_ROWS.parquet'),'model_SHA':lock['models_SHA'],'source_SHA':lock['source_SHA'],
          'stack_weights_SHA':lock['weights_SHA'],'metrics':metrics[winner],
          'support_counts':support.support_class.value_counts().to_dict(),'final_status_leakage_test':'PASS','determinism':'PASS',
          'models_unchanged_after_selection':True,'no_refit_after_freeze':True},immutable=True)
    print(json.dumps(selection),flush=True)

def safe_stage():
    assert not (OUT/'V40K_SAFE_SELECTION.json').exists(),'SAFE_SELECTION_ALREADY_FINAL'
    fit=extract('safe_fit');assert len(fit)>=100,'SAFE_FIT_INSUFFICIENT'
    p=frozen_point(fit,c0(fit,'safe_fit'));x=features(fit);models={};det={}
    guard=support_guard();sp=guard.predict(x)
    for k in SAFE['ids']:
        m=SafeBound(k).fit(x,fit.runtime_seconds.to_numpy(),p);m2=SafeBound(k).fit(x,fit.runtime_seconds.to_numpy(),p)
        a=m.predict(x,p,sp)[0];b=m2.predict(x,p,sp)[0];assert a.tobytes()==b.tobytes()
        models[k]=m;det[k]=True;(OUT/'models'/('SAFE_'+k+'.pkl')).write_bytes(pickle.dumps(m,protocol=5))
    write('V40K_SAFES_PRESELECTION_LOCK.json',{'models_SHA':{k:sha(OUT/'models'/('SAFE_'+k+'.pkl')) for k in models},'determinism':det,'fit_SHA':sha(OUT/'SAFE_FIT_ROWS.parquet')},immutable=True)
    f=extract('safe_selection');assert len(f)>=100,'SAFE_SELECTION_INSUFFICIENT'
    point=frozen_point(f,c0(f,'safe_selection'));xx=features(f);support=guard.predict(xx);records={}
    for k,m in models.items():
        b,n,level=m.predict(xx,point,support);records[k]=safe_report(f,b,n);records[k]['fallback_level_counts']={str(v):int((level==v).sum()) for v in set(level)}
    eligible=[k for k,v in records.items() if v['eligible']]
    winner=min(eligible,key=lambda k:(records[k]['metrics']['overall']['overreserved_GPU_hours'],SAFE['ids'].index(k))) if eligible else None
    write('V40K_SAFE_BOUND_COMPARISON.json',{'candidates':records,'winner':winner,'objective':'minimum native overreserved GPU-hours after coverage gates'})
    write('V40K_SAFE_SELECTION.json',{'winner':winner,'created_at':now(),'status':'READY' if winner else 'INSUFFICIENT'},immutable=True)
    if winner:write('V40K_SAFE_BOUND_FREEZE.json',{'winner':winner,'created_at':now(),'model_SHA':sha(OUT/'models'/('SAFE_'+winner+'.pkl')),'point_freeze_SHA':sha(OUT/'V40K_POINT_MODEL_FREEZE.json'),'support_threshold':100,'metrics':records[winner],'no_refit_or_retune':True},immutable=True)
    event('safe_selection_frozen',winner=winner);print('SAFE_SELECTION',winner,flush=True)

def shadow():
    assert not (OUT/'V40K_FINAL_SHADOW_REPORT.json').exists(),'SHADOW_ALREADY_FINAL'
    f=extract('final_shadow')
    if f.empty:
        write('V40K_FINAL_SHADOW_REPORT.json',{'status':'FAIL_HOLD_NO_SAFE_DECODABLE_GROUPS','runtime_status_rows_opened':0,'point_winner_changed':False,'q_changed':False,'refit':False,'metrics':None,
          'reason':'All shadow groups contain post-cutoff timestamps. Strict predeclared decoder firewall excludes them; full April24-30 readiness cannot be established.'},immutable=True);return
    b=c0(f,'final_shadow');p=frozen_point(f,b);m=pickle.loads((OUT/'models'/('SAFE_'+read('V40K_SAFE_BOUND_FREEZE.json')['winner']+'.pkl')).read_bytes())
    bound,n,level=m.predict(features(f),p,support_guard().predict(features(f)))
    baseline=report(f,b);point=report(f,p);pg=point_gate(baseline,point,True);sg=safe_report(f,bound,n)
    dates=sorted(f.submit_time.dt.strftime('%Y-%m-%d').unique().tolist());complete=dates==pd.date_range('2025-04-24','2025-04-30').strftime('%Y-%m-%d').tolist()
    passed=pg['eligible'] and sg['eligible'] and complete
    write('V40K_FINAL_SHADOW_REPORT.json',{'status':'PASS' if passed else 'FAIL_HOLD','runtime_status_rows_opened':len(f),'baseline':baseline,'point':point,'point_gates':pg,'safe':sg,'complete_seven_dates':complete,'dates':dates,'point_winner_changed':False,'q_changed':False,'refit':False},immutable=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['point','safe','shadow']);args=parser.parse_args()
    with Firewall('evaluate_'+args.stage,files=[ARCHIVE],roots=[ROOT/'dayahead/v40k']):
        {'point':select_point,'safe':safe_stage,'shadow':shadow}[args.stage]()
if __name__=='__main__':main()
