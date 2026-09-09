"""Verify stored D-1 information boundaries, without training or optimization."""
from mission_health import ROOT,BASE,OUT,read,write,refs
from fast_prepare import record
import pandas as pd
import time

def audit_day(day):
    prep=read(BASE/'audit'/day/'INPUT_PREPARATION.json');refs(prep)
    snap=read(prep['new_snapshot']['path']);issue=pd.Timestamp(snap['issue_time'])
    assert snap['target_day']==day
    assert issue==pd.Timestamp(day,tz='Australia/Brisbane')-pd.Timedelta(hours=6)
    authority=snap['input_authority'];refs(authority)
    causal=read(authority['causal_history']['path']);refs(causal['files'])
    assert pd.Timestamp(causal['issue_time'])==issue
    assert causal['future_label_rows_materialized']==0 and causal['event_future_timestamps_censored']
    assert pd.Timestamp(causal['training_max_end'])<issue
    for fit in snap['fit_records']:assert pd.Timestamp(fit['max_training_end'])<issue
    history=pd.read_parquet(causal['files']['runtime_history']['path'],columns=['end_time','submit_time'])
    assert len(history)==snap['runtime_training_N']==causal['runtime_training_N']
    ends=pd.to_datetime(history.end_time,utc=True);submits=pd.to_datetime(history.submit_time,utc=True)
    assert ends.notna().all() and ends.lt(issue).all() and submits.le(issue).all()
    pending=pd.read_parquet(authority['pending_features_source']['path'],columns=['submit_time','state_at_issue','known_running_start'])
    assert pd.to_datetime(pending.submit_time,utc=True).le(issue).all()
    running=pending[pending.state_at_issue=='RUNNING']
    assert pd.to_datetime(running.known_running_start,utc=True).le(issue).all()
    support=snap['H4_calibration_support'];mature=[]
    for row in support['extension_audit']:
        if row['status']=='MATURE_OOS':
            available=pd.Timestamp(row['label_available_at']);assert available<issue
            assert pd.Timestamp(row['day'],tz='Australia/Brisbane')+pd.Timedelta(days=1)<issue
            mature.append(available)
    return dict(status='PASS',day=day,issue_time=issue.isoformat(),snapshot=prep['new_snapshot'],
        causal_authority=authority['causal_history'],runtime_history=causal['files']['runtime_history'],
        pending_source=authority['pending_features_source'],runtime_rows=len(history),
        maximum_training_end=ends.max().isoformat(),scheduler_rows=len(pending),running_rows=len(running),
        matured_H4_extension_days=len(mature),maximum_extension_label_available_at=max(mature).isoformat() if mature else None,
        future_runtime_labels=0,future_scheduler_submissions=0,future_H4_extension_labels=0,
        boundary='D-1 issue only; Actual decision replay boundary is separately checked per policy',
        source=record(__file__),additional_ML_calls=0,additional_optimizer_calls=0)

def main():
    rows=[];errors=[]
    for n in range(1,32):
        day=f'2025-05-{n:02}';path=OUT/'causality'/f'{day}.json'
        try:
            if path.exists():
                value=read(path);refs(value)
                assert value['source']==record(__file__) and value['status']=='PASS'
            else:value=audit_day(day);write(path,value)
            rows.append(value)
        except Exception as e:errors.append(dict(day=day,error=repr(e)))
    result=dict(status='PASS' if len(rows)==31 and not errors else 'FAIL',verified_dates=len(rows),errors=errors,
        checked_at=time.time(),rows=rows)
    write(OUT/'CAUSAL_INPUT_AUDIT.json',result)
    print({k:v for k,v in result.items() if k!='rows'})
    return result
if __name__=='__main__':main()
