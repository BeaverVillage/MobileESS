from __future__ import annotations
import numpy as np, pandas as pd
class Baselines:
    def __init__(self, combined, interval_minutes, daily_steps, weekly_steps):
        self.c=combined.set_index('timestamp_utc',drop=False); self.dd=pd.Timedelta(minutes=interval_minutes*daily_steps); self.wd=pd.Timedelta(minutes=interval_minutes*weekly_steps)
    def predict(self,timestamps,row,hist):
        idx=pd.DatetimeIndex(pd.to_datetime(timestamps,utc=True)); target=str(row.target_column); source=str(row.source_metric); h=int(row.horizon_steps)
        if row.target_type=='point_at_horizon': pers=self.c[source]
        else: pers=self.c[source].rolling(h,min_periods=1).sum()
        p=pers.reindex(idx).to_numpy(float); d=self.c[target].reindex(idx-self.dd).to_numpy(float); w=self.c[target].reindex(idx-self.wd).to_numpy(float)
        hm=np.full(len(idx),float(hist)); p=np.where(np.isfinite(p),p,hm); d=np.where(np.isfinite(d),d,p); w=np.where(np.isfinite(w),w,d)
        return {'persistence':p,'seasonal_daily':d,'seasonal_weekly':w,'historical_mean':hm,'zero':np.zeros(len(idx))}
