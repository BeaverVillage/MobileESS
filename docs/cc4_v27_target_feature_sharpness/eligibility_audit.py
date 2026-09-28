"""Check that excluded positive-GPU outcomes do not secretly mature F1."""
from core import *
from prepare import H,DAY,ns
import zipfile,re
import pyarrow.parquet as pq
def main():
    source=read(ROOT/'RAW_AUTHORITY.json')['source'];assert sha(source['path'])==source['sha256'];invalid=[]
    with zipfile.ZipFile(source['path']) as z:
        for name in sorted(n for n in z.namelist() if re.search(r'year=\d{4}/month=\d+/.*\.parquet$',n)):
            with z.open(name) as f:d=pq.ParquetFile(f).read(columns=['id','submit_time','start_time','end_time','gpus_requested'],use_threads=False).to_pandas()
            for c in ['submit_time','start_time','end_time']:d[c]=pd.to_datetime(d[c],utc=True)
            d['gpus_requested']=d.gpus_requested.astype(float)
            positive=np.isfinite(d.gpus_requested)&d.gpus_requested.gt(0)
            valid=d.start_time.notna()&d.end_time.notna()&d.end_time.gt(d.start_time)&d.start_time.ge(d.submit_time)
            invalid.append(d[positive&~valid])
    bad=pd.concat(invalid,ignore_index=True);s=ns(bad.submit_time);end=ns(bad.end_time);starts=np.array([pd.Timestamp(str(day),tz=TZ).value for day in DAYS]);maxend=np.zeros((len(DAYS),24),np.int64)
    for i in range(len(DAYS)):
        for h in range(24):
            pick=(s>=starts[i]+h*H)&(s<starts[i]+(h+1)*H)
            maxend[i,h]=end[pick].max(initial=0)
    proof=pd.read_parquet(ROOT/'FEATURE_CAUSAL_AVAILABILITY.parquet');f=proof[proof.target.isin(['T0','T1'])&proof.available&proof.feature.str.startswith('same_clock')].copy()
    idx=pd.Index(DAYS).get_indexer(f.source_day);last=maxend[idx,f.slot.to_numpy()]
    violations=f[last>f.issue_ns.to_numpy()].copy()
    violations.to_parquet(ROOT/'EXCLUDED_OUTCOME_F1_VIOLATIONS.parquet',index=False)
    write('EXCLUDED_OUTCOME_AVAILABILITY_AUDIT.json',dict(PASS=len(violations)==0,invalid_positive_GPU_rows=len(bad),available_F1_rows_checked=len(f),excluded_outcome_not_yet_available_violations=len(violations),source_sha256=source['sha256'],interpretation='Conservative diagnostic: even excluded positive-GPU records must have ended by issue before they can justify a fully mature T0/T1 same-clock value. Existing baseline contract remains untouched.'))
    print('EXCLUDED_OUTCOME_AVAILABILITY',len(violations),flush=True)
    assert len(violations)==0,'New F1 eligibility leakage requires correction before support'
if __name__=='__main__':main()
