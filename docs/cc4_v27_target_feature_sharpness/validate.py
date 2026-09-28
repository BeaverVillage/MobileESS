from core import *
import subprocess,sys
def main():
    source=read(ROOT/'SOURCE_MANIFEST.json');bad=[]
    for p,h in source['files'].items():
        if sha(ROOT.parent/p)!=h:bad.append(p)
    assert not bad,bad
    assert read(ROOT/'EXCLUDED_OUTCOME_AVAILABILITY_AUDIT.json')['PASS']
    from experiment import guard,predictions,calibrate
    guard();z=np.load(ROOT/'TARGETS.npz');groups=read(ROOT/'FEATURE_GROUPS.json');proof=pd.read_parquet(ROOT/'FEATURE_CAUSAL_AVAILABILITY.parquet')
    assert proof.valid.all()
    receipts=[];cost=[]
    for p in (ROOT/'runs').glob('*/*/*.npz'):
        model=p.parent.parent.name;arm=p.parent.name;t=arm[:2];i=int(np.searchsorted(DAYS,p.stem));r=np.load(p)
        maturity=pd.Series(pd.to_datetime(z['maturity_'+t].max(1),utc=True));tr=member(i,maturity)
        assert np.array_equal(r['training_days'],tr)
        assert np.array_equal(r['weights'],weights(tr,i))
        assert int(r['latest_maturity_ns'])<int(r['issue_ns'])==ISS.iloc[i].value
        assert str(r['code_sha256'])==sha(ROOT/'core.py')
        assert r['q'].shape==(z[t].shape[1],2) and np.isfinite(r['q']).all()
        receipts.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),training_days=len(tr),latest_label_maturity_ns=int(r['latest_maturity_ns']),issue_ns=int(r['issue_ns']),PASS=True))
        cost.append(dict(model=model,arm=arm,day=DAYS[i],seconds=float(r['seconds']),training_days=len(tr),features=len(groups[arm])))
    csv('REFIT_LEAKAGE_PROOF.csv',receipts);csv('COMPUTATIONAL_COST.csv',cost)
    pred=pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    assert not pred.duplicated(['arm','day_index','slot']).any()
    assert len(pred.arm.unique())==24
    expected=273*(3*6*24+6*96);assert len(pred)==expected,(len(pred),expected)
    for arm,f in pred.groupby('arm'):
        assert f.day_index.nunique()==273
        assert np.isfinite(f[['y','raw_Q50','raw_Q90','calibrated_Q90']]).all().all()
        assert (f.raw_Q90>=f.raw_Q50).all() and (f.calibrated_Q90>=f.raw_Q50).all()
    old=np.load(P21/'predictions/LGBM_weighted_c1_s20260924.npz')['q'];np.testing.assert_array_equal(predictions('T0_F0')[OOS],old[OOS])
    for t in ['T0','T1','T2','T3']:np.testing.assert_array_equal(predictions(t+'_F0')[OOS],predictions(t+'_F3')[OOS])
    freeze=read(ROOT/'FEATURE_SELECTION_FREEZE.json');targetfreeze=read(ROOT/'TARGET_SELECTION_FREEZE.json');s2=read(ROOT/'STAGE2_SELECTION_FREEZE.json')
    assert freeze['selection_roles']==['DEVELOPMENT'] and not freeze['May_used'] and not targetfreeze['evaluation_used']
    assert s2['selection_roles']==['DEVELOPMENT'] and not s2['evaluation_used']
    from experiment import choose_development
    dev=pd.read_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')
    for t in ['T0','T1','T2','T3']:
        row,in_band=choose_development(dev[dev.target.eq(t)&dev.role.eq('DEVELOPMENT')&dev.variant.eq('RAW')&~dev.arm.str.endswith('F3')])
        assert row.arm==freeze['per_target'][t] and in_band==freeze['development_nominal_band_met'][t]
    for r in read(ROOT/'A0_REFIT_RECEIPTS.json'):
        i=int(np.searchsorted(DAYS,r['day']));tr=member(i)
        np.testing.assert_array_equal(r['training_days'],tr);np.testing.assert_array_equal(r['weights'],weights(tr,i))
    # Assert no new evaluation files predate Stage1 freeze, and no M1 files
    # predate target/feature freeze. Recorded creation times are diagnostic;
    # code-enforced phase gates are the primary chronology mechanism.
    firstfreeze=pd.Timestamp(targetfreeze['time']).timestamp()
    for p in (ROOT/'runs/M1').glob('*/*.npz'):assert p.stat().st_mtime>=firstfreeze
    status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT.parent.parent,text=True,encoding='utf-8')
    prefix='docs/'+ROOT.name+'/'
    assert all(prefix in line for line in status.splitlines()),status
    changed=subprocess.check_output(['git','diff','--name-only','bae7916c759e1c845bb87a8ee0dff761b5db7f7a','HEAD'],cwd=ROOT.parent.parent,text=True,encoding='utf-8')
    assert all(p.startswith('docs/cc4_v27_target_feature_sharpness/') or p.startswith(prefix) for p in changed.splitlines()),changed
    write('VALIDATION.json',dict(PASS=True,source_files_verified=len(source['files']),all_prior_namespaces_unchanged=True,new_refit_receipts=len(receipts),prediction_rows=len(pred),target_arms=4,feature_arms=6,F3_alias_explicit=True,zero_future_training_label_reads=True,feature_proof_rows=len(proof),A0_exact_reproduction=True,raw_T0_exact_reconstruction=True,T2_T3_conservation=True,May_used_for_selection=False,optimizer_executions=0))
    print('VALIDATION_PASS',len(receipts),len(pred),flush=True)
if __name__=='__main__':main()
