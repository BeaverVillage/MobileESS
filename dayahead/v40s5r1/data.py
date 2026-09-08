"""Projected feature reads and hash-gated issue outcome reads."""
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from .common import *

def event(t,kind,**details):
    p=OUT/'events'/f'{key(t)}.json'
    events=json.loads(p.read_text()) if p.exists() else []
    events.append(dict(sequence=len(events)+1,timestamp=now(),issue_time=pd.Timestamp(t).isoformat(),kind=kind,**details))
    dump(p,events)

def history(t,log=True):
    t=pd.Timestamp(t);columns=['job_id','submit_time',*LABELS,*FEATURES]
    # The scanner evaluates an end_time eligibility predicate internally. Only
    # qualifying rows and the authorized columns are materialized by this process.
    pred=ds.field('end_time')<pa.scalar(t.to_pydatetime(),type=pa.timestamp('us',tz='UTC'))
    f=ds.dataset(SOURCE,format='parquet').to_table(columns=columns,filter=pred).to_pandas()
    assert f.end_time.lt(t).all() and not f.job_id.duplicated().any()
    np.testing.assert_array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    before=len(f);zero=int(f.runtime_seconds.eq(0).sum())
    valid=np.isfinite(f.runtime_seconds)&f.runtime_seconds.gt(0)&f[CLOCK].notna().all(axis=1)
    f=f[valid].copy();f['job_uid']=f.job_id.astype(str)
    f['source_row_identity']=SOURCE_SHA+':job_id:'+f.job_uid
    f=f.sort_values(['end_time','job_uid'],kind='mergesort').reset_index(drop=True)
    if log:event(t,'HISTORICAL_READ',projected_columns=columns,rows_materialized=before,positive_eligible=len(f),zero_excluded=zero,
      latest_end=f.end_time.max(),predicate='end_time < issue_time',future_rows_materialized=0)
    return f

def features(t):
    assert not set(LABELS)&set(FEATURE_COLUMNS)
    f=pq.read_table(PANEL,columns=FEATURE_COLUMNS,filters=[('issue_time','==',pd.Timestamp(t).to_pydatetime())]).to_pandas()
    assert len(f)>0 and f.issue_time.eq(pd.Timestamp(t)).all()
    f['job_uid']=f.job_id.astype(str)
    mapping=read('PENDING_PANEL_IDENTITY_AUDIT')['ordered_job_issue_ids']
    pos={uid:i for i,uid in enumerate(mapping)}
    f['panel_row_order']=f.job_issue_uid.map(pos)
    assert f.panel_row_order.notna().all() and f.panel_row_order.is_monotonic_increasing
    event(t,'FEATURE_READ',columns=FEATURE_COLUMNS,N=len(f),ordered_ids=ordered_ids(f.job_issue_uid),label_columns=[])
    return f

def labels(t):
    e=json.loads((OUT/'events'/f'{key(t)}.json').read_text())
    hashes={v['track']:v for v in e if v['kind']=='PREDICTION_HASH'}
    assert set(hashes)=={'P','PW'},'PREDICTIONS_MUST_BE_HASHED_BEFORE_LABELS'
    assert not any(v['kind']=='EVALUATION_LABEL_READ' for v in e),'LABELS_ALREADY_OPENED'
    for track,v in hashes.items():assert file_sha(OUT/v['path'])==v['SHA256']
    f=pq.read_table(PANEL,columns=['job_id','job_issue_uid',*LABELS],filters=[('issue_time','==',pd.Timestamp(t).to_pydatetime())]).to_pandas()
    np.testing.assert_array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    assert f.end_time.gt(pd.Timestamp(t)).all() and f.runtime_seconds.gt(0).all()
    event(t,'EVALUATION_LABEL_READ',columns=['job_id','job_issue_uid',*LABELS],N=len(f),
      prediction_hashes_verified={track:v['SHA256'] for track,v in hashes.items()},scope='Current issue only, after both P and PW prediction hashes')
    return f

def check_membership(t,f,previous_t=None,previous_ids=None):
    current=set(f.job_uid);previous_ids=set(previous_ids or [])
    assert previous_ids<=current and f.end_time.lt(pd.Timestamp(t)).all()
    added=f[~f.job_uid.isin(previous_ids)]
    if previous_t is not None:assert added.end_time.ge(pd.Timestamp(previous_t)).all()
    return dict(issue_time=pd.Timestamp(t),training_job_count=len(f),training_job_uid_SHA256=ids(f.job_uid),
      earliest_training_submit=f.submit_time.min(),latest_training_end=f.end_time.max(),new_jobs_added_since_previous_issue=len(added),
      previous_issue_time=previous_t,min_new_end=added.end_time.min() if len(added) else None,
      previous_membership_subset=True,future_or_equal_end_N=0,cache_reuse='NO',source_SHA256=SOURCE_SHA,
      support_route=fold_count(len(f)),training_library_hash=None)
