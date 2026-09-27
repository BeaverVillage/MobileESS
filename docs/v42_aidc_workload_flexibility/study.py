"""Offline eligibility audit. No production module imports or scheduling calls."""
from pathlib import Path
import argparse, gzip, hashlib, json, math, zipfile
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
AUTH = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
LEDGER = Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days')
RAW = Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
WEATHER = WORK/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days'
SOURCES = {}
DIM = ['qos','partition','workload_class','protected','gpu_bucket','wall_bucket','requested_nodes']
CUTOFF = pd.Timestamp('2025-01-01T00:00:00Z')

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(p):
    p=Path(p); SOURCES[str(p.resolve())]={'sha256':sha(p),'bytes':p.stat().st_size}
    return json.loads(p.read_text(encoding='utf-8'))

def dump(name, value, exclusive=False):
    with (HERE/name).open('x' if exclusive else 'w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))

def csv(name, frame):
    frame.to_csv(HERE/name,index=False,lineterminator='\n',float_format='%.12g')

def tracked_table(p, columns=None):
    p=Path(p);SOURCES[str(p.resolve())]={'sha256':sha(p),'bytes':p.stat().st_size}
    return pq.read_table(p,columns=columns).to_pandas()

def enrich(f):
    f=f.copy()
    f['gpu_bucket']=pd.cut(f.requested_GPU,[0,1,4,16,64,np.inf],labels=['1','2-4','5-16','17-64','65+']).astype(str)
    f['wall_bucket']=pd.cut(f.requested_walltime_seconds,[0,3600,14400,86400,np.inf],labels=['<=1h','1-4h','4-24h','>24h']).astype(str)
    f['cohort']=f[DIM].astype(str).agg('|'.join,axis=1)
    return f

def prepare():
    """Only TRAIN labels: freeze algorithm before any rule evaluation."""
    assert not (HERE/'FLEXIBILITY_RULE_REGISTRATION.json').exists()
    rows=[]; inventory=[]
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.parquet'):continue
            # Partition is submit month. Never open post-cutoff partitions for fitting.
            year=int(name.split('year=')[1][:4])
            if year>=2025:continue
            cols=['id','qos','partition','nodes_req','gpus_requested','wallclock_req','submit_time','start_time','end_time']
            f=pq.read_table(z.open(name),columns=cols).to_pandas()
            for c in ['submit_time','start_time','end_time']:f[c]=pd.to_datetime(f[c],utc=True)
            f['requested_walltime_seconds']=f.wallclock_req.dt.total_seconds()
            f['queue_seconds']=(f.start_time-f.submit_time).dt.total_seconds()
            f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds()
            g=pd.to_numeric(f.gpus_requested,errors='coerce')
            valid=(g>0)&(g%1==0)&(f.nodes_req>0)&(g<=4*f.nodes_req)&(f.requested_walltime_seconds>0)&(f.queue_seconds>=0)&(f.runtime_seconds>0)&(f.end_time<CUTOFF)
            q=f[valid].copy();q['requested_GPU']=g[valid].astype(int);q['requested_nodes']=q.nodes_req.astype(int)
            q['qos']=q.qos.fillna('').str.strip().str.lower();q['partition']=q.partition.fillna('').str.strip().str.lower()
            q['workload_class']=np.select([q.qos.eq('normal'),q.qos.eq('standby'),q.qos.isin(['high','urgent'])],['NORMAL_QUEUE_CONTROLLED','STANDBY_QUEUE_CONTROLLED','HIGH_PROTECTED'],default='FIXED_PROTECTED')
            q['protected']=~q.qos.isin(['normal','standby'])
            q['GPUh']=q.requested_GPU*q.runtime_seconds/3600
            rows.append(q[['id',*DIM[:4],'requested_GPU','requested_walltime_seconds','requested_nodes','submit_time','start_time','end_time','queue_seconds','GPUh']])
            inventory.append({'member':name,'raw_rows':len(f),'train_rows':len(q),'CRC':z.getinfo(name).CRC})
    f=pd.concat(rows,ignore_index=True)
    assert not f.id.duplicated().any() and f.end_time.lt(CUTOFF).all()
    f=enrich(f).sort_values('id');csv('TRAIN_MEMBERSHIP.csv',f)
    (HERE/'TRAIN_MEMBERSHIP.csv.gz').write_bytes(gzip.compress((HERE/'TRAIN_MEMBERSHIP.csv').read_bytes(),mtime=0))
    stats=[]
    for key,g in f.groupby('cohort',sort=True):
        r={d:g.iloc[0][d] for d in DIM}
        r.update(cohort=key,N=len(g),GPUh=g.GPUh.sum(),median_seconds=g.queue_seconds.median(),Q75_seconds=g.queue_seconds.quantile(.75),Q90_seconds=g.queue_seconds.quantile(.9),max_end=g.end_time.max(),min_queue_seconds=g.queue_seconds.min(),max_queue_seconds=g.queue_seconds.max())
        # One-slot minimum follows frozen 900-second grid, not a share target.
        r['latency_tolerant']=len(g)>=100 and r['median_seconds']>=900 and not bool(r['protected'])
        r['budget_slots']=int(r['median_seconds']//900) if len(g)>=100 else 0
        stats.append(r)
    csv('COHORT_LATENCY_STATISTICS.csv',pd.DataFrame(stats))
    dump('TRAIN_AUDIT.json',dict(cutoff=str(CUTOFF),N=len(f),max_end=str(f.end_time.max()),partitions=inventory,raw_archive_sha256=sha(RAW)))
    registration=dict(schema='V42_ELIGIBILITY_OFFLINE_V1',frozen_at=datetime.now(timezone.utc).isoformat(),
        training_cutoff=str(CUTOFF),minimum_shift_slots=1,slot_seconds=900,minimum_cohort_N=100,
        cohort_dimensions=DIM,cohort_backoff='NONE; unseen/sparse non-standby cohorts fail closed',
        historical_tolerance='median completed-history queue seconds, floor to slots; a proxy assumption, not an SLA',
        training_population='valid positive GPU jobs completed strictly before 2025-01-01; full raw submit partitions before 2025 only',
        rules={'R0':'Exact frozen eligible_standby gate and restored terminal bounds; zero-width gate is reported separately from movable jobs',
               'R1':'PENDING, not protected, frozen in-day admitted reference, S>=1, standby OR cohort N>=100 and median queue>=900s; original terminal bounds',
               'R2':'R1; cap latest start at RSP_start + min(S, floor(cohort median/900)); sparse/unknown cohort has zero budget, including standby'},
        physical_screen='For new options, full site occupancy including reference tails with all other jobs fixed. Enumerate each compatible site/start; reject violating options. At least one safe witness required for actionable temporal membership. Alternatives are not a simultaneously executable schedule.',
        spatial='Frozen manifest can_relocate OR can_migrate unchanged; no new migration or shifted-start migration products. Protected temporal membership unchanged; legacy protected spatial rights not broadened.',
        metrics={'primary':'day-D GPUh of temporal-flexible jobs / all admitted baseline day-D GPUh; gate/domain/actionable distinguished',
                 'jobs':'job-day records / all frozen reference job-day records, including unadmitted and post-day records',
                 'full_service':'separate safe-duration GPUh over all reference job-day records, not distinct physical job execution',
                 'energy':'exact frozen C1 marginal PCC energy at original reference occupancy, P(total)-P(total-flex); fixed idle stays in denominator; also dynamic IT numerator reported',
                 'union':'temporal OR frozen spatial membership is separately reported, not labeled temporal share'},
        evaluation_period='All available V41R4 frozen domain days (May 01-31); ALL_AVAILABLE equals MAY. Full raw-trace eligibility outside authority coverage is unavailable, never synthesized.',
        sources=[{'url':'https://arxiv.org/abs/2106.11750','use':'delay-tolerant workload and daily-service preservation motivation; no numeric Kestrel latency threshold'},
                 {'url':'https://natlabrockies.github.io/HPC/Documentation/Slurm/batch_jobs/','use':'standby idle-node QoS semantics; does not certify normal-job deadlines'}],
        threshold_rationale='900 s is one existing decision slot. Median requires at least half the mature cohort to have waited a slot. N=100 is a preregistered support heuristic, not a statistical guarantee. No 15/30/60-minute sweep.',
        target_share_used=False,registration_inputs={n:sha(HERE/n) for n in ['TRAIN_MEMBERSHIP.csv','COHORT_LATENCY_STATISTICS.csv','TRAIN_AUDIT.json']},
        forbidden_runs=['ML','CC4','runtime fit/predict','traffic','optimizer','MESS','OpenDSS','Actual replay','A1-M1-A2-M2'])
    dump('FLEXIBILITY_RULE_REGISTRATION.json',registration,exclusive=True)
    print('TRAIN frozen',len(f),'jobs',len(stats),'cohorts',flush=True)

def bounds(r,rule,cohort):
    s,d=int(r['start_slot']),int(r['safe_duration_slots'])
    if r['state_at_issue']!='PENDING' or r['AIDC_site']=='UNASSIGNED' or not 24<=s<120:return s,s
    slack=int(r['RW_completion_slot'])-int(r['RSP_start_slot'])-d
    gate=bool(r['eligible_standby']) if rule=='R0' else (not r['protected'] and slack>=1 and (r['qos']=='standby' or bool(cohort.get('latency_tolerant',False))))
    if not gate:return s,s
    lo=max(24,int(r['RSP_start_slot']))
    hi=min(int(r['RW_completion_slot'])-d,119,120-d+max(0,s+d-120))
    if rule=='R2':hi=min(hi,int(r['RSP_start_slot'])+int(cohort.get('budget_slots',0)))
    if not lo<=s<=hi:return s,s
    return lo,hi

def capacity_options(r,lo,hi,load,caps):
    """All standalone changed-start options, with other jobs at B0."""
    s,d,g=int(r['start_slot']),int(r['safe_duration_slots']),int(r['requested_GPU']);src=r['AIDC_site']
    result=[]
    for site,cap in caps.items():
        if cap<g:continue
        residual=load[site].copy()
        if site==src:residual[s:s+d]-=g
        for t in range(lo,hi+1):
            if t==s:continue
            if np.all(residual[t:t+d]+g<=cap):result.append((site,t))
    return result

def c1(it,weather,model):
    c=model['coefficients'];o=model['other_model_coefficients'];scale=3.4987194698200215
    x=it*scale/1000;wet=weather.t_wb_c.to_numpy()[:,None];rh=weather.rh_pct.to_numpy()[:,None];e=np.maximum(wet-model['t_ref_c'],0)
    latent=c['intercept']+c['it_mw']*x+c['it_mw_squared']*x*x+c['wetbulb_c']*wet+c['wetbulb_excess_c']*e+c['it_mw_x_wetbulb_excess_c']*x*e+c['rh_pct']*rh
    return it+5.987971384940258/scale*(np.logaddexp(0,latent)+np.logaddexp(0,o['intercept']+o['it_mw']*x))

def evaluate():
    reg=read(HERE/'FLEXIBILITY_RULE_REGISTRATION.json')
    if not (HERE/'TRAIN_MEMBERSHIP.csv').exists():
        (HERE/'TRAIN_MEMBERSHIP.csv').write_bytes(gzip.decompress((HERE/'TRAIN_MEMBERSHIP.csv.gz').read_bytes()))
    for n,h in reg['registration_inputs'].items():assert sha(HERE/n)==h
    cohorts=pd.read_csv(HERE/'COHORT_LATENCY_STATISTICS.csv').set_index('cohort').to_dict('index')
    model=read(AUTH/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')
    memberships={r:[] for r in ['R0','R1','R2']}; daily=[]; option_rows=[]; audits=[]; enriched=[]
    domains=sorted((AUTH/'frozen_artifacts/v41r4_may/audit').glob('2025-05-*/domain/DAILY_DOMAIN_AUTHORITY.json'))
    assert len(domains)==31
    for path in domains:
        a=read(path);day=a['day']
        def authority(k):
            p=Path(a[k]['path']);assert sha(p)==a[k]['sha256'];return p
        jobs=read(authority('reference'));base=read(authority('base_manifest'));combined=read(authority('combined_manifest'))
        cap=read(authority('capacity'));rack=read(authority('rack'));caps=cap['site_capacity'];sites=list(caps)
        assert rack['effective_Rack_deliverability_by_AIDC']==caps
        for entry in a['sources']:
            assert sha(entry['path'])==entry['sha256'];SOURCES[str(Path(entry['path']).resolve())]={'sha256':entry['sha256'],'bytes':entry['bytes']}
        ledger=tracked_table(LEDGER/day/'V37_R4A_JOB_LEDGER.parquet',columns=['job_id','workload_class','protected','requested_nodes','qos','partition','RW_scheduled_completion']).set_index('job_id')
        meta={r['job_id']:r for r in base['jobs']};fullmeta={r['job_id']:r for r in combined['jobs']}
        assert set(ledger.index)==set(meta)=={r['job_uid'] for r in jobs}
        horizon=max(r['end_slot'] for r in jobs)+121;load={s:np.zeros(horizon,dtype=np.int32) for s in sites}
        for r in jobs:
            if r['AIDC_site'] in caps:load[r['AIDC_site']][r['start_slot']:r['end_slot']]+=r['requested_GPU']
        assert all(np.max(load[s])<=caps[s] for s in sites)
        powerpath=path.parent.parent/'V41R2_B0_IT_PCC.npz'
        if not powerpath.exists():
            powerpath=AUTH/'dayahead/artifacts/v41r3_fast_power_scale_freeze/V41R2_B0_IT_PCC.npz'
        SOURCES[str(powerpath.resolve())]={'sha256':sha(powerpath),'bytes':powerpath.stat().st_size}
        with np.load(powerpath) as z:gpu=z['gpu'].copy();it=z['it'].copy();pcc=z['pcc'].copy()
        assert np.array_equal(gpu,np.column_stack([load[s][24:120] for s in sites]))
        weather=tracked_table(WEATHER/day/'gfs_d1_weather.parquet')
        assert np.max(np.abs(c1(it,weather,model)-pcc))<1e-8
        prepared=[]
        for r in jobs:
            r=dict(r);l=ledger.loc[r['job_uid']]
            assert r['qos']==l.qos and r['partition']==l.partition and r['RW_completion_slot']==l.RW_scheduled_completion
            r.update(protected=bool(l.protected),workload_class=l.workload_class,requested_nodes=int(l.requested_nodes))
            assert r['end_slot']-r['start_slot']==r['safe_duration_slots']
            assert r['safe_duration_slots']==math.ceil(r['safe_duration_seconds']/900)
            expected=(r['state_at_issue']=='PENDING' and r['qos']=='standby' and r['RSP_start_slot']+r['safe_duration_slots']<=r['RW_completion_slot'])
            assert bool(r['eligible_standby'])==expected
            r['day']=day;prepared.append(r)
        frame=enrich(pd.DataFrame(prepared));enriched.extend(frame.to_dict('records'))
        restored_count=0;restored_jobs=0
        for rule in memberships:
            population=[];flexgpu=np.zeros_like(gpu);gategpu=np.zeros_like(gpu);domaingpu=np.zeros_like(gpu)
            for r in frame.to_dict('records'):
                uid=r['job_uid'];s,d,g=int(r['start_slot']),int(r['safe_duration_slots']),int(r['requested_GPU']);site=r['AIDC_site']
                co=cohorts.get(r['cohort'],{});lo,hi=bounds(r,rule,co)
                domain=hi>lo;opts=capacity_options(r,lo,hi,load,caps) if domain else []
                if rule=='R0':
                    n=(hi-lo)*sum(v>=g for v in caps.values()) if domain else 0
                    assert fullmeta[uid]['candidate_count']-meta[uid]['candidate_count']==n
                    restored_count+=n;restored_jobs+=bool(n)
                if opts:
                    assert not r['protected'] and r['state_at_issue']=='PENDING'
                    for dest,t in opts:
                        assert t+d<=r['RW_completion_slot'] and max(0,t+d-120)<=max(0,s+d-120)
                    # Store compact exact option membership by site; no fake joint dispatch.
                    for dest in sorted({o[0] for o in opts}):
                        starts=[o[1] for o in opts if o[0]==dest]
                        option_rows.append(dict(rule=rule,day=day,job_uid=uid,site=dest,starts=' '.join(map(str,starts)),duration_slots=d))
                inside=max(0,min(s+d,120)-max(s,24)) if site in caps else 0
                spatial=bool(meta[uid]['can_relocate'] or meta[uid]['can_migrate'])
                rr={k:r[k] for k in ['day','job_uid','qos','partition','workload_class','protected','requested_nodes','requested_GPU','requested_walltime_seconds','gpu_bucket','wall_bucket','cohort','state_at_issue','AIDC_site','start_slot','safe_duration_slots','RSP_start_slot','RW_completion_slot']}
                rr.update(rule=rule,eligible_standby=r['eligible_standby'],individual_slack_slots=r['RW_completion_slot']-r['RSP_start_slot']-d,cohort_N=int(co.get('N',0)),cohort_budget_slots=int(co.get('budget_slots',0)),cohort_latency_tolerant=bool(co.get('latency_tolerant',False)),temporal_domain=domain,temporal_flexible=bool(opts),spatial_flexible=spatial,flexible_union=bool(opts) or spatial,
                    category='both' if opts and spatial else 'temporal-only' if opts else 'spatial-only' if spatial else 'fixed',day_GPUh=inside*g/4,full_service_GPUh=d*g/4,
                    lower_slot=lo,upper_slot=hi,allowed_shift_slots=max((t-s for _,t in opts),default=0),option_count=len(opts),
                    reason='standby' if opts and r['qos']=='standby' else 'historical_cohort_and_service_slack' if opts else 'capacity_fail_closed' if domain else 'ineligible_or_no_terminal_slack')
                population.append(rr)
                if inside:
                    sl=slice(max(s,24)-24,min(s+d,120)-24);j=sites.index(site)
                    if opts:flexgpu[sl,j]+=g
                    if r['eligible_standby']:gategpu[sl,j]+=g
                    if domain:domaingpu[sl,j]+=g
            m=pd.DataFrame(population);memberships[rule].extend(population)
            total=m.day_GPUh.sum();base_energy=pcc.sum()/4
            energy=(pcc-c1(it-flexgpu*.5477239090195797,weather,model)).sum()/4
            gate_energy=(pcc-c1(it-gategpu*.5477239090195797,weather,model)).sum()/4
            domain_energy=(pcc-c1(it-domaingpu*.5477239090195797,weather,model)).sum()/4
            daily.append(dict(day=day,rule=rule,total_jobs=len(m),flexible_jobs=int(m.temporal_flexible.sum()),total_GPUh=total,flexible_GPUh=m.loc[m.temporal_flexible,'day_GPUh'].sum(),
                total_full_service_GPUh=m.full_service_GPUh.sum(),flexible_full_service_GPUh=m.loc[m.temporal_flexible,'full_service_GPUh'].sum(),
                total_AIDC_PCC_kWh=base_energy,flexible_AIDC_PCC_kWh=energy,flexible_dynamic_IT_kWh=float(flexgpu.sum()/4*.5477239090195797),
                gate_jobs=int(m.eligible_standby.sum()),gate_GPUh=m.loc[m.eligible_standby,'day_GPUh'].sum(),gate_PCC_kWh=gate_energy,
                domain_jobs=int(m.temporal_domain.sum()),domain_GPUh=m.loc[m.temporal_domain,'day_GPUh'].sum(),domain_PCC_kWh=domain_energy,
                spatial_GPUh=m.loc[m.spatial_flexible,'day_GPUh'].sum(),union_GPUh=m.loc[m.flexible_union,'day_GPUh'].sum(),
                **{c.replace('-','_')+'_GPUh':m.loc[m.category.eq(c),'day_GPUh'].sum() for c in ['temporal-only','spatial-only','both','fixed']}))
            assert math.isclose(m.loc[m.temporal_flexible,'day_GPUh'].sum()+m.loc[~m.temporal_flexible,'day_GPUh'].sum(),total)
        assert restored_count==a['restored_count'] and restored_jobs==a['eligible_temporal_jobs']
        audits.append(dict(day=day,reference_jobs=len(jobs),R0_exact_gate=True,R0_exact_domain_jobs=restored_jobs,R0_exact_domain_options=restored_count,capacity_baseline=True,power_max_error=float(np.max(np.abs(c1(it,weather,model)-pcc)))))
        print(day,'verified',flush=True)
    baseline=pd.DataFrame(memberships['R0']).set_index(['day','job_uid']).temporal_flexible
    strata=[];shifts=[]
    for rule,rows in memberships.items():
        f=pd.DataFrame(rows);f['newly_flexible']=f.temporal_flexible & ~f.set_index(['day','job_uid']).index.map(baseline).to_numpy(bool)
        csv(f'FLEXIBLE_MEMBERSHIP_{rule}.csv',f)
        for dimension in ['qos','workload_class','partition','gpu_bucket','category','reason']:
            for value,g in f.groupby(dimension):
                strata.append(dict(rule=rule,dimension=dimension,value=value,jobs=len(g),flexible_jobs=int(g.temporal_flexible.sum()),GPUh=g.day_GPUh.sum(),flexible_GPUh=g.loc[g.temporal_flexible,'day_GPUh'].sum(),new_jobs=int(g.newly_flexible.sum()),new_GPUh=g.loc[g.newly_flexible,'day_GPUh'].sum()))
        g=f[f.temporal_flexible]
        shifts.append(dict(rule=rule,N=len(g),**{f'Q{int(q*100)}_minutes':float(g.allowed_shift_slots.quantile(q)*15) if len(g) else None for q in [0,.25,.5,.75,.9,1]}))
    csv('FEASIBLE_OPTIONS.csv',pd.DataFrame(option_rows));csv('REFERENCE_POPULATION.csv',pd.DataFrame(enriched).drop(columns=['common_terminal_obligation'],errors='ignore'))
    csv('INCLUSION_BY_COHORT.csv',pd.DataFrame(strata));csv('SHIFT_WINDOW_DISTRIBUTION.csv',pd.DataFrame(shifts))
    f=pd.DataFrame(daily)
    f['flexible_GPUh_pct']=100*f.flexible_GPUh/f.total_GPUh
    csv('GPUH_SHARE_BY_DAY.csv',f)
    comparison=[]
    for rule,g in f.groupby('rule'):
        totals=g.drop(columns=['day','rule','flexible_GPUh_pct']).sum().to_dict()
        m=pd.DataFrame(memberships[rule]);new=m.temporal_flexible.to_numpy() & ~m.set_index(['day','job_uid']).index.map(baseline).to_numpy(bool)
        for period in ['ALL_AVAILABLE','MAY']:
            rr=dict(period=period,rule=rule,**totals,flexible_jobs_pct=100*totals['flexible_jobs']/totals['total_jobs'],flexible_GPUh_pct=100*totals['flexible_GPUh']/totals['total_GPUh'],flexible_AIDC_energy_pct=100*totals['flexible_AIDC_PCC_kWh']/totals['total_AIDC_PCC_kWh'],new_jobs=int(new.sum()),new_GPUh=float(m.loc[new,'day_GPUh'].sum()))
            for target in [20,30,40]:rr[f'naturally_ge_{target}_pct']=rr['flexible_GPUh_pct']>=target
            comparison.append(rr)
    csv('RULE_COMPARISON.csv',pd.DataFrame(comparison))
    dump('SERVICE_FEASIBILITY_AUDIT.json',dict(status='PASS_OFFLINE_STANDALONE_OPTIONS',days=audits,safe_duration_preserved=True,reference_completion_and_terminal_preserved=True,all_new_options_capacity_checked=True,protected_temporal_unchanged=True,fixed_population_retained=True,admission_unchanged=True,full_workload_and_GPUh_conserved=True,spatial_migration_membership_unchanged=True,new_shifted_migration_products=0,joint_schedule_feasibility='NOT_CLAIMED; options are alternatives and retain coupling constraints',actual_runtime_service='NOT_CERTIFIED; frozen safe-duration model retained'))
    dump('LEAKAGE_AUDIT.json',dict(status='PASS_EVENT_TIME_PROXY_ONLY',train_cutoff=str(CUTOFF),minimum_eval_issue='2025-04-30T08:00:00Z',train_inputs_verified=True,eval_realized_start_end_queue_read=False,historical_request_versions='UNVERIFIED',operational_no_future_leakage_certified=False,known_running_state_and_request_fields='frozen scheduler-visible proxy',RW_completion='requested-walltime synthetic reference, not realized end or user SLA',rule_registration_sha256=sha(HERE/'FLEXIBILITY_RULE_REGISTRATION.json')))
    SOURCES[str(RAW.resolve())]={'sha256':sha(RAW),'bytes':RAW.stat().st_size}
    dump('SOURCE_MANIFEST.json',dict(sources=SOURCES,registration_sha256=sha(HERE/'FLEXIBILITY_RULE_REGISTRATION.json'),forbidden_modules_imported=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','evaluate']);a=parser.parse_args()
    globals()[a.phase]()
