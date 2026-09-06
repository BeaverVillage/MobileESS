import sys
import pickle
import numpy as np
from .common import *
from .protocol import IDS,THRESHOLDS,SPLIT,GATES
from .data import frame,extract,authorize
from .models import repair,exceedance_quantile,Hierarchy,fit_cqr
from .metrics import report,choose
from .train import worker

def feature_frame(f):return pickle.loads((OUT/'models/SUPPORT.pkl').read_bytes()).transform(f)
def raw_predictions(f,stage):
    x=feature_frame(f)
    if not (OUT/(stage.upper()+'_K0.parquet')).exists():worker('K0',stage)
    if not (OUT/(stage.upper()+'_T6.parquet')).exists():worker('T6',stage)
    k=frame(OUT/(stage.upper()+'_K0.parquet'));haz=frame(OUT/(stage.upper()+'_T6.parquet'))
    assert k.job_id.tolist()==f.job_id.tolist()==haz.job_id.tolist();k0=k.K0.to_numpy(float)
    models={cid:pickle.loads((OUT/'models'/(cid+'.pkl')).read_bytes()) for cid in ['T1','T2','T7_GATE','T7_EXCESS']}
    r=models['T1'].predict(x)*3600;direct=models['T2'].predict(x)*3600
    probability=models['T7_GATE'].predict(x)[:,0];conditional=models['T7_EXCESS'].predict(x)*3600
    raw={'T0':np.column_stack([k0+Q,k0+Q]),'T1':np.column_stack([k0+r[:,0],k0+r[:,1]]),'T2':direct[:,1:3],
      'T6':haz[['Q90','Q95']].to_numpy(float),'T7':np.column_stack([k0+exceedance_quantile(probability,conditional,a) for a in [.9,.95]])}
    p={};cross={}
    for cid,b in raw.items():p[cid],cross[cid]=repair(k0,b[:,0],b[:,1])
    cross['T2']['raw_Q50_above_Q90']=int(np.sum(direct[:,0]>direct[:,1]))
    cross['T7']['conditional_knot_crossings']=int(np.sum(np.diff(conditional,axis=1)<0))
    return x,k0,p,cross
def calibrated(x,k0,raw):
    p=dict(raw);extra={}
    cal=pickle.loads((OUT/'models/CALIBRATION.pkl').read_bytes())
    for cid,base in [('T3_R','T1'),('T3_D','T2')]:
        b=raw[base]+cal[cid];p[cid],extra[cid]=repair(k0,b[:,0],b[:,1])
    for n in THRESHOLDS:
        m=cal['T4_N'+str(n)]
        cid='T4_N'+str(n);p[cid],extra[cid]=m.predict(x,k0)
        cid='T8_N'+str(n);p[cid],extra[cid]=m.predict(x,k0,hybrid=True,ml=raw['T1'])
    return {cid:p[cid] for cid in IDS if cid in p},extra
def save_predictions(f,k0,p,stage):
    v=f.copy();v['K0']=k0
    for cid,b in p.items():v[cid+'_Q90']=b[:,0];v[cid+'_Q95']=b[:,1]
    path=OUT/(stage.upper()+'_PREDICTIONS.parquet');v.to_parquet(path,index=False);return path

def development():
    require_prereg();f=frame(OUT/'VISIBLE_DEVELOPMENT_ROWS.parquet');x,k0,p,cross=raw_predictions(f,'visible_development')
    results={cid:report(f,k0,b,x,'visible_development') for cid,b in p.items()}
    save_predictions(f,k0,p,'visible_development')
    write('V40L_VISIBLE_DEVELOPMENT_DIAGNOSTIC.json',{'status':'VISIBLE_NOT_BLIND','rows':len(f),'metrics':results,'crossing':cross,'winner_selected':False,'threshold_selected':False,'calibration_correction_fit':False,'architecture_changed':False})
    event('visible_development_diagnostic_complete',rows=len(f),model_or_threshold_changes=False)
    print('VISIBLE_DEVELOPMENT_DIAGNOSTIC_SAVED',len(f),flush=True)

