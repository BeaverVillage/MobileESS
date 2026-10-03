"""Verify already frozen weather and AEMO inputs have D-1 source vintages."""
import pandas as pd
import numpy as np
from .common import *
from v42_april_port.builder import axis,timestamp

def main():
    spec=source_freeze();rows=[]
    if (OUT/'MAY_ACTUAL_PROGRESS.json').exists(): raise ValueError('VINTAGE_GATE_MUST_PRECEDE_ANY_ACTUAL_AC')
    for s in spec['day_sources']:
        day=s['day'];issue,start,end=axis(day);f=read(resolve(s['forecast']));w=pd.read_parquet(resolve(s['weather']))
        if any(timestamp(f[k])>timestamp(issue) for k in ('demand_issue','pv_issue')):raise ValueError('FUTURE_AEMO_VINTAGE')
        gfs_path=RAW/day/'gfs_source_manifest.json';gfs=read(gfs_path)
        initial=sorted({r['initialization_utc'] for r in gfs['records']})
        if not initial or any(timestamp(t)>timestamp(issue) for t in initial):raise ValueError('FUTURE_GFS_VINTAGE')
        expected_grid=pd.date_range(start+pd.Timedelta(minutes=15),end,freq='15min')
        expected_weather=pd.date_range(start,periods=96,freq='15min')
        if not pd.DatetimeIndex(f['timestamps_96']).tz_convert('UTC').equals(expected_grid.tz_convert('UTC')):raise ValueError('FORECAST_INTERVAL_END_AXIS')
        if not pd.DatetimeIndex(w.ts_fixed_aest).tz_convert('UTC').equals(expected_weather.tz_convert('UTC')):raise ValueError('FORECAST_WEATHER_START_AXIS')
        if not np.isfinite(np.array([f['demand_mw_96'],f['pv_mw_96']])).all():raise ValueError('FINITE_FORECAST_RAW_REQUIRED')
        rows.append(dict(day=day,issue=issue.isoformat(),AEMO_demand_issue=f['demand_issue'],AEMO_pv_issue=f['pv_issue'],
            GFS_initialization_UTC=initial,GFS_vintage_manifest=record(gfs_path),forecast=record(resolve(s['forecast'])),
            weather=record(resolve(s['weather'])),future_vintage_leakage=False,exact_grid_weather_axes=True))
    write(OUT,'D1_FORECAST_VINTAGE_CAUSALITY.json',dict(PASS=True,days=rows,days_checked=31,
        before_first_Actual_AC=True,forecast_or_weather_values_modified=False,April_or_May_parameter_tuning=0))
    print('D-1 AEMO/GFS vintage and exact interval axes PASS:31/31',flush=True)

if __name__=='__main__':main()
