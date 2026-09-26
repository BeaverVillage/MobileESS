"""Lossless exact membership delivery; rebuild safe labels/weights from parent jobs.

The full fit-time Parquets remain unchanged locally. Ordered row IDs are delivered
as NPZ; every original safe column is verified by canonical byte digest. Other
model feature values are irrelevant to this label/weight reconstruction and are
filled with NaN here, not passed to a model. Raw model inputs can be rebuilt using
rebuild_jobs.py and the pinned archive.
"""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from censor_proxy import asof_rows,weight,FEATURES
BASE=ROOT.parent/'runtime_vnext_causal_tail'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,indent=2,allow_nan=False)
def digest(column):
    if column.name=='job_id':raw=('\n'.join(column.astype(str))+'\n').encode();kind='utf8-lines'
    elif pd.api.types.is_datetime64_any_dtype(column):raw=column.dt.as_unit('ns').astype('int64').to_numpy(dtype='<i8').tobytes();kind='utc-ns-int64-little-endian'
    elif column.name=='right_censored':raw=column.to_numpy(dtype='u1').tobytes();kind='uint8'
    elif column.name=='row_id':raw=column.to_numpy(dtype='<i8').tobytes();kind='int64-little-endian'
    else:raw=column.to_numpy(dtype='<f8').tobytes();kind='float64-little-endian'
    return {'encoding':kind,'sha256':hashlib.sha256(raw).hexdigest()}
def main(package):
    jobs=pd.read_parquet(BASE/'JOB_MEMBERSHIP.parquet')
    for c in FEATURES:
        if c not in jobs:jobs[c]=np.nan
    rows=[]
    for receiptpath in sorted((ROOT/'fits').glob('*/*/RECEIPT.json')):
        receipt=load(receiptpath);folder=receiptpath.parent;arm=receipt['family'];t=pd.Timestamp(receipt['issue_time'])
        expected=asof_rows(jobs,t)
        if arm=='R2':expected=expected[~expected.right_censored].copy()
        expected['sample_weight'],normalizer=weight(expected,t)
        npz=folder/'ROW_IDS.npz';proofpath=folder/'PORTABLE_MEMBERSHIP.json'
        if package:
            full=folder/'MEMBERSHIP.parquet';actual=pd.read_parquet(full)
            assert sha(full)==receipt['membership_sha256']
            columns={c:digest(actual[c]) for c in actual}
            assert columns=={c:digest(expected[c]) for c in actual},str(folder)
            assert not npz.exists()
            np.savez_compressed(npz,row_id=actual.row_id.to_numpy(dtype='<i8'))
            write(proofpath,{'N':len(actual),'ordered_row_ids_sha256':sha(npz),'full_local_membership_sha256':sha(full),'columns':columns,'parent_job_membership_sha256':sha(BASE/'JOB_MEMBERSHIP.parquet'),'weight_normalizer':normalizer})
        proof=load(proofpath)
        assert proof['parent_job_membership_sha256']==sha(BASE/'JOB_MEMBERSHIP.parquet')
        assert proof['ordered_row_ids_sha256']==sha(npz)
        assert np.array_equal(np.load(npz)['row_id'],expected.row_id.to_numpy())
        assert proof['columns']=={c:digest(expected[c]) for c in proof['columns']}
        assert proof['weight_normalizer']==normalizer
        rows.append({'arm':arm,'issue_time':str(t),'N':len(expected),'right_censored_N':int(expected.right_censored.sum()),'row_ids_sha256':sha(npz),'proof_sha256':sha(proofpath)})
    assert len(rows)==118,len(rows)
    result={'PASS':True,'fits':len(rows),'full_original_safe_columns_reproduced':True,'source':'immutable parent JOB_MEMBERSHIP + ordered ROW_IDS.npz + frozen censor_proxy algorithm','raw_model_features_reproduction':'rebuild_jobs.py, pinned archive and portable preprocessing','rows':rows}
    if package:write(ROOT/'PORTABLE_MEMBERSHIP_AUDIT.json',result)
    else:assert load(ROOT/'PORTABLE_MEMBERSHIP_AUDIT.json')==result
    print('PORTABLE_MEMBERSHIP_PASS',len(rows),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',action='store_true');a=p.parse_args();main(a.package)
