"""Frozen development comparator, calibration and exposed-block evaluation."""
from .train import load,ALL_NAMES
from .metrics import summarize,gates,calibrate,day_block_bootstrap,eligible_proposed
from .common import *
from datetime import datetime

REPORT_NAMES={'ZERO':'ZERO','SEASONAL':'SEASONAL','LIGHTGBM':'LIGHTGBM','HURDLE_LIGHTGBM':'HURDLE_LIGHTGBM',
 'XGBOOST':'XGBOOST','TFT':'TFT','DEEPAR':'DEEPAR','NHITS':'EXTRA_TEMPORAL_BENCHMARK','CMABF':'CMABF'}

def rank(name,metrics):
    m=metrics[name]
    return (m['probabilistic']['primary_positive_Q90_normalized_pinball'],m['burst']['missed_burst_GPUh'],
       m['point']['positive']['WAPE'],m['cumulative']['WAPE'],ALL_NAMES.index(name))

def main():
    reg,commit,a,info,masks=load()
    prefit=read('V40R3_PREFIT_TEST_REPORT.json');assert prefit['failed']==0 and prefit['errors']==0
    y=np.load(OUT/'causal_dataset.npz')['target'];threshold=reg['burst']['training_positive_Q95_GPUh']
    dev=masks['DEVELOPMENT'];cal=masks['CALIBRATION'];test=masks['EXPOSED_EVALUATION']
    dates=info.operating_day.to_numpy();pred={};devmetrics={};devgates={};fit={}
    for name in ALL_NAMES:
        fit[name]=read(f'fits/{name}/result.json');assert fit[name]['status']=='COMPLETE'
        pred[name]=np.load(OUT/'fits'/name/'prediction.npy')
        devmetrics[name]=summarize(y[dev],pred[name][dev],threshold)
        devgates[name]=gates(y[dev],pred[name][dev],threshold,dates[dev])
    baseline_names=[n for n in ALL_NAMES if n!='CMABF']
    eligible_dev=[n for n in baseline_names if devgates[n]['all_pass']]
    comparator=min(eligible_dev or baseline_names,key=lambda name:rank(name,devmetrics))
    frozen={'model':comparator,'source':'DEVELOPMENT before calibration/evaluation comparison and bootstrap',
      'development_safety_pass':devgates[comparator]['all_pass'],'no_development_safety_pass_baseline':not eligible_dev,
      'ranking':sorted(baseline_names,key=lambda name:rank(name,devmetrics)),
      'primary_values':{n:devmetrics[n]['probabilistic']['primary_positive_Q90_normalized_pinball'] for n in baseline_names},
      'prediction_SHA256':fit[comparator]['prediction_SHA256'],'frozen_UTC':datetime.now(timezone.utc).isoformat()}
    dump('V40R3_STRONGEST_BASELINE_SELECTION.json',frozen)
    freeze_hash=sha(OUT/'V40R3_STRONGEST_BASELINE_SELECTION.json')
    metrics={};safety={};calibration={};point=[]
    for name in ALL_NAMES:
        delta,calmeta=(0.,{'definition':'ZERO stays exactly zero'}) if name=='ZERO' else calibrate(y[cal],pred[name][cal],threshold)
        cp=pred[name].copy();cp[...,1]+=delta
        np.save(OUT/'fits'/name/'calibrated_prediction.npy',cp)
        metrics[name]=summarize(y[test],cp[test],threshold);safety[name]=gates(y[test],cp[test],threshold,dates[test]);calibration[name]=calmeta
        worst=[];yb=y[test];q=cp[test,:,1];idx=np.argwhere(yb>=threshold)
        if len(idx):
            errors=np.maximum(yb[idx[:,0],idx[:,1]]-q[idx[:,0],idx[:,1]],0)
            for ix in np.argsort(-errors)[:10]:
                d,k=idx[ix];worst.append({'day':dates[test][d],'slot':int(k),'actual_GPUh':float(yb[d,k]),'Q90_GPUh':float(q[d,k]),'miss_GPUh':float(errors[ix])})
        report={'model':name,'status':'EVALUATED_EXPOSED_BLOCK_NOT_UNTOUCHED_CONFIRMATION','preregistration_commit':commit,
          'fit':fit[name],'development_uncalibrated':devmetrics[name],'calibration':calmeta,
          'evaluation':metrics[name],'raw_evaluation':summarize(y[test],pred[name][test],threshold),
          'safety':safety[name],'worst_burst_intervals':worst}
        dump(f'V40R3_{REPORT_NAMES[name]}_REPORT.json',report)
        row={'model':name,**metrics[name]['point']['overall'],
          **{'positive_'+k:v for k,v in metrics[name]['point']['positive'].items()},'safety_pass':safety[name]['all_pass']}
        point.append(row)
    # Comparator identity is fixed before this inference step and may not change.
    assert sha(OUT/'V40R3_STRONGEST_BASELINE_SELECTION.json')==freeze_hash
    b=np.load(OUT/'fits'/comparator/'calibrated_prediction.npy')[test,:,1]
    c=np.load(OUT/'fits/CMABF/calibrated_prediction.npy')[test,:,1]
    comparison=day_block_bootstrap(y[test],b,c)
    comparison.update(baseline=comparator,baseline_freeze_SHA256=freeze_hash,baseline_frozen_before_bootstrap=True,
      status='PREVALIDATION_COMPARISON_ON_EXPOSED_HISTORY',untouched_confirmatory=False)
    dump('V40R3_PAIRED_BOOTSTRAP_SUPERIORITY.json',comparison)
    best_numeric=all(rank('CMABF',metrics)[0]<rank(n,metrics)[0] for n in baseline_names)
    proposed=eligible_proposed(safety['CMABF']['all_pass'],best_numeric,float(comparison['CI95'][0]))
    existing_pass=[n for n in baseline_names if safety[n]['all_pass']]
    if proposed:selected='CMABF';classification='V40R3_CMABF_PREVALIDATED'
    elif existing_pass:selected=min(existing_pass,key=lambda name:rank(name,metrics));classification='V40R3_EXISTING_MODEL_SELECTED'
    elif not any(s['all_pass'] for s in safety.values()):selected=None;classification='V40R3_FUTURE_GPUWORK_SAFETY_FAIL'
    else:selected=None;classification='V40R3_CMABF_SUPERIORITY_NOT_ESTABLISHED'
    dump('V40R3_METHOD_SELECTION.json',{'classification':classification,'selected_model':selected,
      'CMABF_safety':'PASS' if safety['CMABF']['all_pass'] else 'FAIL','CMABF_superiority_established':bool(comparison['superiority_established']),
      'CMABF_numerically_better_than_every_benchmark':best_numeric,'CMABF_paper_model_eligible':proposed,
      'strongest_development_baseline':comparator,'true_confirmation_available':False,
      'selection_scope':'All final scores are development/prevalidation evidence because historical periods were exposed; no VALIDATED or PRODUCTION_READY claim',
      'reason':'All safety gates first, then frozen hierarchy; CMABF additionally needs every-baseline numeric superiority and paired CI lower>0'})
    dump('V40R3_MODEL_FREEZE.json',{'selected_model':selected,'selection_status':classification,
      'preregistration_commit':commit,'prediction_SHA256':sha(OUT/'fits'/selected/'calibrated_prediction.npy') if selected else None,
      'calibration':calibration.get(selected),'production_integration':False,'optimizer':False})
    dump('V40R3_CONFIRMATORY_RESULT.json',{'available':False,'status':'NOT_RUN_NO_UNTOUCHED_BLOCK','maximum_positive_claim':'PREVALIDATED','retuning_after_evaluation':False})
    pd.DataFrame(point).to_csv(OUT/'V40R3_POINT_METRICS.csv',index=False)
    for file,key in [('PROBABILISTIC_METRICS','probabilistic'),('BURST_METRICS','burst'),('CUMULATIVE_ARRIVAL_METRICS','cumulative')]:
        dump(f'V40R3_{file}.json',{'scope':'mature model forecasts, Dec1..Feb26 exposed evaluation','models':{n:v[key] for n,v in metrics.items()}})
    dump('V40R3_SAFETY_GATE_TABLE.json',{'models':safety,'failed_months_never_pooled_away':True})
    ablation={}
    for name in ['CMABF_A0','CMABF_A1','CMABF_A2']:
        p=np.load(OUT/'fits'/name/'prediction.npy');delta,cm=calibrate(y[cal],p[cal],threshold);p[...,1]+=delta
        ablation[name]={'calibration':cm,'metrics':summarize(y[test],p[test],threshold),'safety':gates(y[test],p[test],threshold,dates[test]),'primary_model_selection_eligible':False}
    ablation['CMABF_FULL']={'calibration':calibration['CMABF'],'metrics':metrics['CMABF'],'safety':safety['CMABF']}
    dump('V40R3_CMABF_ABLATION_REPORT.json',{'secondary_only':True,'ablations':ablation})
    print(json.dumps(clean({'classification':classification,'selected':selected,'CMABF_safety':safety['CMABF']['all_pass'],
      'comparator':comparator,'bootstrap':comparison,'metrics':{n:{'primary':rank(n,metrics)[0],'safety':safety[n]['all_pass']} for n in ALL_NAMES}}),indent=2))

if __name__=='__main__':main()
