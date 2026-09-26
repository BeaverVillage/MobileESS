"""Read-only verification of the complete evidence package; no fitting/import of production."""
from common import *
import argparse
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--external',action='store_true',help='Also rehash local raw and frozen external authorities')
    args=parser.parse_args()
    required=['README.md','TARGET_DEFINITION.md','EXPERIMENT_PROTOCOL.json','DATA_SPLITS_AND_MATURITY.json',
        'TARGET_RECONSTRUCTION_AUDIT.json','POPULATION_COMPARISON.json','LEAKAGE_AUDIT.json','MODEL_METRICS.csv',
        'DAY_METRICS.csv','HOUR_OF_DAY_METRICS.csv','LEAD_TIME_METRICS.csv','BURST_METRICS.csv',
        'PAIRED_DAY_BLOCK_UNCERTAINTY.csv','FINAL_SELECTION_FREEZE.json','FINAL_REVIEW_KO.md','SOURCE_MANIFEST.json',
        'SPLIT_MEMBERSHIP_DIFF.csv','CALIBRATION_FREEZE.json','MODEL_SELECTION_FREEZE.json','PREDICTIONS.parquet']
    for name in required:require((ROOT/name).is_file(),'missing '+name)
    checks={}
    code=json.loads((ROOT/'PRETRAIN_CODE_FREEZE.json').read_text(encoding='utf-8'))
    for name,digest in code['files'].items():require(sha(ROOT/name)==digest,'scientific code drift '+name)
    require(sha(ROOT/'EXPERIMENT_PROTOCOL.json')==code['protocol_sha256'],'protocol changed')
    checks['frozen_code_files']=len(code['files'])
    times=[]
    for file,key in [('EXPERIMENT_PROTOCOL.json','registered_at'),('MODEL_SELECTION_FREEZE.json','time'),
        ('CALIBRATION_FREEZE.json','time'),('EXPOSED_EVALUATION_COMPLETE.json','time'),
        ('MAY_HISTORICAL_COMPLETE.json','time'),('FINAL_SELECTION_FREEZE.json','time')]:
        times.append(pd.Timestamp(json.loads((ROOT/file).read_text(encoding='utf-8'))[key]))
    require(times==sorted(times),'chronology violation')
    checks['chronology']='PASS'
    split=json.loads((ROOT/'DATA_SPLITS_AND_MATURITY.json').read_text(encoding='utf-8'))
    ledger=pd.read_csv(ROOT/'DAY_LEDGER.csv');data=np.load(ROOT/'DATA.npz')
    require(np.array_equal(data['days'],ledger.target_day),'dataset day order')
    datasets=pd.read_parquet(ROOT/'HOURLY_DATASET.parquet')
    require(datasets.groupby('target_day').size().eq(24).all(),'lost hourly rows')
    require(datasets.groupby('target_day').split.nunique().eq(1).all(),'day divided across roles')
    seen=set()
    for role in ROLES:
        m=pd.read_csv(ROOT/f'{role}_MEMBERSHIP.csv')
        require(m.target_day.tolist()==split['memberships'][role]['dates'],'membership date mismatch')
        require(len(m)==split['memberships'][role]['N_days'],'membership count')
        require(not set(m.target_day)&seen,'overlapping split')
        seen.update(m.target_day)
        if role in ROLES[:3]:
            cut=pd.Timestamp(split['memberships'][role]['cutoff'])
            require(pd.to_datetime(m.label_matured_at,utc=True).lt(cut).all(),'late fitting/calibration label')
    proof=pd.read_parquet(ROOT/'FEATURE_MATURITY_PROOF.parquet')
    require(pd.to_datetime(proof.feature_available_at,utc=True).le(pd.to_datetime(proof.issue_time,utc=True)).all(),'late feature')
    require(proof.groupby('target_day').feature.nunique().eq(71).all(),'incomplete feature proof')
    checks['feature_hour_maturity_checks']=len(proof)*24
    reconstruction=pd.read_csv(ROOT/'DAILY_TARGET_RECONSTRUCTION.csv')
    require(reconstruction.absolute_error.max()<1e-7 and reconstruction.atomic_max_error.max()<1e-7,'target reconstruction')
    checks['max_raw_target_error_GPUh']=float(reconstruction.absolute_error.max())
    pred=pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    selected=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    cal=json.loads((ROOT/'CALIBRATION_FREEZE.json').read_text(encoding='utf-8'))
    cal_ids=np.flatnonzero(ledger.split.eq('CALIBRATION')&ledger.eligible)
    for run in selected['runs']:
        cq=np.load(ROOT/'fits'/run['tag']/'calibration_prediction.npy')
        delta,rank=finite_residual(data['y'][cal_ids],cq[...,1])
        saved=cal['corrections'][run['tag']]
        require(np.array_equal(delta,np.array(saved['delta_GPUh'])) and rank==saved['rank'],'residual order statistic')
        require(saved['dates']==split['memberships']['CALIBRATION']['dates'],'calibration population drift')
    for (tag,role),g in pred.groupby(['tag','split']):
        require(g.target_day.nunique()==split['memberships'][role]['N_days'],'evaluation population reduction')
        require(g.groupby('target_day').target_hour.agg(list).apply(lambda x:sorted(x)==list(range(24))).all(),'hour loss/duplicate')
        delta=np.asarray(cal['corrections'][tag]['delta_GPUh'])[g.target_hour.to_numpy()]
        expected=np.maximum(g.Q50.to_numpy(),np.maximum(0,g.raw_Q90.to_numpy()+delta))
        require(np.array_equal(g.Q90,expected),'cap, scaling or calibration drift')
        for day,dd in g.groupby('target_day'):
            i=np.flatnonzero(data['days']==day)[0]
            require(np.array_equal(dd.sort_values('target_hour').actual_GPUh,data['y'][i]),'target changed')
            require((pd.to_datetime(dd.issue_time,utc=True)==issue(day).tz_convert('UTC')).all(),'issue changed')
        require(np.isfinite(g[['Q50','Q90','actual_GPUh']]).all().all(),'nonfinite predictions')
    checks['prediction_rows']=len(pred)
    checks['uncapped_correction_identity']='PASS'
    table=pd.read_csv(ROOT/'MODEL_METRICS.csv')
    for row in table.to_dict('records'):
        g=pred[pred.model.eq(row['model'])&pred.seed.eq(row['seed'])&pred.split.eq(row['split'])]
        q50=g.raw_Q50 if row['variant']=='raw' else g.Q50
        q90=g.raw_Q90 if row['variant']=='raw' else g.Q90
        expected=metrics(g.actual_GPUh,q50,q90)
        for key,value in expected.items():
            require(np.isclose(value,row[key],rtol=1e-12,atol=1e-10,equal_nan=True),'metric mismatch '+key)
    checks['verified_metric_rows']=len(table)
    for role in ROLES[-2:]:
        receipt=json.loads((ROOT/f'{role}_COMPLETE.json').read_text(encoding='utf-8'))
        require(sha(ROOT/f'{role}_PREDICTIONS.parquet')==receipt['prediction_sha256'],'evaluation snapshot changed')
        require(sha(ROOT/'CALIBRATION_FREEZE.json')==receipt['calibration_sha256'],'calibration changed after evaluation')
    if args.external:
        manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        for item in manifest['sources']:require(sha(item['path'])==item['sha256'],'external authority drift '+item['path'])
        checks['external_authority_hashes']=len(manifest['sources'])
        bridge=json.loads((ROOT/'RAW_PR57_BRIDGE.json').read_text(encoding='utf-8'))['frozen_source']
        require(sha(bridge['path'])==bridge['sha256'],'PR57 window source drift')
        checks['external_authority_hashes']+=1
    else:checks['external_authority_hashes']='not requested; originals external to portable package'
    final=json.loads((ROOT/'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    require(not final['OPTIMIZER_CHANGED'] and final['GRID_CAMPAIGN_EXECUTIONS']==0 and not final['PRODUCTION_MODEL_PROMOTED'],'scope flag')
    require(final['selected_family_frozen_on_DEVELOPMENT']==selected['selected_family'],'evaluation reselection')
    require(final['Q90_90PCT_CALIBRATION_SUPPORTED']==all(final['gates'].values()),'gate mismatch')
    if (ROOT/'DELIVERY_MANIFEST.json').exists():
        manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
        for name,digest in manifest['files'].items():require(sha(ROOT/name)==digest,'delivery hash '+name)
        checks['delivery_file_hashes']=len(manifest['files'])
    checks.update(status='PASS',checked_at=now(),required_files=len(required),OPTIMIZER_CHANGED=False,
                  GRID_CAMPAIGN_EXECUTIONS=0,PRODUCTION_MODEL_PROMOTED=False)
    dump('VALIDATION.json',checks)
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