def calibrate():
    assert not (OUT/'V40L_CALIBRATION_FREEZE.json').exists()
    f=extract('calibration')
    if len(f)<100:
        write('V40L_CALIBRATION_STATUS.json',{'status':'INSUFFICIENT_CALIBRATION','rows':len(f)},immutable=True);return
    x,k0,raw,cross=raw_predictions(f,'calibration');y=f.runtime_seconds.to_numpy(float)
    fitted={'T3_R':fit_cqr(y,raw['T1'],block='calibration'),'T3_D':fit_cqr(y,raw['T2'],block='calibration')}
    for n in THRESHOLDS:fitted['T4_N'+str(n)]=Hierarchy(n).fit(x,y-k0,block='calibration')
    path=OUT/'models/CALIBRATION.pkl';path.write_bytes(pickle.dumps(fitted,protocol=5))
    p,extra=calibrated(x,k0,raw);save_predictions(f,k0,p,'calibration')
    write('V40L_T3_CQR_REPORT.json',{'status':'CALIBRATION_ONLY_FROZEN','rows':len(f),'block':SPLIT['calibration'],'corrections_seconds':{k:fitted[k].tolist() for k in ['T3_R','T3_D']},'signed_scores':True,'fitted_on_selection':False,'max_label_end':str(f.end_time.max())})
    write('V40L_T4_HIERARCHICAL_CONFORMAL_REPORT.json',{'status':'CALIBRATION_ONLY_FROZEN','rows':len(f),'thresholds':THRESHOLDS,'selection_of_threshold':False,'hierarchy_levels':4,'deterministic_fallback':True,'calibration_tables':{cid:[{str(key):{'n':v['n'],'q':v['q'].tolist()} for key,v in table.items() if v['n']>=20} for table in fitted[cid].tables] for cid in fitted if cid.startswith('T4')}})
    write('V40L_T8_HYBRID_REPORT.json',{'status':'FROZEN_SUPPORT_ROUTING','thresholds':THRESHOLDS,'OOD':'ABSTAIN; no verified walltime ceiling authority','fallback':extra,'calibration_N':len(f)})
    write('V40L_CALIBRATION_FREEZE.json',{'created_at':now(),'rows':len(f),'file_SHA':{p.relative_to(ROOT).as_posix():sha(p) for p in [path,OUT/'CALIBRATION_ROWS.parquet']},'ML_refits':0,'structure_changes':0,'hyperparameter_changes':0,'selection_opened':False,'shadow_opened':False},immutable=True)
    event('calibration_frozen',rows=len(f),model_SHA=sha(path));print('CALIBRATION_FROZEN',len(f),flush=True)

