from io import BytesIO
import re
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from .protocol import SPLIT

def utc(x):return pd.Timestamp(x,tz='UTC') if pd.Timestamp(x).tzinfo is None else pd.Timestamp(x).tz_convert('UTC')
def frame(p):return pq.read_table(BytesIO(Path(p).read_bytes())).to_pandas()
def timestamp_mask(f):
    ok=np.ones(len(f),dtype=bool)
    for c in ['submit_time','start_time','end_time']:ok &= f[c].notna().to_numpy() & (f[c]<utc(CUTOFF)).to_numpy()
    return ok
def train_mask(f,t):
    t=utc(t)
    return timestamp_mask(f)&(f.submit_time<t)&(f.end_time<t)&(f.end_time>=t-pd.Timedelta(days=120))&f.runtime_seconds.ge(0)&np.isfinite(f.runtime_seconds)&f.requested_seconds.gt(0)&np.isfinite(f.requested_seconds)
def block_mask(f,interval,deadline=None):
    return timestamp_mask(f)&(f.submit_time>=utc(interval[0]))&(f.submit_time<utc(interval[1]))&(f.end_time<utc(deadline or interval[1]))&f.runtime_seconds.ge(0)&np.isfinite(f.runtime_seconds)&f.requested_seconds.gt(0)&np.isfinite(f.requested_seconds)
def memory(x):
    if pd.isna(x):return np.nan
    m=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([KkMmGgTtPp]?)\s*[ncNC]?\s*',str(x))
    return float(m[1])*{'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3,'':1}[m[2].upper()] if m else np.nan
def normalize(r):
    mapping={'id':'job_id','nodes_req':'num_nodes_req','processors_req':'num_cores_req','gpus_requested':'num_gpus_req','state_simple':'job_state','user_hash':'user','account_hash':'account'}
    f=r.rename(columns=mapping).copy()
    for c in ['submit_time','start_time','end_time']:f[c]=pd.to_datetime(f[c],utc=True)
    f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds().clip(lower=0)
    f['requested_seconds']=f.wallclock_req.dt.total_seconds()
    f['requested_memory_mib']=f.memory_req.map(memory)
    for c in ['num_nodes_req','num_cores_req','num_gpus_req']:f[c]=pd.to_numeric(f[c],errors='coerce').astype(float)
    return f[['job_id','submit_time','start_time','end_time','runtime_seconds','job_state']+FEATURES9]

def allowed_group(item,interval):
    b=item['bounds'];s=b['submit_time']
    return bool(s and utc(s['min'])>=utc(interval[0]) and utc(s['max'])<utc(interval[1]) and all(b[c] and utc(b[c]['max'])<utc(CUTOFF) for c in ['submit_time','start_time','end_time']))

def authorize(stage):
    require_prereg()
    if stage in ['safe_fit','safe_selection','final_shadow']:
        p=read('V40K_POINT_MODEL_FREEZE.json');assert p.get('winner'),'POINT_FREEZE_REQUIRED'
        assert p['models_unchanged_after_selection']
    if stage=='final_shadow':assert read('V40K_SAFE_BOUND_FREEZE.json').get('winner'),'SAFE_FREEZE_REQUIRED'

def extract(stage):
    assert stage in ['point_selection','safe_fit','safe_selection','final_shadow']
    authorize(stage)
    path=OUT/(stage.upper()+'_ROWS.parquet')
    if path.exists():return frame(path)
    interval=SPLIT[stage];meta=read('V40K_APRIL_FOOTER_AVAILABILITY.json')
    allowed=[x for x in meta['row_groups'] if allowed_group(x,interval)]
    skipped=[{'row_group':x['row_group'],'rows':x['rows'],'reason':'crosses block or contains timestamp at/after canonical cutoff'} for x in meta['row_groups'] if not allowed_group(x,interval)]
    event('first_stage_payload_open',stage=stage,allowed_groups=[x['row_group'] for x in allowed],preregistration_commit=require_prereg())
    cols=['id','submit_time','start_time','end_time','wallclock_req','nodes_req','processors_req','gpus_requested','memory_req','partition','qos','state_simple','user_hash','account_hash']
    parts=[]
    if allowed:
        with zipfile.ZipFile(ARCHIVE) as z:
            with z.open(APRIL) as stream:
                p=pq.ParquetFile(stream)
                for item in allowed:
                    event('raw_row_group_decoded',stage=stage,member=APRIL,row_group=item['row_group'],rows=item['rows'])
                    raw=p.read_row_group(item['row_group'],columns=cols).to_pandas()
                    a=normalize(raw);a['source_row_group']=item['row_group'];parts.append(a)
    if not parts:
        write('EXTRACTION_'+stage+'.json',{'stage':stage,'status':'NO_SAFE_DECODABLE_ROW_GROUPS','rows':0,'groups_decoded':[],'skipped':skipped,'May_payload_rows':0})
        return pd.DataFrame()
    f=pd.concat(parts,ignore_index=True);mask=block_mask(f,interval)&f.num_gpus_req.gt(0)
    accepted=f.loc[mask].sort_values(['submit_time','job_id'],kind='stable').reset_index(drop=True)
    assert not accepted.job_id.duplicated().any(),'DUPLICATE_JOB_ID'
    accepted.to_parquet(path,index=False)
    write('EXTRACTION_'+stage+'.json',{'stage':stage,'interval':interval,'rows_decoded':len(f),'rows':len(accepted),
      'groups_decoded':[x['row_group'] for x in allowed],'skipped':skipped,
      'rejected_missing_timestamp':int(f[['submit_time','start_time','end_time']].isna().any(axis=1).sum()),
      'rejected_post_cutoff_rows':int((~timestamp_mask(f)&f[['submit_time','start_time','end_time']].notna().all(axis=1)).sum()),
      'late_completing_GPU_rows_excluded':int((f.num_gpus_req.gt(0)&(f.end_time>=utc(interval[1]))).sum()),
      'maximum_accepted_timestamp':str(accepted[['submit_time','start_time','end_time']].max().max()) if len(accepted) else None,
      'actual_submit_range':[str(accepted.submit_time.min()),str(accepted.submit_time.max())],
      'UTC_dates':sorted(accepted.submit_time.dt.strftime('%Y-%m-%d').unique().tolist()),'May_payload_rows':0,
      'whole_group_exclusion_bias':'Cohort omits whole groups containing future completions/boundaries; cannot claim full population.'})
    return accepted

def residual_oof(gpu):
    parts=[]
    for fid,when,stop in [('F1','2025-02-08','2025-02-15'),('F2','2025-02-15','2025-02-22'),('F3','2025-02-22','2025-03-08')]:
        p=frame(J/('C0_'+fid+'.parquet'))
        q=gpu.merge(p,on='job_id',how='inner',validate='one_to_one')
        q=q.loc[(q.submit_time>=utc(when))&(q.submit_time<utc(stop))].copy()
        q['C0_fit_before']=utc(when);q['C0_source']=fid
        # A query submitted after the training freeze cannot have an end-known training label before it.
        assert (q.submit_time>=q.C0_fit_before).all()
        train_ids=set(gpu.loc[train_mask(gpu,when),'job_id'])
        assert not train_ids.intersection(q.job_id),'SELF_FIT_RESIDUAL'
        parts.append(q)
    out=pd.concat(parts,ignore_index=True)
    assert not out.job_id.duplicated().any()
    return out
