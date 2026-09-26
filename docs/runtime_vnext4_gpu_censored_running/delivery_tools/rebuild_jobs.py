"""Recreate the exact PR65 normalized GPU input from the original raw archive."""
from pathlib import Path
import hashlib,json,os,re,zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1]
RAW=Path(os.environ.get('KESTREL_RAW_ZIP','C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip'))

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def memory(v):
    if v is None:return None
    m=re.match(r'^([\d.]+)([KMGTPkmgtp]?)[nN]?$',str(v).strip())
    return float(m[1])*{'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3,'':1}[m[2].upper()] if m else None

def main():
    parent=json.loads((ROOT.parent/'runtime_vnext_causal_tail/PREPARATION_COMPLETE.json').read_text(encoding='utf-8'))
    assert sha(RAW)==parent['archive_sha256']
    path=ROOT/'cache/JOBS.parquet';assert not path.exists(),'Refuse to overwrite existing cache'
    cols=['id','submit_time','start_time','end_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos','user_hash','account_hash'];parts=[]
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(n for n in z.namelist() if re.search(r'year=\d{4}/month=\d+/.*\.parquet$',n)):
            with z.open(name) as stream:r=pq.read_table(stream,columns=cols,use_threads=False).to_pandas()
            r=r[pd.to_numeric(r.gpus_requested,errors='coerce').gt(0)&pd.to_datetime(r.submit_time,utc=True).lt(pd.Timestamp('2025-06-01',tz='UTC'))].copy()
            if not len(r):continue
            f=pd.DataFrame(index=r.index);f['job_id']=r.id.astype(str);f['job_uid']=f.job_id;f['submit_time']=pd.to_datetime(r.submit_time,utc=True)
            f['requested_seconds']=r.wallclock_req.dt.total_seconds().astype(float)
            for source,target in [('gpus_requested','num_gpus_req'),('nodes_req','num_nodes_req'),('processors_req','num_cores_req')]:f[target]=pd.to_numeric(r[source],errors='coerce')
            f['requested_memory_mib']=r.memory_req.map(memory)
            for c in ['partition','qos']:f[c]=r[c]
            f['submit_hour']=f.submit_time.dt.hour.astype(float);f['submit_dow']=f.submit_time.dt.dayofweek.astype(float)
            for c in ['start_time','end_time']:f[c]=pd.to_datetime(r[c],utc=True).astype('datetime64[ns, UTC]')
            f['submit_time']=f.submit_time.astype('datetime64[ns, UTC]');f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds()
            f['user']=r.user_hash;f['account']=r.account_hash;parts.append(f)
    f=pd.concat(parts,ignore_index=True).sort_values('job_id',kind='stable').reset_index(drop=True)
    assert f.job_id.is_unique and np.isfinite(f.num_gpus_req).all()
    f['row_id']=np.arange(len(f),dtype=np.int32)
    f['label_valid']=f.start_time.notna()&f.end_time.notna()&f.runtime_seconds.gt(0)&f.start_time.ge(f.submit_time)
    path.parent.mkdir(exist_ok=True);f.to_parquet(path,index=False)
    digest=sha(path);assert digest==parent['jobs_sha256'],(digest,parent['jobs_sha256'])
    with (ROOT/'RAW_REBUILD_VALIDATION.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(time=pd.Timestamp.now(tz='UTC').isoformat(),PASS=True,N=len(f),raw_sha256=sha(RAW),jobs_sha256=digest,exact_parent_bytes=True),stream,indent=2)
    print('RAW_REBUILD_PASS',len(f),digest,flush=True)

if __name__=='__main__':main()
