from math import ceil,floor
from dataclasses import replace
import numpy as np
from .common import *
from v42_temporal.timeshift import dimensions
from v42_temporal.native import native_jobs

LIVE_LEVELS=(('qos','protected','partition','gpu_bucket','wall_bucket'),('qos','protected','gpu_bucket','wall_bucket'),
             ('qos','protected','wall_bucket'),('qos','protected'))

def known_window(job,source,provider_starts=None):
    ref=int(job['reference_start_if_authorized']);d=int(job['service_slots'])
    result=dict(job_id=job['job_uid'],state=job['state'],reference_start=ref,earliest_start=ref,latest_start=ref,
        allowed_starts=[ref],can_timeshift=False,d50=d,latest_source_completion=None,source_tail_slots=None,reason='FIXED_STATE_OR_CLASS')
    if not job['planning_eligible']:result['reason']='EXTERNAL_UNADMITTED';return result
    cohort=dimensions(job['cohort'])
    if job['state']!='PENDING' or cohort['protected']=='True' or cohort['qos']!='standby' or not 24<=ref<120:return result
    required=('RSP_start_slot','RW_completion_slot','start_slot','safe_duration_slots','source_snapshot_sha256','qos','state_at_issue')
    if not source or any(k not in source for k in required):result['reason']='MISSING_SOURCE_BOUNDARY';return result
    require(source['source_snapshot_sha256']==job['source_snapshot_sha'] and source['qos']==cohort['qos']
            and source['state_at_issue']==job['state'] and int(source['start_slot'])==ref,'SOURCE_BOUNDARY_IDENTITY')
    require(d==ceil(job['V10_Q50_total_seconds']/900),'FROZEN_Q50_DURATION')
    tail=max(0,int(source['start_slot'])+int(source['safe_duration_slots'])-120)
    end=int(source['RW_completion_slot']);lo=max(ref,int(source['RSP_start_slot']),24)
    hi=min(end-d,119,120+tail-d)
    starts=list(range(lo,hi+1))
    if provider_starts is not None:starts=sorted(set(starts)&set(provider_starts))
    if ref not in starts:
        result.update(reason='REFERENCE_OUTSIDE_SHIFT_BOUNDARY_FIXED_ONLY',latest_source_completion=end,source_tail_slots=tail);return result
    result.update(earliest_start=lo,latest_start=max(starts),allowed_starts=starts,can_timeshift=max(starts)>ref,
        latest_source_completion=end,source_tail_slots=tail,reason='SOURCE_R0_Q50_FINITE_DOMAIN' if max(starts)>ref else 'NO_LATER_START')
    return result

class LiveAuthority:
    def __init__(self,rows,cutoff='2025-01-01T00:00:00Z'):
        self.groups=[{} for _ in LIVE_LEVELS];cutoff=pd.Timestamp(cutoff)
        seen=set()
        for r in rows:
            require(r['job_id'] not in seen,'DUPLICATE_HISTORICAL_JOB');seen.add(r['job_id'])
            require(r['authority_reproduced'] is True and r['future_outcome_used'] is False and
                r['source_kind']=='AUTHORIZED_R0_START_WINDOW' and pd.Timestamp(r['issue_time'])<cutoff and
                pd.Timestamp(r['authority_available_at'])<=pd.Timestamp(r['issue_time']),'AUDITED_TRAIN_WINDOW_ONLY')
            require(r['state']=='PENDING' and not r['protected'] and r['qos']=='standby','R0_TEMPORAL_CLASS')
            seconds=(int(r['latest_authorized_start'])-int(r['reference_start']))*900
            require(seconds>=0,'VALID_AUTHORIZED_WINDOW')
            for level,groups in zip(LIVE_LEVELS,self.groups):
                groups.setdefault(tuple(r[k] for k in level),[]).append(seconds)

    def boundary(self,metadata,submit_time,state='PENDING'):
        first=ceil(float(submit_time)/900)
        result=dict(earliest_start=first,latest_start=first,allowed_starts=[first],can_timeshift=False,
            selected_level=None,N_window=0,B_live_seconds=0.,quantile=.25,method='higher',reason='NO_SUPPORTED_TRAIN_WINDOW')
        if state!='PENDING' or metadata['protected'] or metadata['qos']!='standby':
            result['reason']='NO_EXPLICIT_R0_TEMPORAL_QOS';return result
        for i,(level,groups) in enumerate(zip(LIVE_LEVELS,self.groups)):
            values=groups.get(tuple(metadata[k] for k in level),[])
            if len(values)<100:continue
            budget=float(np.quantile(values,.25,method='higher'));last=first+floor(budget/900)
            result.update(latest_start=last,allowed_starts=list(range(first,last+1)),can_timeshift=last>first,
                selected_level='L'+str(i),N_window=len(values),B_live_seconds=budget,
                reason='TRAIN_AUTHORIZED_WINDOW_Q25' if last>first else 'WINDOW_BELOW_ONE_SLOT');return result
        return result

