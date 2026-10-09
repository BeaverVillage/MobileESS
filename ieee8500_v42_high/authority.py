"""Separate-date engineering input binding using unchanged V42/P5 rules.

No feeder build, Native optimization, campaign write, source producer main or
schedule repair is invoked. Actual truth is used only in the private replay.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import csv,hashlib,json,shutil,zipfile,subprocess
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/ieee8500_v42_high_impact_scenario'
DATA=ROOT/'ieee8500_v42_high/data/validation/2025-05-02'
DAY='2025-05-02'
PARENT='35079f458fc9d87a469ebd79e0e5d2cb7bd5fe1e'
EXTERNAL=Path('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout')
INPUT=EXTERNAL/'INPUT/BUNDLE/DAY_20250502'
TZ='Etc/GMT-10'
START=pd.Timestamp(DAY,tz=TZ)
STARTS=pd.date_range(START,periods=96,freq='15min')
ENDS=STARTS+pd.Timedelta(minutes=15)
CHECKED={}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def receipt(path):
    path=Path(path);return dict(path=str(path.resolve()),sha256=sha(path),bytes=path.stat().st_size)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,value):
    path=Path(path);assert path.resolve().is_relative_to(ROOT)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def table(path,rows):
    rows=list(rows);assert rows
    path=Path(path);assert path.resolve().is_relative_to(ROOT)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def checked(record):
    path=Path(record['path']);key=str(path.resolve())
    if key not in CHECKED:
        actual=receipt(path)
        if actual['sha256']!=record['sha256'] or ('bytes' in record and actual['bytes']!=record['bytes']):
            raise ValueError('SOURCE_BYTES_CHANGED:'+key)
        CHECKED[key]=actual
    return path
def copy_checked(record,name):
    source=checked(record);dest=DATA/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,dest);assert sha(dest)==record['sha256']
    return dict(original=receipt(source),copied=receipt(dest))
def axis_equal(actual,expected):
    axis=pd.DatetimeIndex(actual)
    if axis.has_duplicates or axis.tz is None or not axis.tz_convert('UTC').equals(expected.tz_convert('UTC')):
        raise ValueError('EXACT_TIME_AXIS_MISMATCH')


def freeze_date_rule():
    doc=dict(schema='IEEE8500_HIGH_DETERMINISTIC_SEPARATE_DATE_V1',parent_commit=PARENT,
        development_day='2025-05-01',validation_day=DAY,
        selection_rule='Earliest subsequent May date with existing source inputs; no AC, rho or control-effect ranking',
        IEEE8500_prior_exposure_scope='Inherited PR193/196/197 preregistrations inspected: May01 only; no claim of exhaustive historical global nonexposure',
        IEEE123_prior_exposed=True,globally_pristine_holdout=False,
        validation_scope='Separate IEEE8500 engineering date; inherited fit/as-of uncertainties remain',
        Actual_for_BG_GPU_port_selection=False,retuning_after_Actual_forbidden=True,
        baseline_installed_GPU=780,workload_multiplier=1,BG_scale_applied_to_input_arrays=False,
        temporal_rules=dict(Forecast_demand='48 half-hour interval powers repeated2',
            Actual_demand='288 five-minute interval powers averaged3',PV='48 half-hour interval powers repeated2',
            weather='GFS at interval start; NOAA time-linear within bracketing observations',
            reference='V42_COMMON_FCFS_Q50_NOMINAL_RELEASE_V2',
            actual_jobs='unchanged causal FCFS controller with private source-observed durations'),
        Native_calls=0,FULL_builds=0,AC_solves=0,campaign_writes=0)
    path=REPORT/'DATE_SELECTION_PREREGISTRATION.json'
    if path.exists() and read(path)!=doc:raise ValueError('DATE_RULE_DRIFT')
    write(path,doc);return doc


def forecast_raw(forecast):
    from ieee8500_v42_aemo.data_binding import archive_rows
    output={}
    for kind in ('demand','pv'):
        path=checked(dict(path=forecast['cross_month_archive_authority'][kind+'_path'],sha256=forecast[kind+'_source_sha256']))
        selected=[]
        for row in archive_rows(path):
            if row.get('REGIONID')!='VIC1' or any(str(row.get(k,''))!=str(v) for k,v in forecast[kind+'_identity'].items()):continue
            stamp=row.get('DATETIME' if kind=='demand' else 'INTERVAL_DATETIME') or row.get('SETTLEMENTDATE')
            if stamp and START<pd.Timestamp(stamp,tz=TZ)<=START+pd.Timedelta(days=1):selected.append(row)
        if len(selected)!=48:raise ValueError('FORECAST_HALF_HOUR_COVERAGE')
        key='DATETIME' if kind=='demand' else 'INTERVAL_DATETIME'
        if key not in selected[0]:key='SETTLEMENTDATE'
        selected.sort(key=lambda r:r[key]);column='DEMAND' if kind=='demand' else 'POWERMEAN'
        if column not in selected[0] and kind=='demand':column='TOTALDEMAND'
        raw=np.array([float(r[column]) for r in selected]);values=np.asarray(forecast[kind+'_mw_96'])
        if np.max(abs(np.repeat(raw,2)-values))>1e-10:raise ValueError('FORECAST_RAW_VALUE_DRIFT')
        axis_equal([pd.Timestamp(r[key],tz=TZ) for r in selected],pd.date_range(START+pd.Timedelta(minutes=30),periods=48,freq='30min'))
        table(DATA/'sources'/f'FORECAST_SELECTED_{kind.upper()}_30MIN.csv',selected)
        output[kind]=dict(raw=receipt(path),selected_rows=48,derived_rows=96,unit='MW',
            raw_energy_MWh=float(raw.sum()*.5),derived_energy_MWh=float(values.sum()*.25),value_error=0.,
            issue=forecast[kind+'_issue'],cutoff=forecast['cutoff_fixed_aest'])
    return output


def prepare_planning():
    freeze_date_rule()
    from v42_capacity.reference import build_reference
    from v42_capacity.queue import allocate,conservation
    from v42_modelable.power import known_occupancy
    from ieee8500_v42.capacity import load_c1_module
    from ieee8500_v42_aemo.data_binding import temporal_factors
    provenance=read(INPUT/'SOURCE_PROVENANCE.json');plan=read(INPUT/'PLANNING_INPUT_BUNDLE.json')
    if plan['day']!=DAY or sum(plan['capacities'].values())!=780:raise ValueError('DATE_OR_ORIGINAL_CAPACITY_DRIFT')
    copies=[copy_checked(receipt(INPUT/'PLANNING_INPUT_BUNDLE.json'),'PLANNING_INPUT_BUNDLE.json'),
        copy_checked(provenance['daily_sources']['aemo_forecast.json'],'AEMO_FORECAST.json'),
        copy_checked(provenance['daily_sources']['gfs_d1_weather.parquet'],'GFS_D1_WEATHER.parquet'),
        copy_checked(provenance['snapshot'],'D1_Kestrel_SNAPSHOT.parquet')]
    forecast=read(DATA/'sources/AEMO_FORECAST.json');axis_equal(forecast['timestamps_96'],ENDS)
    issue=pd.Timestamp(plan['issue_time'])
    if issue!=pd.Timestamp(forecast['cutoff_fixed_aest']) or any(pd.Timestamp(forecast[k+'_issue'])>issue for k in ('demand','pv')):
        raise ValueError('FORECAST_ISSUE_CUTOFF_DRIFT')
    raw=forecast_raw(forecast)
    weather=pd.read_parquet(DATA/'sources/GFS_D1_WEATHER.parquet');axis_equal(weather.ts_fixed_aest,STARTS)
    if not np.isfinite(weather[['t_wb_c','rh_pct','lead_hours']]).all().all():raise ValueError('FORECAST_WEATHER_MISSING')
    initialization=pd.DatetimeIndex(weather.ts_fixed_aest)-pd.to_timedelta(weather.lead_hours,unit='h')
    if initialization.nunique()!=1 or initialization[0]>issue:raise ValueError('FUTURE_GFS_INITIALIZATION')
    reference,audit=build_reference(plan['known_population'],plan['capacities'],plan['rack_compatibility'],issue_time=plan['issue_time'])
    if not audit['full_reference_ready']:raise ValueError('COMMON_REFERENCE_BLOCKED')
    sites=sorted(plan['capacities']);cap=np.array([plan['capacities'][s] for s in sites]);known=known_occupancy(reference,sites)
    cc=plan['forecast_inputs']['current_CC4']
    if cc['target_day']!=DAY or cc['future_job_ids'] or plan['future_actual_arrival_IDs_present'] or pd.Timestamp(cc['issue_time'])>issue:
        raise ValueError('CC4_OR_FUTURE_JOB_LEAKAGE')
    anon,incoming,outgoing=allocate(known,cc['nominal_unknown_GPU_96'],cap)
    conserved=conservation(sum(cc['Q50_GPUh']),anon,outgoing[-1],cc['full_tail_nominal_GPUh'])
    if not conserved['PASS'] or (known+anon>cap+1e-9).any():raise ValueError('GPU_CAPACITY_OR_CC4_CONSERVATION')
    power=read(INPUT/'POWER_AUTHORITY.json');module=load_c1_module();params=module.load_c1(ROOT/'ieee8500_v42/data/v42_inputs/C1_MODEL.json')
    checked(power['C1']);checked(power['C1_implementation'])
    it=power['current_IT_idle_kW_per_installed_GPU']*cap+power['current_IT_swing_kW_per_active_GPU']*(known+anon)
    P=np.zeros((96,12));coefficients=[]
    for t,w in enumerate(weather.itertuples(index=False)):
        for i,site in enumerate(sites):
            c=module.endpoint_secant(site,t,power['current_IT_idle_kW_per_installed_GPU']*cap[i],
                (power['current_IT_idle_kW_per_installed_GPU']+power['current_IT_swing_kW_per_active_GPU'])*cap[i],float(w.t_wb_c),float(w.rh_pct),params)
            P[t,i]=c.slope*it[t,i]+c.intercept_kw;coefficients.append(dict(asdict(c),site=site))
    Q=P*np.tan(np.arccos(power['PF_AIDC']))
    errors={}
    baseline=EXTERNAL/'BUNDLE/DAY_20250502/PLANNING_PHYSICAL.npz'
    with np.load(baseline,allow_pickle=False) as z:
        for key,value in dict(known_gpu=known,cc4_served_gpu=anon,total_gpu=known+anon,IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q).items():errors[key]=float(abs(value-z[key]).max())
    if max(errors.values())>1e-10:raise ValueError('UNCHANGED_PLANNING_REPLAY_DRIFT')
    parentfreeze=read(ROOT/'docs/ieee8500_v42_aemo_voltage_rebuild/PLANNING_INPUT_FREEZE.json')
    fraction=parentfreeze['source_PV_capacity_fraction'];gross,solar=temporal_factors(forecast['demand_mw_96'],forecast['pv_mw_96'],fraction)
    arrays=dict(sites=np.array(sites),capacities=cap,known_gpu=known,cc4_gpu=anon,total_gpu=known+anon,IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q,
        demand_mw=np.asarray(forecast['demand_mw_96']),pv_mw=np.asarray(forecast['pv_mw_96']),gross_factor=gross,pv_factor=solar)
    (DATA/'derived').mkdir(parents=True,exist_ok=True);np.savez_compressed(DATA/'derived/PLANNING_INPUTS.npz',**arrays)
    write(DATA/'derived/REFERENCE.json',dict(rows=reference,audit=audit));table(DATA/'derived/C1_PLANNING_COEFFICIENTS.csv',coefficients)
    copy_checked(receipt(INPUT/'POWER_AUTHORITY.json'),'POWER_AUTHORITY.json')
    doc=dict(PASS=True,scope='Source-backed input reproduction, not AC/security or complete as-of certification',day=DAY,issue_time=plan['issue_time'],
        arrays=receipt(DATA/'derived/PLANNING_INPUTS.npz'),reference=receipt(DATA/'derived/REFERENCE.json'),sources=copies,raw_forecast=raw,
        installed_GPU=780,original_known_jobs=len(plan['known_population']),original_population_sha=audit['population_sha256'],reproduction_errors=errors,CC4_conservation=conserved,
        source_PV_capacity_fraction=fraction,BG_scaling_applied=False,GFS_initialization=initialization[0].isoformat(),GFS_initialization_before_cutoff=True,
        GFS_publication_before_cutoff='UNVERIFIED',inherited_CC4_Runtime_fit_ingestion='UNVERIFIED',normalization_as_of='UNVERIFIED',
        true_request_version_history='UNVERIFIED_SOURCE_PROXY',source_site_identity='ABSENT_GRID_BLIND_REFERENCE',Actual_values_read=0,Native_calls=0,AC_solves=0,workload_multiplier=1)
    write(REPORT/'VALIDATION_PLANNING_INPUT_FREEZE.json',doc)
    print('May02 Planning input frozen; known1532/780GPU; exact-source reproduction',max(errors.values()),flush=True)
    return doc


def actual_exogenous():
    from ieee8500_v42_aemo.data_binding import archive_rows
    spec=read(EXTERNAL/'PREREGISTRATION.json');sources=spec['exogenous_sources']
    demand_path=checked(sources['demand']);pv_path=checked(sources['pv']);weather_path=checked(sources['weather'])
    raw_demand=[r for r in archive_rows(demand_path) if r.get('REGIONID')=='VIC1' and r.get('INTERVENTION','0')=='0'
        and r.get('SETTLEMENTDATE') and START<pd.Timestamp(r['SETTLEMENTDATE'],tz=TZ)<=START+pd.Timedelta(days=1)]
    raw_demand.sort(key=lambda r:r['SETTLEMENTDATE']);axis_equal([pd.Timestamp(r['SETTLEMENTDATE'],tz=TZ) for r in raw_demand],pd.date_range(START+pd.Timedelta(minutes=5),periods=288,freq='5min'))
    values=np.array([float(r['TOTALDEMAND']) for r in raw_demand]);demand=values.reshape(96,3).mean(1)
    raw_pv=[r for r in archive_rows(pv_path) if r.get('REGIONID')=='VIC1' and r.get('TYPE')=='MEASUREMENT' and r.get('INTERVAL_DATETIME')
        and START<pd.Timestamp(r['INTERVAL_DATETIME'],tz=TZ)<=START+pd.Timedelta(days=1)]
    raw_pv.sort(key=lambda r:r['INTERVAL_DATETIME']);axis_equal([pd.Timestamp(r['INTERVAL_DATETIME'],tz=TZ) for r in raw_pv],pd.date_range(START+pd.Timedelta(minutes=30),periods=48,freq='30min'))
    pv30=np.array([float(r['POWER']) for r in raw_pv]);pv=np.repeat(pv30,2)
    weather=pd.read_parquet(weather_path);weather.index=pd.DatetimeIndex(weather.ts).tz_convert(TZ)
    numeric=weather.drop(columns='ts').select_dtypes(include='number')
    realized=numeric.reindex(numeric.index.union(STARTS)).sort_index().interpolate(method='time',limit_area='inside').reindex(STARTS)
    if not np.isfinite(realized[['t_wb_c','rh_pct']]).all().all():raise ValueError('NOAA_BRACKETING_WEATHER_MISSING')
    realized=realized.reset_index(names='ts_fixed_aest_start');realized.to_parquet(DATA/'derived/NOAA_ACTUAL_96.parquet',index=False)
    pd.DataFrame(dict(ts_fixed_aest_end=ENDS,demand_mw=demand,rooftop_pv_mw=pv)).to_parquet(DATA/'derived/AEMO_ACTUAL_96.parquet',index=False)
    table(DATA/'sources/ACTUAL_SELECTED_DEMAND_5MIN.csv',raw_demand);table(DATA/'sources/ACTUAL_SELECTED_PV_30MIN.csv',raw_pv)
    write(REPORT/'VALIDATION_ACTUAL_EXOGENOUS_AUDIT.json',dict(raw_demand=receipt(demand_path),raw_PV=receipt(pv_path),raw_NOAA=receipt(weather_path),
        demand_original_MWh=float(values.sum()/12),demand_derived_MWh=float(demand.sum()/4),PV_original_MWh=float(pv30.sum()*.5),PV_derived_MWh=float(pv.sum()*.25),
        demand_rule='mean3 consecutive5min interval powers; do not select final5min point',PV_rule='repeat2 half-hour interval powers',
        weather_rule='unchanged time-linear within bracketing observations',Actual_values_to_Planning=0))
    return demand,pv,realized


def actual_gpu():
    from v42_capacity.actual import Request,Environment,replay
    plan=read(DATA/'sources/PLANNING_INPUT_BUNDLE.json');actual=read(INPUT/'ACTUAL_INPUT_BUNDLE.json')
    if actual['day']!=DAY or actual['capacities']!=plan['capacities'] or actual['rack_compatibility']!=plan['rack_compatibility']:raise ValueError('ACTUAL_DAY_CAPACITY_DRIFT')
    copy_checked(receipt(INPUT/'ACTUAL_INPUT_BUNDLE.json'),'PRIVATE_ACTUAL_INPUT_BUNDLE.json')
    jobs=plan['known_population']+actual['post_issue_arrivals'];descriptors={str(j['job_uid']):j for j in jobs}
    if len(descriptors)!=len(jobs):raise ValueError('ACTUAL_UID_DUPLICATE')
    with (EXTERNAL/'ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv').open(encoding='utf-8-sig',newline='') as f:
        truth={r['job_uid']:r for r in csv.DictReader(f) if r['job_uid'] in descriptors}
    if set(truth)!=set(descriptors):raise ValueError('ACTUAL_UID_TRUTH_JOIN_INCOMPLETE')
    spec=read(EXTERNAL/'PREREGISTRATION.json');archive=checked(spec['archive']);needed={}
    for uid,r in truth.items():needed.setdefault(r['source_member'],{})[int(r['source_row'])]=uid
    projected=[]
    with zipfile.ZipFile(archive) as z:
        for member,selected in needed.items():
            with z.open(member) as stream:
                parquet=pq.ParquetFile(stream);offset=0
                for batch in parquet.iter_batches(columns=['id','submit_time','start_time','end_time','gpus_requested'],batch_size=32768,use_threads=False):
                    frame=batch.to_pandas()
                    for i in (i-offset for i in selected if offset<=i<offset+len(frame)):
                        r=frame.iloc[i];uid=selected[offset+i];t=truth[uid]
                        if str(r.id)!=uid or any(pd.Timestamp(getattr(r,k))!=pd.Timestamp(t[k]) for k in ['submit_time','start_time','end_time']):raise ValueError('RAW_ACTUAL_UID_TIMESTAMP_DRIFT')
                        duration=(pd.Timestamp(r.end_time)-pd.Timestamp(r.start_time)).total_seconds()
                        if abs(duration-float(t['realized_seconds']))>1e-6 or int(r.gpus_requested)!=descriptors[uid]['GPU_gang']:raise ValueError('RAW_ACTUAL_GPU_SERVICE_DRIFT')
                        projected.append(dict(job_uid=uid,source_member=member,source_row=offset+i,source_archive_sha256=spec['archive']['sha256'],
                            submit_time=t['submit_time'],start_time=t['start_time'],end_time=t['end_time'],realized_seconds=duration,immutable_requested_GPU=int(r.gpus_requested),controller_future_duration_access=False))
                    offset+=len(frame)
            print('May02 private raw Kestrel join',len(projected),'verified',flush=True)
    if len(projected)!=len(jobs):raise ValueError('RAW_ACTUAL_JOB_COVERAGE')
    table(DATA/'sources/PRIVATE_ACTUAL_Kestrel_UID_JOIN.csv',projected)
    reference=read(DATA/'derived/REFERENCE.json')['rows'];mapping={r['job_uid']:r for r in reference}
    issue=pd.Timestamp(plan['issue_time']);seconds=lambda stamp:(pd.Timestamp(stamp)-issue).total_seconds()
    requests=[];running=[];durations={};completions={}
    for uid,job in descriptors.items():
        t=truth[uid];request=Request(uid,seconds(job['submit_time']),job['GPU_gang'],tuple(job['compatible_sites']),job['Q50_total_seconds'],job['source_site'])
        durations[uid]=float(t['realized_seconds'])
        if job['state_at_D1_cutoff']=='RUNNING':
            start,end=seconds(t['start_time']),seconds(t['end_time'])
            if not start<=0<end:raise ValueError('RUNNING_AT_ISSUE_TRUTH_MISMATCH')
            running.append((request,mapping[uid]['reference_site'],start));completions[uid]=end
        else:requests.append(request)
    gpu,ledger,audit=replay(plan['capacities'],requests,Environment(durations,completions),running=running)
    table(DATA/'derived/ACTUAL_QUEUE_LEDGER.csv',ledger)
    write(REPORT/'VALIDATION_ACTUAL_QUEUE_AUDIT.json',dict(**audit,day=DAY,original_known_jobs=len(plan['known_population']),post_issue_jobs=len(actual['post_issue_arrivals']),raw_requested_UIDs_verified=len(projected),
        raw_archive=spec['archive'],original_reference_and_capacities=True,planning_future_truth_reads=0,Actual_optimizer_calls=0))
    return gpu


def prepare_actual():
    frozen=read(REPORT/'VALIDATION_PLANNING_INPUT_FREEZE.json')
    if sha(DATA/'derived/PLANNING_INPUTS.npz')!=frozen['arrays']['sha256']:raise ValueError('PLANNING_NOT_FROZEN_BEFORE_PRIVATE_ACTUAL')
    from ieee8500_v42.capacity import load_c1_module
    from ieee8500_v42_aemo.data_binding import temporal_factors
    demand,pv,weather=actual_exogenous();gpu=actual_gpu()
    power=read(DATA/'sources/POWER_AUTHORITY.json');plan=read(DATA/'sources/PLANNING_INPUT_BUNDLE.json');sites=sorted(plan['capacities']);cap=np.array([plan['capacities'][s] for s in sites])
    module=load_c1_module();params=module.load_c1(ROOT/'ieee8500_v42/data/v42_inputs/C1_MODEL.json')
    it=power['current_IT_idle_kW_per_installed_GPU']*cap+power['current_IT_swing_kW_per_active_GPU']*gpu
    P=np.array([module.exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),params) for t,w in enumerate(weather.itertuples(index=False))]);Q=P*np.tan(np.arccos(power['PF_AIDC']))
    with np.load(EXTERNAL/'BUNDLE/DAY_20250502/ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
        errors={k:float(abs(v-z[k]).max()) for k,v in dict(GPU=gpu,IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q).items()}
    if max(errors.values())>1e-10:raise ValueError('UNCHANGED_PRIVATE_ACTUAL_REPLAY_DRIFT')
    gross,solar=temporal_factors(demand,pv,frozen['source_PV_capacity_fraction'])
    np.savez_compressed(DATA/'derived/ACTUAL_INPUTS.npz',sites=np.array(sites),capacities=cap,total_gpu=gpu,IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q,demand_mw=demand,pv_mw=pv,gross_factor=gross,pv_factor=solar)
    doc=dict(PASS=True,scope='Private realized source/input join, not AC or feasible policy',day=DAY,arrays=receipt(DATA/'derived/ACTUAL_INPUTS.npz'),
        reproduction_errors=errors,installed_GPU=780,workload_multiplier=1,GPU_capacity_violation_cells=int((gpu>cap+1e-9).sum()),
        future_duration_controller_reads=0,Actual_reoptimization=0,CC4_double_counted=False,Actual_C1_exact=True,Planning_C1_affine=True,
        background_actual_demand_energy_preserved=True,private_preparation_before_AC=True,Actual_for_candidate_selection_forbidden=True,Native_calls=0,AC_solves=0)
    write(REPORT/'VALIDATION_ACTUAL_INPUT_FREEZE.json',doc)
    write(REPORT/'VALIDATION_SOURCE_SHA256.json',dict(checked_original_sources=CHECKED,
        producer=receipt(Path(__file__)),P5_data_binding=receipt(ROOT/'ieee8500_v42_aemo/data_binding.py'),
        original_pipeline_sources={p:receipt(ROOT/p) for p in ['v42_capacity/reference.py','v42_capacity/queue.py','v42_capacity/actual.py','v42_modelable/power.py','v42_final/state.py','ieee8500_v42/data/v42_inputs/c1_affine.py','ieee8500_v42/data/v42_inputs/C1_MODEL.json','ieee8500_v42_aemo/data/authority/grid_background_v16_2.py']},
        output_files={str(p.relative_to(ROOT)):receipt(p) for p in DATA.rglob('*') if p.is_file()},Native_calls=0,AC_solves=0,campaign_writes=0))
    print('May02 Actual input frozen; raw2861Jobs; originalqueue/C1 reproduction',max(errors.values()),flush=True)
    return doc


def campaign_snapshot(label,*,scope_correction=False):
    """Read source/registration identities, writing only this worktree's receipt.

    The before receipt is explicitly late: the source preparation was complete
    when the parent requested this capture. It is not a task-start snapshot.
    Live worker progress is observed, never stopped or compared as immutable.
    """
    live=Path('D:/MobileESS_V42')
    campaign=live/'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
    immutable={str(p):receipt(p) for p in sorted(live.glob('v42*/*.py'))}
    for pattern in ('*MANIFEST.json','*PERMIT.json'):
        immutable.update({str(p):receipt(p) for p in sorted(campaign.glob(pattern))})
    for day in ('2025-05-01',DAY):
        folder=live/'runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1'/day
        immutable.update({str(p):receipt(p) for p in sorted(folder.iterdir()) if p.is_file()})
    commands={
        'processes':"Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|gurobi' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3",
        'scheduler':"Get-ScheduledTask | Where-Object { $_.TaskName -match 'MobileESS_V42|v42' } | Select-Object TaskName,TaskPath,State,@{n='Actions';e={$_.Actions|Select-Object Execute,Arguments}},@{n='Triggers';e={$_.Triggers|Select-Object StartBoundary,Enabled}} | ConvertTo-Json -Depth 5"}
    observed={k:json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',cmd],encoding='utf8') or '[]') for k,cmd in commands.items()}
    inherited=read(ROOT/'docs/ieee8500_v42_balanced_case/CAMPAIGN_AFTER.json')
    # The inherited campaign also pinned B2 May01 inputs; absence from this
    # narrower B1 scan must never be mislabeled an external byte mutation.
    for name in inherited['immutable']:
        p=Path(name)
        if p.is_file():immutable[name]=receipt(p)
    changed_inherited=[name for name,v in inherited['immutable'].items() if immutable.get(name)!=v]
    doc=dict(label=label,captured_at_UTC=datetime.now(timezone.utc).isoformat(),
        capture_timing='after May02 source input preparation; before remaining authority review/seal, not whole-task start',
        immutable=immutable,**observed,inherited_PR197_receipt=receipt(ROOT/'docs/ieee8500_v42_balanced_case/CAMPAIGN_AFTER.json'),
        inherited_immutable_count=len(inherited['immutable']),inherited_changed=changed_inherited,
        own_campaign_writes=0,worker_kills=0,scheduler_mutations=0,
        scope='read-only identities and registrations; other workers remain live')
    output=REPORT/f'CAMPAIGN_{label.upper()}.json'
    if output.exists() and label=='before':
        if not scope_correction:raise ValueError('IMMUTABLE_BEFORE_CAPTURE_EXISTS')
        archived=REPORT/'CAMPAIGN_BEFORE_INITIAL_NARROW_SCOPE.json'
        if archived.exists():raise ValueError('SCOPE_CORRECTION_ALREADY_CAPTURED')
        shutil.copyfile(output,archived)
        doc['initial_capture_archive']=receipt(archived)
        doc['scope_correction']='Read all inherited pinned paths; missing from initial B1-only inventory was not a byte change'
    write(output,doc)
    if label=='after':
        from ieee8500_v42.isolation import scheduler_registration_diff
        before=read(REPORT/'CAMPAIGN_BEFORE.json')
        changed=[name for name,v in before['immutable'].items() if immutable.get(name)!=v]
        diff=scheduler_registration_diff(before['scheduler'],doc['scheduler'])
        write(REPORT/'CAMPAIGN_PRESERVATION.json',dict(
            original_authorities_equal=not changed and not diff['removed'] and not diff['modified'],
            changed=changed,original_immutable_count=len(before['immutable']),
            added_authorities=sorted(set(immutable)-set(before['immutable'])),scheduler_diff=diff,
            earlier_PR197_source_identity_equal=not changed_inherited,earlier_PR197_changed=changed_inherited,
            own_external_mutations=0,scope='late snapshot comparison plus inherited PR197 byte identities; not frozen worker progress'))
    print('Read-only campaign snapshot',label,len(immutable),'identities; inherited changed',len(changed_inherited),flush=True)
    return doc


def audit_saved_inputs():
    """Portable byte/input audit; no external archive or solver is imported."""
    saved=read(REPORT/'VALIDATION_SOURCE_SHA256.json')
    changed=[]
    for name,r in saved['output_files'].items():
        p=ROOT/name
        if not p.is_file() or sha(p)!=r['sha256']:changed.append(name)
    if changed:raise ValueError('FROZEN_VALIDATION_OUTPUT_DRIFT:'+str(changed))
    planning=read(REPORT/'VALIDATION_PLANNING_INPUT_FREEZE.json')
    actual=read(REPORT/'VALIDATION_ACTUAL_INPUT_FREEZE.json')
    forecast=read(DATA/'sources/AEMO_FORECAST.json')
    source_paths=['ieee8500_v42_aemo/data_binding.py','v42_capacity/reference.py','v42_capacity/queue.py','v42_capacity/actual.py',
        'v42_modelable/power.py','ieee8500_v42/data/v42_inputs/c1_affine.py','ieee8500_v42/data/v42_inputs/C1_MODEL.json',
        'ieee8500_v42_aemo/data/authority/grid_background_v16_2.py']
    identities={}
    for name in source_paths:
        original=subprocess.check_output(['git','show',PARENT+':'+name],cwd=ROOT)
        equal=hashlib.sha256(original).hexdigest()==sha(ROOT/name)
        if not equal:raise ValueError('INHERITED_SOURCE_CHANGED:'+name)
        identities[name]=dict(**receipt(ROOT/name),parent_Git_blob=subprocess.check_output(['git','rev-parse',PARENT+':'+name],cwd=ROOT,text=True).strip(),parent_bytes_equal=True)
    folder=Path('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1')/DAY
    route_names=['NATIVE_INPUT.json','OPERATIONS.json','WINDOWS.json','ROUTE_TABLE.json.gz','TRAFFIC_FORECAST.npz']
    routes={name:receipt(folder/name) for name in route_names}
    doc=dict(schema='HIGH_SEPARATE_DATE_SOURCE_AUDIT_V1',parent_commit=PARENT,
        reviewed_V42_authority='625bbcb8b9a54a00c1660c26d96f7737c2f75457',
        V42_authority_scope='inherited PR197 source authority, not a claim of latest remote HEAD',
        source_input_identity_PASS=True,input_arrays_unchanged=True,day=DAY,
        date_preregistration=receipt(REPORT/'DATE_SELECTION_PREREGISTRATION.json'),
        planning_receipt=receipt(REPORT/'VALIDATION_PLANNING_INPUT_FREEZE.json'),
        actual_receipt=receipt(REPORT/'VALIDATION_ACTUAL_INPUT_FREEZE.json'),
        original_pipeline_identities=identities,
        available_route_inputs=routes,route_scope='available source artifacts only; no May02 SUMO replay, Native optimization or physical road-access certification performed here',
        raw_source_SHA=saved['checked_original_sources'],
        producer=receipt(Path(__file__)),initial_input_producer=receipt(REPORT/'INPUT_PRODUCER_FROZEN.py.txt'),
        initial_input_producer_matches_frozen_SHA=sha(REPORT/'INPUT_PRODUCER_FROZEN.py.txt')==saved['producer']['sha256'],
        producer_extension_scope='read-only saved-input/authority/campaign audit methods added; original input producer bytes archived',
        source_manifest=receipt(REPORT/'VALIDATION_SOURCE_SHA256.json'),
        original_known_jobs=planning['original_known_jobs'],post_issue_jobs=len(read(DATA/'sources/PRIVATE_ACTUAL_INPUT_BUNDLE.json')['post_issue_arrivals']),
        raw_Actual_UIDs=read(REPORT/'VALIDATION_ACTUAL_QUEUE_AUDIT.json')['raw_requested_UIDs_verified'],
        Planning_reproduction_max_error=max(planning['reproduction_errors'].values()),Actual_reproduction_max_error=max(actual['reproduction_errors'].values()),
        forecast_cutoff=forecast['cutoff_fixed_aest'],demand_issue=forecast['demand_issue'],PV_issue=forecast['pv_issue'],
        IEEE123_prior_exposed=True,globally_pristine_holdout=False,exhaustive_IE8500_nonexposure_audit=False,
        unresolved=['GFS publication latency before D1','Inherited CC4/runtime calibration ingestion and selection as-of',
            'Annual P95/alpha/PV reference availability at D1','True request version history','Source physical facility placement',
            'Field GIS/protection/access evidence','All real Native/grid/six-axis V42 integrations','Continuous policy/SOC feasibility'],
        AC_security_PASS=False,full_as_of_certified=False,Production=False,workload_multiplier=1,
        Actual_for_candidate_selection_forbidden=True,Native_calls=0,AC_solves=0,FULL_builds=0,campaign_writes=0)
    write(REPORT/'SOURCE_AUDIT.json',doc)
    print('Saved source audit PASS for input identity; as-of/AC/production unverified',flush=True)
    return doc


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['planning','actual','all','source-audit','snapshot-before','snapshot-after']);args=parser.parse_args()
    if args.action in ('planning','all'):prepare_planning()
    if args.action in ('actual','all'):prepare_actual()
    if args.action=='source-audit':audit_saved_inputs()
    if args.action.startswith('snapshot-'):campaign_snapshot(args.action.split('-')[1])
