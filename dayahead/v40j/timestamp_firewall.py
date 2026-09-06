"""Canonical boundary retains the preregistered UTC calendar, not filename dates."""
import pandas as pd

CANONICAL_TIMEZONE='UTC'
LOCAL_CUTOFF='2025-05-01T00:00:00+00:00'
UTC_CUTOFF='2025-05-01T00:00:00+00:00'
FIXED_AEST_EQUIVALENT='2025-05-01T10:00:00+10:00'

def premay_mask(frame,columns=('submit_time','start_time','end_time')):
    mask=pd.Series(True,index=frame.index)
    for col in columns:
        times=pd.to_datetime(frame[col],utc=True)
        mask &= times.notna() & (times < pd.Timestamp(UTC_CUTOFF))
    return mask

def assert_historical_population(frame,prediction_time):
    t=pd.Timestamp(prediction_time)
    if t.tzinfo is None:t=t.tz_localize('UTC')
    if not premay_mask(frame).all() or not (frame.end_time<t).all() or not (frame.submit_time<t).all():
        raise ValueError('V40J_FUTURE_COMPLETION_OR_TIMESTAMP_LEAKAGE')

def timestamp_summary(frame):
    mask=premay_mask(frame)
    times=pd.concat([pd.to_datetime(frame[c],utc=True) for c in ['submit_time','start_time','end_time']])
    accepted=pd.concat([pd.to_datetime(frame.loc[mask,c],utc=True) for c in ['submit_time','start_time','end_time']])
    post=times[times>=pd.Timestamp(UTC_CUTOFF)]
    return {'accepted_rows':int(mask.sum()),'rejected_post_cutoff_row_count':int((~mask & frame[['submit_time','start_time','end_time']].ge(pd.Timestamp(UTC_CUTOFF)).any(axis=1)).sum()),
            'rejected_missing_timestamp_row_count':int(frame[['submit_time','start_time','end_time']].isna().any(axis=1).sum()),
            'maximum_accepted_timestamp':str(accepted.max()) if len(accepted) else None,
            'minimum_rejected_timestamp':str(post.min()) if len(post) else None}