def submit_with_boundary(ledger,book,provider,authority,job_id,submit_time,event_time,gpu,request_metadata,temporal_metadata):
    # No D-1 job identity is manufactured. The inherited event method invokes
    # frozen Q50, depletes once, and creates physical-PENDING occupancy zero.
    job=ledger.submit(job_id,submit_time,event_time,gpu,request_metadata,provider,book)
    window=authority.boundary(temporal_metadata,submit_time)
    job['live_service_boundary']=dict(window,service_slots=ceil(job['q50_seconds']/900),
        representation_completion=window['latest_start']+ceil(job['q50_seconds']/900),user_SLA=False)
    return job

def load_native():
    bundle=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    membership=read(OUT/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['windows']
    by={r['job_id']:r for r in membership}
    ts={u:dict(can_timeshift=r['can_timeshift'],TS_slots=r['latest_start']-r['reference_start']) for u,r in by.items()}
    jobs,windows,seconds,resources,raw=native_jobs(bundle,ts)
    for uid in windows:windows[uid]=replace(windows[uid],allowed_starts=tuple(by[uid]['allowed_starts']))
    return bundle,jobs,windows,seconds,resources,raw

def main():
    require(not (OUT/'KNOWN_TS_MEMBERSHIP.csv').exists(),'BOUNDARY_ALREADY_FROZEN')
    bundle=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');p=Path(bundle['reference']['path'])
    require(sha(p)==bundle['reference']['sha256'],'SOURCE_REFERENCE_SHA')
    src={r['job_uid']:r for r in read(p)};rows=[]
    for j in bundle['known_population']:
        if not j['planning_eligible']:continue
        r=known_window(j,src.get(j['job_uid']));r['nominal_GPUh']=j['service_slots']*j['GPU_gang']/4;rows.append(r)
    csv('KNOWN_TS_MEMBERSHIP.csv',rows)
    native=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
    lineage=[native/'dayahead/v37/aidc_materializer.py',native/'dayahead/v41/common.py',native/'dayahead/v41r1/terminal.py']
    dump('KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json',dict(PASS=True,source=rec(p),lineage=[rec(x) for x in lineage],windows=rows,
        fields=dict(RSP_start_slot='causal planning earliest reference; common.py derives from authorized scalar service schedule',
            RW_completion_slot='requested-walltime RW schedule from issue snapshot; NOT actual end',
            safe_duration_slots='old frozen reference duration used only for inherited authorized terminal tail',
            V10_Q50='unchanged nominal duration from PR96 provider',source_snapshot_sha256='exact issue membership hash'),
        future_realized_reads=0,known_requires_population_support=False,midnight_completion_deadline=False,
        historical_request_version_limitation='Inherited case-study scheduler-visible proxy; not proof of original operational request-version history'))
    # Existing TRAIN rows contain requests and queue labels but no R0 service
    # windows. Reference-only history explicitly records temporal authority null.
    history=ROOT.parent/'v42_reference_episode_pr/docs/v42_aidc_reference_episode_continuity'
    import pyarrow.parquet as pq
    schema=pq.read_schema(history/'CANONICAL_REFERENCE_LEDGER.parquet').names
    f=pd.read_parquet(history/'CANONICAL_REFERENCE_LEDGER.parquet',columns=['operating_day','temporal_eligible_if_authorized'])
    train=f[f.operating_day.astype(str)<'2025-01-01']
    require(train.temporal_eligible_if_authorized.isna().all(),'REVIEW_AVAILABLE_HISTORICAL_TEMPORAL_AUTHORITY')
    columns=['job_id','issue_time','authority_available_at','source_kind','authority_reproduced','future_outcome_used','state',
        'qos','protected','partition','gpu_bucket','wall_bucket','reference_start','latest_authorized_start','B_seconds']
    csv('LIVE_TS_WINDOW_DISTRIBUTION.csv',[],columns=columns)
    dump('LIVE_TS_WINDOW_TRAIN_AUDIT.json',dict(status='FAIL_CLOSED_NO_AUDITED_TRAIN_R0_WINDOWS',valid_windows=0,
        inspected_TRAIN_reference_rows=len(train),TRAIN_cutoff='2025-01-01T00:00:00Z',
        reference_ledger=rec(history/'CANONICAL_REFERENCE_LEDGER.parquet'),schema=rec(history/'CANONICAL_REFERENCE_LEDGER_SCHEMA.json'),
        available_columns=schema,temporal_authority_all_null=True,May_R0_rows_not_used_as_TRAIN=True,
        raw_wait_as_window=False,fabricated_window_rows=0,
        reason='TRAIN reference-only ledger has no authorized R0 temporal boundary; raw queue waits and May R0 rows cannot substitute'))
    dump('LIVE_TS_BACKOFF_AUTHORITY.json',dict(levels=LIVE_LEVELS,N_window=100,quantile=.25,method='higher',
        allowed_qos=['standby'],protected_fail_closed=True,W_greater_than_age=False,TRAIN_windows=0,
        source_support=False,live_rule_implemented=True,May_initial_live_jobs=0,no_target_share=True))
    mass=sum(r['nominal_GPUh'] for r in rows);yes=[r for r in rows if r['can_timeshift']]
    summary=dict(admitted_jobs=len(rows),known_PENDING_jobs=sum(r['state']=='PENDING' for r in rows),
        known_TS_candidates=len(yes),combined_TS_candidates=len(yes),candidate_job_share=len(yes)/len(rows),
        candidate_GPUh_share=sum(r['nominal_GPUh'] for r in yes)/mass,nominal_GPUh=mass,
        known_PENDING_TS_share=len(yes)/sum(r['state']=='PENDING' for r in rows),live_initial_jobs=0,live_TRAIN_support=0,
        globally_witnessed_share=None,selected_TS_share=None,scope='CANDIDATE_FINITE_DOMAIN; NOT_GLOBALLY_EXECUTED')
    dump('FINAL_TS_CAPABILITY_SUMMARY.json',summary)
    dump('TS_AUTHORITY_SUPERSESSION.json',dict(CONDITIONAL_WAIT_TS_STATUS='SUPERSEDED_BY_SERVICE_BOUNDARY_AUTHORITY',
        old_evidence=rec(PR97/'TS_HIERARCHICAL_CAPABILITY_SUMMARY.json'),old_artifacts_edited=False,
        known='SOURCE_R0_Q50_FINITE_STARTS',live='TRAIN_AUTHORIZED_R0_WINDOW_Q25_WITH_FAIL_CLOSED_SUPPORT'))
    print(summary)

if __name__=='__main__':main()
