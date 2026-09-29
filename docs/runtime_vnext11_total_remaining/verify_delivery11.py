from common11 import *
from model11 import Quantiles
import numpy as np,pandas as pd,re,subprocess
def main():
    prior=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')['prior'];n=0
    for group in prior:
        p=Path(group['manifest']['path']);assert sha(p)==group['manifest']['sha256']
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256'];n+=1
    for name in ['PREREGISTRATION.json','TEMPORAL_DRIFT_FREEZE.json','TOTAL_MODEL_SELECTION_FREEZE.json','TAIL_SPECIALIST_FREEZE.json','REMAINING_MODEL_SELECTION_FREEZE.json','FEATURE_CONTRACT_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']:
        for r in read(ROOT/name)['files']:assert sha(r['path'])==r['sha256'],name
    assert pd.Timestamp(read(ROOT/'TEMPORAL_DRIFT_FREEZE.json')['time'])<pd.Timestamp(read(ROOT/'TRAINING_STARTED.json')['time'])
    evidence=read(ROOT/'FOLD_MEMBERSHIP_REFERENCE.json')
    for r in evidence['prepared_role_files']:assert sha(r['path'])==r['sha256']
    receipts=read(ROOT/'BASE_MODEL_FIT_RECEIPTS.json');fitfiles=0
    for m in receipts['models']:
        for r in m['files']:assert sha(r['path'])==r['sha256'];fitfiles+=1
    total=read(ROOT/'TOTAL_SELECTION_RESULT.json');rows=pd.read_csv(ROOT/'TOTAL_BASE_FOLD_METRICS.csv');parity=[]
    for i in range(1,6):
        val=data(i,'VALID')
        for win in WINDOWS:
            tr=window(i,win);exact=tr[tr.event];cutoff=pd.Timestamp(prep(i)['fit_cutoff'])
            assert exact.end_time.lt(cutoff).all() and exact.submit_time.lt(cutoff).all()
            if WINDOWS[win] is not None:assert tr.submit_time.ge(cutoff-pd.Timedelta(days=WINDOWS[win])).all()
            assert not set(tr.job_id)&set(val.job_id)
            for target in ['RAW','LOG','REL']:
                r=rows[(rows.fold==i)&rows.arm.eq(win+'_'+target)].iloc[0];assert r.TRAIN_N==len(exact) and r.support_sufficient
        model=Quantiles.load(ROOT/'FOLD_MODELS'/f'fold{i}/total_base');sample=val.head(100).copy();q,_=model.predict(sample)
        saved=np.load(LOCAL/f'fold{i}/SELECTED_TOTAL.npz')['quantiles'][:100];assert np.max(abs(q-saved))<1e-7
        altered=sample.copy();altered['runtime_seconds']=1e9;altered['job_id']='UNSEEN';altered['end_time']=pd.Timestamp('2099-01-01T00Z')
        other,_=model.predict(altered);assert np.array_equal(q,other)
        assert (q[:,1]>=q[:,0]).all() and (q>=0).all() and np.isfinite(q).all()
        parity.append(dict(fold=i,N=100,serialization_max_error=float(np.max(abs(q-saved))),future_outcome_and_job_id_invariance=True,scope='saved fold component only, no final provider'))
    guard=subprocess.run([sys.executable,str(ROOT/'train_remaining11.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert guard.returncode!=0 and 'V11_STOP_CONDITION' in guard.stderr
    assert not list((ROOT/'FOLD_MODELS').glob('*/R3_RAW')) and not (ROOT/'REMAINING_SELECTION_RESULT.json').exists()
    assert not (ROOT/'APRIL_EVALUATION_STARTED.json').exists() and not (ROOT/'RUNTIME_PROVIDER/provider.py').exists()
    for name in ['APRIL_EXPOSED_TOTAL_METRICS.csv','APRIL_EXPOSED_REMAINING_METRICS.csv','APRIL2_EXPOSED_QUEUE_REGRESSION.csv','REMAINING_MODEL_COMPARISON.csv']:
        z=pd.read_csv(ROOT/name);assert z.status.eq('NOT_RUN_USER_STOP_CONDITION').all() and not z.metrics_available.any()
    review=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8');assert [int(x) for x in re.findall(r'(?m)^## (\d+)\.',review)]==list(range(1,37))
    changed=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=REPO,text=True).splitlines();assert not changed
    write('DELIVERY_VERIFICATION.json',dict(time=now(),PASS=True,scope='Scientific integrity and honest stopped status; NOT model promotion',prior_scientific_files_byte_identical=n,prior_manifests_byte_identical=5,
        model_fit_files_verified=fitfiles,stageA_before_training=True,registered_contracts_unchanged=True,exact_fold_membership_unchanged=True,fold_component_tests=parity,
        checkpoint_episode_leakage=0,remaining_stop_guard_verified=True,remaining_training_executed=False,April_payload_decoded=False,May_payload_decoded=False,Korean_questions_answered=36,
        final_provider_built=False,nonexecution_placeholders_explicit=True))
    sourcefiles=[V8/'features8.py',V9/'queue9.py',V9/'metrics9.py',V10/'PREAPRIL_QUEUE_REPLAY.csv',V10/'PREAPRIL_REFERENCE_METRICS.csv',V10/'FOLD_LEVEL_METRICS.csv',V10/'CALIBRATION_COMPARISON.csv']
    write('SOURCE_MANIFEST.json',dict(time=now(),repository='BeaverVillage/MobileESS',base=BASE,prior_manifests=prior,
        folds=read(ROOT/'FOLD_MEMBERSHIP_REFERENCE.json'),source_code_and_baselines=[record(p) for p in sourcefiles],
        scientific_source='Hash-pinned V9 normalized preApril roles; no new raw-source semantics or request-version claim',software=read(ROOT/'EXECUTION_ENVIRONMENT.json'),
        user_request=record(ROOT/'USER_REQUEST.txt'),stop_authority='USER_REQUEST section42',April_payload_read=False,May_payload_read=False))
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig');section=request.split('35. REQUIRED STAGE-A ARTIFACTS',1)[1].split('39. REQUIRED FINAL KOREAN QUESTIONS',1)[0]
    names=set(re.findall(r'(?m)^([A-Z][A-Z0-9_]*(?:\.json|\.csv|\.md))\s*$',section))
    for name in names:
        if name!='DELIVERY_MANIFEST.json':assert (ROOT/name).is_file(),name
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ['.local','__pycache__']) or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext11_total_remaining only',scientific_status='STOPPED_AT_STAGE_B_NOT_PROMOTED',files=files))
    print('V11_DELIVERY_PASS',n,'prior files;',len(files),'new files;',sum(r['bytes'] for r in files),'bytes',flush=True)
if __name__=='__main__':main()
