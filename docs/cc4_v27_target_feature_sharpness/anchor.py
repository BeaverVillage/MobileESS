from core import *
from concurrent.futures import ProcessPoolExecutor
import time
def task(i):
    tr=member(i);q,imp,h=fit(X0,Y0,tr,i)
    return i,q,dict(day=DAYS[i],training_days=tr.tolist(),weights=weights(tr,i).tolist(),model_sha256=h)
def main():
    assert not (ROOT/'A0_ANCHOR.json').exists()
    sources=read(P26/'SOURCE_MANIFEST.json')['files'].copy()
    for row in read(P26/'DELIVERY_MANIFEST.json')['files']:
        sources[P26.name+'/'+row['path']]=row['sha256']
    sources[P26.name+'/DELIVERY_MANIFEST.json']=sha(P26/'DELIVERY_MANIFEST.json')
    bad=[p for p,h in sources.items() if not (ROOT.parent/p).exists() or sha(ROOT.parent/p)!=h]
    assert not bad,bad
    write('SOURCE_MANIFEST.json',dict(base_PR=74,base_commit='bae7916c759e1c845bb87a8ee0dff761b5db7f7a',files=sources))
    old=np.load(P21/'predictions/LGBM_weighted_c1_s20260924.npz')['q'];q=np.full_like(old,np.nan);receipts=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for j,(i,p,r) in enumerate(pool.map(task,map(int,OOS))):
            q[i]=p;receipts.append(r)
            assert np.array_equal(p,old[i]),(DAYS[i],np.max(abs(p-old[i])))
            if j%20==0:print('A0_REPLAY',j+1,len(OOS),DAYS[i],flush=True)
    np.savez_compressed(ROOT/'A0_PREDICTIONS.npz',q=q)
    write('A0_REFIT_RECEIPTS.json',receipts)
    burst=read(BASE/'TARGET_RECONSTRUCTION_AUDIT.json')['TRAIN_positive_Q95_burst_threshold_GPUh']
    expected=pd.read_csv(P26/'MODEL_METRICS.csv');checks=[]
    for row in expected[expected.arm.eq('B0')].to_dict('records'):
        ids=role_ids(row['role']);m=metrics(Y0[ids],q[ids],burst)
        for key in ['Q90_coverage','Q90_pinball','requirement_ratio','Q50_MAE']:
            assert np.isclose(m[key],row[key],rtol=1e-13,atol=1e-12),(row['role'],key)
        checks.append(dict(role=row['role'],**m))
    write('A0_ANCHOR.json',dict(time=pd.Timestamp.now(tz='UTC'),CURRENT_TARGET_REPRODUCED=False,prediction_bitwise_equal=True,all_daily_refits_replayed=len(OOS),target_reconstruction_pending=True,frozen_X_bytes_sha256=hashlib.sha256(X0.tobytes()).hexdigest(),frozen_y_bytes_sha256=hashlib.sha256(Y0.tobytes()).hexdigest(),prediction_bytes_sha256=hashlib.sha256(q[OOS].tobytes()).hexdigest(),parameters=PARAMS,transform='log1p -> expm1; inherited nonnegative support and Q90>=Q50 constraints; no upper cap',metrics=checks))
    print('A0_MODEL_REPRODUCTION_PASS',flush=True)
if __name__=='__main__':main()
