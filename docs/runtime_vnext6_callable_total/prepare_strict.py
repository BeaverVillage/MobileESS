"""Read only pre-April partitions; no historical request field reaches new training X."""
from paths import *
import re,zipfile
import numpy as np,pandas as pd,pyarrow.parquet as pq

def digest_ids(f):return __import__('hashlib').sha256(('\n'.join(sorted(f.job_id.astype(str)))+'\n').encode()).hexdigest()
def normalize(r,cutoff):
    f=pd.DataFrame({'job_id':r.id.astype(str)})
    for c in ['submit_time','start_time','end_time']:f[c]=pd.to_datetime(r[c],utc=True).astype('datetime64[ns, UTC]')
    # Out-of-cutoff end/start values are not outcomes; null before computing any target.
    f['outcome_unavailable']=f.end_time.isna()|f.end_time.ge(cutoff)
    f.loc[f.outcome_unavailable,'end_time']=pd.NaT
    f.loc[f.start_time.ge(cutoff),'start_time']=pd.NaT
    f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds().clip(lower=0)
    f['label_valid']=f.start_time.notna()&f.end_time.notna()&f.end_time.ge(f.start_time)&f.start_time.ge(f.submit_time)
    f['requested_seconds']=r.wallclock_req.dt.total_seconds().astype(float)
    for src,dst in [('gpus_requested','num_gpus_req'),('nodes_req','num_nodes_req'),('processors_req','num_cores_req')]:f[dst]=pd.to_numeric(r[src],errors='coerce')
    def mem(v):
        m=re.fullmatch(r'([\d.]+)([KMGTPkmgtp]?)[nN]?',str(v).strip())
        return float(m[1])*{'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3,'':1}[m[2].upper()] if m else np.nan
    f['requested_memory_mib']=r.memory_req.map(mem)
    for src,dst in [('partition','partition'),('qos','qos'),('user_hash','user'),('account_hash','account')]:f[dst]=r[src]
    return f

def extract(april=False):
    protocol=read(ROOT/'EXPERIMENT_PROTOCOL.json')
    if april:
        assert (ROOT/'MODEL_SELECTION_FREEZE.json').exists() and (ROOT/'PROVIDER_BUNDLE_FREEZE.json').exists()
        for p in read(ROOT/'PROVIDER_BUNDLE_FREEZE.json')['files']:assert sha(ROOT/p['relative'])==p['sha256']
    cutoff=pd.Timestamp('2025-05-01T00:00Z' if april else protocol['logical_freeze_cutoff'])
    cols=['id','submit_time','start_time','end_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos','user_hash','account_hash']
    parts=[];inventory=[]
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(z.namelist()):
            m=re.search(r'year=(\d{4})/month=(\d+)/.*\.parquet$',name)
            if not m:continue
            ym=tuple(map(int,m.groups()))
            if (april and ym!=(2025,4)) or (not april and not ((2024,9)<=ym<=(2025,3))):continue
            with z.open(name) as stream:r=pq.read_table(stream,columns=cols,use_threads=False).to_pandas()
            raw_n=len(r);r=r[pd.to_numeric(r.gpus_requested,errors='coerce').gt(0)].copy()
            f=normalize(r,cutoff);f=f[f.submit_time.lt(cutoff)]
            if april:f=f[f.submit_time.ge(pd.Timestamp('2025-04-01T00:00Z'))]
            parts.append(f);inventory.append(dict(member=name,raw_rows=raw_n,gpu_rows=len(f)))
            print('PARTITION',name,raw_n,len(f),flush=True)
    f=pd.concat(parts,ignore_index=True).sort_values(['end_time','job_id'],kind='stable').reset_index(drop=True)
    assert f.job_id.is_unique
    if april:
        f.to_parquet(ROOT/'APRIL_JOBS.parquet',index=False)
        write('APRIL_OPEN_RECEIPT.json',dict(partitions=inventory,rows=len(f),unresolved=int((~f.label_valid).sum()),may_partitions_read=0,freeze=record(ROOT/'PROVIDER_BUNDLE_FREEZE.json')))
        return
    f['role']='UNUSED'
    tr=protocol['TRAIN'];fitcut=pd.Timestamp(tr['end_before'])
    f.loc[f.label_valid&f.end_time.lt(fitcut)&f.end_time.ge(pd.Timestamp(tr['end_after'])),'role']='TRAIN'
    for role in ['DEV','CAL_FIT','CAL_VALID']:
        sp=protocol[role];mask=f.submit_time.ge(pd.Timestamp(sp['submit_from']))&f.submit_time.lt(pd.Timestamp(sp['submit_before']))
        f.loc[mask,'role']=role
    f.to_parquet(ROOT/'PREAPRIL_JOBS.parquet',index=False)
    audit=f[['job_id','submit_time','start_time','end_time','label_valid','role']].copy()
    audit['label_available_time']=audit.end_time;audit['fit_cutoff']=fitcut;audit['eligible_for_fit']=f.role.eq('TRAIN')
    audit.to_parquet(ROOT/'RUNTIME_LABEL_MATURITY_AUDIT.parquet',index=False)
    proof=f[['job_id','role']].copy();proof['constant_bias']=1.;proof['availability']='ALWAYS_CONSTRUCTIBLE_NO_JOB_FIELDS'
    proof['request_fields_used']=0;proof['archived_requests_verified']=False
    proof.to_parquet(ROOT/'ROW_FEATURE_AVAILABILITY_PROOF.parquet',index=False)
    details={}
    for role,g in f.groupby('role'):
        mature=g.label_valid if role=='TRAIN' else g.label_valid&g.end_time.lt(pd.Timestamp(protocol[role]['mature_before'])) if role!='UNUSED' else g.label_valid
        details[role]=dict(total=len(g),mature=int(mature.sum()),unresolved=int((~mature).sum()),zero=int((g.runtime_seconds.eq(0)&mature).sum()),membership=digest_ids(g),mature_membership=digest_ids(g[mature]))
    write('DATA_SPLIT_AND_MATURITY.json',dict(partitions=inventory,roles=details,source=record(RAW),data=record(ROOT/'PREAPRIL_JOBS.parquet'),
        maturity_rule='end_time < role cutoff; event-time availability, ingestion delay not certified',
        training_future_or_equal_end=0,negative_duration='excluded label_valid false; nonnegative target computed separately',
        terminal_state='Raw selected schema lacks state; completed means observed end/start, not asserted successful COMPLETED status.',
        provenance_limit='Request fields for research comparator and descriptive strata only; archived submit timestamp used for chronological membership, not predictor.',april_payload_read=False,may_payload_read=False))
    write('FEATURE_CAUSALITY_AUDIT.json',dict(proof=record(ROOT/'ROW_FEATURE_AVAILABILITY_PROOF.parquet'),rows=len(f),
        new_model_feature_fields=['constant_bias'],job_fields_used=0,leakage_feature_count=0,
        request_version_authority=read(ROOT/'REQUEST_VERSION_AUTHORITY_AUDIT.json'),
        strict_scope='Featureless unconditional model. Not a claim all historical request fields verified or historical ingestion certified.'))
    print(details,flush=True)
if __name__=='__main__':
    import sys
    extract('--april' in sys.argv)
