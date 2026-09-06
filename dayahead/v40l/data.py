from io import BytesIO
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from .protocol import SPLIT,BUCKETS
from dayahead.v40k.data import normalize

def utc(t):return pd.Timestamp(t).tz_localize('UTC') if pd.Timestamp(t).tzinfo is None else pd.Timestamp(t).tz_convert('UTC')
def frame(p):return pq.read_table(BytesIO(Path(p).read_bytes())).to_pandas()
def train_mask(f,t='2025-04-01'):
    stop=utc(t)
    return (f.submit_time<stop)&(f.end_time<stop)&(f.end_time>=stop-pd.Timedelta(days=120))&f.start_time.notna()&(f.end_time>=f.submit_time)&(f.end_time>=f.start_time)&f.runtime_seconds.ge(0)&np.isfinite(f.runtime_seconds)&f.requested_seconds.gt(0)&np.isfinite(f.requested_seconds)
def history():
    f=frame(J/'DEVELOPMENT_GPU_ROWS.parquet')
    f=f.loc[train_mask(f)].copy().reset_index(drop=True)
    assert (f[['submit_time','start_time','end_time']]<utc(CUTOFF)).all().all()
    return f
def oof_authority(h):
    verify_k0();f=frame(K/'RESIDUAL_OOF_ROWS.parquet');prior=load(K/'V40K_RESIDUAL_CROSSFIT_PROVENANCE.json')
    assert sha(K/'RESIDUAL_OOF_ROWS.parquet')==prior['rows_SHA']
    f=f.loc[train_mask(f)].reset_index(drop=True)
    assert not f.job_id.duplicated().any()
    sources={}
    for fold,g in f.groupby('C0_source',sort=True):
        receipt=load(J/('C0_'+fold+'_FIT.json'));freeze=utc(receipt['end_known_before'])
        assert (g.C0_fit_before==freeze).all() and (g.submit_time>=freeze).all()
        ids=set(h.loc[h.end_time<freeze,'job_id'])
        assert not ids.intersection(g.job_id),'SELF_FIT_RESIDUAL'
        recorded=frame(J/('C0_'+fold+'.parquet')).set_index('job_id')
        assert np.array_equal(g.point.to_numpy(),recorded.loc[g.job_id,'point'].to_numpy())
        sources[fold]={'fit_before':str(freeze),'OOF_rows':len(g),'fit_receipt_SHA':sha(J/('C0_'+fold+'_FIT.json')),'model_SHA':sha(J/'models'/('C0_'+fold+'.pkl')),'predictions_SHA':sha(J/('C0_'+fold+'.parquet')),'self_fit_overlap':0}
    report={'status':'PASS','rows':len(f),'source_SHA':sha(K/'RESIDUAL_OOF_ROWS.parquet'),'source_provenance_SHA':sha(K/'V40K_RESIDUAL_CROSSFIT_PROVENANCE.json'),
      'sources':sources,'K0_nominal_refit':False,'rolling_recipe':'Existing exact pinned K0 recipe fit strictly before each OOF query block; not frozen Apr01 model in-sample errors',
      'full_signed_residual_distribution':True,'positive_rows':int((f.runtime_seconds>f.point).sum()),'nonpositive_rows':int((f.runtime_seconds<=f.point).sum()),
      'max_label_end':str(f.end_time.max()),'OOF_submit_range':[str(f.submit_time.min()),str(f.submit_time.max())],'tail_fit_end_known_before':SPLIT['training_end_known_before']}
    return f,report

def base_features(f):
    x=f[F9].copy();t=pd.to_datetime(f.submit_time,utc=True)
    for c in F9[:5]:x[c]=pd.to_numeric(x[c],errors='coerce').astype(float)
    for c in F9[5:]:x[c]=x[c].fillna('__MISSING__').astype(str)
    x['submit_hour']=t.dt.hour.astype(float);x['submit_dow']=t.dt.dayofweek.astype(float);x['submit_week']=t.dt.isocalendar().week.astype(float)
    x['hardware']=np.where(x.partition.str.contains('h100',case=False),'H100','OTHER_GPU')
    x['standby']=x.qos.str.lower().eq('standby').astype(float)
    x['wall_bucket']=np.searchsorted(BUCKETS,x.requested_seconds,side='left').astype(float)
    return x
def keys(f,cols):
    if not cols:return [()] * len(f)
    return list(f[cols].astype(object).where(f[cols].notna(),'__MISSING__').itertuples(index=False,name=None))
class Support:
    def __init__(self,h):
        self.freeze=utc(SPLIT['training_end_known_before']).value
        assert (h.end_time<utc(SPLIT['training_end_known_before'])).all()
        x=base_features(h);ends=h.end_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy();self.tables=[]
        for cols in [F9,F9[1:]]:
            table={}
            for key,t in zip(keys(x,cols),ends):table.setdefault(key,[]).append(t)
            self.tables.append({k:np.sort(v) for k,v in table.items()})
    def transform(self,f):
        x=base_features(f);times=np.minimum(f.submit_time.astype('datetime64[ns, UTC]').astype('int64').to_numpy(),self.freeze);counts=[]
        for cols,table in zip([F9,F9[1:]],self.tables):
            counts.append(np.array([np.searchsorted(table[k],t,side='left') if k in table else 0 for k,t in zip(keys(x,cols),times)],int))
        exact,near=counts
        x['exact_count']=exact.astype(float);x['near_count']=near.astype(float)
        x['support_class']=np.where(exact>=100,'STRONG_SUPPORT',np.where(exact>0,'SPARSE_SUPPORT',np.where(near>=100,'REGIME_MISMATCH','OUT_OF_SUPPORT')))
        return x[FEATURES]

