"""Causal May request projection and the frozen physical/modelability pipeline.

Only request descriptors and already observed running starts are loaded here.
No Actual end, duration, voltage or holdout-result fields are read.
"""
from collections import defaultdict, Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import zipfile
import sys
import math
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from v42_april_port.builder import axis,timestamp,build_v42_day_input_bundle
from v42_final.runtime import FrozenQ50
from v42_modelable.population import classify
from v42_modelable.cc4 import april_projection
from v42_final.workload import profile
from v42_capacity.reference import build_reference
from .calendar_adapter import producer

def requests(spec):
    cols=['id','submit_time','gpus_requested','nodes_req','processors_req','memory_req',
          'wallclock_req','partition','qos','account_hash','array_pos']
    result=defaultdict(list); projection=[]
    with zipfile.ZipFile(resolve(spec['archive'])) as z:
        members=sorted(n for n in z.namelist() if n.endswith('.parquet') and
                       any(f'year=2025/month={m}/' in n for m in (4,5)))
        for member in members:
            with z.open(member) as f:
                pf=pq.ParquetFile(f); offset=0
                projection.append(dict(member=member,columns=cols,rows=pf.metadata.num_rows))
                for batch in pf.iter_batches(columns=cols,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas(); frame['source_row']=np.arange(offset,offset+len(frame)); offset+=len(frame)
                    frame=frame[frame.partition.astype(str).str.contains('h100',case=False,regex=False)]
                    frame['requested_seconds']=frame.wallclock_req.dt.total_seconds(); frame.drop(columns='wallclock_req',inplace=True)
                    for row in frame.to_dict('records'):
                        uid=str(row.pop('id')); row.update(source_member=member,source_sha256=spec['archive']['sha256'],
                            submit_time=timestamp(row['submit_time']).isoformat())
                        result[uid].append(clean(row))
    if any(len(r)!=1 for r in result.values()): raise ValueError('EXACT_RAW_UID_DUPLICATE')
    write(OUT,'REQUEST_PROJECTION.json',dict(archive=spec['archive'],members=projection,
        future_start_end_duration_columns_read=False,May_outcome_columns_read=False,raw_files_copied=False))
    return dict(result)

def cc4():
    interface=read(ROOT.parent/'v42_integrated_pr/docs/v42_final/AGGREGATE_BINDING.json')['interface']
    paths={k:resolve(interface[k]) for k in ('prediction','ledger','selection')}
    ledger=pd.read_csv(paths['ledger'],usecols=['target_day','issue_time'])
    selected=ledger[ledger.target_day.between(DAYS[0],DAYS[-1])]
    if selected.target_day.tolist()!=list(DAYS): raise ValueError('FROZEN_MAY_CC4_ALL_DAYS_REQUIRED')
    q,shape=april_projection(paths['prediction'],selected.index.tolist())
    if not np.isfinite(q).all() or (q<0).any() or (q[:,:,0]>q[:,:,1]).any(): raise ValueError('CC4_QUANTILE_SCHEMA')
    kernel=ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv'
    kappa=pd.read_csv(kernel,usecols=['lag_slot','kappa']).kappa.to_numpy(); days={}
    for pos,row in enumerate(selected.itertuples()):
        if timestamp(axis(row.target_day)[0])!=timestamp(row.issue_time): raise ValueError('CC4_CAUSAL_ISSUE_DRIFT')
        nominal=profile(q[pos,:,0],kappa); reserve=profile(q[pos,:,1]-q[pos,:,0],kappa)
        days[row.target_day]=dict(target_day=row.target_day,issue_time=row.issue_time,prediction_index=int(row.Index),
            Q50_GPUh=q[pos,:,0].tolist(),Q90_GPUh=q[pos,:,1].tolist(),nominal_unknown_GPU_96=nominal[:96].tolist(),
            spread_headroom_GPU_96=reserve[:96].tolist(),full_tail_nominal_GPUh=float(nominal[96:].sum()*.25),
            future_job_ids=[],unknown_placement_optimized=False,unknown_profile_site_allocation_bound=False)
        write(OUT,'CC4/'+day_folder(row.target_day)+'.json',days[row.target_day])
    write(OUT,'MAY_CC4_BINDING.json',dict(interface=interface,indices=selected.index.tolist(),days=31,
        kernel=record(kernel),array_shape=shape,forecast_modifications=0,fit_calls=0,
        inherited_model_selection_retrospective=True,unexported_fit_ingestion_receipts_not_certified=True))
    return days

def coefficients(day,p,spec):
    authority=spec['power']; c1path=resolve(authority['C1_implementation']); model=resolve(authority['C1'])
    sys.path.insert(0,str(c1path.parents[2]))
    from dayahead.v28r2.c1_affine import load_c1,endpoint_secant
    import dayahead.v28r2.c1_affine as module
    if Path(module.__file__).resolve()!=c1path.resolve(): raise ValueError('EXACT_C1_IMPLEMENTATION_REQUIRED')
    params=load_c1(model); idle=authority['current_IT_idle_kW_per_installed_GPU']; swing=authority['current_IT_swing_kW_per_active_GPU']
    weather=pd.read_parquet(RAW/day/'gfs_d1_weather.parquet')
    if len(weather)!=96 or not np.isfinite(weather[['t_wb_c','rh_pct']].to_numpy()).all(): raise ValueError('FORECAST_WEATHER_96')
    if 'issue_utc' in weather and any(pd.to_datetime(weather.issue_utc,utc=True)>timestamp(p['issue_time'])):
        raise ValueError('FUTURE_FORECAST_WEATHER')
    rows=[]; cache={}
    for t,w in enumerate(weather.itertuples(index=False)):
        for s,c in sorted(p['capacities'].items()):
            key=(c,float(w.t_wb_c),float(w.rh_pct))
            if key not in cache: cache[key]=endpoint_secant(s,t,idle*c,(idle+swing)*c,key[1],key[2],params)
            rows.append(dict(asdict(cache[key]),aidc_id=s,slot=t))
    dest=INPUT/'BUNDLE'/day_folder(day)
    table(dest,'C1_PLANNING_COEFFICIENTS.csv',rows,list(rows[0]))
    write(dest,'POWER_AUTHORITY.json',dict(authority,GFS=record(RAW/day/'gfs_d1_weather.parquet'),
        NOAA=spec['exogenous_sources']['weather'],planning_C1=record(dest/'C1_PLANNING_COEFFICIENTS.csv'),
        forecast_capacity_preflight=None,coefficients_recomputed_with_frozen_C1_no_fit=True))

def main():
    spec=source_freeze(); raw=requests(spec); forecasts=cc4(); provider=FrozenQ50()
    template=read(ROOT/'docs/v42_april_modelable_population_b0/BUNDLE/DAY_20250401/PLANNING_INPUT_BUNDLE.json')
    physical=deepcopy(template['network_authority']); physical['capacities']=template['capacities']; physical['rack_compatibility']=template['rack_compatibility']
    exclusion=[]; summary=[]; manifest=[]
    for s in spec['day_sources']:
        day=s['day']; issue,start,end=axis(day)
        columns=['id','submit_time','state_at_issue','known_running_start','source_member']
        snap=pd.read_parquet(resolve(s['snapshot']),columns=columns); known=[]
        for r in snap.itertuples(index=False):
            if str(r.id) not in raw: raise ValueError('KNOWN_UID_RAW_REQUEST_ABSENT:'+str(r.id))
            if r.source_member!=raw[str(r.id)][0]['source_member']: raise ValueError('EXACT_SOURCE_MEMBER_REQUIRED')
            observed=r.state_at_issue=='RUNNING'
            if observed and (pd.isna(r.known_running_start) or r.known_running_start>issue): raise ValueError('NONCAUSAL_RUNNING_START')
            elapsed=(issue-timestamp(r.known_running_start)).total_seconds() if observed else 0.
            known.append(dict(job_uid=str(r.id),submit_time=timestamp(r.submit_time).isoformat(),state_at_D1_cutoff=r.state_at_issue,
                elapsed_seconds=elapsed,source_site=None,source_site_authority=None))
        forecast=read(resolve(s['forecast']))
        if timestamp(forecast['cutoff_fixed_aest'])!=timestamp(issue): raise ValueError('FORECAST_CUTOFF_MISMATCH')
        for k in ('demand_issue','pv_issue'):
            if timestamp(forecast[k])>timestamp(issue): raise ValueError('FUTURE_FORECAST_VINTAGE')
        if len(forecast['timestamps_96'])!=96: raise ValueError('FORECAST_96')
        p,a,gate,recovery=build_v42_day_input_bundle(day,known_snapshot=known,raw_requests=raw,
            actual_observations={},runtime_provider=provider,physical_authority=physical,
            forecast_inputs=dict(complete=True,AEMO=forecast,CC4_bound=True,current_CC4=forecasts[day]),
            actual_inputs=dict(complete=True,authority=spec['exogenous_sources']))
        for role,key,b in [('KNOWN_D1','known_population',p),('ACTUAL_POST_ISSUE','post_issue_arrivals',a)]:
            selected=[]; allrows=b[key]
            for row in allrows:
                classification=classify(row,raw[row['job_uid']][0],p['capacities'],p['rack_compatibility'],datetime.fromtimestamp(provider.available,timezone.utc).isoformat())
                if classification['modelable']: selected.append(dict(row,compatible_sites=classification['compatible_sites']))
                else: exclusion.append(dict(day=day,role=role,job_uid=row['job_uid'],source_member=row['source_member'],source_row=row['source_row'],**classification))
            b[key]=selected
            summary.append(dict(day=day,role=role,raw_rows=len(allrows),physical_rows=len(selected),excluded_rows=len(allrows)-len(selected)))
        ids={r['job_uid'] for r in p['known_population']}
        a['observed_known_episodes']=[r for r in a['observed_known_episodes'] if r['job_uid'] in ids]
        a['known_immutable_GPU_map']={r['job_uid']:r['GPU_gang'] for r in p['known_population']}
        for b in (p,a):
            b.update(schema='V42_MODELABLE_DAY_INPUT_BUNDLE_V1',J_PHYSICAL_frozen=True,
                flags=dict(b['flags'],MAY_RUN=True,COMMON_CC4_USED=True),input_gate_PASS=True)
        dest=INPUT/'BUNDLE'/day_folder(day)
        write(dest,'PLANNING_INPUT_BUNDLE.json',p); write(dest,'ACTUAL_INPUT_BUNDLE.json',a)
        # Raw monthly files are hashed, not interpreted, by the Planning gate.
        daily={'aemo_forecast.json':s['forecast'],'gfs_d1_weather.parquet':s['weather'],
            'aemo_actual.parquet':spec['exogenous_sources']['demand'],'noaa_actual_weather.parquet':spec['exogenous_sources']['weather']}
        write(dest,'SOURCE_PROVENANCE.json',dict(day=day,snapshot=s['snapshot'],snapshot_columns=columns,
            archive=spec['archive'],daily_sources=daily,Actual_observations_loaded=False,Actual_voltage_read=False,
            physical_site_absent=True,reference_placement_rule='same frozen grid-blind ascending compatible site rule',
            request_version_history='UNVERIFIED_SOURCE_PROXY'))
        coefficients(day,p,spec)
        manifest.append(dict(day=day,planning=record(dest/'PLANNING_INPUT_BUNDLE.json'),actual=record(dest/'ACTUAL_INPUT_BUNDLE.json')))
        print(day,'current input physical known/arrivals',len(p['known_population']),len(a['post_issue_arrivals']),flush=True)
    table(OUT,'MAY_MODELABILITY_BY_DAY.csv',summary,list(summary[0]))
    table(OUT,'UNMODELABLE_WORKLOAD_LEDGER.csv',exclusion,list(exclusion[0]) if exclusion else ['day','job_uid'])
    write(OUT,'MAY_INPUT_MANIFEST.json',dict(days=manifest,modelability_rule_unchanged=True,excluded_events=len(exclusion),
        exclusions=dict(Counter(r['classification'] for r in exclusion)),request_version_history='UNVERIFIED_SOURCE_PROXY',
        no_GPU_imputation=True,no_outcome_selection=True,source_site_authority_absent=True,
        current_reference_fallback_only=True,Actual_completion_data_loaded=False,forecast_issue_checks_PASS=True))
    # The inherited arithmetic is unchanged; only month, 31-day range and output roots are routed.
    planning=producer('v42_capacity.planning',OUT=OUT,PRIOR=INPUT)
    planning.main()
    write(OUT,'CALENDAR_ADAPTER_AUDIT.json',dict(source=record(ROOT/'v42_capacity/planning.py'),
        allowed_changes=['2025-04 / DAY_202504 date literals to 2025-05 / DAY_202505','range(1,31) to range(1,32)','OUT/PRIOR output routing'],
        computation_rules_changed=False,parameters_changed=False,all_Planning_workload_inputs_frozen=True))

if __name__=='__main__': main()
