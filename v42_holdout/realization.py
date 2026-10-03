"""Post-freeze private realization; no future duration crosses FCFS controller."""
import zipfile
import csv
import io
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from .calendar_adapter import producer

def archive_rows(path):
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'): continue
            with z.open(name) as stream:
                headers={}
                for row in csv.reader(io.TextIOWrapper(stream,encoding='utf-8-sig')):
                    if row and row[0]=='I': headers[tuple(row[1:4])]=row[4:]
                    elif row and row[0]=='D' and tuple(row[1:4]) in headers:
                        yield dict(zip(headers[tuple(row[1:4])],row[4:]))

def truth(spec):
    requested={}; keys={}
    for day in DAYS:
        dest=INPUT/'BUNDLE'/day_folder(day)
        p=read(dest/'PLANNING_INPUT_BUNDLE.json'); a=read(dest/'ACTUAL_INPUT_BUNDLE.json')
        for r in p['known_population']+a['post_issue_arrivals']:
            key=(r['source_member'],int(r['source_row'])); uid=r['job_uid']
            if key in requested and requested[key]!=uid: raise ValueError('SOURCE_ROW_IDENTITY_CONFLICT')
            requested[key]=uid;keys.setdefault(key[0],set()).add(key[1])
    rows={}; cols=['id','submit_time','start_time','end_time','wallclock_used','state','state_simple']
    with zipfile.ZipFile(resolve(spec['archive'])) as z:
        for member,indices in sorted(keys.items()):
            if not any(f'/month={m}/' in member for m in (4,5)): raise ValueError('UNREGISTERED_SOURCE_MONTH')
            with z.open(member) as f:
                pf=pq.ParquetFile(f);offset=0
                for batch in pf.iter_batches(columns=cols,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas();frame['source_row']=np.arange(offset,offset+len(frame));offset+=len(frame)
                    for r in frame[frame.source_row.isin(indices)].to_dict('records'):
                        uid=str(r['id']); key=(member,int(r['source_row']))
                        if requested[key]!=uid or uid in rows: raise ValueError('EXACT_REALIZED_UID_SOURCE_JOIN')
                        start,end,submit=r['start_time'],r['end_time'],r['submit_time']
                        duration=(end-start).total_seconds() if pd.notna(start) and pd.notna(end) else None
                        valid=duration is not None and np.isfinite(duration) and duration>=0 and start>=submit
                        rows[uid]=dict(job_uid=uid,submit_time=submit.isoformat(),start_time=start.isoformat() if pd.notna(start) else None,
                            end_time=end.isoformat() if pd.notna(end) else None,realized_seconds=duration if valid else None,
                            source_member=member,source_row=key[1],source_sha256=spec['archive']['sha256'],
                            authority='SOURCE_OBSERVED_END_MINUS_START' if valid else 'REALIZED_SERVICE_DURATION_NOT_IDENTIFIABLE',
                            controller_receives_future_duration=False)
    if set(rows)!=set(requested.values()): raise ValueError('SOURCE_REALIZATION_POPULATION_JOIN_INCOMPLETE')
    bad=[r for r in rows.values() if r['realized_seconds'] is None]
    table(OUT,'ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv',list(rows.values()),list(next(iter(rows.values()))))
    write(OUT,'ACTUAL_REALIZED_SERVICE_AUTHORITY_AUDIT.json',dict(unique_physical_jobs=len(rows),
        missing_realized_duration_unique_jobs=len(bad),bad_rows=bad,source_members=list(keys),
        future_truth_hidden_in_private_environment=True,requested_walltime_used=False,Q50_used_as_Actual_duration=False,
        zero_imputation=False,raw_archive=spec['archive']))
    if bad: raise ValueError('MISSING_REALIZED_DURATION_NO_FALLBACK:'+str(len(bad)))

def exogenous(spec):
    values={}
    for kind,ts,col in [('demand','SETTLEMENTDATE','TOTALDEMAND'),('pv','INTERVAL_DATETIME','POWER')]:
        rows=[r for r in archive_rows(resolve(spec['exogenous_sources'][kind])) if r.get('REGIONID')=='VIC1' and ts in r and (kind!='pv' or r.get('TYPE')=='MEASUREMENT')]
        f=pd.DataFrame(rows);time=pd.to_datetime(f[ts],format='%Y/%m/%d %H:%M:%S').dt.tz_localize('Etc/GMT-10')
        values[kind]=pd.Series(pd.to_numeric(f[col]).to_numpy(),index=time)
    wf=pd.read_parquet(resolve(spec['exogenous_sources']['weather']));wf.index=pd.DatetimeIndex(wf.ts).tz_convert('Etc/GMT-10')
    numeric=wf.drop(columns='ts').select_dtypes(include='number')
    for day in DAYS:
        start=pd.Timestamp(day,tz='Etc/GMT-10');end=start+pd.Timedelta(days=1)
        grids={}
        for kind in values:
            s=values[kind]; selected=s[(s.index>start)&(s.index<=end)]
            if selected.index.duplicated().any(): raise ValueError('ACTUAL_AEMO_DUPLICATE')
            axis=pd.date_range(start+pd.Timedelta(minutes=15 if kind=='demand' else 30),end,freq='15min' if kind=='demand' else '30min')
            v=selected.reindex(axis).to_numpy(float);grids[kind]=v if kind=='demand' else np.repeat(v,2)
            if grids[kind].shape!=(96,) or not np.isfinite(grids[kind]).all(): raise ValueError('ACTUAL_AEMO_MISSING:'+day)
        target=pd.date_range(start,periods=96,freq='15min')
        # Bracketing observations, the frozen within-day time-linear interpolation.
        weather=numeric.reindex(numeric.index.union(target)).sort_index().interpolate(method='time',limit_area='inside').reindex(target)
        if not np.isfinite(weather[['t_wb_c','rh_pct']].to_numpy()).all(): raise ValueError('ACTUAL_NOAA_MISSING:'+day)
        weather=weather.reset_index(names='ts_fixed_aest_start')
        ending=pd.date_range(start+pd.Timedelta(minutes=15),end,freq='15min')
        forecast=read(RAW/day/'aemo_forecast.json')
        if not ending.tz_convert('UTC').equals(pd.DatetimeIndex(forecast['timestamps_96']).tz_convert('UTC')):
            raise ValueError('EXACT_FORECAST_ACTUAL_INTERVAL_END_ALIGNMENT')
        dest=INPUT/'BUNDLE'/day_folder(day)
        pd.DataFrame(dict(ts_fixed_aest_end=ending,demand_mw=grids['demand'],rooftop_pv_mw=grids['pv'])).to_parquet(dest/'DERIVED_AEMO_ACTUAL.parquet',index=False)
        weather.to_parquet(dest/'DERIVED_NOAA_ACTUAL.parquet',index=False)
        prov=read(dest/'SOURCE_PROVENANCE.json')
        prov['daily_sources']['aemo_actual.parquet']=record(dest/'DERIVED_AEMO_ACTUAL.parquet')
        prov['daily_sources']['noaa_actual_weather.parquet']=record(dest/'DERIVED_NOAA_ACTUAL.parquet')
        prov.update(post_Planning_freeze_realization=True,raw_realized_sources=spec['exogenous_sources'],
            grid_interval_ending=True,weather_interval_start=True,derived_data_not_new_raw_authority=True)
        write(dest,'SOURCE_PROVENANCE.json',prov)

def main():
    spec=source_freeze(); freeze=read(OUT/'ALL_MAY_PLANNING_FROZEN.json')
    if not freeze['PASS'] or freeze['days']!=list(DAYS): raise ValueError('ALL_PLAN_FREEZE_REQUIRED_BEFORE_REALIZATION')
    for day in DAYS:
        f=read(destination(day)/'PLANNING_FREEZE.json')
        for key in ('reference','physical_arrays','voltage','response','planning_input','coefficients'): resolve(f[key])
    truth(spec);exogenous(spec)
    replay=producer('v42_capacity.replay',OUT=OUT,PRIOR=INPUT)
    replay.main()
    write(OUT,'ACTUAL_PHYSICAL_FREEZE.json',dict(days=[dict(day=d,physical=record(destination(d)/'ACTUAL_PHYSICAL.npz'),
        Planning_freeze=record(destination(d)/'PLANNING_FREEZE.json')) for d in DAYS],
        all_31_Planning_frozen_before_private_truth=True,queue_producer=record(ROOT/'v42_capacity/actual.py'),
        future_duration_controller_reads=0,Actual_PQ_repair=0,Actual_reoptimization=0))

if __name__=='__main__': main()