def allowed_group(item,stage):
    interval=SPLIT[stage];b=item['bounds'];s=b['submit_time']
    return bool(s and utc(s['min'])>=utc(interval[0]) and utc(s['max'])<utc(interval[1]) and all(b[c] and utc(b[c]['max'])<utc(CUTOFF) for c in ['submit_time','start_time','end_time']))
def authorize(stage):
    require_prereg()
    lock=read('V40L_PRECALIBRATION_EXECUTION_FREEZE.json')
    for rel,h in lock['file_SHA'].items():assert sha(ROOT/rel)==h,('EXECUTION_CHANGED',rel)
    r=read('V40L_PRECALIBRATION_COMMIT_RECEIPT.json')
    assert hashlib.sha256(git('show',r['commit']+':'+(OUT/'V40L_PRECALIBRATION_EXECUTION_FREEZE.json').relative_to(ROOT).as_posix())).hexdigest()==sha(OUT/'V40L_PRECALIBRATION_EXECUTION_FREEZE.json')
    if stage in ['selection','shadow']:
        cal=read('V40L_CALIBRATION_FREEZE.json')
        for rel,h in cal['file_SHA'].items():assert sha(ROOT/rel)==h
    if stage=='shadow':
        freeze=read('V40L_TAIL_METHOD_FREEZE.json');assert freeze['winner'],'TAIL_WINNER_REQUIRED'
        r=read('V40L_TAIL_WINNER_COMMIT_RECEIPT.json')
        assert hashlib.sha256(git('show',r['commit']+':'+(OUT/'V40L_TAIL_METHOD_FREEZE.json').relative_to(ROOT).as_posix())).hexdigest()==sha(OUT/'V40L_TAIL_METHOD_FREEZE.json')

def extract(stage):
    assert stage in ['calibration','selection','shadow'];authorize(stage)
    path=OUT/(stage.upper()+'_ROWS.parquet')
    assert not path.exists(),'BLOCK_ALREADY_OPENED'
    meta=load(K/'V40K_APRIL_FOOTER_AVAILABILITY.json');allowed=[a for a in meta['row_groups'] if allowed_group(a,stage)]
    event('block_open_authorized',stage=stage,allowed_groups=[a['row_group'] for a in allowed])
    parts=[];cols=['id','submit_time','start_time','end_time','wallclock_req','nodes_req','processors_req','gpus_requested','memory_req','partition','qos','state_simple','user_hash','account_hash']
    if allowed:
        with zipfile.ZipFile(ARCHIVE) as z:
            with z.open(APRIL) as stream:
                pf=pq.ParquetFile(stream)
                for item in allowed:
                    for c in ['submit_time','start_time','end_time']:
                        s=pf.metadata.row_group(item['row_group']).column(pf.schema_arrow.get_field_index(c)).statistics
                        assert str(s.min)==item['bounds'][c]['min'] and str(s.max)==item['bounds'][c]['max'],'FOOTER_CHANGED'
                    event('raw_row_group_decoded',stage=stage,row_group=item['row_group'],rows=item['rows'],columns=cols)
                    f=normalize(pf.read_row_group(item['row_group'],columns=cols).to_pandas());f['source_row_group']=item['row_group'];parts.append(f)
    info={'stage':stage,'block':SPLIT[stage],'groups_decoded':[a['row_group'] for a in allowed],
      'skipped_groups':[{'group':a['row_group'],'rows':a['rows']} for a in meta['row_groups'] if a not in allowed],
      'scanned_partition_count':int(bool(allowed)),'rowgroups_inspected_metadata':31,'May_runtime_status_outcome_rows_read':0,
      'post_cutoff_rows_in_excluded_groups':None,'excluded_group_census':'Unavailable without forbidden value decoding; never reported as zero'}
    if not parts:
        info.update(status='NO_SAFE_DECODABLE_ROW_GROUPS',rows=0,maximum_accepted_timestamp=None,minimum_rejected_timestamp=None)
        write('EXTRACTION_'+stage+'.json',info,immutable=True);return pd.DataFrame()
    f=pd.concat(parts,ignore_index=True);ts=f[['submit_time','start_time','end_time']]
    good=ts.notna().all(axis=1)&(ts<utc(CUTOFF)).all(axis=1)
    assert not ((ts>=utc(CUTOFF)).any(axis=1)).any(),'POST_CUTOFF_PAYLOAD_DECODED'
    mask=good&f.num_gpus_req.gt(0)&f.submit_time.ge(utc(SPLIT[stage][0]))&f.submit_time.lt(utc(SPLIT[stage][1]))&f.end_time.lt(utc(SPLIT[stage][1]))&(f.end_time>=f.start_time)&(f.end_time>=f.submit_time)&f.requested_seconds.gt(0)&np.isfinite(f.requested_seconds)&f.runtime_seconds.ge(0)&np.isfinite(f.runtime_seconds)
    accepted=f.loc[mask].sort_values(['submit_time','job_id'],kind='stable').reset_index(drop=True)
    assert not accepted.job_id.duplicated().any()
    accepted.to_parquet(path,index=False)
    info.update(status='PASS',rows=len(accepted),rows_decoded=len(f),rejected_post_cutoff_row_count=0,rejected_missing_timestamps=int(ts.isna().any(axis=1).sum()),
      late_completing_GPU_exclusions=int((f.num_gpus_req.gt(0)&f.end_time.ge(utc(SPLIT[stage][1]))).sum()),
      maximum_accepted_timestamp=str(accepted[['submit_time','start_time','end_time']].max().max()),minimum_rejected_timestamp=None,
      actual_submit_range=[str(accepted.submit_time.min()),str(accepted.submit_time.max())],dates=sorted(accepted.submit_time.dt.strftime('%Y-%m-%d').unique().tolist()))
    write('EXTRACTION_'+stage+'.json',info,immutable=True);return accepted