def selection():
    assert not (OUT/'V40L_TAIL_SELECTION_COMPARISON.json').exists(),'SELECTION_ALREADY_FINAL'
    f=extract('selection')
    if len(f)<100:
        write('V40L_TAIL_SELECTION_COMPARISON.json',{'winner':None,'eligible':[],'status':'V40L_TAIL_MODEL_INSUFFICIENT','reason':'INSUFFICIENT_SELECTION_ROWS','rows':len(f),'candidates':{}},immutable=True)
        write('V40L_TAIL_METHOD_FREEZE.json',{'winner':None,'status':'NO_WINNER_NO_TAIL_FREEZE'},immutable=True);return
    x,k0,raw,cross=raw_predictions(f,'selection');p,extra=calibrated(x,k0,raw)
    results={cid:report(f,k0,b,x,'selection') for cid,b in p.items()}
    results['T5']={'status':'NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE','eligible':False}
    winner,eligible=choose(results);prediction_path=save_predictions(f,k0,p,'selection')
    comparison={'created_at':now(),'winner':winner,'eligible':eligible,'status':'TAIL_WINNER_SELECTED' if winner else 'V40L_TAIL_MODEL_INSUFFICIENT','rows':len(f),'candidates':results,'crossing_before_repair':cross,'fallback':extra,'gates':GATES,'K0_unchanged':True,'shadow_opened':False}
    write('V40L_TAIL_SELECTION_COMPARISON.json',comparison,immutable=True)
    write('V40L_GPU_WEIGHTED_SAFETY_REPORT.json',{'stage':'selection','baseline':results['T0']['metrics']['overall'],'winner':winner,'winner_metrics':results[winner]['metrics']['overall'] if winner else None,'no_electrical_grid_claim':True})
    freeze={'created_at':now(),'winner':winner,'status':'FROZEN' if winner else 'NO_WINNER_NO_TAIL_FREEZE','Q90_method':winner,'Q95_method':winner if winner else None,'Q95_role':'extreme-risk diagnostic, never Q90 gate substitution',
      'source_SHA':read('V40L_PRECALIBRATION_EXECUTION_FREEZE.json')['file_SHA'],'calibration_freeze_SHA':sha(OUT/'V40L_CALIBRATION_FREEZE.json'),'selection_predictions_SHA':sha(prediction_path),'K0_SHA':sha(K/'models/K0_FINAL.pkl'),'no_refit_retune_reselection':True,'shadow_opened':False}
    write('V40L_TAIL_METHOD_FREEZE.json',freeze,immutable=True);event('tail_winner_frozen',winner=winner,shadow_opened=False)
    print('TAIL_SELECTION',json.dumps({'winner':winner,'eligible':eligible,'rows':len(f),'coverage':{k:v['metrics']['overall']['Q90']['coverage'] for k,v in results.items() if 'metrics' in v}}),flush=True)

def shadow():
    assert not (OUT/'V40L_FINAL_SHADOW_REPORT.json').exists(),'SHADOW_ALREADY_FINAL'
    winner=read('V40L_TAIL_METHOD_FREEZE.json')['winner'];assert winner
    f=extract('shadow')
    if f.empty:
        write('V40L_FINAL_SHADOW_REPORT.json',{'status':'V40L_FINAL_SHADOW_FAIL_HOLD','reason':'NO_SAFE_DECODABLE_SHADOW_ROW_GROUPS','opened':False,'open_authorized_after_winner_freeze':True,'runtime_status_rows_read':0,'metrics':None,'winner':winner,'winner_changed':False,'q_changed':False,'refit':False,'threshold_changed':False},immutable=True);return
    x,k0,raw,cross=raw_predictions(f,'shadow');p,extra=calibrated(x,k0,raw)
    # Compute only baseline and frozen winner metrics, never a shadow candidate ranking.
    metrics={cid:report(f,k0,p[cid],x,'shadow') for cid in ['T0',winner]}
    dates=sorted(f.submit_time.dt.strftime('%Y-%m-%d').unique().tolist());complete=dates==pd.date_range('2025-04-24','2025-04-30').strftime('%Y-%m-%d').tolist()
    passed=metrics[winner]['eligible'] and complete
    save_predictions(f,k0,{cid:p[cid] for cid in ['T0',winner]},'shadow')
    write('V40L_FINAL_SHADOW_REPORT.json',{'status':'PASS' if passed else 'V40L_FINAL_SHADOW_FAIL_HOLD','opened':True,'runtime_status_rows_read':len(f),'metrics':metrics,'all_seven_dates':complete,'dates':dates,'winner':winner,'winner_changed':False,'q_changed':False,'refit':False,'threshold_changed':False},immutable=True)

def main():
    stage=sys.argv[1]
    with Firewall('evaluate_'+stage,raw=stage in ['calibration','selection','shadow']):
        {'development':development,'calibration':calibrate,'selection':selection,'shadow':shadow}[stage]()
if __name__=='__main__':main()
