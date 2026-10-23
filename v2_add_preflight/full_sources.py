"""Precise source omissions and causal initialization audit, no replacement data."""
from datetime import datetime,timedelta,timezone
import numpy as np
import pandas as pd
from .full_common import *

def audit():
    init();resources();rows=[];weather=[];missing=[]
    for day in read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days']:
        n=read(day['files']['native']['path']);w=read(day['files']['windows']['path']);by={r['job_id'] for r in w}
        excluded=[r for r in n['known_population'] if r['job_uid'] not in by and not(r['state']=='RUNNING' and r['service_slots']==0)]
        for r in excluded:missing.append(dict(day=day['day'],uid=r['job_uid'],state=r['state'],service_slots=r['service_slots'],
            planning_eligible=r['planning_eligible'],GPU_gang=r['GPU_gang'],reason='OriginalKnownWindows.issue requires Known WINDOW; not external zero-service Running'))
        p=read(day['files']['provenance']['path'])['raw_realized_sources']['weather'];f=pd.read_parquet(p['path'],columns=['ts','t_wb_c','rh_pct'])
        stamps=np.array([pd.Timestamp(t).timestamp() for t in f.ts]);mask=(stamps>=day['axis']['issue_seconds']-7200)&(stamps<=day['axis']['end_seconds'])
        bad=mask&~np.isfinite(f[['t_wb_c','rh_pct']].to_numpy(float)).all(axis=1)
        for i in np.flatnonzero(bad):weather.append(dict(day=day['day'],row=int(i),timestamp=str(f.ts.iloc[i]),
            t_wb_c=None if not np.isfinite(f.t_wb_c.iloc[i]) else float(f.t_wb_c.iloc[i]),
            rh_pct=None if not np.isfinite(f.rh_pct.iloc[i]) else float(f.rh_pct.iloc[i]),
            required_by='Original CausalSeries rejects nonfinite observations; no forward/future interpolation invented'))
        rows.append(dict(day=day['day'],Known=len(n['known_population']),WINDOWS=len(w),missing_Actual_Known_WINDOW=len(excluded),
            nonfinite_weather_rows=int(bad.sum()),initial_running=sum(r['state']=='RUNNING' for r in n['known_population']),
            inputs_changed=False,source_weather=p,source_native=day['files']['native'],source_windows=day['files']['windows']))
    table('MISSING_ACTUAL_KNOWN_WINDOWS.csv',missing or [dict(day='',uid='',reason='NONE')])
    table('NONFINITE_ORIGINAL_WEATHER.csv',weather or [dict(day='',row='',required_by='NONE')])
    put('DAILY_SOURCE_DEFECT_CENSUS.json',dict(days=rows,missing_windows_not_filled=True,weather_not_imputed=True,
        required_repair='Determine original dated adapter/authority for out-of-horizon Known jobs and source-correct finite observations; no new flexibility or Source QoS authority manufactured'))
    initial=read(day_input('2025-05-01')['files']['initial_running_authority']['path'])
    from v43_actual.observations import load_observations
    day=day_input('2025-05-01');begin=day['axis']['issue_seconds'];hist={}
    try:
        obs=load_observations(begin=begin-86400,end=begin,bundle=Path(day['files']['actual_input']['path']).parent)
        hist=dict(raw_observation_sources=obs.sources,earlier_exogenous_observations_available=True,
            first_asof=obs.at(begin-86400,observed_now=begin-86400))
    except Exception as exc:hist=dict(earlier_exogenous_observations_error=repr(exc))
    put('CAUSAL_PREFIX_INITIALIZATION_AUDIT.json',dict(status='BLOCKED_CAUSAL_PRIOR_STATE_NOT_UNIQUELY_BOUND',
        available_prior_observations=hist,initialization_authority=day['files']['initial_running_authority'],
        initialization_policy=initial['policy_id'],initial_site_source=initial['INITIAL_SITE_SOURCE'],
        source_observed_site_claim=initial['KESTREL_OBSERVED_SITE'],
        previous_IEEE8500_operating_Job_site_power_trace=None,previous_IEEE8500_Tap_Cap_internal_control_state=None,
        previous_IEEE8500_pending_queue_timestamps=None,
        earliest_current_120_axis=day['axis']['issue_AEST'],
        source_Prefix_initial_condition='Original/P5 control taps and CAP3 OFF; empty native Queue; no causal prior operating certificate',
        previous_IEEE123_state_transfer_rejected='Different node/RegControl topology, including Actual additional SVR3; source7/43 counts are not IEEE8500 authorities',
        settled_future_taps_as_initial_state=False,repeated_prefix_as_warmup=False,violation_removed_or_ignored=False,
        physical_delay_vs_iteration='Native queued action timestamps define seconds; 15/100 electrical iteration limit has no seconds interpretation',
        remedy_without_retuning='Bound a common earlier simulation origin with compatible Job episodes/sites and all prior exogenous inputs, then independently replay the entire TIME chain; source initial control state must itself satisfy that declared origin. A retrospective settled-tap copy cannot certify operation.',
        field_installation_status='FIELD_INSTALLATION_UNVERIFIED',scientific_failure_reason='Actual source-initial chronological voltage violations, independent of GIS/protection certification'))
    print('SOURCE DEFECTS',[(r['day'],r['missing_Actual_Known_WINDOW'],r['nonfinite_weather_rows']) for r in rows],flush=True)

if __name__=='__main__':audit()
