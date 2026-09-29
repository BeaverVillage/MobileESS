"""Decode only pre-April leading rows of frozen CC4 arrays, never May payload rows."""
from common15 import *
import csv,zipfile
from numpy.lib import format as fmt

def prefix_array(path,name,count):
    with zipfile.ZipFile(path) as z, z.open(name+'.npy') as f:
        version=fmt.read_magic(f)
        if version==(1,0):shape,fortran,dtype=fmt.read_array_header_1_0(f)
        elif version==(2,0):shape,fortran,dtype=fmt.read_array_header_2_0(f)
        else:raise ValueError('UNSUPPORTED_NPY_HEADER_VERSION')
        if fortran or dtype.hasobject:raise ValueError('ONLY_C_ORDER_NONOBJECT_PREFIX_ALLOWED')
        assert 0<count<=shape[0]
        nbytes=int(count*np.prod(shape[1:],dtype=np.int64)*dtype.itemsize)
        data=f.read(nbytes)
        assert len(data)==nbytes
        a=np.frombuffer(data,dtype=dtype).reshape((count,)+shape[1:]).copy()
        return a,dict(array=name,original_shape=shape,decoded_shape=a.shape,decoded_bytes=nbytes,leading_rows_only=True)

def main():
    base=CC4_SOURCE/'docs/cc4_v2_hourly_future_workload'
    p27=CC4_SOURCE/'docs/cc4_v27_target_feature_sharpness'
    rows=[]
    with (base/'DAY_LEDGER.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['target_day']>='2025-04-01':break
            rows.append(r)
    ledger=pd.DataFrame(rows);n=len(ledger)
    ledger['eligible']=ledger.eligible.eq('True')
    receipts=[];arrays={}
    for name in ['X','y','days']:
        arrays[name],receipt=prefix_array(base/'DATA.npz',name,n);receipts.append(receipt)
    q,receipt=prefix_array(p27/'A0_PREDICTIONS.npz','q',n);receipts.append(receipt)
    assert np.array_equal(arrays['days'].astype(str),ledger.target_day.to_numpy())
    assert np.isfinite(arrays['X']).all() and np.isfinite(arrays['y']).all()
    assert arrays['y'].shape==(n,24) and arrays['X'].shape[:2]==(n,24)
    # Maturity remains an independent evaluation eligibility condition.
    eligible_time=pd.to_datetime(ledger.label_matured_at,utc=True).lt(pd.Timestamp('2025-04-01',tz='UTC'))
    ledger['preApril_maturity']=eligible_time
    oos=ledger.target_day.ge('2024-09-01')&eligible_time
    assert np.isfinite(q[oos]).all()
    np.savez_compressed(LOCAL/'CC4_BASE_PREAPRIL.npz',**arrays,q=q)
    ledger.to_csv(LOCAL/'CC4_DAY_LEDGER_PREAPRIL.csv',index=False)
    sources=[rec(base/n) for n in ['DATA.npz','DAY_LEDGER.csv','TARGET_RECONSTRUCTION_AUDIT.json']]
    sources += [rec(p27/n) for n in ['A0_PREDICTIONS.npz','A0_ANCHOR.json','A0_REFIT_RECEIPTS.json','core.py','ARM_REGISTRATION.json','SOURCE_MANIFEST.json']]
    # Confirm frozen input bytes against existing manifests, where listed.
    authority={}
    for parent in [base,p27]:
        manifest=read(parent/'DELIVERY_MANIFEST.json')
        records=manifest['files']
        if isinstance(records,dict):records=[dict(path=p,sha256=h) for p,h in records.items()]
        for r in records:
            authority[str(parent/r.get('path',r.get('relative')))]=r['sha256']
    for source in sources:
        if source['path'] in authority:assert source['sha256']==authority[source['path']],source['path']
    write('CC4_BASELINE_INPUT_RECEIPT.json',dict(time=now(),C0='T0/B0',rows=n,features=arrays['X'].shape[-1],
        decoder_receipts=receipts,sources=sources,source_manifest_bindings=sum(s['path'] in authority for s in sources),
        target='Hourly GPUh attributed to submission hour: requested GPU count times realized runtime (end-start); exact frozen T0 label, not requested walltime',family='Frozen LightGBM quantile log1p',
        baseline_retrained=False,April_rows_decoded=False,May_rows_decoded=False,
        source_hash_scope='Whole files hashed as bytes only; array payload decoding restricted to pre-April row prefix',
        role_counts=ledger.groupby('split').size().to_dict(),initial_TRAIN_days=int((ledger.split.eq('TRAIN')&ledger.eligible).sum()),
        excluded_preApril_unmatured_days=ledger.loc[~eligible_time,'target_day'].tolist(),
        outputs=[rec(LOCAL/'CC4_BASE_PREAPRIL.npz'),rec(LOCAL/'CC4_DAY_LEDGER_PREAPRIL.csv')]))
    print('CC4 PREAPRIL PREPARED',n,arrays['X'].shape,flush=True)
if __name__=='__main__':main()
